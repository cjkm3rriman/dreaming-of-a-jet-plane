"""Latent edge-case fixes from the review sweep (DOJP-44)

Small hardening items grouped in one ticket. The s3_cache Last-Modified edge
(item 3) is covered in test_s3_cache.py; these cover geolocation nulls, header
trust, the Inworld key-encoding override, and the 0.0-coordinate route guard.
"""

import base64

import httpx
import pytest
import respx
from starlette.requests import Request

import app.location_utils as location_utils
import app.tts_providers.inworld as inworld


def _request(headers):
    raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    return Request({
        "type": "http", "method": "GET", "path": "/", "query_string": b"",
        "headers": raw, "client": ("9.9.9.9", 1234),
    })


# ---------------------------------------------------------------------------
# Item 1: null coordinates from ipapi.co fall back to NYC, never crash
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("lat,lng", [
    (None, None),        # JSON null - the case that bypassed the 0.0 default
    (None, -74.0),
    (0.0, 0.0),          # still the ocean-origin sentinel
])
async def test_null_or_zero_coords_fall_back_to_nyc(monkeypatch, lat, lng):
    payload = {"latitude": lat, "longitude": lng, "country_code": "US",
               "city": "", "region": "", "country_name": ""}

    with respx.mock as router:
        router.get(url__regex=r"https://ipapi\.co/.*").mock(
            return_value=httpx.Response(200, json=payload))
        result = await location_utils.get_location_from_ip("203.0.113.9")

    got_lat, got_lng = result[0], result[1]
    is_fallback = result[6]
    assert (got_lat, got_lng) == (40.7128, -74.0060), "should be the NYC fallback"
    assert is_fallback is True


@pytest.mark.unit
async def test_real_coords_are_preserved(monkeypatch):
    payload = {"latitude": 51.5, "longitude": -0.13, "country_code": "GB",
               "city": "London", "region": "England", "country_name": "United Kingdom"}
    with respx.mock as router:
        router.get(url__regex=r"https://ipapi\.co/.*").mock(
            return_value=httpx.Response(200, json=payload))
        result = await location_utils.get_location_from_ip("203.0.113.10")

    assert (result[0], result[1]) == (51.5, -0.13)
    assert result[6] is False


# ---------------------------------------------------------------------------
# Item 2: the trusted CDN header wins over client-appendable XFF
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_cf_connecting_ip_beats_spoofable_forwarded_for():
    ip = location_utils.extract_client_ip(_request({
        "cf-connecting-ip": "1.1.1.1",
        "x-forwarded-for": "6.6.6.6, 7.7.7.7",  # attacker-supplied first entry
        "x-real-ip": "2.2.2.2",
    }))
    assert ip == "1.1.1.1"


@pytest.mark.unit
def test_forwarded_for_still_used_when_no_trusted_header():
    ip = location_utils.extract_client_ip(_request({"x-forwarded-for": "8.8.8.8, 9.9.9.9"}))
    assert ip == "8.8.8.8"


# ---------------------------------------------------------------------------
# Item 4: explicit Inworld key-encoding override
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_inworld_preencoded_true_passes_key_through(monkeypatch):
    """A raw key that happens to be valid base64 no longer gets mangled when
    the operator declares it pre-encoded"""
    monkeypatch.setattr(inworld, "INWORLD_API_KEY", "abcd1234")  # valid base64, no colon
    monkeypatch.setenv("INWORLD_API_KEY_PREENCODED", "true")
    assert inworld._build_authorization_header() == "Basic abcd1234"


@pytest.mark.unit
def test_inworld_preencoded_false_forces_encoding(monkeypatch):
    monkeypatch.setattr(inworld, "INWORLD_API_KEY", "abcd1234")
    monkeypatch.setenv("INWORLD_API_KEY_PREENCODED", "false")
    expected = "Basic " + base64.b64encode(b"abcd1234").decode()
    assert inworld._build_authorization_header() == expected


@pytest.mark.unit
def test_inworld_colon_key_is_encoded_by_the_heuristic(monkeypatch):
    """Unset override falls back to the heuristic: a user:secret pair encodes"""
    monkeypatch.delenv("INWORLD_API_KEY_PREENCODED", raising=False)
    monkeypatch.setattr(inworld, "INWORLD_API_KEY", "user:secret")
    assert inworld._build_authorization_header() == "Basic " + base64.b64encode(b"user:secret").decode()


# ---------------------------------------------------------------------------
# Item 7: route validation runs for 0.0-coordinate airports
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_route_validation_runs_for_zero_coordinate_airport(monkeypatch):
    """all([...]) treated a legitimate 0.0 lat/lon as missing and fail-open
    skipped the route check for equator/prime-meridian airports. The fixed
    `all(v is not None ...)` guard must call route validation instead (DOJP-44).
    """
    import app.aircraft_providers.airlabs as airlabs

    checked = []
    monkeypatch.setattr(airlabs, "AIRLABS_API_KEY", "test")
    monkeypatch.setattr(airlabs, "is_point_near_route",
                        lambda **kw: checked.append(kw) or True)
    # origin airport sits on the equator/prime meridian (0.0, 0.0)
    monkeypatch.setattr(airlabs, "get_airport_by_iata", lambda iata: (
        {"lat": 0.0, "lon": 0.0} if iata == "ZRO" else {"lat": 40.6, "lon": -73.8}))

    flight = {
        "status": "en-route", "lat": 20.0, "lng": -37.0,
        "updated": __import__("time").time(),
        "dep_iata": "ZRO", "arr_iata": "JFK",
        "flight_number": "42", "aircraft_icao": "B738", "speed": 800, "alt": 10000,
    }

    class _Resp:
        status_code = 200
        def json(self): return {"response": [flight]}

    class _Client:
        async def get(self, *a, **k): return _Resp()

    async def _get_client(): return _Client()
    monkeypatch.setattr(airlabs, "_get_client", _get_client)

    await airlabs.fetch_aircraft(20.0, -37.0, 100, 5)
    assert checked, "route validation was skipped for the 0.0-coordinate airport"
    assert checked[0]["origin_lat"] == 0.0 and checked[0]["origin_lng"] == 0.0
