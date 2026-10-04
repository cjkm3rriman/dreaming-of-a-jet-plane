"""Aircraft type database: coverage of codes seen in production, and the
narratable-type gate that keeps helicopters and junk codes out of the five
(DOJP-58)"""

import json
from pathlib import Path

import pytest

from app.aircraft_database import (
    get_aircraft_name,
    get_passenger_capacity,
    get_phonetic_name,
    is_narratable_type,
)
from app.main import select_diverse_aircraft

AIRCRAFT_JSON = Path(__file__).parent.parent / "app" / "aircraft.json"

# Every fixed-wing code that reached a listener as "Unknown Aircraft (XXXX)" in
# the Jul-Oct 2026 Mixpanel export. Adding a code here means adding its entry.
AUDITED_FIXED_WING = [
    "CL35", "GL7T", "GA6C", "EXEC", "LJ45", "G150", "ASTR",
    "CR9", "BCS2", "320",
    "C402", "B350", "DA40", "P212", "P28A", "C441", "C172", "PA31", "G115",
    "DH3T", "TBM8", "PAY3", "PA34", "M600", "C340", "BN2P", "BE65", "BE36",
]
AUDITED_HELICOPTERS = [
    "S76", "H60", "EC45", "EC35", "EC30", "B429", "B06", "AS50",
    "A169", "A139", "A109",
]


@pytest.fixture(scope="module")
def db():
    return json.loads(AIRCRAFT_JSON.read_text(encoding="utf-8"))


@pytest.mark.unit
@pytest.mark.parametrize("code", AUDITED_FIXED_WING)
def test_audited_fixed_wing_codes_have_a_name(code):
    name = get_aircraft_name(code)
    assert not name.startswith("Unknown"), f"{code} still narrates as {name!r}"
    assert is_narratable_type(code)


@pytest.mark.unit
@pytest.mark.parametrize("code", AUDITED_HELICOPTERS)
def test_audited_helicopters_are_named_but_not_narrated(code):
    assert not get_aircraft_name(code).startswith("Unknown")
    assert not is_narratable_type(code)


@pytest.mark.unit
def test_provider_code_variants_read_like_their_canonical_entry():
    assert get_aircraft_name("CR9") == get_aircraft_name("CRJ9")
    assert get_aircraft_name("320") == get_aircraft_name("A320")
    assert get_phonetic_name("320") == get_phonetic_name("A320")
    assert get_phonetic_name("BCS2") == get_phonetic_name("BCS3")


@pytest.mark.unit
@pytest.mark.parametrize("code", [None, "", "  ", "ZZZZ", "zzzz"])
def test_missing_and_no_designator_codes_are_not_narratable(code):
    assert not is_narratable_type(code)


@pytest.mark.unit
def test_unlisted_fixed_wing_codes_stay_narratable():
    # Keeps new gaps visible in analytics as "Unknown Aircraft (XXXX)"
    assert is_narratable_type("XY99")
    assert get_aircraft_name("XY99") == "Unknown Aircraft (XY99)"
    assert is_narratable_type("a320")


@pytest.mark.unit
def test_every_helicopter_entry_is_excluded(db):
    helicopters = [code for code, e in db.items() if e.get("category") == "helicopter"]
    assert len(helicopters) >= len(AUDITED_HELICOPTERS)
    assert all(not is_narratable_type(code) for code in helicopters)


@pytest.mark.unit
def test_entry_data_invariants(db):
    for code, entry in db.items():
        assert code == code.strip().upper(), f"{code!r} key is not a normalised ICAO code"
        for field in ("technical_name", "simple_name"):
            assert entry.get(field, "").strip() == entry.get(field), f"{code}.{field} has stray whitespace"
            assert entry.get(field), f"{code} missing {field}"
        # "carrying 1 passengers" - flight_text pluralises unconditionally
        assert entry.get("passenger_capacity", 0) != 1, f"{code} would narrate 'carrying 1 passengers'"
        assert entry.get("category") in (None, "helicopter"), f"{code} has an unknown category"


@pytest.mark.unit
def test_light_aircraft_get_the_small_plane_descriptors():
    # <=50 seats switches the scanner sentence from "mega, massive" to "sleek"
    for code in ("C172", "DA40", "P28A", "CL35", "GL7T"):
        assert 0 < get_passenger_capacity(code) <= 50, code


def _plane(icao, city, *, distance_km=100):
    return {
        "aircraft": get_aircraft_name(icao) if icao else "Unknown Aircraft",
        "aircraft_icao": icao,
        "airline_icao": "DAL",
        "origin_city": "Boston",
        "destination_city": city,
        "destination_airport": city[:3].upper(),
        "destination_country": "United States",
        "distance_km": distance_km,
    }


@pytest.mark.unit
def test_selection_skips_helicopters_and_junk_codes():
    sky = [
        _plane("EC35", "Denver", distance_km=5),
        _plane("ZZZZ", "Austin", distance_km=10),
        _plane(None, "Miami", distance_km=15),
        _plane("", "Seattle", distance_km=20),
        _plane("B738", "Chicago", distance_km=30),
        _plane("CL35", "Houston", distance_km=40),
    ]
    chosen = select_diverse_aircraft(sky, user_lat=None, user_lng=None)
    assert [p["aircraft_icao"] for p in chosen] == ["B738", "CL35"]


@pytest.mark.unit
def test_all_helicopter_sky_narrates_nothing():
    sky = [_plane("A139", "Denver"), _plane("R44", "Austin"), _plane("S76", "Miami")]
    assert select_diverse_aircraft(sky, user_lat=None, user_lng=None) == []
