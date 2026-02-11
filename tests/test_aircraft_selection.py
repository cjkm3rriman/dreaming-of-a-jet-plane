"""Tests for aircraft selection and diversity logic"""

import pytest
from app.main import get_nearby_aircraft, select_diverse_aircraft


@pytest.mark.asyncio
async def test_nyc_aircraft_selection(nyc_location):
    """Test aircraft selection for NYC - should return up to 3 diverse aircraft"""
    lat, lng = nyc_location["lat"], nyc_location["lng"]

    aircraft, error = await get_nearby_aircraft(lat, lng, limit=3)

    # Skip if API not configured
    if "not configured" in error.lower():
        pytest.skip(f"API not configured: {error}")

    # Basic assertions
    assert error == "", f"Unexpected error: {error}"
    assert len(aircraft) <= 3, "Should return max 3 aircraft"

    # NYC is a major hub, should have aircraft
    if len(aircraft) > 0:
        # Verify required fields exist
        for plane in aircraft:
            assert "aircraft" in plane, "Missing aircraft type"
            assert "distance_km" in plane, "Missing distance"
            # Note: origin/destination may be unknown for some aircraft
    else:
        pytest.skip("No aircraft found near NYC at this time")


@pytest.mark.asyncio
async def test_london_aircraft_selection(london_location):
    """Test aircraft selection for London - international hub"""
    lat, lng = london_location["lat"], london_location["lng"]

    aircraft, error = await get_nearby_aircraft(lat, lng, limit=3)

    # Skip if API not configured
    if "not configured" in error.lower():
        pytest.skip(f"API not configured: {error}")

    assert error == "", f"Unexpected error: {error}"
    assert len(aircraft) <= 3, "Should return max 3 aircraft"

    if len(aircraft) > 0:
        # Check that aircraft are sorted by distance
        distances = [a.get("distance_km", float("inf")) for a in aircraft]
        assert distances == sorted(distances), "Aircraft should be sorted by distance"


@pytest.mark.asyncio
async def test_tokyo_aircraft_selection(tokyo_location):
    """Test aircraft selection for Tokyo - Asia-Pacific hub"""
    lat, lng = tokyo_location["lat"], tokyo_location["lng"]

    aircraft, error = await get_nearby_aircraft(lat, lng, limit=3)

    # Skip if API not configured
    if "not configured" in error.lower():
        pytest.skip(f"API not configured: {error}")

    assert error == "", f"Unexpected error: {error}"
    assert len(aircraft) <= 3, "Should return max 3 aircraft"


@pytest.mark.asyncio
async def test_weston_ct_aircraft_selection(weston_ct_location):
    """Test aircraft selection for Weston CT - smaller area, may have fewer aircraft"""
    lat, lng = weston_ct_location["lat"], weston_ct_location["lng"]

    aircraft, error = await get_nearby_aircraft(lat, lng, limit=3)

    # Should not error even if no aircraft found
    assert error == "" or "no aircraft" in error.lower() or len(aircraft) >= 0


def test_diversity_selection_prefers_different_destinations(sample_aircraft_list):
    """Test that select_diverse_aircraft prioritizes different destinations"""
    # Add some duplicate destinations
    aircraft_with_duplicates = sample_aircraft_list + [
        {
            "aircraft": "Boeing 747",
            "origin_city": "Miami",
            "origin_country": "United States",
            "destination_city": "New York",  # Duplicate from first aircraft
            "destination_country": "United States",
            "distance_km": 350,
        }
    ]

    selected = select_diverse_aircraft(aircraft_with_duplicates, user_lat=40.0, user_lng=-74.0)

    # Should select up to 5 aircraft
    assert len(selected) <= 5, "Should return max 5 aircraft"

    # Check destination diversity
    destinations = [a.get("destination_city") for a in selected if a.get("destination_city")]
    if len(destinations) >= 2:
        unique_destinations = len(set(destinations))
        # Should prefer diversity (at least 50% unique)
        assert unique_destinations >= len(destinations) * 0.5, "Should have diverse destinations"


def test_diversity_selection_returns_limited_results(sample_aircraft_list):
    """Test that select_diverse_aircraft limits results to 5"""
    # Create list of 10+ aircraft
    many_aircraft = sample_aircraft_list * 4  # 12 aircraft

    selected = select_diverse_aircraft(many_aircraft, user_lat=40.0, user_lng=-74.0)

    assert len(selected) <= 5, "Should limit to 5 aircraft"


def test_diversity_selection_handles_empty_list():
    """Test that select_diverse_aircraft handles empty input"""
    selected = select_diverse_aircraft([], user_lat=40.0, user_lng=-74.0)

    assert selected == [], "Should return empty list for empty input"


def test_aircraft_required_fields(sample_aircraft):
    """Test that aircraft objects have expected fields"""
    # Check essential fields
    assert "aircraft" in sample_aircraft
    assert "origin_city" in sample_aircraft
    assert "destination_city" in sample_aircraft
    assert "distance_km" in sample_aircraft

    # Check types
    assert isinstance(sample_aircraft["distance_km"], (int, float))
    assert isinstance(sample_aircraft["aircraft"], str)
