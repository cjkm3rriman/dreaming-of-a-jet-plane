"""Unit tests for the three TTS providers (DOJP-47 item 7)

The contract every provider must honor: generate_audio(text) returns
(audio_bytes, "") on success and (b"", non-empty error) on ANY failure.
The property that matters most is the second half - if a provider ever
returns an error response body as "audio", it gets cached under a content
key and stitched into narration forever.

ElevenLabs and Inworld are tested through respx against their real request
construction. Google's SDK call is stubbed at the genai.Client seam, but the
PCM->MP3 ffmpeg conversion runs for real.
"""

import base64
import io
import json

import httpx
import pytest
import respx
from pydub import AudioSegment
from pydub.generators import Sine

import app.tts_providers.elevenlabs as elevenlabs
import app.tts_providers.google as google_tts
import google.genai as genai_sdk
import app.tts_providers.inworld as inworld


def _ogg_opus_tone(ms=300):
    seg = Sine(440).to_audio_segment(duration=ms).set_channels(1)
    buf = io.BytesIO()
    seg.export(buf, format="ogg", codec="libopus")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# ElevenLabs
# ---------------------------------------------------------------------------


@pytest.fixture
def elevenlabs_key(monkeypatch):
    monkeypatch.setattr(elevenlabs, "ELEVENLABS_API_KEY", "el-test-key")


@pytest.mark.unit
async def test_elevenlabs_sends_key_voice_and_pause(elevenlabs_key):
    with respx.mock as router:
        route = router.post(url__startswith="https://api.elevenlabs.io/v1/text-to-speech/").mock(
            return_value=httpx.Response(200, content=b"opus-bytes"))

        audio, error = await elevenlabs.generate_audio("Hello there")

    assert (audio, error) == (b"opus-bytes", "")
    request = route.calls[0].request
    assert request.headers["xi-api-key"] == "el-test-key"
    assert elevenlabs.DEFAULT_VOICE_ID in str(request.url)
    assert f"output_format={elevenlabs.DEFAULT_OUTPUT_FORMAT}" in str(request.url)
    body = json.loads(request.content)
    assert body["text"].startswith('<break time="1s"/>')  # the leading pause
    assert body["text"].endswith("Hello there")


@pytest.mark.unit
@pytest.mark.parametrize("status", [401, 429, 500])
async def test_elevenlabs_error_body_never_becomes_audio(elevenlabs_key, status):
    """The cache-poisoning property: a JSON error body must not come back
    in the audio slot"""
    with respx.mock as router:
        router.post(url__startswith="https://api.elevenlabs.io").mock(
            return_value=httpx.Response(status, content=b'{"detail": "quota exceeded"}'))

        audio, error = await elevenlabs.generate_audio("Hello")

    assert audio == b""
    assert error, "failure must carry a non-empty error"
    assert str(status) in error


@pytest.mark.unit
async def test_elevenlabs_unconfigured_is_an_error_not_a_crash(monkeypatch):
    monkeypatch.setattr(elevenlabs, "ELEVENLABS_API_KEY", None)
    audio, error = await elevenlabs.generate_audio("Hello")
    assert audio == b""
    assert "not configured" in error


# ---------------------------------------------------------------------------
# Inworld
# ---------------------------------------------------------------------------


@pytest.fixture
def inworld_env(monkeypatch):
    monkeypatch.setattr(inworld, "INWORLD_API_KEY", "user:secret")  # raw key form

    async def no_sleep(_):
        pass

    monkeypatch.setattr(inworld.asyncio, "sleep", no_sleep)


@pytest.mark.unit
async def test_inworld_success_returns_playable_audio_with_leading_silence(inworld_env):
    tone = _ogg_opus_tone(300)
    payload = {"audioContent": base64.b64encode(tone).decode()}

    with respx.mock as router:
        route = router.post(inworld.INWORLD_BASE_URL).mock(
            return_value=httpx.Response(200, json=payload))

        audio, error = await inworld.generate_audio("Hello")

    assert error == ""
    clip = AudioSegment.from_file(io.BytesIO(audio), format="ogg")
    # 1s prepended silence + ~0.3s tone
    assert clip.duration_seconds == pytest.approx(1.3, abs=0.2)

    request = route.calls[0].request
    body = json.loads(request.content)
    assert body["voice_id"] == inworld.INWORLD_VOICE_ID
    assert body["model_id"] == inworld.INWORLD_MODEL_ID
    assert body["audio_config"]["audio_encoding"] == inworld.INWORLD_AUDIO_ENCODING


@pytest.mark.unit
async def test_inworld_raw_key_with_colon_is_base64_encoded(inworld_env):
    """'user:secret' is a raw credential pair; the Basic header must carry
    its base64, not the raw string"""
    header = inworld._build_authorization_header()
    assert header == "Basic " + base64.b64encode(b"user:secret").decode()


@pytest.mark.unit
async def test_inworld_retries_transient_statuses_then_succeeds(inworld_env):
    tone = _ogg_opus_tone(200)
    payload = {"audioContent": base64.b64encode(tone).decode()}

    with respx.mock as router:
        route = router.post(inworld.INWORLD_BASE_URL)
        route.side_effect = [
            httpx.Response(503),
            httpx.Response(429),
            httpx.Response(200, json=payload),
        ]

        audio, error = await inworld.generate_audio("Hello")

    assert error == ""
    assert len(audio) > 0
    assert route.call_count == 3


@pytest.mark.unit
async def test_inworld_gives_up_after_max_retries(inworld_env):
    with respx.mock as router:
        route = router.post(inworld.INWORLD_BASE_URL).mock(
            return_value=httpx.Response(503))

        audio, error = await inworld.generate_audio("Hello")

    assert audio == b""
    assert "503" in error
    assert route.call_count == inworld.MAX_RETRIES


@pytest.mark.unit
async def test_inworld_non_retryable_error_fails_fast(inworld_env):
    with respx.mock as router:
        route = router.post(inworld.INWORLD_BASE_URL).mock(
            return_value=httpx.Response(401, text="bad key"))

        audio, error = await inworld.generate_audio("Hello")

    assert audio == b""
    assert "401" in error
    assert route.call_count == 1, "auth failures are deterministic - no retry"


@pytest.mark.unit
async def test_inworld_missing_audio_content_is_an_error(inworld_env):
    with respx.mock as router:
        router.post(inworld.INWORLD_BASE_URL).mock(
            return_value=httpx.Response(200, json={"unexpected": "shape"}))

        audio, error = await inworld.generate_audio("Hello")

    assert audio == b""
    assert "audioContent" in error


@pytest.mark.unit
async def test_inworld_undecodable_audio_is_an_error_not_garbage(inworld_env):
    """A 200 whose payload isn't real audio must not reach the cache"""
    payload = {"audioContent": base64.b64encode(b"not really opus").decode()}
    with respx.mock as router:
        router.post(inworld.INWORLD_BASE_URL).mock(
            return_value=httpx.Response(200, json=payload))

        audio, error = await inworld.generate_audio("Hello")

    assert audio == b""
    assert error


# ---------------------------------------------------------------------------
# Google Gemini (SDK stubbed at the genai.Client seam; ffmpeg runs for real)
# ---------------------------------------------------------------------------


def _pcm_tone(ms=300):
    """s16le mono 24kHz PCM - exactly what Gemini returns"""
    seg = (Sine(440).to_audio_segment(duration=ms)
           .set_frame_rate(24000).set_channels(1).set_sample_width(2))
    return seg.raw_data


class _FakeGenaiClient:
    def __init__(self, api_key=None):
        class _Models:
            @staticmethod
            def generate_content(**kwargs):
                class _Obj:  # response.candidates[0].content.parts[0].inline_data.data
                    pass
                node = _Obj()
                node.inline_data = _Obj()
                node.inline_data.data = _pcm_tone()
                part = _Obj(); part.content = _Obj(); part.content.parts = [node]
                resp = _Obj(); resp.candidates = [part]
                return resp
        self.models = _Models()


@pytest.fixture
def google_env(monkeypatch):
    monkeypatch.setattr(google_tts, "GOOGLE_API_KEY", "g-test-key")
    # the provider does `from google import genai` inside the function, which
    # resolves to this module object at call time - so this patch takes effect
    monkeypatch.setattr(genai_sdk, "Client", _FakeGenaiClient)


@pytest.mark.unit
async def test_google_converts_pcm_to_playable_mp3(google_env):
    audio, error = await google_tts.generate_audio("Hello")

    assert error == ""
    clip = AudioSegment.from_file(io.BytesIO(audio), format="mp3")
    # ~0.3s tone + 1s adelay, through the pitch/tempo filter chain
    assert clip.duration_seconds > 1.0
    assert clip.dBFS > -50


@pytest.mark.unit
async def test_google_ffmpeg_failure_returns_a_real_error(google_env, monkeypatch):
    """ffmpeg failure used to yield (b"", "") - empty audio with an EMPTY
    error, making a Google outage undiagnosable (DOJP-43)"""

    class _BrokenFfmpeg:
        returncode = 1

        def __init__(self, *args, **kwargs):
            pass

        def communicate(self, input=None):
            return b"", b"pipe:0: Invalid data found when processing input"

    monkeypatch.setattr(google_tts.subprocess, "Popen", _BrokenFfmpeg)

    audio, error = await google_tts.generate_audio("Hello")

    assert audio == b""
    assert "ffmpeg" in error
    assert "Invalid data" in error, "the ffmpeg stderr must surface in the error"


@pytest.mark.unit
async def test_google_unconfigured_is_an_error(monkeypatch):
    monkeypatch.setattr(google_tts, "GOOGLE_API_KEY", None)
    audio, error = await google_tts.generate_audio("Hello")
    assert audio == b""
    assert "not configured" in error
