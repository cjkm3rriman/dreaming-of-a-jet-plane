"""Tests for duplicate destination handling and origin city fun facts"""

import pytest
from app.flight_text import generate_flight_text_for_aircraft


def test_first_destination_uses_destination_fun_facts():
    """Test that the first occurrence uses destination fun facts"""
    used_destinations = set()

    aircraft = {
        "aircraft": "Boeing 737",
        "origin_city": "Boston",
        "origin_country": "United States",
        "destination_city": "New York",
        "destination_country": "United States",
        "distance_km": 300,
    }

    sentence, fun_fact_source = generate_flight_text_for_aircraft(
        aircraft, 40.0, -74.0, plane_index=1, country_code="US", used_destinations=used_destinations
    )

    # First occurrence should use destination (or None if no fun facts found)
    assert fun_fact_source in ("destination", None), f"First plane should use destination, got: {fun_fact_source}"

    # Destination should be tracked
    assert "New York" in used_destinations, "New York should be added to used_destinations"


def test_duplicate_destination_uses_origin_fun_facts(duplicate_destination_aircraft):
    """Test that duplicate destinations trigger origin fun facts"""
    used_destinations = set()

    # First plane to NYC
    aircraft1 = duplicate_destination_aircraft[0]
    sentence1, source1 = generate_flight_text_for_aircraft(
        aircraft1, 40.0, -74.0, plane_index=1, country_code="US", used_destinations=used_destinations
    )

    # Should use destination or None
    assert source1 in ("destination", None)
    assert "New York" in used_destinations

    # Second plane to NYC (duplicate)
    aircraft2 = duplicate_destination_aircraft[1]
    sentence2, source2 = generate_flight_text_for_aircraft(
        aircraft2, 40.0, -74.0, plane_index=2, country_code="US", used_destinations=used_destinations
    )

    # Should use origin for duplicate destination (or None if no fun facts for origin)
    assert source2 in ("origin", None), f"Second plane to NYC should use origin or None, got: {source2}"
    # If None, it means the origin city doesn't have fun facts in the database


def test_third_different_destination_uses_destination_fun_facts(duplicate_destination_aircraft):
    """Test that a different destination after duplicates uses destination fun facts"""
    used_destinations = set()

    # Process all 3 aircraft
    for i, aircraft in enumerate(duplicate_destination_aircraft, start=1):
        sentence, source = generate_flight_text_for_aircraft(
            aircraft, 40.0, -74.0, plane_index=i, country_code="US", used_destinations=used_destinations
        )

    # Third plane goes to Miami (different destination)
    aircraft3 = duplicate_destination_aircraft[2]
    sentence3, source3 = generate_flight_text_for_aircraft(
        aircraft3, 40.0, -74.0, plane_index=3, country_code="US", used_destinations=used_destinations
    )

    # Should use destination for new city
    assert source3 in ("destination", None), f"New destination should use destination, got: {source3}"
    assert "Miami" in used_destinations


def test_all_same_destination_uses_origin_for_later_planes():
    """Test that when all 3 planes go to same destination, only first uses destination fun facts"""
    used_destinations = set()

    # All 3 planes going to New York from different origins
    aircraft_list = [
        {
            "aircraft": "Boeing 737",
            "origin_city": "Boston",
            "origin_country": "United States",
            "destination_city": "New York",
            "destination_country": "United States",
            "distance_km": 300,
        },
        {
            "aircraft": "Airbus A320",
            "origin_city": "Chicago",
            "origin_country": "United States",
            "destination_city": "New York",  # Duplicate
            "destination_country": "United States",
            "distance_km": 500,
        },
        {
            "aircraft": "Boeing 777",
            "origin_city": "Los Angeles",
            "origin_country": "United States",
            "destination_city": "New York",  # Duplicate again
            "destination_country": "United States",
            "distance_km": 700,
        },
    ]

    sources = []
    for i, aircraft in enumerate(aircraft_list, start=1):
        sentence, source = generate_flight_text_for_aircraft(
            aircraft, 40.0, -74.0, plane_index=i, country_code="US", used_destinations=used_destinations
        )
        sources.append(source)

    # First should use destination (or None)
    assert sources[0] in ("destination", None), f"Plane 1 should use destination, got: {sources[0]}"

    # Second and third should use origin (or None if origin has no fun facts)
    assert sources[1] in ("origin", None), f"Plane 2 should use origin or None, got: {sources[1]}"
    assert sources[2] in ("origin", None), f"Plane 3 should use origin or None, got: {sources[2]}"


def test_no_used_destinations_set_means_all_use_destination():
    """Test that without used_destinations tracking, all planes use destination"""
    aircraft = {
        "aircraft": "Boeing 737",
        "origin_city": "Boston",
        "origin_country": "United States",
        "destination_city": "New York",
        "destination_country": "United States",
        "distance_km": 300,
    }

    # Don't pass used_destinations
    sentence1, source1 = generate_flight_text_for_aircraft(
        aircraft, 40.0, -74.0, plane_index=1, country_code="US"
    )

    sentence2, source2 = generate_flight_text_for_aircraft(
        aircraft, 40.0, -74.0, plane_index=2, country_code="US"
    )

    # Both should use destination (or None) since no tracking
    assert source1 in ("destination", None)
    assert source2 in ("destination", None)


def test_duplicate_with_unknown_origin_falls_back_to_destination():
    """Test that when origin is unknown, we fall back to destination even for duplicates"""
    used_destinations = set()

    aircraft_list = [
        {
            "aircraft": "Boeing 737",
            "origin_city": "Boston",
            "origin_country": "United States",
            "destination_city": "New York",
            "destination_country": "United States",
            "distance_km": 300,
        },
        {
            "aircraft": "Airbus A320",
            "origin_city": "an unknown origin",  # Unknown origin
            "origin_country": "an unknown country",
            "destination_city": "New York",  # Duplicate
            "destination_country": "United States",
            "distance_km": 500,
        },
    ]

    # First plane
    sentence1, source1 = generate_flight_text_for_aircraft(
        aircraft_list[0], 40.0, -74.0, plane_index=1, country_code="US", used_destinations=used_destinations
    )

    # Second plane with unknown origin
    sentence2, source2 = generate_flight_text_for_aircraft(
        aircraft_list[1], 40.0, -74.0, plane_index=2, country_code="US", used_destinations=used_destinations
    )

    # Should fall back to destination since origin is unknown
    assert source2 in ("destination", None), f"Should fall back to destination when origin unknown, got: {source2}"


def test_used_destinations_set_is_mutated():
    """Test that the used_destinations set is properly updated"""
    used_destinations = set()
    assert len(used_destinations) == 0

    aircraft1 = {
        "aircraft": "Boeing 737",
        "destination_city": "New York",
        "destination_country": "United States",
        "origin_city": "Boston",
        "origin_country": "United States",
        "distance_km": 300,
    }

    generate_flight_text_for_aircraft(
        aircraft1, 40.0, -74.0, plane_index=1, country_code="US", used_destinations=used_destinations
    )

    assert len(used_destinations) == 1, "Set should have 1 destination"
    assert "New York" in used_destinations

    aircraft2 = {
        "aircraft": "Airbus A320",
        "destination_city": "Los Angeles",
        "destination_country": "United States",
        "origin_city": "Chicago",
        "origin_country": "United States",
        "distance_km": 500,
    }

    generate_flight_text_for_aircraft(
        aircraft2, 40.0, -74.0, plane_index=2, country_code="US", used_destinations=used_destinations
    )

    assert len(used_destinations) == 2, "Set should have 2 destinations"
    assert "Los Angeles" in used_destinations
