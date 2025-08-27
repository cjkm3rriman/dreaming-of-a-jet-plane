"""
Shared location detection utilities for consistent location handling across endpoints
"""

import logging
from fastapi import Request
import httpx

logger = logging.getLogger(__name__)


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