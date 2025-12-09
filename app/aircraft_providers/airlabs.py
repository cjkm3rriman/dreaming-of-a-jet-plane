"""Airlabs provider implementation"""

import logging
import math
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

from ..aircraft_database import get_aircraft_name, get_passenger_capacity
from ..airport_database import get_city_country, get_airport_by_iata
from ..airline_database import get_airline_name, is_cargo_airline, is_private_airline
from ..location_utils import calculate_distance, is_point_near_route

ESTIMATED_SPEED_KMH = 400 * 1.60934  # Assume constant cruise speed
LANDING_BUFFER_MINUTES = 30
AIRLINE_OVERRIDES = {
    "EDV": {"airline_icao": "DAL", "airline_iata": "DL"},
    "PDT": {"airline_icao": "EGF", "airline_iata": "MQ"},
    "JIA": {"airline_icao": "EGF", "airline_iata": "MQ"},
    "ENY": {"airline_icao": "EGF", "airline_iata": "MQ"},
    "GJS": {"airline_icao": "UAL", "airline_iata": "UA"},
    "QXE": {"airline_icao": "ASA", "airline_iata": "AS"},
}

DISPLAY_NAME = "Airlabs"

logger = logging.getLogger(__name__)

AIRLABS_API_KEY = os.getenv("AIRLABS_API_KEY")
AIRLABS_BASE_URL = os.getenv("AIRLABS_BASE_URL", "https://airlabs.co/api/v9")


def _estimate_eta(distance_km: float) -> Optional[str]:
    """Estimate ETA using a fixed cruise speed plus landing buffer"""
    if distance_km is None or distance_km <= 0:
        return None

    if ESTIMATED_SPEED_KMH <= 0:
        return None

    travel_hours = distance_km / ESTIMATED_SPEED_KMH
    travel_hours += LANDING_BUFFER_MINUTES / 60

    eta_datetime = datetime.now(timezone.utc) + timedelta(hours=travel_hours)
    return eta_datetime.isoformat().replace("+00:00", "Z")


def is_configured() -> Tuple[bool, Optional[str]]:
    """Check whether the Airlabs provider is usable"""
    if not AIRLABS_API_KEY:
        return False, "Airlabs API key not configured"
    return True, None


async def fetch_aircraft(lat: float, lng: float, radius_km: float, limit: int) -> Tuple[List[Dict[str, Any]], str]:
    """Fetch aircraft data from Airlabs using a bounding box"""
    configured, reason = is_configured()
    if not configured:
        return [], reason or "Airlabs provider unavailable"

    lat_delta = radius_km / 111.0
    lon_denominator = 111.0 * max(math.cos(math.radians(lat)), 0.01)
    lon_delta = radius_km / lon_denominator

    bounds = {
        "south": lat - lat_delta,
        "north": lat + lat_delta,
        "west": lng - lon_delta,
        "east": lng + lon_delta,
    }

    params = {
        "bbox": f"{bounds['south']:.3f},{bounds['west']:.3f},{bounds['north']:.3f},{bounds['east']:.3f}",
        "limit": max(limit, 5),
        "api_key": AIRLABS_API_KEY,
        "_fields": "lat,lng,status,updated,aircraft_icao,airline_icao,airline_iata,flight_number,dep_iata,arr_iata,speed,alt,reg_number",
    }

    url = f"{AIRLABS_BASE_URL}/flights"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params=params)

        if response.status_code != 200:
            error_msg = f"Airlabs API returned HTTP {response.status_code}"
            logger.error(f"{error_msg}: Body={response.text[:500]}")
            return [], error_msg

        data = response.json()
        flights = data.get("response") or data.get("data") or []
        error_info = data.get("error")
        if error_info:
            error_message = error_info if isinstance(error_info, str) else error_info.get("message")
            logger.warning(f"Airlabs API error payload: {error_info}")
            return [], error_message or "Airlabs API returned an error"

        aircraft_list: List[Dict[str, Any]] = []

        for flight in flights:
            status = (flight.get("status") or "").strip().lower()
            if status != "en-route":
                continue

            aircraft_lat = flight.get("lat")
            aircraft_lon = flight.get("lng") if flight.get("lng") is not None else flight.get("lon")
            if aircraft_lat is None or aircraft_lon is None:
                continue

            distance = calculate_distance(lat, lng, aircraft_lat, aircraft_lon)
            if distance > radius_km:
                continue

            callsign = (
                flight.get("flight_icao")
                or flight.get("flight_number")
                or flight.get("hex")
                or "Unknown"
            )
            origin_iata = flight.get("dep_iata")
            dest_iata = flight.get("arr_iata")

            # Validate aircraft position makes sense for its route using great circle math
            # Skip aircraft whose flight path doesn't pass near the user
            if origin_iata and dest_iata:
                origin_airport = get_airport_by_iata(origin_iata)
                dest_airport = get_airport_by_iata(dest_iata)

                if origin_airport and dest_airport:
                    origin_lat = origin_airport.get("lat")
                    origin_lon = origin_airport.get("lon")
                    dest_lat = dest_airport.get("lat")
                    dest_lon = dest_airport.get("lon")

                    if all([origin_lat, origin_lon, dest_lat, dest_lon]):
                        # Validate if the flight route could reasonably pass near the user
                        # Uses multiple checks: endpoint proximity, geographic bounds, and generous great circle tolerance
                        route_is_valid = is_point_near_route(
                            point_lat=lat,
                            point_lng=lng,
                            origin_lat=origin_lat,
                            origin_lng=origin_lon,
                            dest_lat=dest_lat,
                            dest_lng=dest_lon
                        )

                        if not route_is_valid:
                            logger.warning(
                                f"Skipping aircraft with invalid route: {callsign} at ({aircraft_lat:.2f}, {aircraft_lon:.2f}) "
                                f"reports {origin_iata}→{dest_iata} route, which doesn't pass near user location. "
                                f"This is likely stale/incorrect position data from Airlabs API."
                            )
                            continue

            origin_city, origin_country = get_city_country(origin_iata) if origin_iata else (None, None)
            dest_city, dest_country = get_city_country(dest_iata) if dest_iata else (None, None)

            eta_estimate = None
            if dest_iata and aircraft_lat is not None and aircraft_lon is not None:
                dest_airport = get_airport_by_iata(dest_iata)
                if dest_airport:
                    dest_lat = dest_airport.get("lat")
                    dest_lon = dest_airport.get("lon")
                    if dest_lat is not None and dest_lon is not None:
                        try:
                            distance_to_dest = calculate_distance(
                                aircraft_lat, aircraft_lon, dest_lat, dest_lon
                            )
                            eta_estimate = _estimate_eta(distance_to_dest)
                        except Exception as exc:
                            logger.debug(
                                "Failed to estimate ETA for Airlabs flight %s: %s",
                                flight.get("flight_number") or flight.get("hex"),
                                exc,
                            )

            airline_icao = flight.get("airline_icao") or flight.get("airline_code")
            airline_iata = flight.get("airline_iata")
            if airline_icao:
                override = AIRLINE_OVERRIDES.get(airline_icao.strip().upper())
                if override:
                    airline_icao = override.get("airline_icao", airline_icao)
                    airline_iata = override.get("airline_iata", airline_iata)
            if airline_icao and airline_icao.upper() in IGNORE_AIRLINES_ICAO:
                continue
            airline_name = get_airline_name(airline_icao) if airline_icao else None
            is_cargo = is_cargo_airline(airline_icao) if airline_icao else False
            is_private = is_private_airline(airline_icao) if airline_icao else False

            flight_iata = flight.get("flight_iata")
            raw_flight_number = flight.get("flight_number")
            if flight_iata:
                formatted_flight_number = flight_iata
            elif airline_iata and raw_flight_number:
                formatted_flight_number = f"{airline_iata}{raw_flight_number}"
            else:
                formatted_flight_number = raw_flight_number

            aircraft_type = flight.get("aircraft_icao") or flight.get("aircraft_type") or ""

            aircraft_info = {
                "icao24": flight.get("hex"),
                "callsign": callsign,
                "flight_number": formatted_flight_number,
                "airline_icao": airline_icao,
                "airline_name": airline_name,
                "is_cargo_operator": is_cargo,
                "is_private_operator": is_private,
                "aircraft_registration": flight.get("reg_number") or flight.get("registration"),
                "aircraft_icao": aircraft_type,
                "aircraft": get_aircraft_name(aircraft_type),
                "passenger_capacity": get_passenger_capacity(aircraft_type),
                "origin_airport": origin_iata,
                "origin_city": origin_city,
                "origin_country": origin_country,
                "destination_airport": dest_iata,
                "destination_city": dest_city,
                "destination_country": dest_country,
                "latitude": aircraft_lat,
                "longitude": aircraft_lon,
                "altitude": None if flight.get("alt") is None or flight.get("alt", 0) * 3.28084 < 1000 else round(flight.get("alt", 0) * 3.28084),
                "velocity": None if flight.get("speed") is None or flight.get("speed", 0) * 0.539957 < 100 else round(flight.get("speed", 0) * 0.539957),
                "distance_km": round(distance),
                "distance_miles": round(distance * 0.621371),
                "status": flight.get("status"),
                "eta": flight.get("arr_time") or eta_estimate,
                "updated": flight.get("updated"),
            }

            aircraft_list.append(aircraft_info)

        aircraft_list.sort(key=lambda x: x.get("distance_km", float("inf")))

        if len(aircraft_list) > 5:
            filters = [
                lambda a: bool(a.get("airline_name")),
                lambda a: bool(a.get("velocity")),
            ]

            for predicate in filters:
                filtered = [a for a in aircraft_list if predicate(a)]
                if len(filtered) >= 5:
                    aircraft_list = filtered
                else:
                    break

        logger.info(f"Airlabs returned {len(aircraft_list)} aircraft candidates")
        return aircraft_list, "" if aircraft_list else "No aircraft reported by Airlabs"

    except httpx.TimeoutException:
        logger.error("Airlabs API Timeout: Request timed out after 10 seconds")
        return [], "Airlabs API request timed out"
    except httpx.RequestError as exc:
        logger.error(f"Airlabs API Connection Error: {exc}")
        return [], f"Airlabs network connection error: {exc}"
IGNORE_AIRLINES_ICAO = {"VJA"}
