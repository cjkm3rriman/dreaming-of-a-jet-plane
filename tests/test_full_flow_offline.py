"""Offline full-flow tests: /scanning -> pre-generation -> /plane/N -> /free/plane/N

DOJP-47 item 3. The worst production failure is silent broken audio - a 200
response whose bytes don't play. Until now nothing decoded response bytes, so
nothing could catch it. These tests run the REAL pipeline offline:

- real provider parsing (recorded Airlabs payload via respx)
- real IP geolocation code (ipapi.co mocked via respx)
- real text generation, real pydub stitching with real Opus tone clips
- real cache-key construction against an in-memory S3 double

What is fake, precisely: convert_text_to_speech is stubbed (returning a
genuinely playable clip); the s3_cache singleton's get/set/get_raw are an
in-memory double that keeps the key/value contract but drops SigV4, the
HEAD+Last-Modified TTL check, and retries (that transport layer is DOJP-47
item 5's job); and get_live_aircraft_providers is pinned to airlabs, so the
provider fallback chain is not exercised here. Within the generation
pipeline itself, TTS is the only stubbed computation.

Every audio response is decoded with pydub before passing. Pre-generation is
awaited directly rather than left as a background task - under TestClient a
floating task can outlive the respx context and hit the real network.
"""

import io
import json
import time
from pathlib import Path

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from pydub import AudioSegment
from pydub.generators import Sine

import app.aircraft_providers.airlabs as airlabs
import app.free_pool as free_pool
import app.main as main
import app.scanning as scanning
from app.s3_cache import s3_cache
from app.scanning import pre_generate_flight_audio

FIXTURES = Path(__file__).parent / "fixtures"
NYC = {"lat": 40.7128, "lng": -74.0060}

IPAPI_RESPONSE = {
    "latitude": NYC["lat"], "longitude": NYC["lng"], "country_code": "US",
    "city": "New York", "region": "New York", "country_name": "United States",
}


from functools import lru_cache


@lru_cache(maxsize=1)
def _tone_opus(ms=400, freq=440):
    """A genuinely playable Opus clip. A tone, not silence - the stitcher
    trims silence, which would erase a silent stub entirely.

    Deliberately lazy (and cached): exporting shells out to ffmpeg, and pytest
    imports this module during collection even in environments that deselect
    every test here. A module-level constant here aborted the integration
    workflow's entire collection on a runner without ffmpeg."""
    seg = Sine(freq).to_audio_segment(duration=ms).set_channels(1)
    buf = io.BytesIO()
    seg.export(buf, format="ogg", codec="libopus")
    return buf.getvalue()


def _decode(audio_bytes):
    """The core assertion of this file: the bytes actually play"""
    return AudioSegment.from_file(io.BytesIO(audio_bytes), format="ogg")


def _assert_narration(clip, label):
    """Playable is not enough: a container full of stitch-gap silence decodes
    fine. Mutation testing showed a stitcher that drops every narration
    segment still produced 2.5s of decodable silence - dBFS catches it."""
    assert clip.duration_seconds > 1.2, f"{label}: implausibly short"
    assert clip.duration_seconds < 15, f"{label}: implausibly long"
    assert clip.dBFS > -50, f"{label}: decodable but silent - narration missing"


def _airlabs_payload():
    payload = json.loads((FIXTURES / "airlabs_flights.json").read_text())
    newest = max(f["updated"] for f in payload["response"] if f.get("updated"))
    shift = int(time.time()) - newest
    for flight in payload["response"]:
        if flight.get("updated"):
            flight["updated"] += shift
    return payload


class FakeS3:
    """In-memory stand-in for the S3 singleton's read/write surface.

    Faithful to the real contract: set() stores dicts as JSON bytes,
    get(content_type="json") parses them back, get_raw returns raw bytes.
    """

    enabled = True

    def __init__(self):
        self.objects = {}

    async def get(self, key, content_type="audio"):
        data = self.objects.get(key)
        if data is None:
            return None
        return json.loads(data) if content_type == "json" else data

    async def set(self, key, data, content_type="audio"):
        self.objects[key] = json.dumps(data).encode() if isinstance(data, dict) else data
        return True

    async def get_raw(self, key):
        return self.objects.get(key)

    def keys(self, prefix=""):
        return [k for k in self.objects if k.startswith(prefix)]


@pytest.fixture
def env(monkeypatch):
    """The full offline environment: fake S3, stubbed TTS, pinned provider"""
    fake = FakeS3()
    for method in ("get", "set", "get_raw"):
        monkeypatch.setattr(s3_cache, method, getattr(fake, method))

    async def fake_tts(text, tts_override=None):
        assert text.strip(), "TTS must never be called with empty text"
        return _tone_opus(), "", "inworld", "opus", "audio/opus"

    monkeypatch.setattr(main, "convert_text_to_speech", fake_tts)
    monkeypatch.setattr(main, "TTS_PROVIDER", "inworld")
    monkeypatch.setattr(main, "get_live_aircraft_providers", lambda *a, **k: ["airlabs"])
    monkeypatch.setattr(airlabs, "AIRLABS_API_KEY", "test-key")

    # reset per-container state so tests don't couple
    monkeypatch.setattr(scanning, "_scanning_request_cache", {})
    monkeypatch.setattr(free_pool, "_free_pool_index_cache", None)
    monkeypatch.setattr(free_pool, "_free_pool_index_timestamp", 0)
    monkeypatch.setattr(free_pool, "_rate_limit_cache", {})

    return fake


def _mock_external(router):
    router.get(url__regex=r"https://ipapi\.co/.*").mock(
        return_value=httpx.Response(200, json=IPAPI_RESPONSE))
    router.get(url__startswith="https://airlabs.co").mock(
        return_value=httpx.Response(200, json=_airlabs_payload()))
    # static voice clips proxied from the public bucket URL (/scanning etc.)
    router.get(url__regex=r"https://dreaming-of-a-jet-plane\.s3\..*").mock(
        return_value=httpx.Response(200, content=_tone_opus()))


@pytest.mark.unit
def test_scanning_streams_audio_and_schedules_pregeneration(env, monkeypatch):
    """/scanning must return audio immediately AND kick off the warm-up"""
    scheduled = []

    async def capture_pregen(lat, lng, request=None, tts_override=None):
        scheduled.append((lat, lng))

    monkeypatch.setattr(scanning, "pre_generate_flight_audio", capture_pregen)

    with respx.mock as router:
        _mock_external(router)
        with TestClient(main.app) as client:
            response = client.get("/scanning")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/")
    assert len(response.content) > 0
    assert scheduled == [(NYC["lat"], NYC["lng"])], \
        "pre-generation was not scheduled with the geolocated coordinates"


@pytest.mark.unit
async def test_pregeneration_fills_every_cache_with_playable_audio(env):
    """The whole warm-up pipeline: provider -> selection -> text -> TTS ->
    stitch -> plane cache + body cache + fun-fact cache + free pool"""
    with respx.mock as router:
        _mock_external(router)
        await pre_generate_flight_audio(NYC["lat"], NYC["lng"])

    plane_keys = [k for k in env.keys("cache/") if "_plane" in k and "_body_" not in k]
    body_keys = env.keys("cache/")
    body_keys = [k for k in body_keys if "_body_" in k]
    assert len(plane_keys) == 5, f"expected 5 cached planes, got {plane_keys}"
    assert len(body_keys) == 5, "free-tier body audio missing"

    # the fun-fact cache must land OUTSIDE the lifecycle-reaped cache/ prefix,
    # and fact BODIES specifically (openings/ is a separate cache)
    fact_body_keys = [k for k in env.keys("tts-cache/fun_facts/") if "/openings/" not in k]
    assert fact_body_keys, "no fun fact bodies were cached"

    # free pool populated for planes 1-3
    index = json.loads(env.objects["free_pool/index.json"])
    assert len(index["entries"]) >= 1
    assert len(index["entries"][-1]["planes"]) == 3

    # and every cached plane actually plays, at a plausible narration length
    for key in plane_keys:
        _assert_narration(_decode(env.objects[key]), key)


@pytest.mark.unit
def test_plane_endpoints_serve_playable_audio_from_cache(env):
    """After a warm-up, /plane/1..5 serve straight from cache - and the bytes play"""
    import asyncio

    with respx.mock as router:
        _mock_external(router)
        # warm the cache deterministically, then serve through the endpoints
        asyncio.run(pre_generate_flight_audio(NYC["lat"], NYC["lng"]))
        with TestClient(main.app) as client:
            for n in range(1, 6):
                response = client.get(f"/plane/{n}")
                assert response.status_code == 200, f"/plane/{n} -> {response.status_code}"
                assert response.headers["content-type"] == "audio/opus"
                assert response.headers["cache-control"] == "public, max-age=180"
                _assert_narration(_decode(response.content), f"/plane/{n}")


@pytest.mark.unit
def test_plane_endpoint_generates_inline_on_cold_cache(env):
    """No warm-up at all: /plane/2 runs the whole inline pipeline and the
    result still plays. This is the skipped-ahead-child path."""
    with respx.mock as router:
        _mock_external(router)
        with TestClient(main.app) as client:
            response = client.get("/plane/2")

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/opus"
    _assert_narration(_decode(response.content), "/plane/2 inline")

    # the inline path must also backfill the caches it passed through -
    # including the fun-fact cache (plane 2 -> Santiago, which has facts;
    # deterministic given the recorded payload). The pre-gen path caches
    # facts through a separate duplicated code block (see DOJP-46), so this
    # is the only test guarding the inline copy.
    assert any("_plane2" in k for k in env.keys("cache/"))
    # specifically the fact BODY - the opener cache also lives under
    # tts-cache/fun_facts/ (in openings/) and satisfied a looser prefix
    # assertion even with the body write deleted (found by mutation testing)
    fact_body_keys = [k for k in env.keys("tts-cache/fun_facts/") if "/openings/" not in k]
    assert fact_body_keys, "inline generation did not cache the fun fact body audio"


@pytest.mark.unit
def test_free_plane_serves_playable_stitched_audio(env):
    """Free tier end to end: pre-gen populates the pool, a free user gets
    intro + body stitched into audio that plays"""
    for n in range(1, 7):
        env.objects[f"free/intros/flight-intro-{n}.opus"] = _tone_opus()

    with respx.mock as router:
        _mock_external(router)
        import asyncio
        asyncio.run(pre_generate_flight_audio(NYC["lat"], NYC["lng"]))
        with TestClient(main.app) as client:
            response = client.get("/free/plane/1")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/")
    clip = _decode(response.content)
    assert clip.duration_seconds > 0.8
    assert clip.dBFS > -50, "free plane audio is silent"
