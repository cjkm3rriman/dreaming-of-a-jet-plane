"""
Scanning endpoint for streaming MP3 file from S3 and pre-generating flight MP3
"""

import asyncio
import logging
import hashlib
import uuid
import time
from fastapi import Request
from fastapi.responses import StreamingResponse
import httpx
from .s3_cache import s3_cache
from .flight_text import generate_flight_text
from .location_utils import get_user_location, extract_client_ip, extract_user_agent, parse_user_agent
from .analytics import analytics

logger = logging.getLogger(__name__)

# Cache to prevent duplicate scanning requests within short time window
# Format: {session_key: last_request_time}
_scanning_request_cache = {}
SCANNING_DEBOUNCE_SECONDS = 30  # Prevent duplicate requests within 30 seconds




async def pre_generate_flight_audio(lat: float, lng: float, request: Request = None, tts_override: str = None):
    """Background task to pre-generate and cache flight audio for all 3 planes

    Args:
        lat: Latitude
        lng: Longitude
        request: Optional FastAPI Request object
        tts_override: Optional TTS provider override
    """
    try:

        # Import here to avoid circular imports
        from .main import get_nearby_aircraft, convert_text_to_speech, TTS_PROVIDER
        from .flight_text import generate_flight_text_for_aircraft, generate_flight_text
        from .location_utils import get_location_from_ip, extract_client_ip

        # Get country code for metric/imperial units
        # We already have lat/lng, just need country code
        if request:
            client_ip = extract_client_ip(request)
            _, _, country_code = await get_location_from_ip(client_ip, request)
        else:
            country_code = "US"  # Default fallback if no request

        # Get flight data (this will use cached API data if available, or cache new data)
        aircraft, error_message = await get_nearby_aircraft(lat, lng, limit=3, request=request)

        # Determine effective TTS provider
        effective_provider = tts_override if tts_override else TTS_PROVIDER

        # Get audio format for this provider
        from .main import get_audio_format_for_provider
        file_ext, mime_type = get_audio_format_for_provider(effective_provider)

        # Track destination cities across all 3 planes for diversity
        used_destinations = set()

        # Pre-generate audio for up to 3 planes
        tasks = []
        for plane_index in range(1, 4):  # 1, 2, 3
            zero_based_index = plane_index - 1

            # Check cache first for this specific plane (include TTS provider and format in cache key)
            plane_cache_key = s3_cache.generate_cache_key(lat, lng, plane_index=plane_index, tts_provider=effective_provider, audio_format=file_ext)
            cached_audio = await s3_cache.get(plane_cache_key)

            if cached_audio:
                continue


            # Generate appropriate text for this plane
            if aircraft and len(aircraft) > zero_based_index:
                selected_aircraft = aircraft[zero_based_index]
                sentence = generate_flight_text_for_aircraft(selected_aircraft, lat, lng, plane_index, country_code, used_destinations)
            elif aircraft and len(aircraft) > 0:
                # Not enough planes, generate appropriate message
                if plane_index == 2:
                    sentence = "I'm sorry my old chum but scanner bot could only find one jet plane nearby. Try firing up the scanner again in a few minutes."
                elif plane_index == 3:
                    plane_count = len(aircraft)
                    if plane_count == 1:
                        sentence = "I'm sorry my old chum but scanner bot could only find one jet plane nearby. Try firing up the scanner again in a few minutes."
                    else:
                        sentence = "I'm sorry my old chum but scanner bot could only find two jet planes nearby. Try firing up the scanner again in a few minutes."
            else:
                # No aircraft found at all
                sentence = generate_flight_text([], error_message, lat, lng, country_code=country_code)

            # Create task to generate and cache this plane's audio
            selected_aircraft = aircraft[zero_based_index] if aircraft and len(aircraft) > zero_based_index else None
            task = asyncio.create_task(
                _generate_and_cache_plane_audio(plane_index, plane_cache_key, sentence, lat, lng, request, selected_aircraft, tts_override)
            )
            tasks.append(task)
        
        # Wait for all plane MP3s to be generated concurrently
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            successes = sum(1 for r in results if r is True)
        else:
            pass
            
    except Exception as e:
        logger.error(f"Error in MP3 pre-generation: {e}")


async def _generate_and_cache_plane_audio(plane_index: int, cache_key: str, sentence: str, lat: float, lng: float, request: Request = None, aircraft: dict = None, tts_override: str = None) -> bool:
    """Helper function to generate and cache audio for a specific plane

    Args:
        plane_index: 1-based plane index (1, 2, 3)
        cache_key: S3 cache key (already includes TTS provider and format)
        sentence: Text to convert to speech
        lat: Latitude
        lng: Longitude
        request: Optional FastAPI Request object
        aircraft: Optional aircraft data dict
        tts_override: Optional TTS provider override

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Import here to avoid circular imports
        from .main import convert_text_to_speech, track_audio_generation
        import time

        # Convert to speech with timing (pass TTS override)
        tts_start_time = time.time()
        audio_content, tts_error, tts_provider_used, file_ext, mime_type = await convert_text_to_speech(sentence, tts_override=tts_override)
        tts_generation_time_ms = int((time.time() - tts_start_time) * 1000)

        if audio_content and not tts_error:
            # Cache the audio
            success = await s3_cache.set(cache_key, audio_content)
            if success:

                # Track audio generation analytics if we have request and aircraft data
                if request and aircraft:
                    track_audio_generation(request, lat, lng, plane_index, aircraft, sentence, tts_generation_time_ms, len(audio_content), tts_provider_used, file_ext)

                return True
            else:
                logger.warning(f"Failed to cache pre-generated plane {plane_index} audio for location: lat={lat}, lng={lng}")
                return False
        else:
            logger.warning(f"TTS generation failed for plane {plane_index} during pre-generation: {tts_error}")
            return False

    except Exception as e:
        logger.error(f"Error generating plane {plane_index} audio: {e}")
        return False


async def _stream_scanning_mp3_only(request: Request, tts_override: str = None):
    """Stream scanning MP3 file from S3 without analytics or background processing"""
    # Import here to avoid circular imports
    from .main import get_voice_specific_s3_url
    mp3_url = get_voice_specific_s3_url("scanning.mp3", tts_override)
    
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


async def stream_scanning(request: Request, lat: float = None, lng: float = None):
    """Stream scanning MP3 file from S3 and trigger audio pre-generation"""

    # Get user location using shared function
    user_lat, user_lng, country_code = await get_user_location(request, lat, lng)

    # Get TTS provider override from query parameters
    from .main import get_tts_provider_override
    tts_override = get_tts_provider_override(request)
    
    # Create session key for duplicate request prevention
    client_ip = extract_client_ip(request)
    user_agent = extract_user_agent(request)
    hash_string = f"{client_ip or 'unknown'}:{user_agent or 'unknown'}:{user_lat or 0}:{user_lng or 0}"
    session_key = hashlib.md5(hash_string.encode('utf-8')).hexdigest()[:8]
    
    current_time = time.time()
    
    # Check if we've recently processed a request from this session
    if session_key in _scanning_request_cache:
        last_request_time = _scanning_request_cache[session_key]
        if current_time - last_request_time < SCANNING_DEBOUNCE_SECONDS:
            # Still stream the MP3, but skip analytics and background processing
            return await _stream_scanning_mp3_only(request, tts_override)
    
    # Update cache with current request time
    _scanning_request_cache[session_key] = current_time
    
    # Track scan:start event
    try:
        browser_info = parse_user_agent(user_agent)
        session_id = session_key  # Use the same session key for consistency
        
        analytics.track_event("scan:start", {
            "ip": client_ip,
            "$user_agent": user_agent,
            "$session_id": session_id,  # Use $session_id label
            "$insert_id": f"scan_{session_id}",  # Prevents duplicates
            "browser": browser_info["browser"],
            "browser_version": browser_info["browser_version"],
            "os": browser_info["os"],
            "os_version": browser_info["os_version"],
            "device": browser_info["device"],
            "lat": round(user_lat, 3),
            "lng": round(user_lng, 3),
            "location_source": "params" if (lat is not None and lng is not None) else "ip"
        })
    except Exception as e:
        # Log error but don't break the response
        logger.error(f"Analytics tracking failed: {e}")
        # Still try to track without session data
        try:
            analytics.track_event("scan:start", {
                "lat": round(user_lat, 3),
                "lng": round(user_lng, 3),
                "location_source": "params" if (lat is not None and lng is not None) else "ip"
            })
        except:
            pass  # Silently fail if analytics completely broken
    
    # Start audio pre-generation in background (don't await)
    if user_lat != 0.0 or user_lng != 0.0:  # Only if we have a valid location
        asyncio.create_task(pre_generate_flight_audio(user_lat, user_lng, request, tts_override))
    else:
        logger.warning("Could not determine location for audio pre-generation")
    
    # Continue with normal scanning MP3 streaming
    # Import here to avoid circular imports
    from .main import get_voice_specific_s3_url
    mp3_url = get_voice_specific_s3_url("scanning.mp3", tts_override)
    
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