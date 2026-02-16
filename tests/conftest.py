"""Pytest configuration and shared fixtures for tests"""

import pytest
import asyncio


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
async def _reset_airlabs_client():
    """Reset the Airlabs shared HTTP client after each test.

    The Airlabs provider uses a module-level httpx.AsyncClient for connection
    pooling. When the event loop changes between tests the client's connection
    pool becomes stale, causing 'Event loop is closed' errors. Closing it here
    forces a fresh client on the next test.
    """
    yield
    try:
        from app.aircraft_providers.airlabs import close_client
        await close_client()
    except Exception:
        pass


# Test locations
@pytest.fixture
def nyc_location():
    """New York City coordinates - high traffic, US (imperial units)"""
    return {"lat": 40.7128, "lng": -74.0060, "country_code": "US", "name": "NYC"}


@pytest.fixture
def london_location():
    """London coordinates - international hub (metric units)"""
    return {"lat": 51.5074, "lng": -0.1278, "country_code": "GB", "name": "London"}


@pytest.fixture
def tokyo_location():
    """Tokyo coordinates - Asia-Pacific (metric units)"""
    return {"lat": 35.6762, "lng": 139.6503, "country_code": "JP", "name": "Tokyo"}


@pytest.fixture
def weston_ct_location():
    """Weston, CT coordinates - small town, lower traffic"""
    return {"lat": 41.2220, "lng": -73.3690, "country_code": "US", "name": "Weston CT"}


@pytest.fixture
def sample_aircraft():
    """Sample aircraft data for testing"""
    return {
        "aircraft": "Boeing 737",
        "origin_city": "Boston",
        "origin_country": "United States",
        "origin_airport": "BOS",
        "destination_city": "New York",
        "destination_country": "United States",
        "destination_airport": "JFK",
        "distance_km": 300,
        "velocity": 450,
        "altitude": 35000,
        "flight_number": "AA123",
        "airline_name": "American Airlines",
    }


@pytest.fixture
def sample_aircraft_list():
    """List of diverse sample aircraft for testing"""
    return [
        {
            "aircraft": "Boeing 737",
            "origin_city": "Boston",
            "origin_country": "United States",
            "destination_city": "New York",
            "destination_country": "United States",
            "distance_km": 300,
            "velocity": 450,
            "altitude": 35000,
        },
        {
            "aircraft": "Airbus A320",
            "origin_city": "Chicago",
            "origin_country": "United States",
            "destination_city": "Los Angeles",
            "destination_country": "United States",
            "distance_km": 500,
            "velocity": 470,
            "altitude": 37000,
        },
        {
            "aircraft": "Boeing 787",
            "origin_city": "London",
            "origin_country": "United Kingdom",
            "destination_city": "Dubai",
            "destination_country": "United Arab Emirates",
            "distance_km": 200,
            "velocity": 500,
            "altitude": 41000,
        },
    ]


@pytest.fixture
def duplicate_destination_aircraft():
    """Aircraft with duplicate destinations for testing"""
    return [
        {
            "aircraft": "Boeing 737",
            "origin_city": "Boston",
            "origin_country": "United States",
            "destination_city": "New York",
            "destination_country": "United States",
            "destination_airport": "JFK",
            "distance_km": 300,
        },
        {
            "aircraft": "Airbus A320",
            "origin_city": "Chicago",
            "origin_country": "United States",
            "destination_city": "New York",  # Duplicate
            "destination_country": "United States",
            "destination_airport": "LGA",
            "distance_km": 500,
        },
        {
            "aircraft": "Boeing 777",
            "origin_city": "Atlanta",
            "origin_country": "United States",
            "destination_city": "Miami",  # Different
            "destination_country": "United States",
            "destination_airport": "MIA",
            "distance_km": 400,
        },
    ]
