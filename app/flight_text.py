"""
Shared flight text generation for consistent messaging across endpoints
"""

from typing import List, Dict, Any, Optional


def generate_flight_text(aircraft: List[Dict[str, Any]], error_message: Optional[str] = None) -> str:
    """Generate descriptive text about detected aircraft or no-aircraft conditions
    
    Args:
        aircraft: List of aircraft data (empty list if no aircraft found)
        error_message: Optional error message if aircraft detection failed
        
    Returns:
        str: Human-readable sentence describing the flight situation
    """
    if aircraft and len(aircraft) > 0:
        closest_aircraft = aircraft[0]
        
        # Extract values for the sentence template
        distance_miles = closest_aircraft.get("distance_miles", "unknown")
        flight_number = closest_aircraft.get("flight_number") or closest_aircraft.get("callsign", "unknown flight")
        airline_name = closest_aircraft.get("airline_name")
        destination_city = closest_aircraft.get("destination_city", "an unknown destination")
        destination_country = closest_aircraft.get("destination_country", "an unknown country")
        
        # Build flight identifier with airline name if available
        if airline_name:
            flight_identifier = f"{airline_name} flight {flight_number}"
        else:
            flight_identifier = f"flight {flight_number}"
        
        # Build the descriptive sentences
        detection_sentence = f"Jet plane detected in the sky overhead {distance_miles} miles from your Yoto player."
        
        if destination_city == "an unknown destination" or destination_country == "an unknown country":
            flight_sentence = f"This is {flight_identifier}, travelling to an unknown destination."
        else:
            flight_sentence = f"This is {flight_identifier}, travelling to {destination_city} in {destination_country}."
        
        return f"{detection_sentence} {flight_sentence}"
    else:
        # Handle error cases with descriptive sentence
        if error_message:
            return f"No aircraft detected nearby, because of {error_message.lower()}"
        else:
            return "No aircraft detected nearby, because no passenger aircraft found within 100km radius"