"""
Shared flight text generation for consistent messaging across endpoints
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import random
import time
import re
from .cities_database import get_fun_facts
from .airport_database import get_airport_by_iata
from .location_utils import uses_metric_system
from .aircraft_database import get_phonetic_name


# Mapping for converting digits to English words for TTS
DIGIT_TO_WORD = {
    '0': 'zero',
    '1': 'one',
    '2': 'two',
    '3': 'three',
    '4': 'four',
    '5': 'five',
    '6': 'six',
    '7': 'seven',
    '8': 'eight',
    '9': 'nine'
}


SPECIAL_PLANE3_TEXT = (
    "Incredible! My radar just picked up something truly extraordinary, gliding silently through the clouds! "
    "It's not a jet, and it's not a bird - it's a wooden sleigh being pulled by a team of eight... no, wait... "
    "nine flying reindeer!\n\n"
    "My scanner is showing a very mysterious figure at the reigns, wearing a bright red suit and navigating with a "
    "glowing red light right at the front of the pack. This unusual craft doesn't have a flight number, but it's moving "
    "at incredible speeds, zig-zagging across the globe and carrying a massive sack overflowing with colorful packages.\n\n"
    "Fun fact: Reindeer are the only deer species where both the males and females grow antlers, and they are excellent "
    "swimmers, able to cross wide rivers and even parts of the ocean!\n\n"
    "This magical team seems to be on a very tight schedule tonight, stopping at every rooftop before whisking away into "
    "the starry night."
)


def get_plane_sentence_override(plane_index: int) -> Optional[str]:
    """Return special holiday copy when applicable (7am GMT Dec 24 to 7am GMT Dec 25)"""
    now_utc = datetime.now(timezone.utc)
    if plane_index == 5 and now_utc.month == 12:
        # Active from 7am GMT Dec 24 to 7am GMT Dec 25
        if (now_utc.day == 24 and now_utc.hour >= 7) or (now_utc.day == 25 and now_utc.hour < 7):
            return SPECIAL_PLANE3_TEXT
    return None


def convert_aircraft_name_digits(aircraft_name: str) -> str:
    """Convert numbers in aircraft names to individual words separated by spaces

    Args:
        aircraft_name: Aircraft name that may contain numbers

    Returns:
        str: Aircraft name with numbers converted to individual words

    Examples:
        "Boeing 737" -> "Boeing seven three seven"
        "Airbus A320" -> "Airbus A three two zero"
    """
    def replace_number(match):
        number_str = match.group(0)
        return ' '.join(DIGIT_TO_WORD[digit] for digit in number_str)

    # Match sequences of digits
    pattern = r'\d+'
    result = re.sub(pattern, replace_number, aircraft_name)

    return result


def format_flight_number_for_tts(flight_number: str) -> str:
    """Format flight number with spaces between letters and words for numbers for TTS

    Args:
        flight_number: Flight number like "BA123" or "AA4567"

    Returns:
        str: Flight number with spaces between letters and words for numbers

    Examples:
        "BA123" -> "B A one two three"
        "AA4567" -> "A A four five six seven"
        "unknown flight" -> "unknown flight" (unchanged if not alphanumeric)
    """
    if not flight_number or flight_number == "unknown flight":
        return flight_number

    # Convert each character individually, using words for digits
    result_parts = []
    for char in flight_number:
        if char.isdigit():
            result_parts.append(DIGIT_TO_WORD[char])
        else:
            result_parts.append(char)

    return ' '.join(result_parts)


def is_location_in_us(lat: float, lng: float) -> bool:
    """Check if coordinates are within the United States (approximate bounds)
    
    Args:
        lat: Latitude
        lng: Longitude
        
    Returns:
        bool: True if coordinates are in the US
    """
    # Approximate US bounds (including Alaska and Hawaii)
    # Continental US: lat 24.5-49.4, lng -125 to -66.9
    # Alaska: lat 54.8-71.4, lng -179.8 to -129.9  
    # Hawaii: lat 18.9-28.5, lng -178.3 to -154.8
    
    if 24.5 <= lat <= 49.4 and -125 <= lng <= -66.9:  # Continental US
        return True
    elif 54.8 <= lat <= 71.4 and -179.8 <= lng <= -129.9:  # Alaska
        return True
    elif 18.9 <= lat <= 28.5 and -178.3 <= lng <= -154.8:  # Hawaii
        return True
    return False


def km_to_miles(km: float) -> float:
    """Convert kilometers to miles

    Args:
        km: Distance in kilometers

    Returns:
        float: Distance in miles
    """
    return km * 0.621371


def format_distance(distance_km: float, use_metric: bool) -> tuple[int, str]:
    """Format distance with appropriate units

    Args:
        distance_km: Distance in kilometers
        use_metric: True for kilometers, False for miles

    Returns:
        tuple: (distance_value, unit_name) e.g., (100, "kilometers") or (62, "miles")
    """
    if use_metric:
        return int(round(distance_km)), "kilometers"
    else:
        distance_miles = km_to_miles(distance_km)
        return int(round(distance_miles)), "miles"


def format_speed(speed_kmh: float, use_metric: bool) -> tuple[int, str]:
    """Format speed with appropriate units

    Args:
        speed_kmh: Speed in km/h
        use_metric: True for km/h, False for mph

    Returns:
        tuple: (speed_value, unit_name) e.g., (800, "kilometers per hour") or (497, "miles per hour")
    """
    if use_metric:
        return int(round(speed_kmh)), "kilometers per hour"
    else:
        speed_mph = km_to_miles(speed_kmh)
        return int(round(speed_mph)), "miles per hour"


def generate_flight_text_for_aircraft(
    aircraft: Dict[str, Any],
    user_lat: float = None,
    user_lng: float = None,
    plane_index: int = 1,
    country_code: str = "US",
    used_destinations: set = None,
    split_text: bool = False,
) -> tuple[str, Optional[str]] | tuple[str, str, Optional[str]]:
    """Generate descriptive text for a specific aircraft

    Args:
        aircraft: Single aircraft data dictionary
        user_lat: User's latitude (for determining US location)
        user_lng: User's longitude (for determining US location)
        plane_index: 1-based plane index (1, 2, 3) to determine opening words
        country_code: ISO 3166-1 alpha-2 country code for unit localization (default: "US")
        used_destinations: Optional set of destination cities already used (for diversity)
        split_text: If True, return (opening, body, fun_fact_source) instead of (full_text, fun_fact_source)

    Returns:
        If split_text=False (default): tuple (sentence, fun_fact_source)
            - sentence: Human-readable sentence describing the flight
            - fun_fact_source: "destination", "origin", or None (if no fun fact included)
        If split_text=True: tuple (opening_text, body_text, fun_fact_source)
            - opening_text: Detection sentence with distance (~80-100 chars)
            - body_text: Everything else - scanner, flight details, fun fact, closing (~400-500 chars)
            - fun_fact_source: "destination", "origin", or None (if no fun fact included)
    """
    # Ensure fresh random state for each text generation
    random.seed(time.time_ns())

    # Determine if user's country uses metric system
    use_metric = uses_metric_system(country_code)

    # Extract values for the sentence template
    distance_km = aircraft.get("distance_km", 0)
    if distance_km > 0:
        distance_value, distance_unit = format_distance(distance_km, use_metric)
    else:
        distance_value, distance_unit = "unknown", ""
    flight_number = aircraft.get("flight_number") or aircraft.get("callsign") or "unknown flight"
    airline_name = aircraft.get("airline_name") or "an unknown airline"
    origin_city = aircraft.get("origin_city") or "an unknown origin"
    origin_country = aircraft.get("origin_country") or "an unknown country"
    destination_city = aircraft.get("destination_city") or "an unknown destination"
    destination_country = aircraft.get("destination_country") or "an unknown country"
    
    # Check if we should use state instead of country for US locations
    destination_location = destination_country
    origin_location = origin_country
    user_in_us = user_lat is not None and user_lng is not None and is_location_in_us(user_lat, user_lng)
    
    if user_in_us and destination_country == "the United States":
        # Get destination airport data to find state
        destination_airport = aircraft.get("destination_airport")
        if destination_airport:
            airport_data = get_airport_by_iata(destination_airport)
            if airport_data and airport_data.get("country") == "US":
                state = airport_data.get("state")
                if state:
                    destination_location = state
    
    if user_in_us and origin_country == "the United States":
        # Get origin airport data to find state
        origin_airport = aircraft.get("origin_airport")
        if origin_airport:
            airport_data = get_airport_by_iata(origin_airport)
            if airport_data and airport_data.get("country") == "US":
                state = airport_data.get("state")
                if state:
                    origin_location = state
    
    
    # Build the descriptive sentences with different opening words based on plane index
    opening_words = ["Marvelous!", "Good Heavens!", "Fantastic!", "Splendid!", "What Luck!", "Wow!"]
    base_opening_word = random.choice(opening_words)

    # Format distance with appropriate units
    if distance_value != "unknown":
        distance_str = f"{distance_value} {distance_unit}"
    else:
        distance_str = "an unknown distance"

    if plane_index == 2:
        detection_sentence = f"{base_opening_word} We've found another jet plane, flying high {distance_str} from this Yoto!"
    elif plane_index == 3:
        detection_sentence = f"{base_opening_word} Our scanner has identified one more jet plane up there, {distance_str} from this Yoto!"
    elif plane_index == 4:
        detection_sentence = f"{base_opening_word} We've spotted yet another jet plane soaring through the sky, {distance_str} from this Yoto!"
    elif plane_index == 5:
        detection_sentence = f"{base_opening_word} Our scanner has locked on to one final jet plane, {distance_str} from this Yoto!"
    else:
        # Default for plane 1 or any other index
        detection_sentence = f"{base_opening_word} We've detected a jet plane up in the sky, {distance_str} from this Yoto!"
    
    # Add aircraft type, capacity, speed, and altitude information
    aircraft_name = aircraft.get("aircraft") or "unknown aircraft type"
    aircraft_icao = aircraft.get("aircraft_icao")

    # Check if we have a phonetic name for this aircraft
    # If yes, use it; otherwise fall back to digit conversion algorithm
    phonetic_name = get_phonetic_name(aircraft_icao) if aircraft_icao else None
    if phonetic_name:
        aircraft_name_with_digits = phonetic_name
    else:
        # Convert numbers in aircraft name to individual digits for TTS
        aircraft_name_with_digits = convert_aircraft_name_digits(aircraft_name)
    passenger_capacity = aircraft.get("passenger_capacity", 0)
    velocity_knots = aircraft.get("velocity", 0)
    velocity_kmh = round(velocity_knots * 1.852) if velocity_knots else 0  # Convert knots to km/h
    altitude_feet = aircraft.get("altitude", 0)
    
    # Generate random captain name (last names only)
    pilot_names = [
        "Al-Saud", "Anderson", "Boo Boo Butt", "Brooks", "Brown",
        "Campbell", "Chen", "Cooper", "Ezra", "Garcia", "Gonzalez",
        "Hassan", "Havencroft", "Jackson", "Jensen", "Johnson",
        "Jørgensen", "Khoury", "Kouyaté", "Kovács", "Li", "Lindberg",
        "Martinez", "Merriman", "Miles", "Mitchell", "Morrison", "Mueller",
        "Nakamura", "Nkosi", "Novak", "Okafor", "Olsen", "Parker", "Patel",
        "Peterson", "Petrov", "Popescu", "Rodriguez", "Santos", "Sharma",
        "Silva", "Singh", "Smith", "Steele", "Sullivan", "Svensson",
        "Taylor", "Thompson", "Turner", "Vega", "Wang", "Williams",
        "Wilson", "Wren", "Wright", "Zhang"
    ]
    captain_name = random.choice(pilot_names)
    
    # Build scanner sentence with random selection of available data
    aircraft_descriptors = ["big, shiny", "mega, massive", "super powered", "humongous", "gigantic", "enormous"]
    small_aircraft_descriptors = ["shiny", "beautiful", "swanky", "svelte", "sleek", "elegant"]
    descriptor_pool = aircraft_descriptors
    if passenger_capacity and passenger_capacity <= 50:
        descriptor_pool = small_aircraft_descriptors
    aircraft_descriptor = random.choice(descriptor_pool)
    scanner_info = (
        f"Captain {captain_name} is piloting this "
        f"{aircraft_descriptor} {aircraft_name_with_digits}"
    )
    
    # Collect available information options
    available_info = []
    
    if passenger_capacity and passenger_capacity > 0:
        available_info.append(f"carrying {passenger_capacity} passengers")

    if velocity_kmh > 0:
        speed_words = ["whopping", "stupendous", "astounding", "speedy", "super fast"]
        speed_word = random.choice(speed_words)
        # Use "an" for words starting with vowel sounds
        article = "an" if speed_word[0].lower() in 'aeiou' else "a"
        speed_value, speed_unit = format_speed(velocity_kmh, use_metric)
        available_info.append(f"travelling at {article} {speed_word} {speed_value} {speed_unit}")
        
    if altitude_feet and altitude_feet > 0:
        altitude_words = ["soaring", "cruising", "flying"]
        altitude_word = random.choice(altitude_words)
        available_info.append(f"{altitude_word} at {altitude_feet:,} feet")
    
    # Randomly select one piece of additional info if available
    if available_info:
        selected_info = random.choice(available_info)
        scanner_info += f" {selected_info}"
        
    scanner_sentence = scanner_info + "."
    
    # Build flight details sentence with ETA
    eta_string = aircraft.get("eta")
    eta_text = ""
    
    if eta_string:
        try:
            # Parse ISO 8601 UTC datetime string (format: 2025-08-25T02:26:49Z)
            eta_datetime = datetime.fromisoformat(eta_string.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            time_diff = eta_datetime - now
            
            if time_diff.total_seconds() > 0:
                total_minutes = int(time_diff.total_seconds() // 60)
                
                if total_minutes <= 7:
                    eta_options = [
                        " landing in just a few minutes",
                        " landing very soon"
                    ]
                    eta_text = random.choice(eta_options)
                elif total_minutes <= 15:
                    eta_options = [
                        " landing in about 15 minutes - that's about the same time it takes to watch two episodes of Bluey",
                        " landing in about 15 minutes - that's about how long it takes to eat your dinner"
                    ]
                    eta_text = random.choice(eta_options)
                elif total_minutes <= 20:
                    eta_options = [
                        " landing in about 20 minutes - that's about the time you spend in the water at bath time",
                        " landing in about 20 minutes - that's about how long it takes to walk to the park and back"
                    ]
                    eta_text = random.choice(eta_options)
                elif total_minutes <= 30:
                    eta_options = [
                        " landing in about half an hour - that's about the length of a short car journey",
                        " landing in about half an hour - that's about how long it takes to read three bedtime stories"
                    ]
                    eta_text = random.choice(eta_options)
                elif total_minutes <= 45:
                    eta_options = [
                        " landing in about 45 minutes - that's how long you usually spend at the playground",
                        " landing in about 45 minutes - that's about the time it takes for grown ups to cook dinner"
                    ]
                    eta_text = random.choice(eta_options)
                elif total_minutes <= 60:
                    eta_options = [
                        " landing in about an hour - that's about the time it takes to do bath and bed time",
                        " landing in about an hour - that's about how long a short nap lasts"
                    ]
                    eta_text = random.choice(eta_options)
                elif total_minutes <= 90:
                    eta_options = [
                        " landing in about an hour and a half - that's about the time it takes to watch a Disney movie",
                        " landing in about an hour and a half - that's about how long a fun play date lasts"
                    ]
                    eta_text = random.choice(eta_options)
                elif total_minutes <= 120:  # 2 hours
                    eta_options = [
                        " landing in about 2 hours - that's like watching eight of your favorite tv episodes in a row",
                        " landing in about 2 hours - that's about how long a soccer game lasts"
                    ]
                    eta_text = random.choice(eta_options)
                elif total_minutes <= 180:  # 3 hours
                    eta_options = [
                        " landing in about 3 hours - that's like watching a really long grown-ups movie",
                        " landing in about 3 hours - that's about how long it takes to walk around a big zoo"
                    ]
                    eta_text = random.choice(eta_options)
                elif total_minutes <= 240:  # 4 hours
                    eta_options = [
                        " landing in about 4 hours - that's time to watch two Disney movies back to back",
                        " landing in about 4 hours - that's about how long a really fun morning at the beach lasts"
                    ]
                    eta_text = random.choice(eta_options)
                elif total_minutes <= 360:  # 6 hours
                    eta_options = [
                        " landing in about 6 hours - that's about the time between breakfast and lunch",
                        " landing in about 6 hours - that's about how long you sleep during the night"
                    ]
                    eta_text = random.choice(eta_options)
                elif total_minutes <= 480:  # 8 hours
                    eta_options = [
                        " landing in about 8 hours - that's like a full day at school",
                        " landing in about 8 hours - that's about how long it would take to watch 30 tv episodes in a row!"
                    ]
                    eta_text = random.choice(eta_options)
                elif total_minutes <= 720:  # 12 hours
                    eta_options = [
                        " landing in about 12 hours - that's like a full night's sleep",
                        " landing in about 12 hours - that's like from breakfast to bedtime"
                    ]
                    eta_text = random.choice(eta_options)
                else:
                    # For very long flights, round to nearest hour
                    hours = round(total_minutes / 60)
                    if hours <= 24:
                        eta_text = f" landing in about {hours} hours - that's like a whole day and night"
                    else:
                        eta_text = " landing sometime tomorrow"
            else:
                eta_text = " landing there very soon"
        except (ValueError, TypeError):
            # Invalid ETA timestamp
            pass
    
    # Choose random movement word
    movement_words = ["zooming", "speeding", "whizzing", "zoom zooming", "cloud hopping", "sky skimming"]
    movement_word = random.choice(movement_words)

    # Format flight number for better TTS pronunciation, or use "private jet" for private operators
    is_private_jet = aircraft.get("is_private_operator", False)
    if is_private_jet:
        flight_number_tts = "private jet"
    else:
        flight_number_tts = f"flight {format_flight_number_for_tts(flight_number)}"

    if (origin_city == "an unknown origin" or origin_location == "an unknown country") and (destination_city == "an unknown destination" or destination_location == "an unknown country"):
        flight_sentence = f"This {flight_number_tts} belongs to {airline_name} and is {movement_word} all the way to somewhere exciting, It is not quite clear'."
    elif origin_city == "an unknown origin" or origin_location == "an unknown country":
        flight_sentence = f"This {flight_number_tts} belongs to {airline_name} and is {movement_word} all the way to {destination_city} in {destination_location}{eta_text}."
    elif destination_city == "an unknown destination" or destination_location == "an unknown country":
        flight_sentence = f"This {flight_number_tts} belongs to {airline_name} and is {movement_word} from {origin_city} in {origin_location} all the way to somewhere exciting, it is not quite clear."
    else:
        flight_sentence = f"This {flight_number_tts} belongs to {airline_name} and is {movement_word} from {origin_city} in {origin_location} all the way to {destination_city} in {destination_location}{eta_text}."
    
    # Build body text (scanner + flight details + fun fact + closing)
    body_text = f"{scanner_sentence} {flight_sentence}"
    fun_fact_source = None  # Track which city we used for fun facts

    if destination_city and destination_city != "an unknown destination":
        # Check for duplicate destinations - use origin city for fun facts if duplicate
        city_for_facts = destination_city
        location_for_facts = destination_location
        country_for_facts = destination_country
        airport_code_for_facts = aircraft.get("destination_airport")
        fun_fact_source = "destination"  # Default to destination

        if used_destinations is not None and destination_city in used_destinations:
            # Duplicate destination - use origin instead if available
            if origin_city and origin_city != "an unknown origin":
                city_for_facts = origin_city
                location_for_facts = origin_location
                country_for_facts = origin_country
                airport_code_for_facts = aircraft.get("origin_airport")
                fun_fact_source = "origin"  # Override to origin for duplicates
            # If origin unavailable, fall back to destination (will be duplicate but no choice)

        # Add destination to tracking set (even if we're using origin for facts)
        if used_destinations is not None:
            used_destinations.add(destination_city)

        # Get fun facts for the chosen city (using same logic as before)
        if country_for_facts == "the United States" and location_for_facts != "an unknown country":
            # Use the actual state name if we have it, otherwise use location_for_facts
            if airport_code_for_facts:
                airport_data = get_airport_by_iata(airport_code_for_facts)
                if airport_data and airport_data.get("country") == "US":
                    state = airport_data.get("state")
                    if state:
                        fun_facts = get_fun_facts(city_for_facts, state, "United States")
                    else:
                        fun_facts = get_fun_facts(city_for_facts, location_for_facts, "United States")
                else:
                    fun_facts = get_fun_facts(city_for_facts, location_for_facts, "United States")
            else:
                fun_facts = get_fun_facts(city_for_facts, location_for_facts, "United States")
        else:
            fun_facts = get_fun_facts(city_for_facts)

        if fun_facts:
            random_fact = random.choice(fun_facts)
            fun_fact_openings = ["Fun fact.", "Guess what?", "Did you know?", "A tidbit for you."]
            fun_fact_opening = random.choice(fun_fact_openings)
            body_text += f" {fun_fact_opening} {random_fact}."
        else:
            # No fun facts available for this city
            fun_fact_source = None

    if split_text:
        return detection_sentence, body_text, fun_fact_source
    else:
        full_response = f"{detection_sentence} {body_text}"
        return full_response, fun_fact_source


def make_error_message_friendly(error_message: str, user_location: str = "") -> str:
    """Convert technical error messages to friendly, kid-appropriate explanations

    Args:
        error_message: Technical error message from the system
        user_location: Optional user location string for "no aircraft found" messages

    Returns:
        Kid-friendly error explanation
    """
    error_lower = error_message.lower()

    # Common ending for all error messages
    ending = ", try again in a minute or so will you?"

    # API key issues
    if "api key not configured" in error_lower:
        return "my scanner's acting all silly" + ending

    # No aircraft found - use location-aware message
    if "no passenger aircraft found" in error_lower:
        if user_location:
            return f"there just are not any jet planes in the celestial quadrant above {user_location} right now" + ending
        else:
            return "there just are not any jet planes in this celestial quadrant right now" + ending

    # HTTP status errors
    if "api returned http" in error_lower:
        return "my scanner's tracking module is acting up" + ending

    # Timeout errors
    if "timed out" in error_lower:
        return "my scanner took too long to search and gave up" + ending

    # Network connection errors
    if "network connection error" in error_lower or "connection error" in error_lower:
        return "my scanner's connection to the tracking module is acting up" + ending

    # Unexpected errors
    if "unexpected error" in error_lower:
        return "something unexpected happened with my scanner" + ending

    # Unknown errors
    if "unknown error" in error_lower:
        return "my scanner encountered a mystery problem" + ending

    # Default fallback for any other error
    return "my scanner had a technical hiccup" + ending


def generate_generic_opening(plane_index: int) -> str:
    """Generate distance-free opening for free tier

    Args:
        plane_index: 1-based plane index (1, 2, 3)

    Returns:
        str: Generic opening text without distance reference (~80-100 chars)
    """
    # Ensure fresh random state
    random.seed(time.time_ns())

    opening_words = ["Marvelous!", "Good Heavens!", "Fantastic!", "Splendid!", "What Luck!", "Wow!"]
    word = random.choice(opening_words)

    if plane_index == 2:
        return f"{word} We've found another jet plane, flying high up in the sky!"
    elif plane_index == 3:
        return f"{word} We've identified one more jet plane up there in the clouds!"
    elif plane_index == 4:
        return f"{word} We've spotted yet another jet plane soaring through the sky!"
    elif plane_index == 5:
        return f"{word} Our scanner has locked on to one final jet plane!"
    else:
        # Default for plane 1 or any other index
        return f"{word} We've detected a jet plane up in the sky!"


def generate_free_tier_distance_intro(distance_miles: int) -> str:
    """Generate intro text with distance to the flight for free tier plane 1

    Args:
        distance_miles: Distance in miles from free user to the flight

    Returns:
        str: Intro text with distance (~50-60 chars)
    """
    return f"We recently spotted a jet plane {distance_miles:,} miles from this Yoto!"


# Static intro text for free tier /free/scan endpoint
FREE_SCAN_INTRO = "Let's tune into some jet planes that have been spotted around the world! Ready? Here we go!"


def format_user_location(city: str = "", region: str = "", country_name: str = "") -> str:
    """Format user location for display in error messages.

    Returns the most specific available location: city, then region, then country.
    Returns empty string if no location info is available.
    """
    if city:
        return city
    if region:
        return region
    if country_name:
        return country_name
    return ""


def generate_flight_text(aircraft: List[Dict[str, Any]], error_message: Optional[str] = None, user_lat: float = None, user_lng: float = None, plane_index: int = 0, country_code: str = "US", user_city: str = "", user_region: str = "", user_country_name: str = "") -> str:
    """Generate descriptive text about detected aircraft or no-aircraft conditions

    Args:
        aircraft: List of aircraft data (empty list if no aircraft found)
        error_message: Optional error message if aircraft detection failed
        user_lat: User's latitude (for determining US location)
        user_lng: User's longitude (for determining US location)
        plane_index: Index of aircraft to use from the list (0-based)
        country_code: ISO 3166-1 alpha-2 country code for unit localization (default: "US")
        user_city: User's city name for error messages
        user_region: User's region/state name for error messages (fallback)
        user_country_name: User's country name for error messages (fallback)

    Returns:
        str: Human-readable sentence describing the flight situation
    """
    if aircraft and len(aircraft) > plane_index:
        selected_aircraft = aircraft[plane_index]
        # Convert 0-based index to 1-based for plane_index parameter
        sentence, _ = generate_flight_text_for_aircraft(selected_aircraft, user_lat, user_lng, plane_index + 1, country_code)
        return sentence
    elif aircraft and len(aircraft) > 0:
        # Fallback to first aircraft if plane_index is out of bounds
        selected_aircraft = aircraft[0]
        # Use plane index 1 for fallback
        sentence, _ = generate_flight_text_for_aircraft(selected_aircraft, user_lat, user_lng, 1, country_code)
        return sentence
    else:
        # Handle error cases with friendly error messages
        user_location = format_user_location(user_city, user_region, user_country_name)

        if error_message:
            friendly_error = make_error_message_friendly(error_message, user_location)
        else:
            friendly_error = make_error_message_friendly("no passenger aircraft found within 100km radius", user_location)

        return f"I'm sorry my old chum but my scanner was not able to find any jet planes nearby, because {friendly_error}"
