import json
import os
from typing import Optional

class AirlineDatabase:
    """Airline database for looking up airline names by ICAO code"""
    
    def __init__(self):
        self._airlines: Optional[dict] = None
    
    def _load_airlines(self):
        """Load airlines data from JSON file"""
        if self._airlines is not None:
            return
            
        # Get the directory where this module is located
        current_dir = os.path.dirname(__file__)
        airlines_file = os.path.join(current_dir, "airlines.json")
        
        try:
            with open(airlines_file, 'r', encoding='utf-8') as f:
                self._airlines = json.load(f)
        except FileNotFoundError:
            self._airlines = {}
    
    def get_airline_name(self, icao_code: str) -> Optional[str]:
        """Get airline name by ICAO code
        
        Args:
            icao_code: 3-letter ICAO airline code (e.g., 'OCN', 'AAL')
            
        Returns:
            Airline name or None if not found
        """
        if not icao_code:
            return None
            
        self._load_airlines()
        
        # Normalize ICAO code
        icao_code = icao_code.strip().upper()
        
        return self._airlines.get(icao_code)

# Global instance for efficient reuse
_airline_db = AirlineDatabase()

def get_airline_name(icao_code: str) -> Optional[str]:
    """Get airline name by ICAO code"""
    return _airline_db.get_airline_name(icao_code)