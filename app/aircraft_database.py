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
    
    def get_aircraft_name(self, icao_code: str) -> str:
        """Get aircraft name by ICAO code
        
        Args:
            icao_code: Aircraft ICAO type code (e.g., 'A320', 'B737')
            
        Returns:
            Aircraft name or "Unknown Aircraft" if not found
        """
        if not icao_code:
            return "Unknown Aircraft"
            
        self._load_aircraft()
        
        # Normalize ICAO code
        icao_code = icao_code.strip().upper()
        
        aircraft_name = self._aircraft.get(icao_code)
        if aircraft_name:
            return aircraft_name
        else:
            return f"Unknown Aircraft ({icao_code})"

# Global instance for efficient reuse
_aircraft_db = AircraftDatabase()

def get_aircraft_name(icao_code: str) -> str:
    """Get aircraft name by ICAO code"""
    return _aircraft_db.get_aircraft_name(icao_code)