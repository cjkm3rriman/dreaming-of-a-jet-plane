"""Tests for flight text generation with units and content validation"""

import pytest
from app.flight_text import generate_flight_text_for_aircraft, generate_flight_text


def test_text_generation_imperial_units(sample_aircraft):
    """Test flight text uses miles for US location"""
    sentence, fun_fact_source = generate_flight_text_for_aircraft(
        sample_aircraft, 40.7128, -74.0060, plane_index=1, country_code="US"
    )

    # Check units
    assert "miles" in sentence, "Should use miles for US"
    assert "kilometers" not in sentence, "Should not use kilometers for US"

    # Check it's a string and has content
    assert isinstance(sentence, str)
    assert len(sentence) > 50, "Sentence should be substantial"


def test_text_generation_metric_units(sample_aircraft):
    """Test flight text uses kilometers for France location"""
    # Modify aircraft to use European cities
    aircraft = sample_aircraft.copy()
    aircraft.update({
        "origin_city": "London",
        "origin_country": "United Kingdom",
        "destination_city": "Paris",
        "destination_country": "France",
    })

    sentence, fun_fact_source = generate_flight_text_for_aircraft(
        aircraft, 48.8566, 2.3522, plane_index=1, country_code="FR"
    )

    # Check units
    assert "kilometers" in sentence or "kilometres" in sentence, "Should use kilometers for France"
    assert "miles" not in sentence, "Should not use miles for France"


def test_text_generation_japanese_metric(sample_aircraft):
    """Test flight text uses kilometers for Japan"""
    sentence, fun_fact_source = generate_flight_text_for_aircraft(
        sample_aircraft, 35.6762, 139.6503, plane_index=1, country_code="JP"
    )

    # Check units
    assert "kilometers" in sentence or "kilometres" in sentence, "Should use kilometers for JP"


def test_text_includes_aircraft_name(sample_aircraft):
    """Test that generated text includes aircraft name with digits as words"""
    sentence, _ = generate_flight_text_for_aircraft(
        sample_aircraft, 40.0, -74.0, plane_index=1, country_code="US"
    )

    # Boeing 737 should become "Boeing seven three seven"
    assert "Boeing seven three seven" in sentence, "Should spell out aircraft number digits as words"


def test_text_includes_origin_and_destination(sample_aircraft):
    """Test that text mentions origin and destination cities"""
    sentence, _ = generate_flight_text_for_aircraft(
        sample_aircraft, 40.0, -74.0, plane_index=1, country_code="US"
    )

    assert "Boston" in sentence, "Should mention origin city"
    assert "New York" in sentence, "Should mention destination city"


def test_text_has_opening_phrase(sample_aircraft):
    """Test that text starts with one of the expected opening phrases"""
    sentence, _ = generate_flight_text_for_aircraft(
        sample_aircraft, 40.0, -74.0, plane_index=1, country_code="US"
    )

    opening_words = ["Marvelous!", "Good Heavens!", "Fantastic!", "Splendid!", "What Luck!", "Wow!"]
    assert any(sentence.startswith(word) for word in opening_words), f"Should start with opening phrase, got: {sentence[:20]}"


def test_text_has_closing_prompt_plane1(sample_aircraft):
    """Test that plane 1 has correct closing prompt"""
    sentence, _ = generate_flight_text_for_aircraft(
        sample_aircraft, 40.0, -74.0, plane_index=1, country_code="US"
    )

    assert "Should we find another jet plane?" in sentence, "Plane 1 should ask about finding another"


def test_text_has_closing_prompt_plane2(sample_aircraft):
    """Test that plane 2 has correct closing prompt"""
    sentence, _ = generate_flight_text_for_aircraft(
        sample_aircraft, 40.0, -74.0, plane_index=2, country_code="US"
    )

    assert "Let's find one more jet plane shall we?" in sentence, "Plane 2 should suggest one more"


def test_text_no_closing_prompt_plane3(sample_aircraft):
    """Test that plane 3 has no closing prompt"""
    sentence, _ = generate_flight_text_for_aircraft(
        sample_aircraft, 40.0, -74.0, plane_index=3, country_code="US"
    )

    assert "Should we find another" not in sentence, "Plane 3 should not ask for another"
    assert "Let's find one more" not in sentence, "Plane 3 should not suggest one more"


def test_fun_fact_source_is_tracked(sample_aircraft):
    """Test that fun_fact_source is returned"""
    sentence, fun_fact_source = generate_flight_text_for_aircraft(
        sample_aircraft, 40.0, -74.0, plane_index=1, country_code="US"
    )

    # fun_fact_source should be "destination", "origin", or None
    assert fun_fact_source in ("destination", "origin", None), f"Invalid fun_fact_source: {fun_fact_source}"


def test_private_jet_text():
    """Test that private jets show 'private jet' instead of flight number"""
    aircraft = {
        "aircraft": "Cessna Citation",
        "origin_city": "Boston",
        "origin_country": "United States",
        "destination_city": "New York",
        "destination_country": "United States",
        "distance_km": 300,
        "airline_name": "NetJets",
        "flight_number": "N123AB",
        "is_private_operator": True,
    }

    sentence, _ = generate_flight_text_for_aircraft(
        aircraft, 40.0, -74.0, plane_index=1, country_code="US"
    )

    assert "private jet" in sentence, "Should mention 'private jet'"
    # Should not spell out the tail number as a flight number
    assert "flight N 1 2 3 A B" not in sentence, "Should not spell out tail number"


def test_error_message_generation():
    """Test generate_flight_text with no aircraft (error case)"""
    sentence = generate_flight_text(
        [],
        error_message="No aircraft providers configured",
        user_lat=40.0,
        user_lng=-74.0,
        country_code="US"
    )

    # Should return a friendly error message
    assert isinstance(sentence, str)
    assert len(sentence) > 0
    assert "scanner bot" in sentence.lower() or "error" in sentence.lower() or "sorry" in sentence.lower()


def test_text_generation_returns_tuple(sample_aircraft):
    """Test that generate_flight_text_for_aircraft returns a tuple"""
    result = generate_flight_text_for_aircraft(
        sample_aircraft, 40.0, -74.0, plane_index=1, country_code="US"
    )

    assert isinstance(result, tuple), "Should return tuple"
    assert len(result) == 2, "Should return 2-element tuple (sentence, fun_fact_source)"


def test_unknown_origin_destination_handling():
    """Test graceful handling of unknown origin/destination"""
    aircraft = {
        "aircraft": "Boeing 737",
        "origin_city": "an unknown origin",
        "origin_country": "an unknown country",
        "destination_city": "an unknown destination",
        "destination_country": "an unknown country",
        "distance_km": 300,
    }

    sentence, fun_fact_source = generate_flight_text_for_aircraft(
        aircraft, 40.0, -74.0, plane_index=1, country_code="US"
    )

    # Should still generate text
    assert isinstance(sentence, str)
    assert len(sentence) > 0

    # Should not have fun facts for unknown destinations
    assert fun_fact_source is None, "Should not have fun facts for unknown destination"
