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
    
    def get_city_by_name(self, city_name: str) -> Optional[Dict[str, Any]]:
        """Get city information by city name
        
        Args:
            city_name: Name of the city (e.g., 'Tokyo', 'New York')
            
        Returns:
            Dictionary with city information or None if not found
        """
        if not city_name:
            return None
            
        self._load_cities()
        
        # Normalize city name
        city_name = city_name.strip()
        
        # Direct lookup
        if city_name in self._cities:
            return self._cities[city_name]
        
        # Case-insensitive lookup
        for key, value in self._cities.items():
            if key.lower() == city_name.lower():
                return value
        
        return None
    
    def get_fun_facts(self, city_name: str) -> List[str]:
        """Get fun facts for a city by name
        
        Args:
            city_name: Name of the city
            
        Returns:
            List of fun facts or empty list if not found
        """
        city = self.get_city_by_name(city_name)
        if city:
            return city.get('fun_facts', [])
        return []
    
    def get_city_info(self, city_name: str) -> tuple[Optional[str], Optional[str], Optional[str], Optional[int]]:
        """Get city, state, country, and population for a city by name
        
        Args:
            city_name: Name of the city
            
        Returns:
            Tuple of (city, state, country, population) or (None, None, None, None) if not found
        """
        city = self.get_city_by_name(city_name)
        if city:
            return (
                city.get('city'),
                city.get('state'),
                city.get('country'),
                city.get('population')
            )
        return None, None, None, None
    
    def get_all_cities(self) -> List[str]:
        """Get list of all city names in the database
        
        Returns:
            List of city names
        """
        self._load_cities()
        return list(self._cities.keys())
    
    def search_cities_by_country(self, country: str) -> List[str]:
        """Get list of cities in a specific country
        
        Args:
            country: Country name or code
            
        Returns:
            List of city names in the country
        """
        self._load_cities()
        cities = []
        
        for city_name, city_data in self._cities.items():
            if city_data.get('country', '').lower() == country.lower():
                cities.append(city_name)
        
        return cities

# Global instance for efficient reuse
_cities_db = CitiesDatabase()

def get_city_by_name(city_name: str) -> Optional[Dict[str, Any]]:
    """Get city information by name"""
    return _cities_db.get_city_by_name(city_name)

def get_fun_facts(city_name: str) -> List[str]:
    """Get fun facts for a city by name"""
    return _cities_db.get_fun_facts(city_name)

def get_city_info(city_name: str) -> tuple[Optional[str], Optional[str], Optional[str], Optional[int]]:
    """Get city, state, country, and population for a city by name"""
    return _cities_db.get_city_info(city_name)

def get_all_cities() -> List[str]:
    """Get list of all city names in the database"""
    return _cities_db.get_all_cities()

def search_cities_by_country(country: str) -> List[str]:
    """Get list of cities in a specific country"""
    return _cities_db.search_cities_by_country(country)