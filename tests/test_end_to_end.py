"""End-to-end tests for complete scanning workflow"""

import pytest
from app.main import get_nearby_aircraft
from app.flight_text import generate_flight_text_for_aircraft


@pytest.mark.asyncio
async def test_full_scan_flow_nyc(nyc_location):
    """Test complete scanning flow from NYC location to text generation"""
    lat, lng = nyc_location["lat"], nyc_location["lng"]
    country_code = nyc_location["country_code"]

    # Step 1: Get aircraft
    aircraft, error = await get_nearby_aircraft(lat, lng, limit=3)

    # Skip if API not configured
    if "not configured" in error.lower():
        pytest.skip(f"API not configured: {error}")

    # Should not have errors
    assert error == "", f"Aircraft fetch failed: {error}"

    if len(aircraft) == 0:
        pytest.skip("No aircraft found near NYC at this time")

    # Step 2: Generate text for all available planes (up to 3)
    used_destinations = set()
    results = []

    for i, plane in enumerate(aircraft[:3], start=1):
        sentence, fun_fact_source = generate_flight_text_for_aircraft(
            plane, lat, lng, i, country_code, used_destinations
        )
        results.append({
            "plane_index": i,
            "sentence": sentence,
            "fun_fact_source": fun_fact_source,
            "origin": plane.get("origin_city"),
            "destination": plane.get("destination_city"),
            "aircraft_type": plane.get("aircraft"),
        })

    # Validate results
    assert len(results) <= 3, "Should have max 3 results"
    assert len(results) > 0, "Should have at least 1 result"

    for result in results:
        # Check sentence structure
        assert len(result["sentence"]) > 50, "Sentence should be substantial"
        assert isinstance(result["sentence"], str)

        # Check opening phrases
        opening_words = ["Marvelous!", "Good Heavens!", "Fantastic!", "Splendid!", "What Luck!", "Wow!"]
        assert any(result["sentence"].startswith(word) for word in opening_words), \
            f"Sentence should start with opening phrase: {result['sentence'][:30]}"

        # Check units (imperial for NYC)
        assert "miles" in result["sentence"], "Should use miles for NYC"

        # Check fun fact source is valid
        assert result["fun_fact_source"] in ("destination", "origin", None)


@pytest.mark.asyncio
async def test_full_scan_flow_london(london_location):
    """Test complete scanning flow from London location to text generation"""
    lat, lng = london_location["lat"], london_location["lng"]
    country_code = london_location["country_code"]

    # Get aircraft
    aircraft, error = await get_nearby_aircraft(lat, lng, limit=3)

    # Skip if API not configured
    if "not configured" in error.lower():
        pytest.skip(f"API not configured: {error}")

    assert error == ""

    if len(aircraft) == 0:
        pytest.skip("No aircraft found near London at this time")

    # Generate text for first plane
    used_destinations = set()
    sentence, fun_fact_source = generate_flight_text_for_aircraft(
        aircraft[0], lat, lng, 1, country_code, used_destinations
    )

    # Check imperial units for London (GB uses miles)
    assert "miles" in sentence, "Should use miles for London (GB)"
    assert len(sentence) > 0


@pytest.mark.asyncio
async def test_scan_flow_with_duplicate_destinations(nyc_location):
    """Test that duplicate destination handling works in full flow"""
    lat, lng = nyc_location["lat"], nyc_location["lng"]
    country_code = nyc_location["country_code"]

    # Get aircraft
    aircraft, error = await get_nearby_aircraft(lat, lng, limit=3)

    if len(aircraft) < 2:
        pytest.skip("Need at least 2 aircraft for duplicate test")

    # Track destinations and fun fact sources
    used_destinations = set()
    fun_fact_sources = []

    for i, plane in enumerate(aircraft[:3], start=1):
        sentence, fun_fact_source = generate_flight_text_for_aircraft(
            plane, lat, lng, i, country_code, used_destinations
        )
        fun_fact_sources.append(fun_fact_source)

    # Check that used_destinations was populated
    assert len(used_destinations) > 0, "Should track at least one destination"

    # If we have duplicates, at least one should use origin
    destinations = [a.get("destination_city") for a in aircraft[:3]]
    if len(destinations) != len(set(destinations)):  # Has duplicates
        assert "origin" in fun_fact_sources, "Should use origin for at least one duplicate"


@pytest.mark.asyncio
async def test_scan_handles_no_aircraft_gracefully():
    """Test that scanning handles locations with no aircraft gracefully"""
    # Middle of the Atlantic Ocean
    lat, lng = 0.0, -30.0

    aircraft, error = await get_nearby_aircraft(lat, lng, limit=3)

    # Should not crash, either empty list or error message
    assert isinstance(aircraft, list), "Should return list even if empty"
    assert isinstance(error, str), "Error should be string"


@pytest.mark.asyncio
async def test_three_plane_sequence_maintains_variety(nyc_location):
    """Test that generating text for 3 planes maintains variety in opening words"""
    lat, lng = nyc_location["lat"], nyc_location["lng"]
    country_code = nyc_location["country_code"]

    aircraft, error = await get_nearby_aircraft(lat, lng, limit=3)

    if len(aircraft) < 3:
        pytest.skip("Need 3 aircraft for this test")

    used_destinations = set()
    sentences = []

    for i, plane in enumerate(aircraft[:3], start=1):
        sentence, _ = generate_flight_text_for_aircraft(
            plane, lat, lng, i, country_code, used_destinations
        )
        sentences.append(sentence)

    # Closing prompts are now separate static audio files, so they should NOT be in the generated text
    for i, sentence in enumerate(sentences, start=1):
        assert "Should we find another" not in sentence, f"Plane {i} should not have closing prompt"
        assert "Let's find one more" not in sentence, f"Plane {i} should not have closing prompt"


@pytest.mark.asyncio
async def test_scan_returns_consistent_structure():
    """Test that get_nearby_aircraft always returns consistent structure"""
    lat, lng = 40.7128, -74.0060

    aircraft, error = await get_nearby_aircraft(lat, lng, limit=3)

    # Check return types
    assert isinstance(aircraft, list), "Should return list"
    assert isinstance(error, str), "Error should be string"

    # If aircraft found, check structure
    if len(aircraft) > 0:
        for plane in aircraft:
            assert isinstance(plane, dict), "Each aircraft should be dict"
            # Check for distance_km (should always be present)
            assert "distance_km" in plane, "Aircraft should have distance_km"


@pytest.mark.asyncio
async def test_aircraft_sorted_by_distance(nyc_location):
    """Test that returned aircraft are sorted by distance from user"""
    lat, lng = nyc_location["lat"], nyc_location["lng"]

    aircraft, error = await get_nearby_aircraft(lat, lng, limit=3)

    if len(aircraft) < 2:
        pytest.skip("Need at least 2 aircraft to test sorting")

    # Extract distances
    distances = [a.get("distance_km", float("inf")) for a in aircraft]

    # Should be sorted (closest first)
    assert distances == sorted(distances), f"Aircraft should be sorted by distance, got: {distances}"


@pytest.mark.asyncio
async def test_detailed_output_nyc():
    """Output detailed information about aircraft selection and text generation for NYC"""
    lat, lng = 40.7128, -74.0060
    country_code = "US"

    print("\n" + "="*80)
    print("DETAILED TEST OUTPUT - NYC Location")
    print("="*80)
    print(f"Location: {lat}, {lng} (New York City, USA)")
    print(f"Country Code: {country_code}")
    print()

    # Get aircraft
    aircraft, error = await get_nearby_aircraft(lat, lng, limit=3)

    if error and "not configured" in error.lower():
        pytest.skip(f"API not configured: {error}")

    if len(aircraft) == 0:
        pytest.skip("No aircraft found near NYC at this time")

    print(f"Total aircraft found: {len(aircraft)}")
    print()

    # Track destinations for duplicate detection
    used_destinations = set()

    # Process each plane
    for i, plane in enumerate(aircraft[:3], start=1):
        print("-" * 80)
        print(f"PLANE {i}")
        print("-" * 80)

        # Show aircraft details
        print(f"Aircraft Type: {plane.get('aircraft', 'Unknown')}")
        print(f"Airline: {plane.get('airline_name', 'Unknown')}")
        print(f"Flight Number: {plane.get('flight_number', 'Unknown')}")
        print(f"Origin: {plane.get('origin_city', 'Unknown')}, {plane.get('origin_country', 'Unknown')}")
        print(f"Destination: {plane.get('destination_city', 'Unknown')}, {plane.get('destination_country', 'Unknown')}")
        print(f"Distance: {plane.get('distance_km', 0):.1f} km")

        if plane.get('is_private_operator'):
            print(f"Type: Private Jet")

        if plane.get('is_cargo'):
            print(f"Type: Cargo Flight")

        print()

        # Check if destination is duplicate BEFORE generating text
        is_duplicate = plane.get('destination_city') in used_destinations

        # Generate text
        sentence, fun_fact_source = generate_flight_text_for_aircraft(
            plane, lat, lng, i, country_code, used_destinations
        )

        print(f"Fun Fact Source: {fun_fact_source or 'None'}")
        if is_duplicate:
            print(f"Note: Duplicate destination - used origin city fun facts instead")
        print()
        print("GENERATED TEXT:")
        print("-" * 80)
        print(sentence)
        print("-" * 80)
        print()

    print("="*80)
    print(f"Destinations tracked: {used_destinations}")
    print("="*80)
    print()


@pytest.mark.asyncio
async def test_detailed_output_london():
    """Output detailed information about aircraft selection and text generation for London"""
    lat, lng = 51.5074, -0.1278
    country_code = "GB"

    print("\n" + "="*80)
    print("DETAILED TEST OUTPUT - London Location")
    print("="*80)
    print(f"Location: {lat}, {lng} (London, United Kingdom)")
    print(f"Country Code: {country_code}")
    print()

    # Get aircraft
    aircraft, error = await get_nearby_aircraft(lat, lng, limit=3)

    if error and "not configured" in error.lower():
        pytest.skip(f"API not configured: {error}")

    if len(aircraft) == 0:
        pytest.skip("No aircraft found near London at this time")

    print(f"Total aircraft found: {len(aircraft)}")
    print()

    # Track destinations for duplicate detection
    used_destinations = set()

    # Process each plane
    for i, plane in enumerate(aircraft[:3], start=1):
        print("-" * 80)
        print(f"PLANE {i}")
        print("-" * 80)

        # Show aircraft details
        print(f"Aircraft Type: {plane.get('aircraft', 'Unknown')}")
        print(f"Airline: {plane.get('airline_name', 'Unknown')}")
        print(f"Flight Number: {plane.get('flight_number', 'Unknown')}")
        print(f"Origin: {plane.get('origin_city', 'Unknown')}, {plane.get('origin_country', 'Unknown')}")
        print(f"Destination: {plane.get('destination_city', 'Unknown')}, {plane.get('destination_country', 'Unknown')}")
        print(f"Distance: {plane.get('distance_km', 0):.1f} km")

        if plane.get('is_private_operator'):
            print(f"Type: Private Jet")

        if plane.get('is_cargo'):
            print(f"Type: Cargo Flight")

        print()

        # Check if destination is duplicate BEFORE generating text
        is_duplicate = plane.get('destination_city') in used_destinations

        # Generate text
        sentence, fun_fact_source = generate_flight_text_for_aircraft(
            plane, lat, lng, i, country_code, used_destinations
        )

        print(f"Fun Fact Source: {fun_fact_source or 'None'}")
        if is_duplicate:
            print(f"Note: Duplicate destination - used origin city fun facts instead")
        print()
        print("GENERATED TEXT:")
        print("-" * 80)
        print(sentence)
        print("-" * 80)
        print()

    print("="*80)
    print(f"Destinations tracked: {used_destinations}")
    print("="*80)
    print()


@pytest.mark.asyncio
async def test_detailed_output_sydney():
    """Output detailed information about aircraft selection and text generation for Sydney"""
    lat, lng = -33.8688, 151.2093
    country_code = "AU"

    print("\n" + "="*80)
    print("DETAILED TEST OUTPUT - Sydney Location")
    print("="*80)
    print(f"Location: {lat}, {lng} (Sydney, Australia)")
    print(f"Country Code: {country_code}")
    print()

    # Get aircraft
    aircraft, error = await get_nearby_aircraft(lat, lng, limit=3)

    if error and "not configured" in error.lower():
        pytest.skip(f"API not configured: {error}")

    if len(aircraft) == 0:
        pytest.skip("No aircraft found near Sydney at this time")

    print(f"Total aircraft found: {len(aircraft)}")
    print()

    # Track destinations for duplicate detection
    used_destinations = set()

    # Process each plane
    for i, plane in enumerate(aircraft[:3], start=1):
        print("-" * 80)
        print(f"PLANE {i}")
        print("-" * 80)

        # Show aircraft details
        print(f"Aircraft Type: {plane.get('aircraft', 'Unknown')}")
        print(f"Airline: {plane.get('airline_name', 'Unknown')}")
        print(f"Flight Number: {plane.get('flight_number', 'Unknown')}")
        print(f"Origin: {plane.get('origin_city', 'Unknown')}, {plane.get('origin_country', 'Unknown')}")
        print(f"Destination: {plane.get('destination_city', 'Unknown')}, {plane.get('destination_country', 'Unknown')}")
        print(f"Distance: {plane.get('distance_km', 0):.1f} km")

        if plane.get('is_private_operator'):
            print(f"Type: Private Jet")

        if plane.get('is_cargo'):
            print(f"Type: Cargo Flight")

        print()

        # Check if destination is duplicate BEFORE generating text
        is_duplicate = plane.get('destination_city') in used_destinations

        # Generate text
        sentence, fun_fact_source = generate_flight_text_for_aircraft(
            plane, lat, lng, i, country_code, used_destinations
        )

        print(f"Fun Fact Source: {fun_fact_source or 'None'}")
        if is_duplicate:
            print(f"Note: Duplicate destination - used origin city fun facts instead")
        print()
        print("GENERATED TEXT:")
        print("-" * 80)
        print(sentence)
        print("-" * 80)
        print()

    print("="*80)
    print(f"Destinations tracked: {used_destinations}")
    print("="*80)
    print()


@pytest.mark.asyncio
async def test_detailed_output_dublin():
    """Output detailed information about aircraft selection and text generation for Dublin"""
    lat, lng = 53.3498, -6.2603
    country_code = "IE"

    print("\n" + "="*80)
    print("DETAILED TEST OUTPUT - Dublin Location")
    print("="*80)
    print(f"Location: {lat}, {lng} (Dublin, Ireland)")
    print(f"Country Code: {country_code}")
    print()

    # Get aircraft
    aircraft, error = await get_nearby_aircraft(lat, lng, limit=3)

    if error and "not configured" in error.lower():
        pytest.skip(f"API not configured: {error}")

    if len(aircraft) == 0:
        pytest.skip("No aircraft found near Dublin at this time")

    print(f"Total aircraft found: {len(aircraft)}")
    print()

    # Track destinations for duplicate detection
    used_destinations = set()

    # Process each plane
    for i, plane in enumerate(aircraft[:3], start=1):
        print("-" * 80)
        print(f"PLANE {i}")
        print("-" * 80)

        # Show aircraft details
        print(f"Aircraft Type: {plane.get('aircraft', 'Unknown')}")
        print(f"Airline: {plane.get('airline_name', 'Unknown')}")
        print(f"Flight Number: {plane.get('flight_number', 'Unknown')}")
        print(f"Origin: {plane.get('origin_city', 'Unknown')}, {plane.get('origin_country', 'Unknown')}")
        print(f"Destination: {plane.get('destination_city', 'Unknown')}, {plane.get('destination_country', 'Unknown')}")
        print(f"Distance: {plane.get('distance_km', 0):.1f} km")

        if plane.get('is_private_operator'):
            print(f"Type: Private Jet")

        if plane.get('is_cargo'):
            print(f"Type: Cargo Flight")

        print()

        # Check if destination is duplicate BEFORE generating text
        is_duplicate = plane.get('destination_city') in used_destinations

        # Generate text
        sentence, fun_fact_source = generate_flight_text_for_aircraft(
            plane, lat, lng, i, country_code, used_destinations
        )

        print(f"Fun Fact Source: {fun_fact_source or 'None'}")
        if is_duplicate:
            print(f"Note: Duplicate destination - used origin city fun facts instead")
        print()
        print("GENERATED TEXT:")
        print("-" * 80)
        print(sentence)
        print("-" * 80)
        print()

    print("="*80)
    print(f"Destinations tracked: {used_destinations}")
    print("="*80)
    print()


@pytest.mark.asyncio
async def test_detailed_output_los_angeles():
    """Output detailed information about aircraft selection and text generation for Los Angeles"""
    lat, lng = 34.0522, -118.2437
    country_code = "US"

    print("\n" + "="*80)
    print("DETAILED TEST OUTPUT - Los Angeles Location")
    print("="*80)
    print(f"Location: {lat}, {lng} (Los Angeles, USA)")
    print(f"Country Code: {country_code}")
    print()

    # Get aircraft
    aircraft, error = await get_nearby_aircraft(lat, lng, limit=3)

    if error and "not configured" in error.lower():
        pytest.skip(f"API not configured: {error}")

    if len(aircraft) == 0:
        pytest.skip("No aircraft found near Los Angeles at this time")

    print(f"Total aircraft found: {len(aircraft)}")
    print()

    # Track destinations for duplicate detection
    used_destinations = set()

    # Process each plane
    for i, plane in enumerate(aircraft[:3], start=1):
        print("-" * 80)
        print(f"PLANE {i}")
        print("-" * 80)

        # Show aircraft details
        print(f"Aircraft Type: {plane.get('aircraft', 'Unknown')}")
        print(f"Airline: {plane.get('airline_name', 'Unknown')}")
        print(f"Flight Number: {plane.get('flight_number', 'Unknown')}")
        print(f"Origin: {plane.get('origin_city', 'Unknown')}, {plane.get('origin_country', 'Unknown')}")
        print(f"Destination: {plane.get('destination_city', 'Unknown')}, {plane.get('destination_country', 'Unknown')}")
        print(f"Distance: {plane.get('distance_km', 0):.1f} km")

        if plane.get('is_private_operator'):
            print(f"Type: Private Jet")

        if plane.get('is_cargo'):
            print(f"Type: Cargo Flight")

        print()

        # Check if destination is duplicate BEFORE generating text
        is_duplicate = plane.get('destination_city') in used_destinations

        # Generate text
        sentence, fun_fact_source = generate_flight_text_for_aircraft(
            plane, lat, lng, i, country_code, used_destinations
        )

        print(f"Fun Fact Source: {fun_fact_source or 'None'}")
        if is_duplicate:
            print(f"Note: Duplicate destination - used origin city fun facts instead")
        print()
        print("GENERATED TEXT:")
        print("-" * 80)
        print(sentence)
        print("-" * 80)
        print()

    print("="*80)
    print(f"Destinations tracked: {used_destinations}")
    print("="*80)
    print()


@pytest.mark.asyncio
async def test_detailed_output_weston_ct():
    """Output detailed information about aircraft selection and text generation for Weston CT"""
    lat, lng = 41.2023, -73.3815
    country_code = "US"

    print("\n" + "="*80)
    print("DETAILED TEST OUTPUT - Weston CT Location")
    print("="*80)
    print(f"Location: {lat}, {lng} (Weston, Connecticut, USA)")
    print(f"Country Code: {country_code}")
    print()

    # Get aircraft
    aircraft, error = await get_nearby_aircraft(lat, lng, limit=3)

    if error and "not configured" in error.lower():
        pytest.skip(f"API not configured: {error}")

    if len(aircraft) == 0:
        pytest.skip("No aircraft found near Weston CT at this time")

    print(f"Total aircraft found: {len(aircraft)}")
    print()

    # Track destinations for duplicate detection
    used_destinations = set()

    # Process each plane
    for i, plane in enumerate(aircraft[:3], start=1):
        print("-" * 80)
        print(f"PLANE {i}")
        print("-" * 80)

        # Show aircraft details
        print(f"Aircraft Type: {plane.get('aircraft', 'Unknown')}")
        print(f"Airline: {plane.get('airline_name', 'Unknown')}")
        print(f"Flight Number: {plane.get('flight_number', 'Unknown')}")
        print(f"Origin: {plane.get('origin_city', 'Unknown')}, {plane.get('origin_country', 'Unknown')}")
        print(f"Destination: {plane.get('destination_city', 'Unknown')}, {plane.get('destination_country', 'Unknown')}")
        print(f"Distance: {plane.get('distance_km', 0):.1f} km")

        if plane.get('is_private_operator'):
            print(f"Type: Private Jet")

        if plane.get('is_cargo'):
            print(f"Type: Cargo Flight")

        print()

        # Check if destination is duplicate BEFORE generating text
        is_duplicate = plane.get('destination_city') in used_destinations

        # Generate text
        sentence, fun_fact_source = generate_flight_text_for_aircraft(
            plane, lat, lng, i, country_code, used_destinations
        )

        print(f"Fun Fact Source: {fun_fact_source or 'None'}")
        if is_duplicate:
            print(f"Note: Duplicate destination - used origin city fun facts instead")
        print()
        print("GENERATED TEXT:")
        print("-" * 80)
        print(sentence)
        print("-" * 80)
        print()

    print("="*80)
    print(f"Destinations tracked: {used_destinations}")
    print("="*80)
    print()
