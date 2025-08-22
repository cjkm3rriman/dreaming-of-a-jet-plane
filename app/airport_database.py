import json
import os
from typing import Optional, Dict, Any

class AirportDatabase:
    """Airport database for looking up airport information by IATA code"""
    
    def __init__(self):
        self._airports: Optional[Dict[str, Dict[str, Any]]] = None
        self._iata_index: Optional[Dict[str, str]] = None
    
    def _load_airports(self):
        """Load airports data from JSON file and create IATA index"""
        if self._airports is not None:
            return
            
        # Get the directory where this module is located
        current_dir = os.path.dirname(__file__)
        airports_file = os.path.join(current_dir, "airports.json")
        
        try:
            with open(airports_file, 'r') as f:
                self._airports = json.load(f)
            
            # Create IATA code index for faster lookups
            self._iata_index = {}
            for airport_code, airport_data in self._airports.items():
                iata = airport_data.get('iata', '').strip()
                if iata:
                    self._iata_index[iata] = airport_code
                    
        except FileNotFoundError:
            self._airports = {}
            self._iata_index = {}
    
    def get_airport_by_iata(self, iata_code: str) -> Optional[Dict[str, Any]]:
        """Get airport information by IATA code
        
        Args:
            iata_code: 3-letter IATA airport code (e.g., 'LAX', 'JFK')
            
        Returns:
            Dictionary with airport information or None if not found
        """
        if not iata_code:
            return None
            
        self._load_airports()
        
        # Normalize IATA code
        iata_code = iata_code.strip().upper()
        
        # Look up airport using IATA index
        airport_key = self._iata_index.get(iata_code)
        if airport_key:
            return self._airports.get(airport_key)
        
        return None
    
    def get_city_country(self, iata_code: str) -> tuple[Optional[str], Optional[str]]:
        """Get city and country for an airport by IATA code
        
        Args:
            iata_code: 3-letter IATA airport code
            
        Returns:
            Tuple of (city, country) or (None, None) if not found
        """
        airport = self.get_airport_by_iata(iata_code)
        if airport:
            return airport.get('city'), airport.get('country')
        return None, None
    
    def get_airport_name(self, iata_code: str) -> Optional[str]:
        """Get airport name by IATA code
        
        Args:
            iata_code: 3-letter IATA airport code
            
        Returns:
            Airport name or None if not found
        """
        airport = self.get_airport_by_iata(iata_code)
        if airport:
            return airport.get('name')
        return None

# Global instance for efficient reuse
_airport_db = AirportDatabase()

def get_airport_by_iata(iata_code: str) -> Optional[Dict[str, Any]]:
    """Get airport information by IATA code"""
    return _airport_db.get_airport_by_iata(iata_code)

def get_city_country(iata_code: str) -> tuple[Optional[str], Optional[str]]:
    """Get city and country for an airport by IATA code"""
    return _airport_db.get_city_country(iata_code)

def get_airport_name(iata_code: str) -> Optional[str]:
    """Get airport name by IATA code"""
    return _airport_db.get_airport_name(iata_code)