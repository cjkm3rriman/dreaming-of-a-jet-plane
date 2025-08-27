"""
Shared flight text generation for consistent messaging across endpoints
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import random
from .cities_database import get_fun_facts
from .airport_database import get_airport_by_iata


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
    destination_city = aircraft.get("destination_city", "an unknown destination")
    destination_country = aircraft.get("destination_country", "an unknown country")
    
    # Check if we should use state instead of country for US destinations
    destination_location = destination_country
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
    
    # Build flight identifier with airline name if available
    if airline_name:
        flight_identifier = f"{airline_name} flight {flight_number}"
    else:
        flight_identifier = f"flight {flight_number}"
    
    # Build the descriptive sentences with different opening words based on plane index
    if plane_index == 2:
        opening_word = "Another"
    elif plane_index == 3:
        opening_word = "One more"
    else:
        # Default for plane 1 or any other index - keep original random opening words
        opening_words = ["Marvelous!", "Tally Ho!", "Jolly Good!", "Splendid!", "What Luck!"]
        opening_word = random.choice(opening_words)
    
    detection_sentence = f"{opening_word} Jet plane detected in the sky above about {distance_miles} miles from this Yoto right now."
    
    # Add aircraft type, capacity, and speed information
    aircraft_name = aircraft.get("aircraft", "unknown aircraft type")
    passenger_capacity = aircraft.get("passenger_capacity", 0)
    velocity_knots = aircraft.get("velocity", 0)
    velocity_mph = round(velocity_knots * 1.15078) if velocity_knots else 0
    
    # Build scanner sentence with capacity and speed
    scanner_info = f"My scanners tell me this is a {aircraft_name}"
    
    if passenger_capacity and passenger_capacity > 0:
        scanner_info += f" carrying {passenger_capacity} passengers"
        
    if velocity_mph > 0:
        speed_words = ["whopping", "stupendous", "astounding", "speedy", "breathtaking"]
        speed_word = random.choice(speed_words)
        scanner_info += f" travelling at a {speed_word} {velocity_mph} miles per hour"
        
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
                hours = int(time_diff.total_seconds() // 3600)
                minutes = int((time_diff.total_seconds() % 3600) // 60)
                
                if hours > 0:
                    if hours == 1:
                        eta_text = f" arriving in {hours} hour"
                    else:
                        eta_text = f" arriving in {hours} hours"
                    
                    if minutes > 0:
                        eta_text += f" and {minutes} minutes"
                elif minutes > 0:
                    if minutes == 1:
                        eta_text = f" arriving in {minutes} minute"
                    else:
                        eta_text = f" arriving in {minutes} minutes"
                else:
                    eta_text = " arriving there very soon"
        except (ValueError, TypeError):
            # Invalid ETA timestamp
            pass
    
    if destination_city == "an unknown destination" or destination_location == "an unknown country":
        flight_sentence = f"This is {flight_identifier}, travelling to an unknown destination, {eta_text}."
    else:
        flight_sentence = f"This is {flight_identifier}, travelling to {destination_city} in {destination_location}, {eta_text}."
    
    # Add random fun fact about destination city if available
    full_response = f"{detection_sentence} {scanner_sentence} {flight_sentence}"
    
    if destination_city and destination_city != "an unknown destination":
        fun_facts = get_fun_facts(destination_city)
        if fun_facts:
            random_fact = random.choice(fun_facts)
            full_response += f"My friend, did you know {random_fact}"
    
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
            return f"I'm sorry my old chum but scanner bot was not able to find any jet planes nearby, because of {error_message.lower()}"
        else:
            return "I'm sorry my old chum but scanner bot was not able to find any jet planes nearby, because no passenger aircraft found within 100km radius"