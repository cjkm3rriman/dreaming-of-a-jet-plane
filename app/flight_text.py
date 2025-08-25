"""
Shared flight text generation for consistent messaging across endpoints
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timezone


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
        detection_sentence = f"Jet plane detected in the sky overhead, currently about {distance_miles} miles from this Yoto player."
        
        # Add aircraft type, capacity, and speed information
        aircraft_name = closest_aircraft.get("aircraft", "unknown aircraft type")
        passenger_capacity = closest_aircraft.get("passenger_capacity", 0)
        velocity_knots = closest_aircraft.get("velocity", 0)
        velocity_mph = round(velocity_knots * 1.15078) if velocity_knots else 0
        
        # Build scanner sentence with capacity and speed
        scanner_info = f"My scanners tell me this is a {aircraft_name}"
        
        if passenger_capacity and passenger_capacity > 0:
            scanner_info += f" carrying {passenger_capacity} passengers"
            
        if velocity_mph > 0:
            scanner_info += f" travelling at {velocity_mph} miles per hour"
            
        scanner_sentence = scanner_info + "."
        
        # Build flight details sentence with ETA
        eta_string = closest_aircraft.get("eta")
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
                            eta_text = f" At its current speed it will be there in {hours} hour"
                        else:
                            eta_text = f" At its current speed it will be there in {hours} hours"
                        
                        if minutes > 0:
                            eta_text += f" and {minutes} minutes"
                    elif minutes > 0:
                        if minutes == 1:
                            eta_text = f" At its current speed it will be there in {minutes} minute"
                        else:
                            eta_text = f" At its current speed it will be there in {minutes} minutes"
                    else:
                        eta_text = " At its current speed it will be there very soon"
            except (ValueError, TypeError):
                # Invalid ETA timestamp
                pass
        
        if destination_city == "an unknown destination" or destination_country == "an unknown country":
            flight_sentence = f"Using my super vision I can see the jet plane is {flight_identifier}, travelling to an unknown destination.{eta_text}."
        else:
            flight_sentence = f"Using my super vision I can see the jet plane is {flight_identifier}, travelling to {destination_city} in {destination_country}.{eta_text}."
        
        return f"{detection_sentence} {scanner_sentence} {flight_sentence}"
    else:
        # Handle error cases with descriptive sentence
        if error_message:
            return f"I'm sorry old chum my scanner bot was not able to find any jet planes nearby, because of {error_message.lower()}"
        else:
            return "I'm sorry old chum my scanner bot was not able to find any jet planes nearby, because no passenger aircraft found within 100km radius"