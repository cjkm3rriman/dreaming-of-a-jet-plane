"""FlightRadar24 provider implementation"""

import logging
import math
import os
from typing import Any, Dict, List, Optional, Tuple

import httpx

from ..aircraft_database import get_aircraft_name, get_passenger_capacity
from ..airline_database import get_airline_name, is_cargo_airline, is_private_airline
from ..airport_database import get_city_country
from ..location_utils import calculate_distance

DISPLAY_NAME = "FlightRadar24"

logger = logging.getLogger(__name__)

FR24_API_KEY = os.getenv("FR24_API_KEY")
FR24_BASE_URL = os.getenv("FR24_BASE_URL", "https://fr24api.flightradar24.com")


def is_configured() -> Tuple[bool, Optional[str]]:
    """Check whether the provider can be used"""
    if not FR24_API_KEY:
        return False, "FlightRadar24 API key not configured"
    return True, None


async def fetch_aircraft(lat: float, lng: float, radius_km: float, limit: int) -> Tuple[List[Dict[str, Any]], str]:
    """Fetch aircraft data from Flightradar24 within the bounding box"""
    configured, reason = is_configured()
    if not configured:
        return [], reason or "FlightRadar24 provider unavailable"

    lat_delta = radius_km / 111.0  # 1 degree lat ≈ 111 km
    lon_denominator = 111.0 * max(math.cos(math.radians(lat)), 0.01)
    lon_delta = radius_km / lon_denominator

    bounds = {
        "south": lat - lat_delta,
        "north": lat + lat_delta,
        "west": lng - lon_delta,
        "east": lng + lon_delta,
    }

    url = f"{FR24_BASE_URL}/api/live/flight-positions/full"
    headers = {
        "Authorization": f"Bearer {FR24_API_KEY}",
        "Accept": "application/json",
        "Accept-Version": "v1",
    }

    params = {
        "bounds": f"{bounds['north']:.3f},{bounds['south']:.3f},{bounds['west']:.3f},{bounds['east']:.3f}",
        "limit": max(limit, 5),
        "categories": "P",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers, params=params)

        if response.status_code != 200:
            error_msg = f"FlightRadar24 API returned HTTP {response.status_code}"
            logger.error(f"{error_msg}: Body={response.text[:500]}")
            return [], error_msg

        data = response.json()
        flights = data.get("data", [])
        aircraft_list: List[Dict[str, Any]] = []

        for flight in flights:
            aircraft_lat = flight.get("lat")
            aircraft_lon = flight.get("lon")
            if aircraft_lat is None or aircraft_lon is None:
                continue

            distance = calculate_distance(lat, lng, aircraft_lat, aircraft_lon)
            if distance > radius_km:
                continue

            callsign_value = flight.get("callsign")
            callsign = (callsign_value or "").strip()
            if not callsign:
                continue
            origin_iata = flight.get("orig_iata")
            dest_iata = flight.get("dest_iata")

            origin_city, origin_country = get_city_country(origin_iata) if origin_iata else (None, None)
            dest_city, dest_country = get_city_country(dest_iata) if dest_iata else (None, None)

            airline_icao = flight.get("painted_as")
            airline_name = get_airline_name(airline_icao) if airline_icao else None
            is_cargo = is_cargo_airline(airline_icao) if airline_icao else False
            is_private = is_private_airline(airline_icao) if airline_icao else False

            aircraft_info = {
                "icao24": flight.get("hex"),
                "callsign": callsign,
                "flight_number": flight.get("flight"),
                "airline_icao": airline_icao,
                "airline_name": airline_name,
                "is_cargo_operator": is_cargo,
                "is_private_operator": is_private,
                "aircraft_registration": flight.get("reg"),
                "aircraft_icao": flight.get("type"),
                "aircraft": get_aircraft_name(flight.get("type", "")),
                "passenger_capacity": get_passenger_capacity(flight.get("type", "")),
                "origin_airport": origin_iata,
                "origin_city": origin_city,
                "origin_country": origin_country,
                "destination_airport": dest_iata,
                "destination_city": dest_city,
                "destination_country": dest_country,
                "latitude": aircraft_lat,
                "longitude": aircraft_lon,
                "altitude": flight.get("alt", 0),
                "velocity": flight.get("gspeed", 0),
                "distance_km": round(distance),
                "distance_miles": round(distance * 0.621371),
                "status": None,
                "eta": flight.get("eta"),
            }

            aircraft_list.append(aircraft_info)

        logger.info(f"FlightRadar24 returned {len(aircraft_list)} aircraft candidates")
        return aircraft_list, "" if aircraft_list else "No passenger aircraft found within radius"

    except httpx.TimeoutException:
        logger.error("FlightRadar24 API Timeout: Request timed out after 10 seconds")
        return [], "FlightRadar24 API request timed out"
    except httpx.RequestError as exc:
        logger.error(f"FlightRadar24 API Connection Error: {exc}")
        return [], f"FlightRadar24 network connection error: {exc}"
