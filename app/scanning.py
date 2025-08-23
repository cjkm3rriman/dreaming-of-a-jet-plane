"""
Scanning endpoint for streaming MP3 file from S3 and pre-generating flight MP3
"""

import asyncio
import logging
from fastapi import Request
from fastapi.responses import StreamingResponse
import httpx
from .s3_cache import s3_cache

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


async def pre_generate_flight_mp3(lat: float, lng: float):
    """Background task to pre-generate and cache flight MP3"""
    try:
        logger.info(f"Starting MP3 pre-generation for location: lat={lat}, lng={lng}")
        
        # Import here to avoid circular imports
        from .main import get_nearby_aircraft, convert_text_to_speech
        
        # Get flight data
        aircraft, error_message = await get_nearby_aircraft(lat, lng)
        
        # Generate the same sentence as main endpoint
        if aircraft and len(aircraft) > 0:
            closest_aircraft = aircraft[0]
            
            distance_miles = closest_aircraft.get("distance_miles", "unknown")
            flight_number = closest_aircraft.get("flight_number") or closest_aircraft.get("callsign", "unknown flight")
            airline_name = closest_aircraft.get("airline_name")
            destination_city = closest_aircraft.get("destination_city", "an unknown destination")
            destination_country = closest_aircraft.get("destination_country", "an unknown country")
            
            if airline_name:
                flight_identifier = f"{airline_name} flight {flight_number}"
            else:
                flight_identifier = f"flight {flight_number}"
            
            detection_sentence = f"Jet plane detected in the sky overhead {distance_miles} miles from your Yoto player."
            
            if destination_city == "an unknown destination" or destination_country == "an unknown country":
                flight_sentence = f"This is {flight_identifier}, travelling to an unknown destination."
            else:
                flight_sentence = f"This is {flight_identifier}, travelling to {destination_city} in {destination_country}."
            
            sentence = f"{detection_sentence} {flight_sentence}"
        else:
            if error_message:
                sentence = f"No aircraft detected nearby, because of {error_message.lower()}"
            else:
                sentence = "No aircraft detected nearby, because no passenger aircraft found within 100km radius"
        
        # Convert to speech
        audio_content, tts_error = await convert_text_to_speech(sentence)
        
        if audio_content and not tts_error:
            # Cache the MP3
            cache_key = s3_cache.generate_cache_key(lat, lng)
            success = await s3_cache.set(cache_key, audio_content)
            if success:
                logger.info(f"Successfully pre-generated and cached MP3 for location: lat={lat}, lng={lng}")
            else:
                logger.warning(f"Failed to cache pre-generated MP3 for location: lat={lat}, lng={lng}")
        else:
            logger.warning(f"TTS generation failed during pre-generation: {tts_error}")
            
    except Exception as e:
        logger.error(f"Error in MP3 pre-generation: {e}")


async def stream_scanning(request: Request, lat: float = None, lng: float = None):
    """Stream scanning MP3 file from S3 and trigger MP3 pre-generation"""
    # Get location for pre-generation
    if lat is not None and lng is not None:
        user_lat, user_lng = lat, lng
        logger.info(f"Using provided coordinates for pre-generation: lat={lat}, lng={lng}")
    else:
        # Get client IP and location
        client_ip = (
            request.headers.get("x-forwarded-for", "").split(",")[0].strip() or
            request.headers.get("x-real-ip") or
            request.headers.get("cf-connecting-ip") or
            request.client.host
        )
        user_lat, user_lng = await get_location_from_ip(client_ip)
        logger.info(f"Using IP-based location for pre-generation: lat={user_lat}, lng={user_lng} for IP {client_ip}")
    
    # Start MP3 pre-generation in background (don't await)
    if user_lat != 0.0 or user_lng != 0.0:  # Only if we have a valid location
        asyncio.create_task(pre_generate_flight_mp3(user_lat, user_lng))
    else:
        logger.warning("Could not determine location for MP3 pre-generation")
    
    # Continue with normal scanning MP3 streaming
    mp3_url = "https://dreaming-of-a-jet-plane.s3.us-east-2.amazonaws.com/scanning.mp3"
    
    try:
        # Prepare headers for the S3 request
        request_headers = {}
        
        # Handle Range requests for seeking/partial content
        range_header = request.headers.get("range")
        if range_header:
            request_headers["Range"] = range_header
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(mp3_url, headers=request_headers)
            
            if response.status_code in [200, 206]:
                # Get content details
                content = response.content
                content_length = len(content)
                content_type = response.headers.get("content-type", "audio/mpeg")
                
                # Build response headers
                response_headers = {
                    "Content-Type": "audio/mpeg",
                    "Content-Length": str(content_length),
                    "Accept-Ranges": "bytes",
                    "Cache-Control": "public, max-age=3600",
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
                    "Access-Control-Allow-Headers": "Range, Content-Range, Content-Length",
                    "Access-Control-Expose-Headers": "Content-Length, Content-Range, Accept-Ranges"
                }
                
                # Handle range requests
                if range_header and response.status_code == 206:
                    content_range = response.headers.get("content-range")
                    if content_range:
                        response_headers["Content-Range"] = content_range
                
                # Copy important S3 headers if present
                if response.headers.get("etag"):
                    response_headers["ETag"] = response.headers["etag"]
                if response.headers.get("last-modified"):
                    response_headers["Last-Modified"] = response.headers["last-modified"]
                
                # Return the content directly
                return StreamingResponse(
                    iter([content]),
                    status_code=response.status_code,
                    media_type="audio/mpeg",
                    headers=response_headers
                )
            else:
                return {"error": f"MP3 file not accessible. Status: {response.status_code}", "url": mp3_url}
                
    except httpx.TimeoutException:
        return {"error": "Timeout accessing MP3 file", "url": mp3_url}
    except Exception as e:
        return {"error": f"Failed to stream MP3: {str(e)}", "url": mp3_url}


async def scanning_options():
    """Handle CORS preflight requests for /scanning endpoint"""
    return StreamingResponse(
        iter([b""]),
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
            "Access-Control-Allow-Headers": "Range, Content-Range, Content-Length",
            "Access-Control-Max-Age": "3600"
        }
    )