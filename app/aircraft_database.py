import json
import os
from typing import Optional

class AircraftDatabase:
    """Aircraft database for looking up aircraft names by ICAO code"""
    
    def __init__(self):
        self._aircraft: Optional[dict] = None
    
    def _load_aircraft(self):
        """Load aircraft data from JSON file"""
        if self._aircraft is not None:
            return
            
        # Get the directory where this module is located
        current_dir = os.path.dirname(__file__)
        aircraft_file = os.path.join(current_dir, "aircraft.json")
        
        try:
            with open(aircraft_file, 'r', encoding='utf-8') as f:
                self._aircraft = json.load(f)
        except FileNotFoundError:
            self._aircraft = {}
    
    def get_aircraft_name(self, icao_code: str, use_simple_name: bool = True) -> str:
        """Get aircraft name by ICAO code

        Args:
            icao_code: Aircraft ICAO type code (e.g., 'A320', 'B737')
            use_simple_name: If True, returns simplified name (e.g., 'Boeing 787 Dreamliner'),
                           if False, returns technical name (e.g., 'Boeing 787-8')

        Returns:
            Aircraft name or "Unknown Aircraft" if not found
        """
        if not icao_code:
            return "Unknown Aircraft"

        self._load_aircraft()

        # Normalize ICAO code
        icao_code = icao_code.strip().upper()

        aircraft_data = self._aircraft.get(icao_code)
        if aircraft_data:
            if isinstance(aircraft_data, dict):
                # New structure with simple and technical names
                if use_simple_name:
                    return aircraft_data.get("simple_name", "Unknown Aircraft")
                else:
                    return aircraft_data.get("technical_name", "Unknown Aircraft")
            else:
                # Old structure (just a string) - fallback
                return aircraft_data
        else:
            return f"Unknown Aircraft ({icao_code})"

    def get_phonetic_name(self, icao_code: str) -> Optional[str]:
        """Get phonetic name for TTS pronunciation by ICAO code

        Args:
            icao_code: Aircraft ICAO type code (e.g., 'A320', 'B737')

        Returns:
            Phonetic name if available, None otherwise
        """
        if not icao_code:
            return None

        self._load_aircraft()

        # Normalize ICAO code
        icao_code = icao_code.strip().upper()

        aircraft_data = self._aircraft.get(icao_code)
        if aircraft_data and isinstance(aircraft_data, dict):
            return aircraft_data.get("phonetic_name")
        else:
            return None
    
    def get_passenger_capacity(self, icao_code: str) -> int:
        """Get passenger capacity by ICAO code

        Args:
            icao_code: Aircraft ICAO type code (e.g., 'A320', 'B737')

        Returns:
            Passenger capacity or 0 if not found
        """
        if not icao_code:
            return 0

        self._load_aircraft()

        # Normalize ICAO code
        icao_code = icao_code.strip().upper()

        aircraft_data = self._aircraft.get(icao_code)
        if aircraft_data and isinstance(aircraft_data, dict):
            return aircraft_data.get("passenger_capacity", 0)
        else:
            return 0

    def get_cruise_speed(self, icao_code: str) -> float:
        """Get cruise speed in km/h by ICAO code

        Args:
            icao_code: Aircraft ICAO type code (e.g., 'A320', 'B737')

        Returns:
            Cruise speed in km/h, or 840 (default narrow-body speed) if not found
        """
        if not icao_code:
            return 840  # Default: typical narrow-body

        self._load_aircraft()

        # Normalize ICAO code
        icao_code = icao_code.strip().upper()

        aircraft_data = self._aircraft.get(icao_code)
        if aircraft_data and isinstance(aircraft_data, dict):
            return aircraft_data.get("cruise_speed_kmh", 840)
        else:
            return 840

# Global instance for efficient reuse
_aircraft_db = AircraftDatabase()

def get_aircraft_name(icao_code: str, use_simple_name: bool = True) -> str:
    """Get aircraft name by ICAO code"""
    return _aircraft_db.get_aircraft_name(icao_code, use_simple_name)

def get_passenger_capacity(icao_code: str) -> int:
    """Get passenger capacity by ICAO code"""
    return _aircraft_db.get_passenger_capacity(icao_code)

def get_cruise_speed(icao_code: str) -> float:
    """Get cruise speed in km/h by ICAO code"""
    return _aircraft_db.get_cruise_speed(icao_code)

def get_phonetic_name(icao_code: str) -> Optional[str]:
    """Get phonetic name for TTS pronunciation by ICAO code"""
    return _aircraft_db.get_phonetic_name(icao_code)