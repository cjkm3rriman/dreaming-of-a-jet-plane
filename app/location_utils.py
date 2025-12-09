"""
Shared location detection utilities for consistent location handling across endpoints
"""

import logging
from fastapi import Request
import httpx
from ua_parser import user_agent_parser
import time
from typing import Dict, Tuple
import hashlib
import math

logger = logging.getLogger(__name__)

# IP location cache: {ip: (lat, lng, timestamp)}
_ip_cache: Dict[str, Tuple[float, float, float]] = {}
IP_CACHE_DURATION = 24 * 60 * 60  # 24 hours in seconds


def _track_ip_geolocation_failure(request: Request, ip: str, failure_type: str, fallback_lat: float, fallback_lng: float):
    """Track IP geolocation failure analytics event"""
    try:
        from .analytics import analytics
        
        client_ip = extract_client_ip(request)
        user_agent = extract_user_agent(request)
        browser_info = parse_user_agent(user_agent)
        
        # Create session ID
        hash_string = f"{client_ip or 'unknown'}:{user_agent or 'unknown'}:{fallback_lat or 0}:{fallback_lng or 0}"
        session_id = hashlib.md5(hash_string.encode('utf-8')).hexdigest()[:8]
        
        analytics.track_event("error:location", {
            "ip": client_ip,
            "$user_agent": user_agent,
            "$session_id": session_id,
            "$insert_id": f"ip_geo_fail_{session_id}_{ip}_{failure_type}",
            "browser": browser_info["browser"],
            "browser_version": browser_info["browser_version"],
            "os": browser_info["os"],
            "os_version": browser_info["os_version"],
            "device": browser_info["device"],
            "failure_type": failure_type,
            "target_ip": ip,
            "fallback_lat": fallback_lat,
            "fallback_lng": fallback_lng,
            "fallback_location": "NYC" if (fallback_lat == 40.7128 and fallback_lng == -74.0060) else "origin"
        })
        logger.info(f"Tracked IP geolocation failure: {failure_type} for IP {ip}")
    except Exception as e:
        logger.error(f"Failed to track IP geolocation failure event: {e}", exc_info=True)


async def get_location_from_ip(ip: str, request: Request = None) -> tuple[float, float]:
    """Get latitude and longitude from IP address using ipapi.co with 24-hour caching"""
    current_time = time.time()

    # Skip caching for localhost/development IPs to make testing easier
    is_localhost = ip in ['127.0.0.1', 'localhost', '::1']

    # Check cache first (skip for localhost)
    if not is_localhost and ip in _ip_cache:
        lat, lng, timestamp = _ip_cache[ip]
        if current_time - timestamp < IP_CACHE_DURATION:
            logger.info(f"Using cached location for IP {ip}: {lat}, {lng}")
            return lat, lng
        else:
            # Cache expired, remove entry
            del _ip_cache[ip]
    
    # Cache miss or expired - fetch from API
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"https://ipapi.co/{ip}/json/")
            if response.status_code == 200:
                data = response.json()
                
                # Check if API returned an error response
                if data.get("error", False):
                    error_reason = data.get("reason", "unknown_error")
                    logger.warning(f"IP geolocation API returned error for IP {ip}: {error_reason}")

                    # Use NYC fallback for API error responses
                    fallback_lat, fallback_lng = 40.7128, -74.0060
                    logger.info(f"Using NYC fallback for API error: {fallback_lat}, {fallback_lng}")

                    # Track API error response with fallback coordinates
                    if request:
                        _track_ip_geolocation_failure(request, ip, f"api_response_error_{error_reason.lower()}", fallback_lat, fallback_lng)

                    # Cache the fallback location (skip for localhost)
                    if not is_localhost:
                        _ip_cache[ip] = (fallback_lat, fallback_lng, current_time)

                    return fallback_lat, fallback_lng
                
                lat = data.get("latitude", 0.0)
                lng = data.get("longitude", 0.0)
                
                # Check if we got null/missing coordinates and use NYC fallback
                if lat == 0.0 and lng == 0.0:
                    fallback_lat, fallback_lng = 40.7128, -74.0060
                    logger.warning(f"IP geolocation API returned 0.0,0.0 for IP {ip}, using NYC fallback")
                    
                    # Track null coordinates event
                    if request:
                        _track_ip_geolocation_failure(request, ip, "api_response_null_coordinates", fallback_lat, fallback_lng)
                    
                    # Cache the fallback location (skip for localhost)
                    if not is_localhost:
                        _ip_cache[ip] = (fallback_lat, fallback_lng, current_time)
                    return fallback_lat, fallback_lng
                
                # Cache the result (skip for localhost)
                if not is_localhost:
                    _ip_cache[ip] = (lat, lng, current_time)
                    logger.info(f"Cached new location for IP {ip}: {lat}, {lng}")
                else:
                    logger.info(f"Skipping cache for localhost IP {ip}: {lat}, {lng}")
                return lat, lng
                
            elif response.status_code == 429:
                logger.warning(f"IP geolocation API rate limited for IP {ip}, using default location")
                # Cache the fallback location too (but for shorter duration, skip for localhost)
                fallback_lat, fallback_lng = 40.7128, -74.0060
                if not is_localhost:
                    _ip_cache[ip] = (fallback_lat, fallback_lng, current_time - IP_CACHE_DURATION + 300)  # Cache for 5 minutes only
                
                # Track rate limit event
                if request:
                    _track_ip_geolocation_failure(request, ip, "rate_limited", fallback_lat, fallback_lng)
                
                return fallback_lat, fallback_lng
            else:
                logger.warning(f"IP geolocation API returned status {response.status_code} for IP {ip}")
                
                # Track API error event
                if request:
                    _track_ip_geolocation_failure(request, ip, f"api_error_{response.status_code}", 0.0, 0.0)
                
    except Exception as e:
        logger.error(f"IP geolocation API error for IP {ip}: {e}")
        
        # Track API exception event
        if request:
            _track_ip_geolocation_failure(request, ip, "api_exception", 40.7128, -74.0060)
    
    # Use NYC fallback for any error case or missing coordinates
    fallback_lat, fallback_lng = 40.7128, -74.0060
    logger.info(f"Using NYC fallback location for IP {ip}: {fallback_lat}, {fallback_lng}")
    
    # Cache the fallback location (skip for localhost)
    if not (ip in ['127.0.0.1', 'localhost', '::1']):
        _ip_cache[ip] = (fallback_lat, fallback_lng, time.time())
    
    return fallback_lat, fallback_lng


def extract_client_ip(request: Request) -> str:
    """Extract client IP from request headers, handling proxies and CDNs"""
    client_ip = (
        request.headers.get("x-forwarded-for", "").split(",")[0].strip() or
        request.headers.get("x-real-ip") or
        request.headers.get("cf-connecting-ip") or  # Cloudflare
        request.client.host
    )
    return client_ip


def extract_user_agent(request: Request) -> str:
    """Extract user agent from request headers"""
    return request.headers.get("user-agent", "unknown")


def parse_user_agent(user_agent_string: str) -> dict:
    """Parse user agent string and return browser/device info"""
    try:
        parsed_ua = user_agent_parser.Parse(user_agent_string)
        
        # Extract browser info
        browser_info = {
            "browser": parsed_ua.get('user_agent', {}).get('family', 'Unknown'),
            "browser_version": parsed_ua.get('user_agent', {}).get('major', 'Unknown'),
            "os": parsed_ua.get('os', {}).get('family', 'Unknown'),
            "os_version": parsed_ua.get('os', {}).get('major', 'Unknown'),
            "device": parsed_ua.get('device', {}).get('family', 'Unknown')
        }
        
        # Special handling for Yoto Player devices
        if (user_agent_string == "ESP32 HTTP Client/1.0" and 
            browser_info["browser"] == "Other" and 
            browser_info["device"] == "Other" and 
            browser_info["os"] == "Other"):
            browser_info.update({
                "browser": "Yoto",
                "device": "Yoto Player",
                "os": "Yoto"
            })
        
        return browser_info
    except Exception:
        # Fallback if parsing fails
        return {
            "browser": "Unknown",
            "browser_version": "Unknown", 
            "os": "Unknown",
            "os_version": "Unknown",
            "device": "Unknown"
        }


def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the Haversine distance between two coordinates in kilometers"""
    R = 6371  # Earth's radius in kilometers

    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)

    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad

    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


def calculate_min_distance_to_route(
    point_lat: float,
    point_lng: float,
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float
) -> float:
    """
    Calculate the minimum distance from a point to a great circle route.

    Returns the closest distance in kilometers.
    """
    from geographiclib.geodesic import Geodesic

    try:
        geod = Geodesic.WGS84
        line = geod.InverseLine(origin_lat, origin_lng, dest_lat, dest_lng)
        route_distance_m = line.s13

        sample_interval_m = 100000  # 100 km
        num_samples = max(int(route_distance_m / sample_interval_m), 10)
        min_distance_km = float('inf')

        for i in range(num_samples + 1):
            distance_along_route = (i / num_samples) * route_distance_m
            position = line.Position(distance_along_route)
            sample_lat = position['lat2']
            sample_lng = position['lon2']

            distance_to_sample = calculate_distance(point_lat, point_lng, sample_lat, sample_lng)
            min_distance_km = min(min_distance_km, distance_to_sample)

        return min_distance_km

    except Exception as e:
        logger.error(f"Error calculating minimum distance to route: {e}", exc_info=True)
        return float('inf')


def is_point_near_route(
    point_lat: float,
    point_lng: float,
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
    max_distance_km: float = 500
) -> bool:
    """
    Determine if a point could reasonably be near a flight route between origin and destination.

    NOTE: Real aircraft don't fly perfect great circles! They follow:
    - Airways and air traffic control routes
    - Jet streams (especially trans-oceanic routes)
    - ETOPS restrictions for twin-engine aircraft
    - Weather avoidance
    - North Atlantic Tracks (NAT) which change daily

    This function uses multiple checks to balance accuracy with real-world route deviations:
    1. Great circle distance (with generous tolerance for route deviations)
    2. Endpoint proximity (if origin OR destination is nearby, likely valid)
    3. Geographic bounding box (user should be roughly "between" origin and destination)

    Args:
        point_lat: Latitude of the point to check (e.g., user location)
        point_lng: Longitude of the point to check
        origin_lat: Latitude of route origin airport
        origin_lng: Longitude of route origin airport
        dest_lat: Latitude of route destination airport
        dest_lng: Longitude of route destination airport
        max_distance_km: Maximum distance in km to consider "near" the route (default: 500km)

    Returns:
        True if the point could reasonably be on or near the flight route, False otherwise
    """
    # Check 1: Is user close to origin or destination airport?
    # If so, definitely valid (takeoff/landing/approach)
    distance_to_origin = calculate_distance(point_lat, point_lng, origin_lat, origin_lng)
    distance_to_dest = calculate_distance(point_lat, point_lng, dest_lat, dest_lng)

    ENDPOINT_PROXIMITY_KM = 300  # Within 300km of origin or destination
    if distance_to_origin < ENDPOINT_PROXIMITY_KM or distance_to_dest < ENDPOINT_PROXIMITY_KM:
        logger.debug(
            f"Route validation PASS: Point is near endpoint "
            f"(origin: {distance_to_origin:.0f}km, dest: {distance_to_dest:.0f}km)"
        )
        return True

    # Check 2: Is user roughly "between" origin and destination geographically?
    # This catches completely wrong routes like BNE->DFW showing in Connecticut
    lat_min = min(origin_lat, dest_lat) - 10  # 10 degree margin (~1100km)
    lat_max = max(origin_lat, dest_lat) + 10
    lng_min = min(origin_lng, dest_lng) - 10
    lng_max = max(origin_lng, dest_lng) + 10

    # Handle date line crossing for longitude
    if abs(origin_lng - dest_lng) > 180:
        # Route crosses date line, invert the check
        if not (lng_min <= point_lng <= lng_max):
            logger.debug(
                f"Route validation FAIL: Point outside geographic bounds of route "
                f"(lat range: {lat_min:.1f} to {lat_max:.1f}, lng range: {lng_min:.1f} to {lng_max:.1f}, "
                f"point: {point_lat:.1f}, {point_lng:.1f})"
            )
            return False
    else:
        # Normal case
        if not (lat_min <= point_lat <= lat_max and lng_min <= point_lng <= lng_max):
            logger.debug(
                f"Route validation FAIL: Point outside geographic bounds of route "
                f"(lat range: {lat_min:.1f} to {lat_max:.1f}, lng range: {lng_min:.1f} to {lng_max:.1f}, "
                f"point: {point_lat:.1f}, {point_lng:.1f})"
            )
            return False

    # Check 3: Calculate great circle distance with VERY generous tolerance
    # Trans-oceanic routes can deviate 1000+ km due to jet streams, NATs, ETOPS, etc.
    min_distance_km = calculate_min_distance_to_route(
        point_lat, point_lng, origin_lat, origin_lng, dest_lat, dest_lng
    )

    GENEROUS_TOLERANCE_KM = 1500  # Very generous for trans-oceanic route deviations
    if min_distance_km < GENEROUS_TOLERANCE_KM:
        logger.debug(
            f"Route validation PASS: Point is {min_distance_km:.0f}km from great circle "
            f"(within {GENEROUS_TOLERANCE_KM}km generous tolerance for route deviations)"
        )
        return True
    else:
        logger.warning(
            f"Route validation FAIL: Point is {min_distance_km:.0f}km from great circle "
            f"(exceeds {GENEROUS_TOLERANCE_KM}km tolerance)"
        )
        return False


async def get_user_location(request: Request, lat: float = None, lng: float = None) -> tuple[float, float]:
    """Get user location from URL parameters or IP geolocation
    
    Args:
        request: FastAPI Request object
        lat: Optional latitude from URL parameters
        lng: Optional longitude from URL parameters
        
    Returns:
        tuple: (latitude, longitude) as floats
    """
    if lat is not None and lng is not None:
        # Use provided coordinates
        logger.info(f"Using provided coordinates: lat={lat}, lng={lng}")
        return lat, lng
    else:
        # Get latitude and longitude from IP
        client_ip = extract_client_ip(request)
        user_lat, user_lng = await get_location_from_ip(client_ip, request)
        logger.info(f"Using IP-based location: lat={user_lat}, lng={user_lng} for IP {client_ip}")
        return user_lat, user_lng
