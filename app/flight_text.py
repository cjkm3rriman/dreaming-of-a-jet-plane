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
    distance_miles = aircraft.get("distance_miles", "unknown")
    flight_number = aircraft.get("flight_number") or aircraft.get("callsign", "unknown flight")
    airline_name = aircraft.get("airline_name")
    origin_city = aircraft.get("origin_city", "an unknown origin")
    origin_country = aircraft.get("origin_country", "an unknown country")
    destination_city = aircraft.get("destination_city", "an unknown destination")
    destination_country = aircraft.get("destination_country", "an unknown country")
    
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
    opening_words = ["Marvelous!", "Wooosh!", "Fantastic!", "Splendid!", "What Luck!"]
    base_opening_word = random.choice(opening_words)
    
    if plane_index == 2:
        detection_sentence = f"{base_opening_word} We've detected another jet plane, flying {distance_miles} miles from this Yoto!"
    elif plane_index == 3:
        detection_sentence = f"{base_opening_word} We've detected one more jet plane up there, {distance_miles} miles from this Yoto!"
    else:
        # Default for plane 1 or any other index
        detection_sentence = f"{base_opening_word} We've detected a jet plane in the sky, {distance_miles} miles from this Yoto!"
    
    # Add aircraft type, capacity, speed, and altitude information
    aircraft_name = aircraft.get("aircraft", "unknown aircraft type")
    # Convert numbers in aircraft name to individual digits for TTS
    aircraft_name_with_digits = convert_aircraft_name_digits(aircraft_name)
    passenger_capacity = aircraft.get("passenger_capacity", 0)
    velocity_knots = aircraft.get("velocity", 0)
    velocity_mph = round(velocity_knots * 1.15078) if velocity_knots else 0
    altitude_feet = aircraft.get("altitude", 0)
    
    # Generate random captain name
    pilot_last_names = [
        "Smith", "Johnson", "Mitchell", "Sullivan", "Rodriguez", "Nakamura", 
        "Mueller", "Petrov", "Anderson", "Thomson", "Williams", "Gonzalez",
        "Lindberg", "Wright", "Taylor", "Davis", "Wilson", "Garcia", "Brown", "Jensen"
    ]
    captain_name = random.choice(pilot_last_names)
    
    # Build scanner sentence with random selection of available data
    aircraft_descriptors = ["big, shiny", "mega, massive", "super powered", "humongous"]
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
                    eta_text = " landing in just a few minutes"
                elif total_minutes <= 15:
                    eta_text = " landing in about 15 minutes - that's like watching two episodes of Bluey"
                elif total_minutes <= 20:
                    eta_text = " landing in about 20 minutes - that's like the time you spend in the water at bath time"
                elif total_minutes <= 30:
                    eta_text = " landing in about half an hour - that's like a short car journey for you"
                elif total_minutes <= 45:
                    eta_text = " landing in about 45 minutes - that's how long you usually spend at a playground"
                elif total_minutes <= 60:
                    eta_text = " landing in about an hour - that's like the time it takes to do bath and bed time"
                elif total_minutes <= 90:
                    eta_text = " landing in about an hour and a half - that's the time it takes to watch a Disney movie"
                elif total_minutes <= 120:  # 2 hours
                    eta_text = " landing in about 2 hours - that's like watching a lot of tv episodes in a row"
                elif total_minutes <= 180:  # 3 hours
                    eta_text = " landing in about 3 hours - that's like watching a really long adult movie"
                elif total_minutes <= 240:  # 4 hours
                    eta_text = " landing in about 4 hours - that's like watching a Disney movie twice"
                elif total_minutes <= 360:  # 6 hours
                    eta_text = " landing in about 6 hours - that's the time between breakfast and lunch"
                elif total_minutes <= 480:  # 8 hours
                    eta_text = " landing in about 8 hours - that's like a full day at school for you"
                elif total_minutes <= 720:  # 12 hours
                    eta_text = " landing in about 12 hours - that's like a full night's sleep for you"
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
    
    if (origin_city == "an unknown origin" or origin_location == "an unknown country") and (destination_city == "an unknown destination" or destination_location == "an unknown country"):
        flight_sentence = f"This plane belongs to {airline_name} and is {movement_word} all the way to somewhere, I am not quite sure."
    elif origin_city == "an unknown origin" or origin_location == "an unknown country":
        flight_sentence = f"This plane belongs to {airline_name} and is {movement_word} all the way to {destination_city} in {destination_location}{eta_text}."
    elif destination_city == "an unknown destination" or destination_location == "an unknown country":
        flight_sentence = f"This plane belongs to {airline_name} and is {movement_word} from {origin_city} in {origin_location} all the way to somewhere?"
    else:
        flight_sentence = f"This plane belongs to {airline_name} and is {movement_word} from {origin_city} in {origin_location} all the way to {destination_city} in {destination_location}{eta_text}."
    
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
            full_response += f" {fun_fact_opening} {random_fact}"
    
    return full_response


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
        # Handle error cases with descriptive sentence
        if error_message:
            return f"I'm sorry my old chum but my scanner was not able to find any jet planes nearby, because of {error_message.lower()}"
        else:
            return "I'm sorry my old chum but my scanner was not able to find any jet planes nearby, because no passenger aircraft found within 100km radius"