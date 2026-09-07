"""Tests for the is_fallback_location flag returned by get_user_location

The flag drives the plane-1 apology ("We couldn't find your location so let's
find some jet planes over New York City!"). It must mean "we do not trust this
location", not "this location did not come from IP geolocation" — explicit
lat/lng query parameters give us the location precisely, so they must not
trigger the apology (DOJP-24).
"""

import pytest
from starlette.requests import Request

from app.flight_text import generate_flight_text_for_aircraft
from app.location_utils import get_user_location

NYC_APOLOGY = "We couldn't find your location"


def _fake_request() -> Request:
    """Minimal Starlette Request; the explicit-coordinates branch never reads it"""
    return Request({
        "type": "http",
        "method": "GET",
        "path": "/plane/1",
        "headers": [],
        "query_string": b"",
        "client": ("127.0.0.1", 12345),
    })


@pytest.mark.unit
@pytest.mark.asyncio
async def test_explicit_coordinates_are_not_a_fallback():
    """Explicit lat/lng means we know where the user is, so no apology"""
    *_, is_fallback = await get_user_location(_fake_request(), lat=51.5074, lng=-0.1278)
    assert is_fallback is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_explicit_coordinates_are_passed_through_unchanged():
    """The override still returns the coordinates it was given"""
    lat, lng, country_code, *_ = await get_user_location(
        _fake_request(), lat=51.5074, lng=-0.1278, country="gb"
    )
    assert (lat, lng) == (51.5074, -0.1278)
    assert country_code == "GB"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_genuine_geolocation_failure_is_still_a_fallback(monkeypatch):
    """A real NYC fallback from IP geolocation must still set the flag"""
    async def _failed_lookup(ip, request):
        return 40.7128, -74.0060, "US", "New York", "New York", "United States", True

    monkeypatch.setattr("app.location_utils.get_location_from_ip", _failed_lookup)

    *_, is_fallback = await get_user_location(_fake_request())
    assert is_fallback is True


@pytest.mark.unit
def test_apology_omitted_when_location_is_known(sample_aircraft):
    """Plane 1 text has no NYC apology when the location is trusted"""
    text, _ = generate_flight_text_for_aircraft(
        sample_aircraft, 51.5074, -0.1278, 1, "GB", set(), is_fallback_location=False
    )
    assert NYC_APOLOGY not in text


@pytest.mark.unit
def test_apology_present_when_location_is_a_fallback(sample_aircraft):
    """Plane 1 text still apologises when we genuinely fell back to NYC"""
    text, _ = generate_flight_text_for_aircraft(
        sample_aircraft, 40.7128, -74.0060, 1, "US", set(), is_fallback_location=True
    )
    assert NYC_APOLOGY in text
