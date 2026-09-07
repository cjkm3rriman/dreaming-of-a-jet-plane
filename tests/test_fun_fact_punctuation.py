"""Tests for fun fact punctuation invariants in cities.json

`generate_flight_text_for_aircraft` uses each fact verbatim, appending nothing.
That relies on every fact in the database carrying its own terminal punctuation.
These tests enforce that invariant so a newly added fact cannot silently ship
without one — or with a doubled terminator, which TTS renders as an odd pause.
"""

import json
from pathlib import Path

import pytest

from app.cities_database import get_fun_facts
from app.flight_text import generate_flight_text_for_aircraft

CITIES_PATH = Path(__file__).parent.parent / "app" / "cities.json"


def _all_facts():
    """Yield (city, index, fact) for every fun fact in the database"""
    cities = json.loads(CITIES_PATH.read_text())
    for key, entry in cities.items():
        if not isinstance(entry, dict):
            continue
        city = entry.get("city", key)
        for i, fact in enumerate(entry.get("fun_facts", [])):
            yield city, i, fact


@pytest.mark.unit
def test_every_fun_fact_ends_with_exclamation():
    """Every fact ends with '!' so the code never needs to append a terminator"""
    offenders = [
        f"{city} [fun_facts[{i}]]: ...{fact.strip()[-40:]!r}"
        for city, i, fact in _all_facts()
        if not fact.strip().endswith("!")
    ]
    assert not offenders, (
        "Fun facts must end with '!' (house style, and the code appends nothing). "
        f"{len(offenders)} offender(s):\n" + "\n".join(offenders[:10])
    )


@pytest.mark.unit
def test_no_fun_fact_has_surrounding_whitespace():
    """Leading/trailing whitespace would survive into the TTS text and cache key"""
    offenders = [
        f"{city} [fun_facts[{i}]]: {fact!r}"
        for city, i, fact in _all_facts()
        if fact != fact.strip()
    ]
    assert not offenders, "Fun facts must not have surrounding whitespace:\n" + "\n".join(offenders[:10])


@pytest.mark.unit
def test_generated_fun_fact_has_no_doubled_terminator(sample_aircraft):
    """The assembled fun fact segment must not end in '!.' or '?.' or '..'"""
    # Use a destination with known facts so the fun fact branch is exercised
    facts = get_fun_facts("Lisbon", country="Portugal")
    assert facts, "Expected Lisbon to have fun facts for this test to be meaningful"

    aircraft = dict(sample_aircraft)
    aircraft["destination_city"] = "Lisbon"
    aircraft["destination_country"] = "Portugal"
    aircraft["destination_airport"] = "LIS"

    for _ in range(25):  # text generation is randomised; sample repeatedly
        _, _, _, fun_fact_body, source = generate_flight_text_for_aircraft(
            aircraft, 40.7128, -74.0060, plane_index=1, country_code="US", split_text=True
        )
        if not fun_fact_body:
            continue
        assert source == "destination"
        assert not fun_fact_body.endswith(("!.", "?.", "..")), (
            f"Doubled terminator in generated fun fact: ...{fun_fact_body[-30:]!r}"
        )
