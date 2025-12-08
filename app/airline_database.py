import json
import os
from typing import Optional, Dict, Any

class AirlineDatabase:
    """Airline database for looking up airline names by ICAO code"""
    
    def __init__(self):
        self._airlines: Optional[Dict[str, Any]] = None
    
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
    
    def _get_airline_entry(self, icao_code: str) -> Optional[Dict[str, Any]]:
        if not icao_code:
            return None

        self._load_airlines()
        icao_code = icao_code.strip().upper()
        entry = self._airlines.get(icao_code)

        if entry is None:
            return None

        if isinstance(entry, str):
            return {"name": entry, "cargo_only": False, "private_or_charter": False}

        if isinstance(entry, dict):
            return {
                "name": entry.get("name", "Unknown Airline"),
                "cargo_only": bool(entry.get("cargo_only", False)),
                "private_or_charter": bool(entry.get("private_or_charter", False)),
            }

        return None

    def get_airline_name(self, icao_code: str) -> Optional[str]:
        entry = self._get_airline_entry(icao_code)
        return entry.get("name") if entry else None

    def is_cargo_airline(self, icao_code: str) -> bool:
        entry = self._get_airline_entry(icao_code)
        return bool(entry and entry.get("cargo_only"))

    def is_private_airline(self, icao_code: str) -> bool:
        entry = self._get_airline_entry(icao_code)
        return bool(entry and entry.get("private_or_charter"))

# Global instance for efficient reuse
_airline_db = AirlineDatabase()

def get_airline_name(icao_code: str) -> Optional[str]:
    """Get airline name by ICAO code"""
    return _airline_db.get_airline_name(icao_code)

def is_cargo_airline(icao_code: str) -> bool:
    """Return True if airline is marked as cargo-only"""
    return _airline_db.is_cargo_airline(icao_code)

def is_private_airline(icao_code: str) -> bool:
    """Return True if airline is marked as private/charter"""
    return _airline_db.is_private_airline(icao_code)
