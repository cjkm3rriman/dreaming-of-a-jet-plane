"""Tests for deterministic fun fact rotation (DOJP-28)

Facts used to be chosen with random.choice, so a listener could hear the same
one twice in a row. Rotation replaces that with a clock-derived counter: the
fact changes every few minutes, cycles the whole list before repeating, and is
reproducible from its inputs.

The counter has to advance *within* a day as well as across days — a family
scanning morning and evening is the case that motivated this — so these tests
pin both axes.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.flight_text import FUN_FACT_ROTATION_SECONDS, select_rotating_fun_fact

CITIES_PATH = Path(__file__).parent.parent / "app" / "cities.json"

FACTS = ["fact one", "fact two", "fact three", "fact four", "fact five"]
MORNING = datetime(2026, 9, 7, 9, 0, tzinfo=timezone.utc)


def _database_fact_counts() -> set:
    """Distinct fun-fact list lengths present in cities.json"""
    cities = json.loads(CITIES_PATH.read_text())
    counts = {
        len(entry.get("fun_facts", []))
        for entry in cities.values()
        if isinstance(entry, dict) and entry.get("fun_facts")
    }
    assert counts, "expected at least one city with facts"
    return counts


@pytest.mark.unit
def test_same_moment_gives_same_fact():
    """Selection is deterministic: identical inputs, identical output"""
    first = select_rotating_fun_fact(FACTS, plane_index=1, now=MORNING)
    second = select_rotating_fun_fact(FACTS, plane_index=1, now=MORNING)
    assert first == second


@pytest.mark.unit
@pytest.mark.parametrize("gap_hours", [1, 2, 3, 4, 8, 12])
def test_rescan_later_the_same_day_gives_a_different_fact(gap_hours):
    """The case that motivated the amendment: scanning again hours later.

    A daily-only rotation would return the identical fact for every gap here.
    Note this is not a universal guarantee - with a 25-minute cycle for a
    5-fact city, gaps that are an exact multiple of it (5h, 10h) still land on
    the same fact. No memoryless scheme can do better than 1/len for an
    arbitrary gap; the bucket size is chosen so the colliding gaps are the
    unusual ones rather than every round half-hour.
    """
    later = MORNING + timedelta(hours=gap_hours)
    assert select_rotating_fun_fact(FACTS, 1, MORNING) != select_rotating_fun_fact(FACTS, 1, later)


@pytest.mark.unit
def test_rotation_advances_once_per_bucket():
    """One bucket later is always the next fact in the list"""
    later = MORNING + timedelta(seconds=FUN_FACT_ROTATION_SECONDS)
    first = FACTS.index(select_rotating_fun_fact(FACTS, 1, MORNING))
    second = FACTS.index(select_rotating_fun_fact(FACTS, 1, later))
    assert second == (first + 1) % len(FACTS)


@pytest.mark.unit
def test_full_list_cycles_before_repeating():
    """Consecutive buckets visit every fact exactly once before wrapping"""
    seen = [
        select_rotating_fun_fact(FACTS, 1, MORNING + timedelta(seconds=FUN_FACT_ROTATION_SECONDS * i))
        for i in range(len(FACTS))
    ]
    assert sorted(seen) == sorted(FACTS)


@pytest.mark.unit
def test_consecutive_days_at_the_same_time_differ():
    """Same city, same clock time, next day - must not repeat"""
    tomorrow = MORNING + timedelta(days=1)
    assert select_rotating_fun_fact(FACTS, 1, MORNING) != select_rotating_fun_fact(FACTS, 1, tomorrow)


@pytest.mark.unit
def test_planes_to_the_same_city_in_one_scan_differ():
    """The plane_index offset separates two planes sharing a destination"""
    assert select_rotating_fun_fact(FACTS, 1, MORNING) != select_rotating_fun_fact(FACTS, 2, MORNING)


@pytest.mark.unit
def test_no_facts_returns_none():
    """Cities with no facts must not blow up the selector"""
    assert select_rotating_fun_fact([], 1, MORNING) is None


@pytest.mark.unit
def test_single_fact_city_is_stable():
    """A one-fact city has nothing to rotate through"""
    assert select_rotating_fun_fact(["only fact"], 1, MORNING) == "only fact"


@pytest.mark.unit
def test_no_daily_aliasing_for_fact_counts_in_the_database():
    """A day advances the counter by 86400/FUN_FACT_ROTATION_SECONDS + 1 steps.
    That number must share no factor with a city's fact count, or the city lands
    on the same fact at the same time every single day - the exact bug rotation
    exists to prevent. This test fails if FUN_FACT_ROTATION_SECONDS is retuned to
    a value without that property (10 minutes gives 145 = 5 x 29, and 5 is the
    fact count of most of the database).
    """
    tomorrow = MORNING + timedelta(days=1)

    for count in sorted(_database_fact_counts()):
        if count == 1:
            continue  # nothing to rotate through
        facts = [f"fact {i}" for i in range(count)]
        assert select_rotating_fun_fact(facts, 1, MORNING) != select_rotating_fun_fact(facts, 1, tomorrow), \
            f"cities with {count} facts repeat at the same time each day"


@pytest.mark.unit
def test_no_city_has_a_fact_count_that_breaks_rotation():
    """The 5-minute bucket gives 289 = 17^2 steps a day, so a city with a
    multiple of 17 facts would hear the same fact at the same time every day.
    Nothing is near that today; this guards a city being expanded into it.
    """
    steps_per_day = 86400 // FUN_FACT_ROTATION_SECONDS + 1
    for count in _database_fact_counts():
        if count == 1:
            continue  # a single-fact city repeats under any scheme
        assert steps_per_day % count != 0, \
            f"a city with {count} facts aliases against the {steps_per_day}-step day"
