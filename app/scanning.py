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
from .flight_text import generate_flight_text, get_plane_sentence_override
from .location_utils import get_user_location, extract_client_ip, extract_user_agent, parse_user_agent
from .analytics import analytics

logger = logging.getLogger(__name__)

# Cache to prevent duplicate scanning requests within short time window
# Format: {session_key: last_request_time}
_scanning_request_cache = {}
SCANNING_DEBOUNCE_SECONDS = 30  # Prevent duplicate requests within 30 seconds




async def pre_generate_flight_audio(lat: float, lng: float, request: Request = None, tts_override: str = None):
    """Background task to pre-generate and cache flight audio for all 5 planes

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
        from .free_pool import populate_free_pool

        # Get country code and city for metric/imperial units and analytics
        # We already have lat/lng
        if request:
            client_ip = extract_client_ip(request)
            _, _, country_code, city, region, country_name = await get_location_from_ip(client_ip, request)
        else:
            country_code = "US"  # Default fallback if no request
            city = "Unknown"
            region = ""
            country_name = ""

        # Get flight data (this will use cached API data if available, or cache new data)
        aircraft, error_message = await get_nearby_aircraft(
            lat,
            lng,
            limit=5,
            request=request,
            user_city=city,
        )

        # Determine effective TTS provider
        effective_provider = tts_override if tts_override else TTS_PROVIDER

        # Get audio format for this provider
        from .main import get_audio_format_for_provider
        file_ext, mime_type = get_audio_format_for_provider(effective_provider)

        # Compute location hash once for body cache keys
        location_str = f"{round(lat, 2)},{round(lng, 2)}"
        location_hash = hashlib.md5(location_str.encode()).hexdigest()

        # Track destination cities across all 5 planes for diversity
        used_destinations = set()

        # Pre-generate audio for up to 5 planes
        tasks = []
        for plane_index in range(1, 6):  # 1, 2, 3, 4, 5
            zero_based_index = plane_index - 1

            # Check cache first for this specific plane (include TTS provider and format in cache key)
            plane_cache_key = s3_cache.generate_cache_key(lat, lng, plane_index=plane_index, tts_provider=effective_provider, audio_format=file_ext)
            cached_audio = await s3_cache.get(plane_cache_key)

            if cached_audio:
                # Skip if already cached
                continue


            # Generate appropriate text for this plane
            current_fun_fact_source = None
            opening_text = None
            body_text = None
            if aircraft and len(aircraft) > zero_based_index:
                selected_aircraft = aircraft[zero_based_index]
                # Use split_text=True to get opening and body separately for free pool support
                opening_text, body_text, current_fun_fact_source = generate_flight_text_for_aircraft(
                    selected_aircraft, lat, lng, plane_index, country_code, used_destinations, split_text=True
                )
                sentence = f"{opening_text} {body_text}"
            elif aircraft and len(aircraft) > 0:
                # Not enough planes, generate appropriate message
                plane_count = len(aircraft)
                if plane_index == 2:
                    sentence = "I'm sorry my old chum but scanner bot could only find one jet plane nearby. Try firing up the scanner again in a few minutes."
                elif plane_index == 3:
                    if plane_count == 1:
                        sentence = "I'm sorry my old chum but scanner bot could only find one jet plane nearby. Try firing up the scanner again in a few minutes."
                    else:
                        sentence = "I'm sorry my old chum but scanner bot could only find two jet planes nearby. Try firing up the scanner again in a few minutes."
                elif plane_index == 4:
                    sentence = f"I'm sorry my old chum but scanner bot could only find {plane_count} jet plane{'s' if plane_count != 1 else ''} nearby. Try firing up the scanner again in a few minutes."
                elif plane_index == 5:
                    sentence = f"I'm sorry my old chum but scanner bot could only find {plane_count} jet plane{'s' if plane_count != 1 else ''} nearby. Try firing up the scanner again in a few minutes."
            else:
                # No aircraft found at all
                sentence = generate_flight_text([], error_message, lat, lng, country_code=country_code, user_city=city, user_region=region, user_country_name=country_name)

            override_sentence = get_plane_sentence_override(plane_index)
            if override_sentence:
                sentence = override_sentence
                opening_text = None  # Don't use split TTS for overrides
                body_text = None

            # Create task to generate and cache this plane's audio
            selected_aircraft = aircraft[zero_based_index] if aircraft and len(aircraft) > zero_based_index else None
            task = asyncio.create_task(
                _generate_and_cache_plane_audio(
                    plane_index,
                    plane_cache_key,
                    sentence,
                    lat,
                    lng,
                    city,
                    location_hash=location_hash,
                    opening_text=opening_text,
                    body_text=body_text,
                    request=request,
                    aircraft=selected_aircraft,
                    tts_override=tts_override,
                    fun_fact_source=current_fun_fact_source,
                )
            )
            tasks.append(task)

        # Wait for all plane MP3s to be generated concurrently
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            successes = sum(1 for r in results if r is True)
            logger.info(f"Pre-generation completed: {successes}/{len(results)} planes cached successfully")
        else:
            logger.info("Pre-generation skipped: all planes already cached")

        # After all planes complete, populate free pool (up to 5 planes)
        if aircraft and len(aircraft) >= 2:
            await populate_free_pool(
                aircraft_list=aircraft[:5],
                location_hash=location_hash,
                tts_provider=effective_provider,
            )

    except Exception as e:
        logger.error(f"Error in MP3 pre-generation: {e}")


async def _generate_and_cache_plane_audio(
    plane_index: int,
    cache_key: str,
    sentence: str,
    lat: float,
    lng: float,
    city: str,
    location_hash: str = None,
    opening_text: str = None,
    body_text: str = None,
    request: Request = None,
    aircraft: dict = None,
    tts_override: str = None,
    fun_fact_source: str = None,
) -> bool:
    """Helper function to generate and cache audio for a specific plane

    Args:
        plane_index: 1-based plane index (1-5)
        cache_key: S3 cache key (already includes TTS provider and format)
        sentence: Text to convert to speech (fallback if split text fails)
        lat: Latitude
        lng: Longitude
        city: City associated with the user request
        location_hash: Hash of location for body cache key
        opening_text: Opening text for split TTS (optional)
        body_text: Body text for split TTS (optional)
        request: Optional FastAPI Request object
        aircraft: Optional aircraft data dict
        tts_override: Optional TTS provider override
        fun_fact_source: Optional fun fact source ("destination", "origin", or None)

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Import here to avoid circular imports
        from .main import convert_text_to_speech, track_audio_generation
        from .free_pool import stitch_audio
        import time

        tts_start_time = time.time()
        audio_content = None
        tts_error = None
        tts_provider_used = None
        file_ext = None
        mime_type = None

        # Try split TTS if we have opening and body text
        if opening_text and body_text and location_hash:
            opening_audio, opening_error, _, _, _ = await convert_text_to_speech(opening_text, tts_override=tts_override)
            body_audio, body_error, tts_provider_used, file_ext, mime_type = await convert_text_to_speech(body_text, tts_override=tts_override)

            if opening_audio and body_audio and not opening_error and not body_error:
                # Stitch opening + body with 1s silence at start
                audio_content = await stitch_audio(opening_audio, body_audio, add_silence=True)
                tts_error = ""

                # Cache body audio separately for free pool reuse
                body_cache_key = f"cache/{location_hash}_plane{plane_index}_body_{tts_provider_used}.{file_ext}"
                await s3_cache.set(body_cache_key, body_audio)
                logger.info(f"Cached body audio at {body_cache_key}")
            else:
                # Split TTS failed, fall through to single TTS
                logger.warning(f"Split TTS failed for plane {plane_index}, falling back to single TTS. Opening error: {opening_error}, Body error: {body_error}")

        # Fallback to single TTS if split didn't work or wasn't requested
        if not audio_content:
            audio_content, tts_error, tts_provider_used, file_ext, mime_type = await convert_text_to_speech(sentence, tts_override=tts_override)

        tts_generation_time_ms = int((time.time() - tts_start_time) * 1000)

        if audio_content and not tts_error:
            # Cache the audio
            success = await s3_cache.set(cache_key, audio_content)
            if success:

                # Track audio generation analytics if we have request and aircraft data
                if request and aircraft:
                    track_audio_generation(request, lat, lng, city, plane_index, aircraft, sentence, tts_generation_time_ms, len(audio_content), tts_provider_used, file_ext, fun_fact_source)

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
    user_lat, user_lng, user_country_code, user_city, _, _ = await get_user_location(request, lat, lng)
    country_code = user_country_code  # Keep for backwards compatibility

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
            "user_lat": round(user_lat, 2),
            "user_lng": round(user_lng, 2),
            "user_city": user_city,
            "location_source": "params" if (lat is not None and lng is not None) else "ip"
        })
    except Exception as e:
        # Log error but don't break the response
        logger.error(f"Analytics tracking failed: {e}")
        # Still try to track without session data
        try:
            analytics.track_event("scan:start", {
                "lat": round(user_lat, 2),
                "lng": round(user_lng, 2),
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
