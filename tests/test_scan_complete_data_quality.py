"""scan:complete must carry the provider data-quality counters (DOJP-37)

The rejection gates in the Airlabs provider only earn their keep if their
counts are observable - thresholds are tuned from Mixpanel, not guesswork.
"""

from unittest.mock import Mock

import pytest
from starlette.requests import Request

import app.main as main


def _fake_request():
    return Request({
        "type": "http", "method": "GET", "path": "/scanning",
        "headers": [(b"user-agent", b"ESP32 HTTP Client/1.0")],
        "query_string": b"", "client": ("203.0.113.7", 1234),
    })


@pytest.fixture
def captured_event(monkeypatch):
    capture = Mock()
    monkeypatch.setattr(main.analytics, "track_event", capture)
    return capture


STATS = {
    "rejected_stale": 2,
    "rejected_route": 1,
    "rejected_implausible": 0,
    "accepted_no_route": 1,
    "oldest_signal_age_s": 421,
    "stale_threshold_s": 300,
}


@pytest.mark.unit
def test_data_quality_counters_land_on_scan_complete(captured_event):
    main.track_scan_complete(
        _fake_request(), 40.7, -74.0, "New York",
        from_cache=False, nearby_aircraft=5, provider="airlabs",
        data_quality=STATS,
    )

    (event_name, properties), kwargs = captured_event.call_args
    assert event_name == "scan:complete"
    for key, value in STATS.items():
        assert properties[key] == value, f"{key} missing or wrong on scan:complete"
    # the merge must not clobber the existing properties
    assert properties["nearby_aircraft"] == 5
    assert properties["aircraft_provider"] == "airlabs"


@pytest.mark.unit
def test_counters_absent_when_no_fetch_ran(captured_event):
    """Cache hits and provider failures carry no stats - the properties must
    be absent, not zero, so Mixpanel rates divide by live fetches only"""
    main.track_scan_complete(
        _fake_request(), 40.7, -74.0, "New York",
        from_cache=True, nearby_aircraft=5, provider="airlabs",
    )

    (_, properties), _ = captured_event.call_args
    assert "rejected_stale" not in properties
    assert "stale_threshold_s" not in properties
