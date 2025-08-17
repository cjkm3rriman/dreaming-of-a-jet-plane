from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
import httpx
import math
import os
import re
from typing import List, Dict, Any, Optional
from .aircraft_database import get_aircraft_name
from .intro import stream_intro, intro_options

app = FastAPI()

# FlightLabs API configuration
FLIGHTLABS_API_KEY = os.getenv("FLIGHTLABS_API_KEY")
FLIGHTLABS_BASE_URL = "https://www.goflightlabs.com"

def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two points using Haversine formula (in km)"""
    R = 6371  # Earth's radius in kilometers
    
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)
    
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    
    a = math.sin(dlat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    
    return R * c

def is_likely_commercial(callsign: str, category: int = None) -> bool:
    """Determine if an aircraft is likely a commercial flight"""
    if not callsign or callsign == "Unknown":
        return False
    
    callsign = callsign.strip().upper()
    
    # Filter out obviously non-commercial callsigns
    non_commercial_patterns = [
        # Private aircraft (typically start with N in US, G- in UK, etc.)
        r'^N\d+[A-Z]*$',  # US private aircraft (N123AB, N456CD)
        r'^G-[A-Z]+$',    # UK private aircraft  
        r'^D-[A-Z]+$',    # German private aircraft
        r'^F-[A-Z]+$',    # French private aircraft
        
        # Special purpose flights
        r'LIFEGUARD',     # Medical flights
        r'RESCUE',        # Search and rescue
        r'POLICE',        # Police flights
        r'MEDEVAC',       # Medical evacuation
        r'FIRE',          # Fire fighting
        
        # Military patterns (common ones)
        r'^RCH\d+$',      # US Military
        r'^CNV\d+$',      # US Military convoy
        r'^REACH\d+$',    # US Military
        
        # Test flights
        r'TEST\d+',
        r'FLIGHT\d+',
    ]
    
    for pattern in non_commercial_patterns:
        if re.match(pattern, callsign):
            return False
    
    # Commercial airline callsigns typically follow patterns:
    # 3-letter airline code + flight number (UAL123, DAL456, SWA789)
    commercial_patterns = [
        r'^[A-Z]{3}\d+[A-Z]?$',     # Standard airline format (UAL123, SWA456A)
        r'^[A-Z]{2}\d+[A-Z]?$',     # Some airlines use 2-letter codes
    ]
    
    for pattern in commercial_patterns:
        if re.match(pattern, callsign):
            # Additional check: must be reasonable flight number (not too high)
            flight_num = ''.join(filter(str.isdigit, callsign))
            if flight_num and 1 <= int(flight_num) <= 9999:
                return True
    
    # Category-based filtering (if available)
    # Categories 2-6 are typically commercial aircraft categories
    if category is not None and 2 <= category <= 6:
        return True
    
    return False

async def get_flight_details(icao24: str) -> Optional[Dict[str, Any]]:
    """Get detailed flight information from FlightLabs API using ICAO24 address"""
    if not FLIGHTLABS_API_KEY:
        return None
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{FLIGHTLABS_BASE_URL}/flights",
                params={
                    "access_key": FLIGHTLABS_API_KEY,
                    "icao24": icao24.strip()
                },
                timeout=5.0
            )
            
            if response.status_code == 200:
                data = response.json()
                if data and isinstance(data, list) and len(data) > 0:
                    flight = data[0]  # Take first matching flight
                    aircraft_icao = flight.get("aircraft_icao", "")
                    
                    return {
                        "airline_iata": flight.get("airline_iata"),
                        "airline_icao": flight.get("airline_icao"), 
                        "flight_number": flight.get("flight_number"),
                        "aircraft_registration": flight.get("reg_number"),
                        "aircraft_icao": aircraft_icao,
                        "aircraft": get_aircraft_name(aircraft_icao),
                        "origin_airport": flight.get("dep_iata"),
                        "destination_airport": flight.get("arr_iata"),
                        "origin_country": flight.get("dep_country"),
                        "destination_country": flight.get("arr_country"),
                        "status": flight.get("flight_status")
                    }
            else:
                # Return error info for non-200 responses
                return {"error": f"FlightLabs API returned status {response.status_code}"}
                
    except httpx.TimeoutException:
        # Specific timeout error
        return {"error": "FlightLabs API timeout (5 seconds exceeded)"}
    except httpx.RequestError as e:
        # Network/connection errors
        return {"error": f"FlightLabs API connection error: {str(e)}"}
    except Exception as e:
        # Other unexpected errors
        return {"error": f"FlightLabs API unexpected error: {str(e)}"}
    
    return None

async def get_nearby_aircraft(lat: float, lng: float, radius_km: float = 100) -> List[Dict[str, Any]]:
    """Get aircraft near the given coordinates using OpenSky Network API"""
    try:
        # Create bounding box (approximate)
        lat_delta = radius_km / 111.0  # 1 degree lat ≈ 111 km
        lon_delta = radius_km / (111.0 * math.cos(math.radians(lat)))  # Adjust for longitude
        
        lamin = lat - lat_delta
        lamax = lat + lat_delta
        lomin = lng - lon_delta
        lomax = lng + lon_delta
        
        url = f"https://opensky-network.org/api/states/all?extended=1&lamin={lamin}&lomin={lomin}&lamax={lamax}&lomax={lomax}"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=10.0)
            if response.status_code == 200:
                data = response.json()
                states = data.get("states", [])
                
                aircraft_list = []
                for state in states:
                    if len(state) >= 7 and state[6] is not None and state[5] is not None:
                        aircraft_lat = state[6]
                        aircraft_lon = state[5]
                        distance = calculate_distance(lat, lng, aircraft_lat, aircraft_lon)
                        
                        icao24 = state[0] if state[0] else None
                        callsign = state[1].strip() if state[1] else "Unknown"
                        # Category from extended data (safer access)
                        category = None
                        if len(state) > 17 and state[17] is not None:
                            category = state[17]
                        
                        # Filter for likely commercial aircraft only
                        try:
                            if not is_likely_commercial(callsign, category):
                                continue
                        except Exception:
                            # If filtering fails, skip this aircraft
                            continue
                        
                        aircraft_info = {
                            "icao24": icao24,
                            "callsign": callsign,
                            "country": state[2] if state[2] else "Unknown",
                            "latitude": aircraft_lat,
                            "longitude": aircraft_lon,
                            "altitude": state[7] if state[7] else 0,
                            "velocity": state[9] if state[9] else 0,
                            "heading": state[10] if state[10] else 0,
                            "distance_km": round(distance, 2),
                            "category": category,
                            "is_commercial": True
                        }
                        
                        aircraft_list.append(aircraft_info)
                
                # Sort by distance and get only the closest aircraft
                aircraft_list.sort(key=lambda x: x["distance_km"])
                
                # Only call FlightLabs for the closest aircraft
                if aircraft_list and len(aircraft_list) > 0:
                    closest_aircraft = aircraft_list[0]
                    icao24 = closest_aircraft.get("icao24")
                    
                    # Try to get detailed flight information using ICAO24
                    if icao24 and FLIGHTLABS_API_KEY:
                        flight_details = await get_flight_details(icao24)
                        if flight_details:
                            if "error" in flight_details:
                                closest_aircraft["flight_details_error"] = flight_details["error"]
                            else:
                                closest_aircraft["flight_details"] = flight_details
                        else:
                            closest_aircraft["flight_details_error"] = "No flight data returned from FlightLabs API"
                    elif icao24 and not FLIGHTLABS_API_KEY:
                        closest_aircraft["flight_details_error"] = "FlightLabs API key not configured"
                    elif not icao24:
                        closest_aircraft["flight_details_error"] = "No ICAO24 address available for this aircraft"
                
                return aircraft_list[:1]
    
    except Exception:
        pass
    
    return []

async def get_location_from_ip(ip: str) -> tuple[float, float]:
    """Get latitude and longitude from IP address using ipapi.co"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"https://ipapi.co/{ip}/json/")
            if response.status_code == 200:
                data = response.json()
                return data.get("latitude", 0.0), data.get("longitude", 0.0)
    except Exception:
        pass
    return 0.0, 0.0

@app.get("/")
async def read_root(request: Request):
    # Check for real IP in common proxy headers
    client_ip = (
        request.headers.get("x-forwarded-for", "").split(",")[0].strip() or
        request.headers.get("x-real-ip") or
        request.headers.get("cf-connecting-ip") or  # Cloudflare
        request.client.host
    )
    
    # Get latitude and longitude from IP
    lat, lng = await get_location_from_ip(client_ip)
    
    # Get nearby aircraft
    aircraft = await get_nearby_aircraft(lat, lng)
    
    # If we found commercial aircraft, return detailed info about the closest one
    if aircraft and len(aircraft) > 0:
        closest_aircraft = aircraft[0]
        return {
            "ip_address": client_ip,
            "latitude": lat,
            "longitude": lng,
            "closest_commercial_aircraft": closest_aircraft
        }
    else:
        return {
            "ip_address": client_ip,
            "latitude": lat,
            "longitude": lng,
            "closest_commercial_aircraft": None,
            "message": "No commercial aircraft found nearby"
        }

@app.get("/intro.mp3")
async def intro_endpoint(request: Request):
    """Stream MP3 file from S3"""
    return await stream_intro(request)

@app.options("/intro.mp3") 
async def intro_options_endpoint():
    """Handle CORS preflight requests for /intro.mp3 endpoint"""
    return await intro_options()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)