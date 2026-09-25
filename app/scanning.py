"""
Scanning endpoint for streaming MP3 file from S3 and pre-generating flight MP3
"""

import asyncio
import logging
import hashlib
import time
from fastapi import Request
from fastapi.responses import StreamingResponse
import httpx
from .s3_cache import s3_cache
from .audio_response import recent_plane_audio
from .flight_text import generate_flight_text
from .special_events import get_active_event, aircraft_slot_for_plane, ensure_event_audio
from .location_utils import get_user_location, extract_client_ip, extract_user_agent
from .background import spawn

logger = logging.getLogger(__name__)

# Cache to prevent duplicate scanning requests within short time window
# Format: {session_key: last_request_time}
_scanning_request_cache = {}
SCANNING_DEBOUNCE_SECONDS = 30  # Prevent duplicate requests within 30 seconds




async def _ensure_event_audio_ok(event, tts_override) -> bool:
    """Pre-warm the event's shared audio key; True on success (for gather counts)"""
    result = await ensure_event_audio(event, tts_override=tts_override)
    return bool(result["audio"]) and not result["error"]


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
            _, _, country_code, city, region, country_name, _ = await get_location_from_ip(client_ip, request)
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

        # Special Signal Events (DOJP-33): during an event the event owns
        # track 1 (pre-warmed once into its shared per-provider key) and the
        # real planes shift down a slot
        event = get_active_event()

        # Pre-generate audio for up to 5 planes
        tasks = []
        if event:
            tasks.append(asyncio.create_task(_ensure_event_audio_ok(event, tts_override)))
        for plane_index in range(1, 6):  # 1, 2, 3, 4, 5
            zero_based_index = aircraft_slot_for_plane(plane_index, event is not None)
            if zero_based_index is None:
                continue  # the event track; its audio is handled above

            # Check cache first for this specific plane (include TTS provider and format in cache key).
            # HEAD-only: pre-generation only needs to know the audio exists and is
            # fresh; the old full get() downloaded up to ~500KB x5 planes just to
            # throw the bytes away (DOJP-46)
            plane_cache_key = s3_cache.generate_cache_key(lat, lng, plane_index=plane_index, tts_provider=effective_provider, audio_format=file_ext)
            if await s3_cache.exists_and_fresh(plane_cache_key):
                # Skip if already cached
                continue


            # Generate appropriate text for this plane
            current_fun_fact_source = None
            opening_text = None
            body_text = None
            fun_fact_opening_text = None
            fun_fact_body_text = None
            if aircraft and len(aircraft) > zero_based_index:
                selected_aircraft = aircraft[zero_based_index]
                # Use split_text=True to get opening and body separately for free pool support
                opening_text, body_text, fun_fact_opening_text, fun_fact_body_text, current_fun_fact_source = generate_flight_text_for_aircraft(
                    selected_aircraft, lat, lng, plane_index, country_code, used_destinations, split_text=True
                )
                if fun_fact_opening_text and fun_fact_body_text:
                    sentence = f"{opening_text} {body_text} {fun_fact_opening_text} {fun_fact_body_text}"
                else:
                    sentence = f"{opening_text} {body_text}"
            elif aircraft and len(aircraft) > 0:
                # Not enough planes - one canonical apology (DOJP-46)
                from .flight_text import not_enough_planes_message
                sentence = not_enough_planes_message(plane_index, len(aircraft) + (1 if event else 0))
            else:
                # No aircraft found at all
                sentence = generate_flight_text([], error_message, lat, lng, country_code=country_code, user_city=city, user_region=region, user_country_name=country_name)

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
                    fun_fact_opening_text=fun_fact_opening_text,
                    fun_fact_body_text=fun_fact_body_text,
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

        # After all planes complete, populate free pool. Only three free plane
        # endpoints exist, so populate_free_pool consumes at most three.
        if aircraft and len(aircraft) >= 2:
            await populate_free_pool(
                slot_offset=1 if event else 0,
                aircraft_list=aircraft[:3],
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
    fun_fact_opening_text: str = None,
    fun_fact_body_text: str = None,
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
        fun_fact_opening_text: Fun fact opening phrase e.g. "Did you know?" (optional)
        fun_fact_body_text: Fun fact body text (optional)
        request: Optional FastAPI Request object
        aircraft: Optional aircraft data dict
        tts_override: Optional TTS provider override
        fun_fact_source: Optional fun fact source ("destination", "origin", or None)

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        from .main import track_audio_generation
        from .plane_audio import generate_plane_audio

        result = await generate_plane_audio(
            sentence,
            opening_text=opening_text,
            body_text=body_text,
            fun_fact_opening_text=fun_fact_opening_text,
            fun_fact_body_text=fun_fact_body_text,
            location_hash=location_hash,
            plane_index=plane_index,
            tts_override=tts_override,
        )

        if result["audio"] and not result["error"]:
            success = await s3_cache.set(cache_key, result["audio"])
            if success:
                # Same container will most likely serve the play that follows
                # this scan; keep the bytes hot so its range requests never
                # touch S3 (DOJP-56)
                recent_plane_audio.put(cache_key, result["audio"])
                if request and aircraft:
                    track_audio_generation(request, lat, lng, city, plane_index, aircraft, sentence, result["generation_ms"], len(result["audio"]), result["provider"], result["file_ext"], fun_fact_source, fun_fact_cache_hit=result["fun_fact_cache_hit"])
                return True
            logger.warning(f"Failed to cache pre-generated plane {plane_index} audio for location: lat={lat}, lng={lng}")
            return False

        logger.warning(f"TTS generation failed for plane {plane_index} during pre-generation: {result['error']}")
        return False

    except Exception as e:
        logger.error(f"Error generating plane {plane_index} audio: {e}")
        return False


async def _stream_scanning_mp3_only(request: Request, tts_override: str = None):
    """Stream scanning audio with no analytics or pre-generation - the
    debounced-duplicate path. Pure proxy via the shared streamer (DOJP-46)."""
    from .static_audio import stream_voice_clip
    return await stream_voice_clip(request, "scanning.mp3", None, tts_override=tts_override)


async def stream_scanning(request: Request, lat: float = None, lng: float = None):
    """Stream scanning MP3 file from S3 and trigger audio pre-generation"""

    # Get user location using shared function
    user_lat, user_lng, user_country_code, user_city, _, _, _ = await get_user_location(request, lat, lng)

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
    
    # Update cache with current request time, and opportunistically drop
    # entries older than the debounce window - they can never match the check
    # above again, so keeping them just grows the dict forever (DOJP-42)
    cutoff = current_time - SCANNING_DEBOUNCE_SECONDS
    for key in [k for k, t in _scanning_request_cache.items() if t < cutoff]:
        del _scanning_request_cache[key]
    _scanning_request_cache[session_key] = current_time

    # Track scan:start event using unified tracking function
    from .main import track_scan_start
    track_scan_start(request, subscription="yoto-club")
    
    # Start audio pre-generation in background (don't await)
    if user_lat != 0.0 or user_lng != 0.0:  # Only if we have a valid location
        spawn(pre_generate_flight_audio(user_lat, user_lng, request, tts_override), "pre-generate flight audio")
    else:
        logger.warning("Could not determine location for audio pre-generation")
    
    # Continue with normal scanning audio streaming - same proxy as the
    # debounced path (this tail used to duplicate it verbatim, DOJP-46)
    return await _stream_scanning_mp3_only(request, tts_override)


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
