"""Contract tests for both aircraft providers (DOJP-47 item 2)

Provider payload parsing is where the worst production bugs have lived -- the
Airlabs ETA use-before-assignment (DOJP-23) shipped for months because nothing
exercised `fetch_aircraft` against a known response. These tests replay real
recorded payloads through the real parser with respx, so a renamed upstream
field, a dropped unit conversion, or a regression in enrichment fails here
rather than reaching a child as "an unknown destination".

The fixtures in tests/fixtures/ are genuine responses captured from the live
APIs over New York on 2026-09-12. Refresh them by re-recording, never by hand
editing: their value is that no one chose their contents.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
import respx

import app.aircraft_providers.airlabs as airlabs
import app.aircraft_providers.fr24 as fr24

FIXTURES = Path(__file__).parent / "fixtures"
USER_LAT, USER_LNG = 40.7128, -74.0060
RADIUS_KM = 100

# Every key main.py, flight_text.py and select_diverse_aircraft rely on. A
# provider that stops emitting one of these breaks text generation downstream.
REQUIRED_KEYS = {
    "icao24", "callsign", "flight_number", "airline_icao", "airline_name",
    "is_cargo_operator", "is_private_operator", "aircraft_registration",
    "aircraft_icao", "aircraft", "passenger_capacity", "origin_airport",
    "origin_city", "origin_country", "destination_airport", "destination_city",
    "destination_country", "latitude", "longitude", "altitude", "velocity",
    "distance_km", "distance_miles", "status", "eta",
}


def _load(name):
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture
def fr24_payload():
    return _load("fr24_flight_positions.json")


@pytest.fixture
def airlabs_payload():
    """The recorded payload with `updated` shifted so the newest signal is now.

    Relative ages are preserved. Without this shift every recorded flight ages
    past the freshness gate as wall-clock time advances, and the fixture would
    silently stop exercising anything (DOJP-37).
    """
    import time
    payload = _load("airlabs_flights.json")
    newest = max(f["updated"] for f in payload["response"] if f.get("updated"))
    shift = int(time.time()) - newest
    for flight in payload["response"]:
        if flight.get("updated"):
            flight["updated"] += shift
    return payload


@pytest.fixture
def configured_providers(monkeypatch):
    """Both providers read their key at import time"""
    monkeypatch.setattr(fr24, "FR24_API_KEY", "test-key")
    monkeypatch.setattr(airlabs, "AIRLABS_API_KEY", "test-key")


async def _fetch_fr24(payload):
    with respx.mock:
        respx.get(url__startswith="https://fr24api.flightradar24.com").mock(
            return_value=httpx.Response(200, json=payload)
        )
        return await fr24.fetch_aircraft(USER_LAT, USER_LNG, RADIUS_KM, 5)


async def _fetch_airlabs(payload):
    with respx.mock:
        respx.get(url__startswith="https://airlabs.co").mock(
            return_value=httpx.Response(200, json=payload)
        )
        return await airlabs.fetch_aircraft(USER_LAT, USER_LNG, RADIUS_KM, 5)


def _by_registration(aircraft, registration):
    match = [a for a in aircraft if a.get("aircraft_registration") == registration]
    assert match, f"{registration} missing from normalized output"
    return match[0]


# --------------------------------------------------------------------------
# Shared shape contract
# --------------------------------------------------------------------------

@pytest.mark.unit
async def test_fr24_emits_every_required_key(configured_providers, fr24_payload):
    aircraft, error, _stats = await _fetch_fr24(fr24_payload)

    assert error == ""
    assert aircraft
    for plane in aircraft:
        assert REQUIRED_KEYS <= set(plane), \
            f"missing {REQUIRED_KEYS - set(plane)} for {plane.get('callsign')}"


@pytest.mark.unit
async def test_airlabs_emits_every_required_key(configured_providers, airlabs_payload):
    aircraft, error, _stats = await _fetch_airlabs(airlabs_payload)

    assert error == ""
    assert aircraft
    for plane in aircraft:
        assert REQUIRED_KEYS <= set(plane), \
            f"missing {REQUIRED_KEYS - set(plane)} for {plane.get('callsign')}"


@pytest.mark.unit
async def test_both_providers_agree_on_shape(configured_providers, fr24_payload, airlabs_payload):
    """The two providers must be interchangeable for downstream code.

    get_nearby_aircraft falls back from one to the other mid-request, so a key
    present in only one of them is a latent crash on the fallback path.
    """
    fr24_aircraft, _, _stats = await _fetch_fr24(fr24_payload)
    airlabs_aircraft, _, _stats = await _fetch_airlabs(airlabs_payload)

    fr24_keys = set(fr24_aircraft[0])
    airlabs_keys = set(airlabs_aircraft[0])

    # Airlabs additionally reports `updated`; nothing downstream requires it,
    # but any *other* divergence means the shapes have drifted apart
    assert airlabs_keys - fr24_keys == {"updated"}
    assert fr24_keys - airlabs_keys == set()


# --------------------------------------------------------------------------
# FR24: golden record
# --------------------------------------------------------------------------

@pytest.mark.unit
async def test_fr24_normalizes_a_known_flight_exactly(configured_providers, fr24_payload):
    """Southwest 1450, BWI->BOS, as recorded. Pins field mapping and enrichment:
    painted_as->airline_icao->airline_name, type->aircraft name and capacity,
    orig/dest_iata->city and country.
    """
    aircraft, _, _stats = await _fetch_fr24(fr24_payload)
    plane = _by_registration(aircraft, "N941WN")

    assert plane["icao24"] == "AD12E0"
    assert plane["callsign"] == "SWA1450"
    assert plane["flight_number"] == "WN1450"
    assert plane["airline_icao"] == "SWA"
    assert plane["airline_name"] == "Southwest Airlines"
    assert plane["aircraft_icao"] == "B737"
    assert plane["aircraft"] == "Boeing 737"
    assert plane["passenger_capacity"] == 149
    assert plane["origin_airport"] == "BWI"
    assert plane["origin_city"] == "Baltimore"
    assert plane["destination_airport"] == "BOS"
    assert plane["destination_city"] == "Boston"
    assert plane["destination_country"] == "the United States"
    assert plane["is_cargo_operator"] is False
    assert plane["is_private_operator"] is False
    # FR24 supplies ETA directly; it is passed through untouched
    assert plane["eta"] == "2026-09-12T02:05:36Z"


@pytest.mark.unit
async def test_fr24_passes_altitude_and_speed_through_unconverted(configured_providers, fr24_payload):
    """FR24 already reports feet and knots - a conversion added here would be a bug"""
    raw = {f["reg"]: f for f in fr24_payload["data"]}["N941WN"]
    aircraft, _, _stats = await _fetch_fr24(fr24_payload)
    plane = _by_registration(aircraft, "N941WN")

    assert plane["altitude"] == raw["alt"]
    assert plane["velocity"] == raw["gspeed"]


# --------------------------------------------------------------------------
# Airlabs: golden record and unit conversions
# --------------------------------------------------------------------------

@pytest.mark.unit
async def test_airlabs_normalizes_a_known_flight_exactly(configured_providers, airlabs_payload):
    """Southwest 3364, HOU->LGA, as recorded"""
    aircraft, _, _stats = await _fetch_airlabs(airlabs_payload)
    plane = _by_registration(aircraft, "N8918Q")

    assert plane["airline_icao"] == "SWA"
    assert plane["airline_name"] == "Southwest Airlines"
    assert plane["flight_number"] == "WN3364"
    assert plane["aircraft_icao"] == "B38M"
    assert plane["origin_airport"] == "HOU"
    assert plane["origin_city"] == "Houston"
    assert plane["destination_airport"] == "LGA"
    assert plane["destination_city"] == "New York City"
    assert plane["status"] == "en-route"


@pytest.mark.unit
async def test_airlabs_converts_altitude_and_speed_to_feet_and_knots(configured_providers, airlabs_payload):
    """Airlabs reports metres and km/h; flight_text expects feet and knots.

    Dropping either conversion still yields a plausible-looking number, so this
    pins the arithmetic against the recorded raw values rather than a range.
    """
    raw = {f["reg_number"]: f for f in airlabs_payload["response"]}["N8918Q"]
    aircraft, _, _stats = await _fetch_airlabs(airlabs_payload)
    plane = _by_registration(aircraft, "N8918Q")

    assert plane["altitude"] == round(raw["alt"] * 3.28084)
    assert plane["velocity"] == round(raw["speed"] * 0.539957)
    # and the converted values must actually differ from the raw ones
    assert plane["altitude"] != raw["alt"]
    assert plane["velocity"] != raw["speed"]


@pytest.mark.unit
async def test_airlabs_gives_every_aircraft_an_eta(configured_providers, airlabs_payload):
    """Regression guard for DOJP-23.

    Airlabs has no arrival-time field, so every ETA is estimated locally. The
    use-before-assignment bug left the first flight of each batch with eta=None
    and computed the rest at the previous flight's cruise speed. Against this
    recorded payload the old code produced a None; the fixed code produces an
    ETA for every aircraft with a known destination.
    """
    aircraft, _, _stats = await _fetch_airlabs(airlabs_payload)

    assert len(aircraft) > 5, "fixture should exercise a realistic batch"
    missing = [p["callsign"] for p in aircraft if p["destination_airport"] and not p["eta"]]
    assert not missing, f"aircraft with a destination but no ETA: {missing}"


@pytest.mark.unit
async def test_airlabs_etas_are_parseable_future_timestamps(configured_providers, airlabs_payload):
    """flight_text parses the ETA with fromisoformat and subtracts now()"""
    aircraft, _, _stats = await _fetch_airlabs(airlabs_payload)
    now = datetime.now(timezone.utc)

    for plane in aircraft:
        if not plane["eta"]:
            continue
        parsed = datetime.fromisoformat(plane["eta"].replace("Z", "+00:00"))
        assert parsed.tzinfo is not None, f"{plane['callsign']} ETA is naive"
        hours_out = (parsed - now).total_seconds() / 3600
        assert 0 < hours_out < 24, f"{plane['callsign']} ETA {hours_out:.1f}h away is implausible"


# --------------------------------------------------------------------------
# Enrichment and filtering behaviour
# --------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.parametrize("provider", ["fr24", "airlabs"])
async def test_destinations_resolve_to_real_cities(configured_providers, fr24_payload, airlabs_payload, provider):
    """The 'every plane is an unknown destination' failure mode.

    If an upstream field is renamed, IATA codes stop resolving and every flight
    silently loses its city. Most flights in a real batch should resolve.
    """
    if provider == "fr24":
        aircraft, _, _stats = await _fetch_fr24(fr24_payload)
    else:
        aircraft, _, _stats = await _fetch_airlabs(airlabs_payload)

    with_dest = [p for p in aircraft if p["destination_airport"]]
    resolved = [p for p in with_dest if p["destination_city"]]
    assert len(resolved) >= 0.8 * len(with_dest), \
        f"only {len(resolved)}/{len(with_dest)} destinations resolved to a city"


@pytest.mark.unit
async def test_all_returned_aircraft_are_within_the_radius(configured_providers, airlabs_payload):
    """The recorded payload is a bounding box, which is wider than the radius"""
    aircraft, _, _stats = await _fetch_airlabs(airlabs_payload)

    assert aircraft
    assert all(p["distance_km"] <= RADIUS_KM for p in aircraft)
    # and sorted nearest-first, which select_diverse_aircraft relies on
    distances = [p["distance_km"] for p in aircraft]
    assert distances == sorted(distances)


@pytest.mark.unit
async def test_airlabs_skips_flights_that_are_not_en_route(configured_providers, airlabs_payload):
    """The recorded batch contains non-en-route rows that must be filtered out"""
    statuses = {f.get("status") for f in airlabs_payload["response"]}
    assert statuses - {"en-route"}, "fixture no longer exercises the status filter"

    aircraft, _, _stats = await _fetch_airlabs(airlabs_payload)
    assert all(p["status"] == "en-route" for p in aircraft)
