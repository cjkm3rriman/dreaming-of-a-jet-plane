"""Range handling, the recent-audio memory cache, and single-flight
generation for dynamic plane audio (DOJP-56).

The new Yoto players did not play the dynamic Opus tracks while the static
ones worked. One measured difference: static clips answer Range requests
with 206, the dynamic endpoints answered with a 200 and the whole file (Ogg
Opus has no duration in its header, so a player wanting the length seeks to
the last page). Range support was removed in DOJP-22 because advertising it
without honouring it caused a burst of full-file fetches per play; these
tests pin both halves - real 206 slices, and no amplification behind them.
"""

import asyncio

import pytest
from fastapi import Request

from app.audio_response import (
    RecentAudioCache,
    SingleFlight,
    parse_range,
    plane_audio_response,
)

AUDIO = bytes(range(256)) * 4  # 1024 distinctive bytes


def _request(range_header=None):
    headers = [(b"range", range_header.encode())] if range_header else []
    return Request({"type": "http", "method": "GET", "path": "/plane/1",
                    "query_string": b"", "headers": headers})


# ---------------------------------------------------------------------------
# parse_range
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("header,expected", [
    (None, ("full", None)),
    ("", ("full", None)),
    ("bytes=0-1023", ("partial", (0, 1023))),
    ("bytes=0-9", ("partial", (0, 9))),
    ("bytes=500-", ("partial", (500, 1023))),
    ("bytes=-100", ("partial", (924, 1023))),          # tail probe for Ogg duration
    ("bytes=-5000", ("partial", (0, 1023))),           # suffix longer than the body
    ("bytes=0-99999", ("partial", (0, 1023))),         # end clamped to the body
    ("bytes=1024-", ("unsatisfiable", None)),
    ("bytes=2000-3000", ("unsatisfiable", None)),
    ("bytes=-0", ("unsatisfiable", None)),
    ("bytes=0-10,20-30", ("full", None)),              # multi-range: ignored, serve 200
    ("bytes=-", ("full", None)),
    ("bytes=50-10", ("full", None)),                   # malformed: ignored
    ("items=0-10", ("full", None)),
])
def test_parse_range(header, expected):
    assert parse_range(header, 1024) == expected


@pytest.mark.unit
def test_parse_range_on_empty_body_is_always_full():
    assert parse_range("bytes=0-10", 0) == ("full", None)


# ---------------------------------------------------------------------------
# plane_audio_response
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_full_response_when_no_range_requested():
    response = plane_audio_response(_request(), AUDIO, "audio/opus")
    assert response.status_code == 200
    assert response.body == AUDIO
    assert response.headers["content-length"] == str(len(AUDIO))
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["content-type"] == "audio/opus"
    assert "content-range" not in response.headers


@pytest.mark.unit
def test_partial_response_serves_exactly_the_requested_slice():
    response = plane_audio_response(_request("bytes=100-199"), AUDIO, "audio/opus")
    assert response.status_code == 206
    assert response.body == AUDIO[100:200]
    assert response.headers["content-length"] == "100"
    assert response.headers["content-range"] == f"bytes 100-199/{len(AUDIO)}"
    assert response.headers["accept-ranges"] == "bytes"


@pytest.mark.unit
def test_tail_range_returns_the_last_ogg_bytes():
    """The request an Ogg-aware player makes to find the duration"""
    response = plane_audio_response(_request("bytes=-64"), AUDIO, "audio/opus")
    assert response.status_code == 206
    assert response.body == AUDIO[-64:]
    assert response.headers["content-range"] == f"bytes 960-1023/{len(AUDIO)}"


@pytest.mark.unit
def test_unsatisfiable_range_is_a_416_with_the_full_size():
    response = plane_audio_response(_request("bytes=99999-"), AUDIO, "audio/opus")
    assert response.status_code == 416
    assert response.body == b""
    assert response.headers["content-range"] == f"bytes */{len(AUDIO)}"


@pytest.mark.unit
def test_slices_reassemble_to_the_original_file():
    """Whatever chunking a client picks, concatenating the 206 bodies must
    reproduce the bytes - the property that makes range playback work"""
    chunks = []
    for start in range(0, len(AUDIO), 300):
        response = plane_audio_response(_request(f"bytes={start}-{start + 299}"), AUDIO, "audio/opus")
        assert response.status_code == 206
        chunks.append(response.body)
    assert b"".join(chunks) == AUDIO


# ---------------------------------------------------------------------------
# RecentAudioCache
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_recent_audio_cache_round_trips_and_bounds_entries():
    cache = RecentAudioCache(ttl_seconds=60, max_entries=2)
    cache.put("a", b"aaa")
    cache.put("b", b"bbb")
    assert cache.get("a") == b"aaa"          # touch a, so b is now the oldest
    cache.put("c", b"ccc")
    assert len(cache) == 2
    assert cache.get("b") is None
    assert cache.get("a") == b"aaa"
    assert cache.get("c") == b"ccc"


@pytest.mark.unit
def test_recent_audio_cache_expires_entries(monkeypatch):
    import app.audio_response as module

    now = [1000.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: now[0])
    cache = RecentAudioCache(ttl_seconds=30, max_entries=8)
    cache.put("k", b"data")
    now[0] += 29
    assert cache.get("k") == b"data"
    now[0] += 2
    assert cache.get("k") is None
    assert len(cache) == 0


@pytest.mark.unit
def test_recent_audio_cache_ignores_empty_payloads():
    cache = RecentAudioCache(ttl_seconds=30, max_entries=8)
    cache.put("k", b"")
    assert cache.get("k") is None


# ---------------------------------------------------------------------------
# SingleFlight
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_concurrent_callers_share_one_producer_run():
    """Five range requests arriving during one TTS generation must cost one
    generation, not five - the DOJP-22 amplification, prevented"""
    flight = SingleFlight()
    calls = 0
    started = asyncio.Event()

    async def producer():
        nonlocal calls
        calls += 1
        started.set()
        await asyncio.sleep(0.05)
        return b"generated"

    first = asyncio.create_task(flight.run("key", producer))
    await started.wait()
    assert flight.is_inflight("key")
    others = [asyncio.create_task(flight.run("key", producer)) for _ in range(4)]

    results = await asyncio.gather(first, *others)
    assert results == [b"generated"] * 5
    assert calls == 1
    assert not flight.is_inflight("key")


@pytest.mark.unit
async def test_different_keys_do_not_share():
    flight = SingleFlight()

    async def producer(value):
        await asyncio.sleep(0.01)
        return value

    a, b = await asyncio.gather(flight.run("a", lambda: producer("A")), flight.run("b", lambda: producer("B")))
    assert (a, b) == ("A", "B")


@pytest.mark.unit
async def test_producer_failure_reaches_every_waiter_and_clears_the_slot():
    flight = SingleFlight()
    started = asyncio.Event()

    async def producer():
        started.set()
        await asyncio.sleep(0.02)
        raise RuntimeError("tts down")

    first = asyncio.create_task(flight.run("key", producer))
    await started.wait()
    second = asyncio.create_task(flight.run("key", producer))

    with pytest.raises(RuntimeError):
        await first
    with pytest.raises(RuntimeError):
        await second
    assert not flight.is_inflight("key")

    # A later call runs afresh rather than replaying the failure
    async def recovered():
        return b"ok"
    assert await flight.run("key", recovered) == b"ok"
