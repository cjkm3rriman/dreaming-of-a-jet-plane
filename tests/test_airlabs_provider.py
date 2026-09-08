"""Tests for Airlabs payload parsing (DOJP-23)

fetch_aircraft used to read `aircraft_type` forty lines before assigning it: the
first flight of every batch lost its ETA to a swallowed UnboundLocalError and
every later flight was estimated at the *previous* flight's cruise speed. A
sibling bug wrapped the whole parse loop in one broad except, so a single
malformed record discarded the entire batch.

These tests run the real parser against a canned payload served by a fake HTTP
client - no live API, no skipping when the sky is empty.
"""

from datetime import datetime, timedelta, timezone

import pytest

import app.aircraft_providers.airlabs as airlabs
from app.aircraft_database import get_cruise_speed
from app.location_utils import calculate_distance

# User just north of JFK; flights positioned overhead, bound for LAX.
USER_LAT, USER_LNG = 40.8, -73.8
LAX = "LAX"


def _flight(**overrides):
    """One realistic /flights record; en-route JFK->LAX right over the user"""
    record = {
        "lat": 40.9,
        "lng": -73.9,
        "status": "en-route",
        "updated": 1757300000,
        "aircraft_icao": "B738",
        "airline_icao": "DAL",
        "airline_iata": "DL",
        "flight_number": "499",
        "dep_iata": "JFK",
        "arr_iata": LAX,
        "speed": 780,
        "alt": 10000,
        "reg_number": "N123DL",
    }
    record.update(overrides)
    return record


class _FakeResponse:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, payload):
        self._payload = payload

    async def get(self, url, params=None):
        return _FakeResponse(self._payload)


@pytest.fixture
def serve_payload(monkeypatch):
    """Point the provider at a canned payload and a dummy API key"""

    def _serve(flights):
        payload = {"response": flights}

        async def _fake_get_client():
            return _FakeClient(payload)

        monkeypatch.setattr(airlabs, "AIRLABS_API_KEY", "test-key")
        monkeypatch.setattr(airlabs, "_get_client", _fake_get_client)

    return _serve


def _eta_travel_hours(aircraft):
    """Hours from now until the aircraft's parsed ETA"""
    eta = datetime.fromisoformat(aircraft["eta"].replace("Z", "+00:00"))
    return (eta - datetime.now(timezone.utc)).total_seconds() / 3600


@pytest.mark.unit
async def test_every_flight_gets_an_eta(serve_payload):
    """The first flight of a batch used to lose its ETA to UnboundLocalError"""
    serve_payload([
        _flight(flight_number="101", aircraft_icao="B738"),
        _flight(flight_number="202", aircraft_icao="DH8D"),
        _flight(flight_number="303", aircraft_icao="B77W"),
    ])

    aircraft, error = await airlabs.fetch_aircraft(USER_LAT, USER_LNG, 100, 5)

    assert error == ""
    assert len(aircraft) == 3
    for plane in aircraft:
        assert plane["eta"] is not None, f"flight {plane['flight_number']} has no ETA"


@pytest.mark.unit
async def test_eta_uses_each_aircrafts_own_cruise_speed(serve_payload):
    """A Dash 8 following a 737 used to inherit the 737's speed"""
    assert get_cruise_speed("B738") != get_cruise_speed("DH8D"), \
        "test needs two types with distinct cruise speeds"

    serve_payload([
        _flight(flight_number="101", aircraft_icao="B738"),
        _flight(flight_number="202", aircraft_icao="DH8D"),
    ])

    aircraft, _ = await airlabs.fetch_aircraft(USER_LAT, USER_LNG, 100, 5)
    by_type = {plane["aircraft_icao"]: plane for plane in aircraft}
    assert set(by_type) == {"B738", "DH8D"}

    distance_to_dest = calculate_distance(40.9, -73.9, 33.9425, -118.4081)
    buffer_hours = airlabs.LANDING_BUFFER_MINUTES / 60

    for icao, plane in by_type.items():
        expected = distance_to_dest / get_cruise_speed(icao) + buffer_hours
        actual = _eta_travel_hours(plane)
        assert actual == pytest.approx(expected, abs=0.1), \
            f"{icao} ETA implies the wrong cruise speed"

    # And therefore the slower type lands later, from the same position
    assert _eta_travel_hours(by_type["DH8D"]) > _eta_travel_hours(by_type["B738"])


@pytest.mark.unit
async def test_one_malformed_record_does_not_discard_the_batch(serve_payload):
    """A single bad record used to throw away every already-parsed aircraft"""
    serve_payload([
        _flight(flight_number="101"),
        _flight(flight_number="BAD1", alt="not-a-number"),
        _flight(flight_number="303", aircraft_icao="B77W"),
    ])

    aircraft, error = await airlabs.fetch_aircraft(USER_LAT, USER_LNG, 100, 5)

    assert error == ""
    numbers = {plane["flight_number"] for plane in aircraft}
    assert len(aircraft) == 2
    assert not any("BAD1" in (n or "") for n in numbers)


@pytest.mark.unit
async def test_eta_is_always_the_estimate(serve_payload):
    """The bulk /flights endpoint has no arrival-time field; a stray arr_time in
    the payload must not leak through as a raw non-ISO string"""
    serve_payload([_flight(flight_number="101", arr_time="2026-09-08 14:30")])

    aircraft, _ = await airlabs.fetch_aircraft(USER_LAT, USER_LNG, 100, 5)

    assert len(aircraft) == 1
    # ISO with Z suffix, parseable the way flight_text parses it
    parsed = datetime.fromisoformat(aircraft[0]["eta"].replace("Z", "+00:00"))
    assert parsed.tzinfo is not None
