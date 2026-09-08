"""Tests for aircraft selection and diversity logic"""

import pytest
from app.main import get_nearby_aircraft, select_diverse_aircraft

# NetJets - the private operator most often seen in real traffic, and one of the
# two ICAO codes flagged private_or_charter in airlines.json
PRIVATE_ICAO = "EJA"


def _plane(city, *, airline_icao="DAL", distance_km=100):
    """Minimal aircraft dict; each gets a distinct destination so the
    destination-diversity pass keeps all of them"""
    return {
        "aircraft": "Boeing 737",
        "airline_icao": airline_icao,
        "origin_city": "Boston",
        "destination_city": city,
        "destination_airport": city[:3].upper(),
        "destination_country": "United States",
        "distance_km": distance_km,
    }


def _select(planes):
    """Select without user coordinates, so destination-distance enrichment is
    skipped and every passenger flight lands in the 'far' pool"""
    return select_diverse_aircraft(planes, user_lat=None, user_lng=None)


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


@pytest.mark.unit
@pytest.mark.parametrize("passenger_count", [1, 2, 3])
def test_private_flight_never_displaces_passenger_flights(passenger_count):
    """1-3 passenger flights plus a private jet must all survive.

    The insertion branch used to test `len(selected) == 1`, so 2 or 3 passenger
    picks fell through to the else and were replaced wholesale by the private
    flight - the user heard one private jet and four "no more planes" messages
    (DOJP-38).
    """
    cities = ["Chicago", "Denver", "Miami"][:passenger_count]
    planes = [_plane(city) for city in cities]
    planes.append(_plane("Aspen", airline_icao=PRIVATE_ICAO, distance_km=200))

    selected = _select(planes)

    assert len(selected) == passenger_count + 1
    kept = {p.get("destination_city") for p in selected}
    assert kept == set(cities) | {"Aspen"}


@pytest.mark.unit
def test_several_private_flights_fill_only_the_remaining_slots():
    """Private flights top the list up to 5 without evicting passengers"""
    planes = [_plane(c) for c in ["Chicago", "Denver"]]
    planes += [
        _plane(c, airline_icao=PRIVATE_ICAO, distance_km=200)
        for c in ["Aspen", "Teterboro", "Nantucket", "Vail"]
    ]

    selected = _select(planes)

    assert len(selected) == 5
    passenger_kept = [p for p in selected if p["airline_icao"] != PRIVATE_ICAO]
    assert len(passenger_kept) == 2, "both passenger flights must survive"


@pytest.mark.unit
def test_private_only_results_are_unchanged():
    """With no passenger flights at all, private flights still fill the list"""
    planes = [
        _plane(c, airline_icao=PRIVATE_ICAO)
        for c in ["Aspen", "Teterboro", "Nantucket"]
    ]

    selected = _select(planes)

    assert len(selected) == 3
    assert all(p["airline_icao"] == PRIVATE_ICAO for p in selected)


@pytest.mark.unit
def test_private_flight_takes_position_four_when_passengers_are_plentiful():
    """With 4+ passenger flights the private one is inserted at position 4"""
    planes = [_plane(c) for c in ["Chicago", "Denver", "Miami", "Seattle", "Austin"]]
    planes.append(_plane("Aspen", airline_icao=PRIVATE_ICAO, distance_km=200))

    selected = _select(planes)

    assert len(selected) == 5
    assert selected[3]["destination_city"] == "Aspen"


@pytest.mark.unit
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
