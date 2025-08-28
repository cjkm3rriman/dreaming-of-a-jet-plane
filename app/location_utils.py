"""
Shared location detection utilities for consistent location handling across endpoints
"""

import logging
from fastapi import Request
import httpx
from ua_parser import user_agent_parser
import time
from typing import Dict, Tuple

logger = logging.getLogger(__name__)

# IP location cache: {ip: (lat, lng, timestamp)}
_ip_cache: Dict[str, Tuple[float, float, float]] = {}
IP_CACHE_DURATION = 24 * 60 * 60  # 24 hours in seconds


async def get_location_from_ip(ip: str) -> tuple[float, float]:
    """Get latitude and longitude from IP address using ipapi.co with 24-hour caching"""
    current_time = time.time()
    
    # Check cache first
    if ip in _ip_cache:
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
                lat = data.get("latitude", 0.0)
                lng = data.get("longitude", 0.0)
                
                # Cache the result
                _ip_cache[ip] = (lat, lng, current_time)
                logger.info(f"Cached new location for IP {ip}: {lat}, {lng}")
                return lat, lng
                
            elif response.status_code == 429:
                logger.warning(f"IP geolocation API rate limited for IP {ip}, using default location")
                # Cache the fallback location too (but for shorter duration)
                fallback_lat, fallback_lng = 40.7128, -74.0060
                _ip_cache[ip] = (fallback_lat, fallback_lng, current_time - IP_CACHE_DURATION + 300)  # Cache for 5 minutes only
                return fallback_lat, fallback_lng
            else:
                logger.warning(f"IP geolocation API returned status {response.status_code} for IP {ip}")
                
    except Exception as e:
        logger.error(f"IP geolocation API error for IP {ip}: {e}")
    
    return 0.0, 0.0


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
        user_lat, user_lng = await get_location_from_ip(client_ip)
        logger.info(f"Using IP-based location: lat={user_lat}, lng={user_lng} for IP {client_ip}")
        return user_lat, user_lng