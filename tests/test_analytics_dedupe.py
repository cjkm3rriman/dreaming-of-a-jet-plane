"""Tests for analytics dedupe and city reporting (DOJP-41)

The "session_id" hashed into every $insert_id is a stable device+location
fingerprint - nothing in it varies between a 9am and a 5pm scan from the same
living room. Mixpanel dedupes on (event, distinct_id, date, $insert_id), so
same-day rescans were silently collapsed to one event per household, and
scan:complete always reported user_city="Unknown" despite the caller knowing
the real city. These tests pin both fixes.
"""

import json
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest
import respx
from starlette.requests import Request

import app.aircraft_providers.airlabs as airlabs
import app.main as main

FIXTURES = Path(__file__).parent / "fixtures"


def _fake_request():
    return Request({
        "type": "http", "method": "GET", "path": "/scanning",
        "headers": [(b"user-agent", b"ESP32 HTTP Client/1.0")],
        "query_string": b"", "client": ("203.0.113.7", 1234),
    })


@pytest.fixture
def captured_events(monkeypatch):
    capture = Mock()
    monkeypatch.setattr(main.analytics, "track_event", capture)
    return capture


def _insert_id(capture, call=0):
    (_, properties), _ = capture.call_args_list[call]
    return properties["$insert_id"]


@pytest.mark.unit
def test_scans_in_different_buckets_get_different_insert_ids(captured_events, monkeypatch):
    """A 9am and a 5pm scan from the same device must both count"""
    request = _fake_request()

    monkeypatch.setattr(main.time, "time", lambda: 1_000_000.0)
    main.track_scan_complete(request, 40.7, -74.0, "New York",
                             from_cache=False, nearby_aircraft=5, provider="airlabs")

    monkeypatch.setattr(main.time, "time", lambda: 1_000_000.0 + 8 * 3600)
    main.track_scan_complete(request, 40.7, -74.0, "New York",
                             from_cache=False, nearby_aircraft=5, provider="airlabs")

    assert _insert_id(captured_events, 0) != _insert_id(captured_events, 1)


@pytest.mark.unit
def test_client_retries_within_a_bucket_still_dedupe(captured_events, monkeypatch):
    """Yoto re-requests arrive seconds apart - those must keep collapsing"""
    request = _fake_request()
    base = 1_000_000.0 - (1_000_000.0 % main.ANALYTICS_DEDUPE_BUCKET_S)

    monkeypatch.setattr(main.time, "time", lambda: base + 1.0)
    main.track_scan_complete(request, 40.7, -74.0, "New York",
                             from_cache=False, nearby_aircraft=5, provider="airlabs")

    monkeypatch.setattr(main.time, "time", lambda: base + 20.0)
    main.track_scan_complete(request, 40.7, -74.0, "New York",
                             from_cache=False, nearby_aircraft=5, provider="airlabs")

    assert _insert_id(captured_events, 0) == _insert_id(captured_events, 1)


@pytest.mark.unit
def test_every_tracker_carries_the_time_bucket(captured_events, monkeypatch):
    """All insert_ids gain the bucket, not just scan:complete"""
    monkeypatch.setattr(main.time, "time", lambda: 1_000_000.0)
    bucket = main._analytics_dedupe_bucket()
    request = _fake_request()

    main.track_scan_complete(request, 40.7, -74.0, "X",
                             from_cache=False, nearby_aircraft=1, provider="airlabs")
    main.track_scan_start(request)
    main.track_plane_request(request, 40.7, -74.0, "X", plane_index=1, from_cache=True)

    assert captured_events.call_count == 3
    for call in range(3):
        assert _insert_id(captured_events, call).endswith(f"_{bucket}"), \
            f"call {call} missing the time bucket"


@pytest.mark.unit
async def test_scan_complete_reports_the_real_city(captured_events, monkeypatch):
    """get_nearby_aircraft knew the city and hardcoded "Unknown" anyway.

    Runs the real fetch path offline: recorded Airlabs payload via respx,
    S3 cache stubbed out, real provider parsing and selection.
    """
    import time as _time
    payload = json.loads((FIXTURES / "airlabs_flights.json").read_text())
    newest = max(f["updated"] for f in payload["response"] if f.get("updated"))
    shift = int(_time.time()) - newest
    for flight in payload["response"]:
        if flight.get("updated"):
            flight["updated"] += shift

    async def _no_cache(*a, **k):
        return None

    async def _no_store(*a, **k):
        return True

    monkeypatch.setattr(main.s3_cache, "get", _no_cache)
    monkeypatch.setattr(main.s3_cache, "set", _no_store)
    monkeypatch.setattr(main, "get_live_aircraft_providers", lambda *a, **k: ["airlabs"])
    monkeypatch.setattr(airlabs, "AIRLABS_API_KEY", "test-key")

    with respx.mock:
        respx.get(url__startswith="https://airlabs.co").mock(
            return_value=httpx.Response(200, json=payload)
        )
        aircraft, error = await main.get_nearby_aircraft(
            40.7128, -74.0060, request=_fake_request(), user_city="Testville"
        )

    assert error == ""
    assert aircraft

    (event_name, properties), _ = captured_events.call_args
    assert event_name == "scan:complete"
    assert properties["user_city"] == "Testville"
    # and the DOJP-37 data-quality counters ride along on the same event
    assert "stale_threshold_s" in properties
