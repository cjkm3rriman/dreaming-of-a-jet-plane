"""Special Signal Events calendar (DOJP-33)

The event table replaces the hardcoded Santa module. During an event window
the event owns track 1 and the real planes shift down a slot (fifth drops);
event audio caches once per event+provider, never per location; the free
pool's metadata follows the shift so shifted tracks aren't mislabeled.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

import app.special_events as se
from app.special_events import (
    aircraft_slot_for_plane,
    event_cache_key,
    get_active_event,
)


def _utc(month, day, hour, minute=0):
    return datetime(2026, month, day, hour, minute, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Window logic
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("now,expected", [
    (_utc(12, 24, 6, 59), None),        # one minute before the window
    (_utc(12, 24, 7), "santa"),         # boundary: start is inclusive
    (_utc(12, 24, 23), "santa"),        # mid-window
    (_utc(12, 25, 6, 59), "santa"),     # last hour
    (_utc(12, 25, 7), None),            # boundary: end is exclusive
    (_utc(7, 15, 12), None),            # ordinary day
])
def test_santa_window_boundaries(now, expected):
    event = get_active_event(now)
    assert (event["name"] if event else None) == expected


@pytest.mark.unit
def test_year_wrapping_window(monkeypatch):
    """A start greater than its end wraps the year boundary (future NYE)"""
    monkeypatch.setattr(se, "EVENTS", [
        {"name": "nye", "start": (12, 31, 12), "end": (1, 1, 12), "text": "x"},
    ])
    assert get_active_event(_utc(12, 31, 13))["name"] == "nye"
    assert get_active_event(_utc(1, 1, 11))["name"] == "nye"
    assert get_active_event(_utc(1, 1, 12)) is None
    assert get_active_event(_utc(6, 1, 0)) is None


# ---------------------------------------------------------------------------
# Slot shift: event first, planes pushed down, fifth drops
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_slot_mapping_without_event_is_identity():
    assert [aircraft_slot_for_plane(n, False) for n in range(1, 6)] == [0, 1, 2, 3, 4]


@pytest.mark.unit
def test_slot_mapping_during_event_shifts_planes_down():
    """Track 1 is the event; track N serves aircraft N-2; the 5th aircraft
    (index 4) is no longer reachable from any track"""
    slots = [aircraft_slot_for_plane(n, True) for n in range(1, 6)]
    assert slots == [None, 0, 1, 2, 3]
    assert 4 not in slots


# ---------------------------------------------------------------------------
# Event audio caching: once per event+provider, location-independent
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_cache_key_is_location_independent_and_content_hashed():
    event = {"name": "santa", "text": "Ho ho ho"}
    key = event_cache_key(event, "inworld", "opus")
    assert key.startswith("special-events/santa_")
    assert key.endswith("_inworld.opus")
    assert "cache/" not in key  # the lifecycle-reaped prefix (DOJP-50)

    # same text -> same key; edited script -> new key
    assert event_cache_key(event, "inworld", "opus") == key
    assert event_cache_key({"name": "santa", "text": "Ho ho ho!"}, "inworld", "opus") != key


@pytest.mark.unit
async def test_ensure_event_audio_generates_once_then_serves_cached(monkeypatch):
    event = {"name": "santa", "text": "Ho ho ho"}
    store = {}

    async def fake_get_raw(key):
        return store.get(key)

    async def fake_set(key, data, content_type="audio"):
        store[key] = data
        return True

    monkeypatch.setattr(se.s3_cache, "get_raw", fake_get_raw)
    monkeypatch.setattr(se.s3_cache, "set", fake_set)

    import app.main as main
    tts = AsyncMock(return_value=(b"sleigh-audio", "", "inworld", "opus", "audio/opus"))
    monkeypatch.setattr(main, "convert_text_to_speech", tts)
    monkeypatch.setattr(main, "TTS_PROVIDER", "inworld")

    first = await se.ensure_event_audio(event)
    assert first["audio"] == b"sleigh-audio" and first["from_cache"] is False
    assert len(store) == 1, "audio cached under the shared event key"

    second = await se.ensure_event_audio(event)
    assert second["audio"] == b"sleigh-audio" and second["from_cache"] is True
    assert tts.await_count == 1, "one TTS call serves every listener in the window"


@pytest.mark.unit
async def test_failed_event_generation_caches_nothing(monkeypatch):
    store = {}

    async def fake_get_raw(key):
        return store.get(key)

    async def fake_set(key, data, content_type="audio"):
        store[key] = data
        return True

    monkeypatch.setattr(se.s3_cache, "get_raw", fake_get_raw)
    monkeypatch.setattr(se.s3_cache, "set", fake_set)

    import app.main as main
    monkeypatch.setattr(main, "convert_text_to_speech",
                        AsyncMock(return_value=(b"", "Inworld API returned status 503", "inworld", "opus", "audio/opus")))
    monkeypatch.setattr(main, "TTS_PROVIDER", "inworld")

    result = await se.ensure_event_audio({"name": "santa", "text": "Ho"})
    assert result["audio"] == b"" and result["error"]
    assert store == {}, "a failed generation must not poison the event cache"


# ---------------------------------------------------------------------------
# Free pool: shifted metadata alignment, event track excluded
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_populate_free_pool_slot_offset_aligns_metadata(monkeypatch):
    """During an event, plane 2's body cache holds aircraft 0's audio - the
    index metadata must come from aircraft 0 too, and track 1 (the event)
    must contribute nothing to the free pool"""
    import app.free_pool as fp

    reads, writes = [], []

    async def fake_get_raw(key):
        reads.append(key)
        return b"body-bytes"

    async def fake_set(key, data, content_type="audio"):
        writes.append(key)
        return True

    captured = {}

    async def fake_update_index(session_id, planes_data, tts_provider):
        captured["planes"] = planes_data
        return True

    monkeypatch.setattr(fp.s3_cache, "get_raw", fake_get_raw)
    monkeypatch.setattr(fp.s3_cache, "set", fake_set)
    monkeypatch.setattr(fp, "update_free_pool_index", fake_update_index)

    aircraft_list = [
        {"origin_city": "Oslo", "destination_city": "Tromso", "airline_name": "Wideroe"},
        {"origin_city": "Lima", "destination_city": "Cusco", "airline_name": "LATAM"},
        {"origin_city": "Cork", "destination_city": "Paris", "airline_name": "Aer Lingus"},
    ]
    ok = await fp.populate_free_pool(aircraft_list, "abc123", "inworld", slot_offset=1)
    assert ok

    planes = captured["planes"]
    by_index = {p["index"]: p for p in planes}
    assert 1 not in by_index, "the event track must not enter the free pool"
    # plane 2 carries aircraft 0's flight, plane 3 carries aircraft 1's
    assert by_index[2]["destination_city"] == "Tromso"
    assert by_index[3]["destination_city"] == "Cusco"
    # and the body reads came from the plane-numbered cache keys
    assert any("plane2_body" in k for k in reads)
    assert any("plane3_body" in k for k in reads)
    assert not any("plane1_body" in k for k in reads)


@pytest.mark.unit
async def test_populate_free_pool_unshifted_behavior_unchanged(monkeypatch):
    import app.free_pool as fp

    async def fake_get_raw(key):
        return b"body-bytes"

    async def fake_set(key, data, content_type="audio"):
        return True

    captured = {}

    async def fake_update_index(session_id, planes_data, tts_provider):
        captured["planes"] = planes_data
        return True

    monkeypatch.setattr(fp.s3_cache, "get_raw", fake_get_raw)
    monkeypatch.setattr(fp.s3_cache, "set", fake_set)
    monkeypatch.setattr(fp, "update_free_pool_index", fake_update_index)

    aircraft_list = [{"origin_city": "A", "destination_city": "B", "airline_name": "C"}] * 3
    assert await fp.populate_free_pool(aircraft_list, "abc123", "inworld")
    assert [p["index"] for p in captured["planes"]] == [1, 2, 3]


# ---------------------------------------------------------------------------
# Secret-gated preview (the manual-verification path)
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("params,expected", [
    ({"event_preview": "santa", "secret": "s3cret"}, "santa"),
    ({"event_preview": "santa", "secret": "wrong"}, None),
    ({"event_preview": "santa"}, None),
    ({"event_preview": "nope", "secret": "s3cret"}, None),
    ({}, None),
])
def test_event_preview_requires_secret_and_known_name(monkeypatch, params, expected):
    import app.main as main
    from starlette.requests import Request

    monkeypatch.setattr(main, "PROVIDER_OVERRIDE_SECRET", "s3cret")
    query = "&".join(f"{k}={v}" for k, v in params.items()).encode()
    request = Request({"type": "http", "method": "GET", "path": "/plane/1",
                       "query_string": query, "headers": [], "client": ("1.2.3.4", 1)})
    event = main.get_event_preview_override(request)
    assert (event["name"] if event else None) == expected
