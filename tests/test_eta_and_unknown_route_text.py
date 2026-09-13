"""Tests for two TTS-audible text defects (DOJP-40)

1. The both-endpoints-unknown template carried a stray apostrophe before the
   period and a capitalized "It" mid-sentence - TTS read the garble out loud.
2. Every flight over 12 hours was described as "a whole day and night", so a
   13-hour flight got a 24-hour comparison, and a ~12.2-hour flight rendered
   "about 12 hours" with day-and-night copy duplicating the 12-hour bucket.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.flight_text import generate_flight_text_for_aircraft


def _aircraft(eta_hours=None, **overrides):
    plane = {
        "aircraft": "Boeing 777",
        "airline_name": "Delta Air Lines",
        "flight_number": "DL100",
        "origin_city": "New York City",
        "origin_country": "United States",
        "destination_city": "Tokyo",
        "destination_country": "Japan",
        "distance_km": 20,
        "velocity": 480,
        "altitude": 36000,
    }
    if eta_hours is not None:
        eta = datetime.now(timezone.utc) + timedelta(hours=eta_hours)
        plane["eta"] = eta.isoformat().replace("+00:00", "Z")
    plane.update(overrides)
    return plane


def _text(plane):
    sentence, _ = generate_flight_text_for_aircraft(plane, 40.7, -74.0, 1, "US", set())
    return sentence


@pytest.mark.unit
def test_unknown_route_sentence_is_clean():
    """No stray apostrophe, no mid-sentence capital It"""
    plane = _aircraft(
        origin_city=None, origin_country=None,
        destination_city=None, destination_country=None,
    )
    text = _text(plane)

    assert "somewhere exciting, it is not quite clear." in text
    assert "'." not in text
    assert ", It " not in text


@pytest.mark.unit
def test_13_hour_flight_is_not_a_whole_day_and_night():
    """The case from the ticket: a 13-hour flight got a 24-hour comparison"""
    text = _text(_aircraft(eta_hours=13))

    assert "about 13 hours" in text
    assert "whole day and night" not in text


@pytest.mark.unit
def test_12_point_2_hour_flight_no_longer_duplicates_the_12_hour_bucket():
    """~732 minutes rounds to 12 hours; it used to say 'about 12 hours' with
    day-and-night copy, clashing with the <=720-minute bucket's phrasing"""
    text = _text(_aircraft(eta_hours=12.2))

    assert "about 12 hours" in text
    assert "whole day and night" not in text


@pytest.mark.unit
def test_22_hour_flight_still_gets_the_day_and_night_scale():
    """The long end of the bucket keeps a day-scale comparison"""
    text = _text(_aircraft(eta_hours=22))

    assert "about 22 hours" in text
    assert ("whole day and night" in text) or ("spin of the Earth" in text)


@pytest.mark.unit
def test_over_24_hours_still_lands_sometime_tomorrow():
    text = _text(_aircraft(eta_hours=27))
    assert "landing sometime tomorrow" in text


@pytest.mark.unit
def test_12_hour_bucket_itself_is_unchanged():
    """The <=720-minute branch keeps its existing copy"""
    text = _text(_aircraft(eta_hours=11.5))
    assert "about 12 hours" in text
