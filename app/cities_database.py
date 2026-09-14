import json
import os
from typing import Optional, Dict, Any, List

class CitiesDatabase:
    """Cities database for looking up city information and fun facts"""
    
    def __init__(self):
        self._cities: Optional[Dict[str, Dict[str, Any]]] = None
    
    def _load_cities(self):
        """Load cities data from JSON file"""
        if self._cities is not None:
            return
            
        # Get the directory where this module is located
        current_dir = os.path.dirname(__file__)
        cities_file = os.path.join(current_dir, "cities.json")
        
        try:
            with open(cities_file, 'r', encoding='utf-8') as f:
                self._cities = json.load(f)
        except FileNotFoundError:
            self._cities = {}
    
    def get_city_by_name(self, city_name: str, state: str = None, country: str = None) -> Optional[Dict[str, Any]]:
        """Get city information by city name, with optional state/country for disambiguation
        
        Args:
            city_name: Name of the city (e.g., 'Tokyo', 'New York', 'Portland')
            state: Optional state name for US cities (e.g., 'Oregon', 'Maine')
            country: Optional country name for additional context
            
        Returns:
            Dictionary with city information or None if not found
        """
        if not city_name:
            return None
            
        self._load_cities()
        
        # Normalize city name
        city_name = city_name.strip()
        
        # For US cities, try "City, State" format first if state is provided
        if state and country and country.lower() in ["united states", "the united states", "us", "usa"]:
            combined_key = f"{city_name}, {state}"
            if combined_key in self._cities:
                return self._cities[combined_key]
            
            # Case-insensitive lookup for "City, State" format
            for key, value in self._cities.items():
                if key.lower() == combined_key.lower():
                    return value
        
        # For non-US cities, try "City, Country" format if country is provided
        if country and (not state or country.lower() not in ["united states", "the united states", "us", "usa"]):
            combined_key = f"{city_name}, {country}"
            if combined_key in self._cities:
                return self._cities[combined_key]

            # Case-insensitive lookup for "City, Country" format
            for key, value in self._cities.items():
                if key.lower() == combined_key.lower():
                    return value

        # Direct lookup with city name only
        if city_name in self._cities:
            return self._cities[city_name]

        # Case-insensitive lookup with city name only
        for key, value in self._cities.items():
            if key.lower() == city_name.lower():
                return value

        return None
    
    def get_fun_facts(self, city_name: str, state: str = None, country: str = None) -> List[str]:
        """Get fun facts for a city by name
        
        Args:
            city_name: Name of the city
            state: Optional state name for US cities
            country: Optional country name for additional context
            
        Returns:
            List of fun facts or empty list if not found
        """
        city = self.get_city_by_name(city_name, state, country)
        if city:
            return city.get('fun_facts', [])
        return []
    
# Global instance for efficient reuse
_cities_db = CitiesDatabase()

def get_city_by_name(city_name: str, state: str = None, country: str = None) -> Optional[Dict[str, Any]]:
    """Get city information by name"""
    return _cities_db.get_city_by_name(city_name, state, country)

def get_fun_facts(city_name: str, state: str = None, country: str = None) -> List[str]:
    """Get fun facts for a city by name"""
    return _cities_db.get_fun_facts(city_name, state, country)
