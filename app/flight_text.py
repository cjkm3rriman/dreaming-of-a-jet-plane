"""
Shared flight text generation for consistent messaging across endpoints
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import random
import re
from .cities_database import get_fun_facts
from .airport_database import get_airport_by_iata


def convert_aircraft_name_digits(aircraft_name: str) -> str:
    """Convert numbers in aircraft names to individual digits separated by spaces

    Args:
        aircraft_name: Aircraft name that may contain numbers

    Returns:
        str: Aircraft name with numbers converted to individual digits

    Examples:
        "Boeing 737" -> "Boeing 7 3 7"
        "Airbus A320" -> "Airbus A 3 2 0"
    """
    def replace_number(match):
        number_str = match.group(0)
        return ' '.join(number_str)

    # Match sequences of digits
    pattern = r'\d+'
    result = re.sub(pattern, replace_number, aircraft_name)

    return result


def format_flight_number_for_tts(flight_number: str) -> str:
    """Format flight number with spaces between letters and numbers for TTS

    Args:
        flight_number: Flight number like "BA123" or "AA4567"

    Returns:
        str: Flight number with spaces between letters and numbers

    Examples:
        "BA123" -> "B A 1 2 3"
        "AA4567" -> "A A 4 5 6 7"
        "unknown flight" -> "unknown flight" (unchanged if not alphanumeric)
    """
    if not flight_number or flight_number == "unknown flight":
        return flight_number

    # Add spaces between all characters for flight numbers
    result = ' '.join(flight_number)
    return result


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


def generate_flight_text_for_aircraft(aircraft: Dict[str, Any], user_lat: float = None, user_lng: float = None, plane_index: int = 1) -> str:
    """Generate descriptive text for a specific aircraft
    
    Args:
        aircraft: Single aircraft data dictionary
        user_lat: User's latitude (for determining US location)
        user_lng: User's longitude (for determining US location)
        plane_index: 1-based plane index (1, 2, 3) to determine opening words
        
    Returns:
        str: Human-readable sentence describing the flight
    """
    # Extract values for the sentence template
    distance_miles = aircraft.get("distance_miles") or "unknown"
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
    opening_words = ["Marvelous!", "Good Heavens!", "Fantastic!", "Splendid!", "What Luck!", "Golly!"]
    base_opening_word = random.choice(opening_words)
    
    if plane_index == 2:
        detection_sentence = f"{base_opening_word} We've detected another jet plane, flying high {distance_miles} miles from this Yoto!"
    elif plane_index == 3:
        detection_sentence = f"{base_opening_word} We've detected one more jet plane up there, {distance_miles} miles from this Yoto!"
    else:
        # Default for plane 1 or any other index
        detection_sentence = f"{base_opening_word} We've detected a jet plane up in the sky, {distance_miles} miles from this Yoto!"
    
    # Add aircraft type, capacity, speed, and altitude information
    aircraft_name = aircraft.get("aircraft") or "unknown aircraft type"
    # Convert numbers in aircraft name to individual digits for TTS
    aircraft_name_with_digits = convert_aircraft_name_digits(aircraft_name)
    passenger_capacity = aircraft.get("passenger_capacity", 0)
    velocity_knots = aircraft.get("velocity", 0)
    velocity_mph = round(velocity_knots * 1.15078) if velocity_knots else 0
    altitude_feet = aircraft.get("altitude", 0)
    
    # Generate random captain name (last names only)
    pilot_names = [
        "Smith", "Johnson", "Mitchell", "Sullivan",
        "Rodriguez", "Nakamura", "Mueller", "Petrov",
        "Anderson", "Steele", "Gonzalez",
        "Lindberg", "Wright", "Taylor",
        "Wilson", "Garcia", "Brown", "Jensen", "Boo Boo Butt",
        "Merriman", "Ezra", "Havencroft",
        "Cooper", "Williams", "Wren", "Miles",
        "Parker", "Thompson", "Martinez", "Campbell", "Jackson", "Turner",
        "Peterson", "Vega",
        "Brooks", "Silva", "Santos", "Chen",
        "Morrison"
    ]
    captain_name = random.choice(pilot_names)
    
    # Build scanner sentence with random selection of available data
    aircraft_descriptors = ["big, shiny", "mega, massive", "super powered", "humongous", "gigantic", "enormous"]
    aircraft_descriptor = random.choice(aircraft_descriptors)
    scanner_info = f"My scanner tells me that Captain {captain_name} is piloting this {aircraft_descriptor} {aircraft_name_with_digits}"
    
    # Collect available information options
    available_info = []
    
    if passenger_capacity and passenger_capacity > 0:
        available_info.append(f"carrying {passenger_capacity} passengers")
        
    if velocity_mph > 0:
        speed_words = ["whopping", "stupendous", "astounding", "speedy", "super fast"]
        speed_word = random.choice(speed_words)
        # Use "an" for words starting with vowel sounds
        article = "an" if speed_word[0].lower() in 'aeiou' else "a"
        available_info.append(f"travelling at {article} {speed_word} {velocity_mph} miles per hour")
        
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

    # Format flight number for better TTS pronunciation
    flight_number_tts = format_flight_number_for_tts(flight_number)

    if (origin_city == "an unknown origin" or origin_location == "an unknown country") and (destination_city == "an unknown destination" or destination_location == "an unknown country"):
        flight_sentence = f"This flight {flight_number_tts} belongs to {airline_name} and is {movement_word} all the way to somewhere, I am not quite sure."
    elif origin_city == "an unknown origin" or origin_location == "an unknown country":
        flight_sentence = f"This flight {flight_number_tts} belongs to {airline_name} and is {movement_word} all the way to {destination_city} in {destination_location}{eta_text}."
    elif destination_city == "an unknown destination" or destination_location == "an unknown country":
        flight_sentence = f"This flight {flight_number_tts} belongs to {airline_name} and is {movement_word} from {origin_city} in {origin_location} all the way to somewhere?"
    else:
        flight_sentence = f"This flight {flight_number_tts} belongs to {airline_name} and is {movement_word} from {origin_city} in {origin_location} all the way to {destination_city} in {destination_location}{eta_text}."
    
    # Add random fun fact about destination city if available
    full_response = f"{detection_sentence} {scanner_sentence} {flight_sentence}"
    
    if destination_city and destination_city != "an unknown destination":
        # For US destinations, pass state information to help with city disambiguation
        if destination_country == "the United States" and destination_location != "an unknown country":
            # Use the actual state name if we have it, otherwise use destination_location
            destination_state = aircraft.get("destination_airport")
            if destination_state:
                airport_data = get_airport_by_iata(destination_state)
                if airport_data and airport_data.get("country") == "US":
                    state = airport_data.get("state")
                    if state:
                        fun_facts = get_fun_facts(destination_city, state, "United States")
                    else:
                        fun_facts = get_fun_facts(destination_city, destination_location, "United States")
                else:
                    fun_facts = get_fun_facts(destination_city, destination_location, "United States")
            else:
                fun_facts = get_fun_facts(destination_city, destination_location, "United States")
        else:
            fun_facts = get_fun_facts(destination_city)
            
        if fun_facts:
            random_fact = random.choice(fun_facts)
            fun_fact_openings = ["Fun fact.", "Guess what?", "Did you know?", "A tidbit for you."]
            fun_fact_opening = random.choice(fun_fact_openings)
            full_response += f" {fun_fact_opening} {random_fact}."
    
    # Add closing prompt for plane index 1 and 2
    if plane_index == 1:
        full_response += " Should we find another jet plane?"
    elif plane_index == 2:
        full_response += " Let's find one more jet plane shall we?"
    
    return full_response


def make_error_message_friendly(error_message: str) -> str:
    """Convert technical error messages to friendly, kid-appropriate explanations"""
    error_lower = error_message.lower()

    # Common ending for all error messages
    ending = ", try again in a minute or so will you?"

    # API key issues
    if "api key not configured" in error_lower:
        return "my scanner's acting all silly" + ending

    # No aircraft found
    if "no passenger aircraft found" in error_lower:
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


def generate_flight_text(aircraft: List[Dict[str, Any]], error_message: Optional[str] = None, user_lat: float = None, user_lng: float = None, plane_index: int = 0) -> str:
    """Generate descriptive text about detected aircraft or no-aircraft conditions
    
    Args:
        aircraft: List of aircraft data (empty list if no aircraft found)
        error_message: Optional error message if aircraft detection failed
        user_lat: User's latitude (for determining US location)
        user_lng: User's longitude (for determining US location)
        plane_index: Index of aircraft to use from the list (0-based)
        
    Returns:
        str: Human-readable sentence describing the flight situation
    """
    if aircraft and len(aircraft) > plane_index:
        selected_aircraft = aircraft[plane_index]
        # Convert 0-based index to 1-based for plane_index parameter
        return generate_flight_text_for_aircraft(selected_aircraft, user_lat, user_lng, plane_index + 1)
    elif aircraft and len(aircraft) > 0:
        # Fallback to first aircraft if plane_index is out of bounds
        selected_aircraft = aircraft[0]
        # Use plane index 1 for fallback
        return generate_flight_text_for_aircraft(selected_aircraft, user_lat, user_lng, 1)
    else:
        # Handle error cases with friendly error messages
        if error_message:
            friendly_error = make_error_message_friendly(error_message)
            return f"I'm sorry my old chum but my scanner was not able to find any jet planes nearby, because {friendly_error}"
        else:
            friendly_error = make_error_message_friendly("no passenger aircraft found within 100km radius")
            return f"I'm sorry my old chum but my scanner was not able to find any jet planes nearby, because {friendly_error}"
