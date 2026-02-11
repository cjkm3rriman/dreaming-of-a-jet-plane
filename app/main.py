from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
import httpx
import os
import sys
import asyncio
import logging
from typing import List, Dict, Any, Optional

# Configure logging with explicit format and stream
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout  # Ensure logs go to stdout not stderr
)
logger = logging.getLogger(__name__)

# Filter out HEAD requests from httpx logs to reduce noise
class SupressHeadRequestsFilter(logging.Filter):
    def filter(self, record):
        # Suppress log records that contain "HEAD" HTTP requests
        return 'HEAD' not in record.getMessage()

# Apply filter to httpx logger
httpx_logger = logging.getLogger('httpx')
httpx_logger.addFilter(SupressHeadRequestsFilter())

# Suppress verbose Google GenAI SDK logs (AFC notifications, etc.)
google_genai_logger = logging.getLogger('google_genai')
google_genai_logger.setLevel(logging.WARNING)

from .airport_database import get_airport_by_iata
from .airline_database import AirlineDatabase
from .location_utils import calculate_distance, calculate_min_distance_to_route
from .intro import stream_intro, intro_options
from .overandout import stream_overandout, overandout_options
from .scanning_again import stream_scanning_again, scanning_again_options
from .scanning import stream_scanning, scanning_options
from .s3_cache import s3_cache
from .flight_text import (
    generate_flight_text,
    generate_flight_text_for_aircraft,
    get_plane_sentence_override,
)
from .location_utils import get_user_location, extract_client_ip, extract_user_agent, parse_user_agent
from .analytics import analytics
from .website_home import register_website_home_routes
from .test_gemini_tts import register_test_gemini_tts_routes
from .test_live_aircraft import register_test_live_aircraft_routes
from .aircraft_providers import get_provider_definition, get_provider_names
from .tts_providers import (
    TTS_PROVIDERS,
    get_provider_definition as get_tts_provider_definition,
    get_audio_format as get_tts_audio_format,
    get_voice_folder as get_tts_voice_folder,
)

# Initialize Sentry for error monitoring (only if DSN is configured)
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration

if os.getenv("SENTRY_DSN"):
    sentry_sdk.init(
        dsn=os.getenv("SENTRY_DSN"),
        environment=os.getenv("SENTRY_ENVIRONMENT", "development"),
        traces_sample_rate=0.1,  # 10% of requests for performance monitoring
        integrations=[FastApiIntegration()],
    )
    logger.info("Sentry error monitoring initialized")

app = FastAPI()

# Serve static assets
app.mount("/assets", StaticFiles(directory="assets"), name="assets")

# Register website home routes
register_website_home_routes(app)

# Register test Gemini TTS routes
register_test_gemini_tts_routes(app)

# Live aircraft provider configuration
LIVE_AIRCRAFT_PROVIDER = (os.getenv("LIVE_AIRCRAFT_PROVIDER") or "fr24").lower()
LIVE_AIRCRAFT_PROVIDER_FALLBACKS = [p.strip().lower() for p in os.getenv("LIVE_AIRCRAFT_PROVIDER_FALLBACKS", "").split(",") if p.strip()]
PROVIDER_OVERRIDE_SECRET = os.getenv("PROVIDER_OVERRIDE_SECRET")

# TTS Configuration
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "elevenlabs")  # Options: "elevenlabs", "google", "inworld", "fallback"

def get_tts_provider_override(request: Request) -> Optional[str]:
    """Extract and validate TTS provider override from query parameters

    Allows testing different TTS providers via query parameters:
    Example: ?tts=google&secret=your_secret_key

    Args:
        request: FastAPI Request object

    Returns:
        str: Provider name if valid override, None otherwise
    """
    if not PROVIDER_OVERRIDE_SECRET:
        return None

    # Extract query parameters
    tts_param = request.query_params.get("tts")
    secret_param = request.query_params.get("secret")

    # Validate both parameters are present
    if not tts_param or not secret_param:
        return None

    # Validate secret
    if secret_param != PROVIDER_OVERRIDE_SECRET:
        logger.warning(f"Invalid TTS override secret attempt from IP: {extract_client_ip(request)}")
        return None

    # Validate provider is supported
    valid_providers = ["elevenlabs", "google", "inworld", "fallback"]
    if tts_param.lower() not in valid_providers:
        logger.warning(f"Invalid TTS provider override: {tts_param}")
        return None

    logger.info(f"TTS provider override: {tts_param} from IP: {extract_client_ip(request)}")
    return tts_param.lower()


def get_aircraft_provider_override(request: Optional[Request]) -> Optional[str]:
    """Allow overriding the live aircraft provider for debugging"""
    if not request or not PROVIDER_OVERRIDE_SECRET:
        return None

    provider_param = request.query_params.get("aircraft_provider") or request.query_params.get("provider")
    secret_param = request.query_params.get("secret")

    if not provider_param or not secret_param:
        return None

    if secret_param != PROVIDER_OVERRIDE_SECRET:
        logger.warning(
            f"Invalid aircraft provider override secret attempt from IP: {extract_client_ip(request)}"
        )
        return None

    provider_value = provider_param.lower()
    valid_providers = get_provider_names()

    if provider_value not in valid_providers:
        logger.warning(f"Invalid aircraft provider override: {provider_param}")
        return None

    logger.info(
        f"Aircraft provider override '{provider_value}' from IP: {extract_client_ip(request)}"
    )
    return provider_value


def get_live_aircraft_providers(request: Optional[Request], forced_provider: Optional[str] = None) -> List[str]:
    """Determine the ordered list of providers to try"""
    override = forced_provider or get_aircraft_provider_override(request)
    provider_names = get_provider_names()

    if override:
        return [override]

    ordered: List[str] = []
    seen = set()

    def _add_provider(name: Optional[str]):
        if not name:
            return
        if name not in provider_names:
            logger.warning(f"Requested aircraft provider '{name}' is not registered")
            return
        if name not in seen:
            ordered.append(name)
            seen.add(name)

    _add_provider(LIVE_AIRCRAFT_PROVIDER)
    for fallback in LIVE_AIRCRAFT_PROVIDER_FALLBACKS:
        _add_provider(fallback)

    if not ordered:
        _add_provider("fr24")

    return ordered


def ensure_override_secret(secret: Optional[str]):
    """Validate override secret when sensitive parameters are provided"""
    if not PROVIDER_OVERRIDE_SECRET:
        raise HTTPException(status_code=403, detail="Override secret is not configured")

    if secret != PROVIDER_OVERRIDE_SECRET:
        raise HTTPException(status_code=403, detail="Invalid override secret")


def validate_flight_position_override(lat: Optional[float], lng: Optional[float], secret: Optional[str]):
    """Ensure manual lat/lng overrides are authorized"""
    if lat is None and lng is None:
        return

    ensure_override_secret(secret)

def get_audio_format_for_provider(provider: str) -> tuple[str, str]:
    """Get audio file extension and MIME type for TTS provider

    Args:
        provider: TTS provider name (elevenlabs, google, inworld)

    Returns:
        tuple: (file_extension, mime_type)
        - file_extension: "mp3" or "ogg"
        - mime_type: "audio/mpeg" or "audio/ogg"
    """
    return get_tts_audio_format(provider)

def get_voice_folder(tts_override: Optional[str] = None) -> str:
    """Get the voice folder name based on TTS provider configuration

    Args:
        tts_override: Optional TTS provider override (e.g., "google", "inworld")

    Returns:
        str: "edward" for ElevenLabs, "sadachbia" for Google TTS, "ronald" for Inworld
    """
    provider = (tts_override or TTS_PROVIDER).lower()
    # Handle "fallback" by defaulting to elevenlabs folder
    if provider == "fallback":
        provider = "elevenlabs"
    return get_tts_voice_folder(provider)

def get_voice_specific_s3_url(filename: str, tts_override: Optional[str] = None) -> str:
    """Generate voice-specific S3 URL for static MP3 files

    Args:
        filename: The MP3 filename (e.g., "scanning.mp3")
        tts_override: Optional TTS provider override (e.g., "google", "inworld")

    Returns:
        str: Full S3 URL with voice folder (e.g., "https://.../edward/scanning.mp3")
    """
    voice_folder = get_voice_folder(tts_override)
    return f"https://dreaming-of-a-jet-plane.s3.us-east-2.amazonaws.com/{voice_folder}/{filename}"

async def convert_text_to_speech(text: str, tts_override: Optional[str] = None) -> tuple[bytes, str, str, str, str]:
    """Convert text to speech using configured or overridden TTS provider

    Supports multiple providers based on TTS_PROVIDER environment variable:
    - "elevenlabs": Use ElevenLabs (default)
    - "google": Use Google Gemini Flash TTS
    - "inworld": Use Inworld's TTS API
    - "fallback": Try ElevenLabs first, fallback to Inworld on error

    Args:
        text: Text to convert to speech
        tts_override: Optional TTS provider override (from query params)

    Returns:
        tuple: (audio_content, error_message, provider_used, file_extension, mime_type)
        - audio_content: Audio bytes if successful, empty bytes if failed
        - error_message: Empty string if successful, error description if failed
        - provider_used: Which provider was actually used ("elevenlabs", "google", "inworld")
        - file_extension: File extension for the audio format ("mp3" or "ogg")
        - mime_type: MIME type for the audio format ("audio/mpeg" or "audio/ogg")
    """
    provider = tts_override.lower() if tts_override else TTS_PROVIDER.lower()

    audio_content = b""
    error = ""
    provider_used = ""

    if provider == "fallback":
        # Try ElevenLabs first, fallback to Inworld on error
        logger.info("Using fallback strategy: trying ElevenLabs first")
        elevenlabs_def = get_tts_provider_definition("elevenlabs")
        if elevenlabs_def:
            audio_content, error = await elevenlabs_def["generate_audio"](text)
            if audio_content and not error:
                provider_used = "elevenlabs"
            else:
                logger.info(f"ElevenLabs failed ({error}), falling back to Inworld")
                inworld_def = get_tts_provider_definition("inworld")
                if inworld_def:
                    audio_content, error = await inworld_def["generate_audio"](text)
                    provider_used = "inworld"
        if not provider_used:
            error = "Fallback providers not available"
            provider_used = "fallback"
    else:
        # Use specific provider
        provider_def = get_tts_provider_definition(provider)
        if provider_def:
            audio_content, error = await provider_def["generate_audio"](text)
            provider_used = provider
        else:
            error_msg = f"Unknown TTS provider: {provider}. Use 'elevenlabs', 'google', 'inworld', or 'fallback'"
            logger.error(error_msg)
            return b"", error_msg, "unknown", "mp3", "audio/mpeg"

    # Get format info for the provider that was used
    file_ext, mime_type = get_audio_format_for_provider(provider_used)
    return audio_content, error, provider_used, file_ext, mime_type

def track_scan_complete(
    request: Request,
    lat: float,
    lng: float,
    city: str,
    from_cache: bool,
    nearby_aircraft: int,
    provider: str,
    subscription: str = "yoto-club",
):
    """Track scan:complete analytics event with flight data results

    Args:
        request: FastAPI request object
        lat: User latitude
        lng: User longitude
        city: User city name
        from_cache: Whether data was served from cache
        nearby_aircraft: Number of aircraft found
        provider: Aircraft data provider used
        subscription: "yoto-club" for paid, "free" for free tier
    """
    try:
        import hashlib

        client_ip = extract_client_ip(request)
        user_agent = extract_user_agent(request)
        browser_info = parse_user_agent(user_agent)

        # Create consistent session ID
        hash_string = f"{client_ip or 'unknown'}:{user_agent or 'unknown'}:{lat or 0}:{lng or 0}"
        session_id = hashlib.md5(hash_string.encode('utf-8')).hexdigest()[:8]

        analytics.track_event("scan:complete", {
            "ip": client_ip,
            "$user_agent": user_agent,
            "$session_id": session_id,
            "$insert_id": f"scan_complete_{subscription}_{session_id}",  # Prevents duplicates
            "browser": browser_info["browser"],
            "browser_version": browser_info["browser_version"],
            "os": browser_info["os"],
            "os_version": browser_info["os_version"],
            "device": browser_info["device"],
            "user_lat": round(lat, 2),
            "user_lng": round(lng, 2),
            "user_city": city,
            "from_cache": from_cache,
            "nearby_aircraft": nearby_aircraft,
            "aircraft_provider": provider,
            "subscription": subscription,
        })
    except Exception as e:
        logger.error(f"Failed to track scan:complete event: {e}", exc_info=True)

def track_plane_request(
    request: Request,
    lat: float,
    lng: float,
    city: str,
    plane_index: int,
    from_cache: bool,
    subscription: str = "yoto-club",
    free_pool_entry_id: str = None,
    distance_miles: int = None,
):
    """Track plane:request analytics event for plane endpoint requests

    Args:
        request: FastAPI request object
        lat: User latitude
        lng: User longitude
        city: User city name
        plane_index: 1-based plane index
        from_cache: Whether audio was served from cache
        subscription: "yoto-club" for paid, "free" for free tier
        free_pool_entry_id: Free pool session ID (free tier only)
        distance_miles: Calculated distance to flight (free tier plane 1 only)
    """
    try:
        import hashlib

        client_ip = extract_client_ip(request)
        user_agent = extract_user_agent(request)
        browser_info = parse_user_agent(user_agent)

        # Create consistent session ID
        hash_string = f"{client_ip or 'unknown'}:{user_agent or 'unknown'}:{lat or 0}:{lng or 0}"
        session_id = hashlib.md5(hash_string.encode('utf-8')).hexdigest()[:8]

        properties = {
            "ip": client_ip,
            "$user_agent": user_agent,
            "$session_id": session_id,
            "$insert_id": f"plane_req_{subscription}_{session_id}_{plane_index}",  # Prevents duplicates
            "browser": browser_info["browser"],
            "browser_version": browser_info["browser_version"],
            "os": browser_info["os"],
            "os_version": browser_info["os_version"],
            "device": browser_info["device"],
            "user_lat": round(lat, 2),
            "user_lng": round(lng, 2),
            "user_city": city,
            "plane_index": plane_index,
            "from_cache": from_cache,
            "subscription": subscription,
        }

        # Add free tier specific properties
        if free_pool_entry_id:
            properties["free_pool_entry_id"] = free_pool_entry_id
        if distance_miles is not None:
            properties["distance_miles"] = distance_miles

        analytics.track_event("plane:request", properties)
    except Exception as e:
        logger.error(f"Failed to track plane:request event: {e}", exc_info=True)


def track_scan_start(request: Request, subscription: str = "yoto-club"):
    """Track scan:start analytics event when user initiates a scan

    Args:
        request: FastAPI request object
        subscription: "yoto-club" for paid, "free" for free tier
    """
    try:
        import hashlib

        client_ip = extract_client_ip(request)
        user_agent = extract_user_agent(request)
        browser_info = parse_user_agent(user_agent)

        hash_string = f"{client_ip or 'unknown'}:{user_agent or 'unknown'}"
        session_id = hashlib.md5(hash_string.encode('utf-8')).hexdigest()[:8]

        analytics.track_event("scan:start", {
            "ip": client_ip,
            "$user_agent": user_agent,
            "$session_id": session_id,
            "$insert_id": f"scan_start_{subscription}_{session_id}",
            "browser": browser_info["browser"],
            "browser_version": browser_info["browser_version"],
            "os": browser_info["os"],
            "os_version": browser_info["os_version"],
            "device": browser_info["device"],
            "subscription": subscription,
        })
    except Exception as e:
        logger.error(f"Failed to track scan:start event: {e}", exc_info=True)

def track_audio_generation(request: Request, lat: float, lng: float, city: str, plane_index: int, aircraft: Dict[str, Any], sentence: str, generation_time_ms: int, audio_size_bytes: int, tts_provider: str = "elevenlabs", audio_format: str = "mp3", fun_fact_source: Optional[str] = None, subscription: str = "yoto-club"):
    """Track generate:audio analytics event with flight and audio details"""
    try:
        import hashlib

        client_ip = extract_client_ip(request)
        user_agent = extract_user_agent(request)
        browser_info = parse_user_agent(user_agent)

        # Create consistent session ID
        hash_string = f"{client_ip or 'unknown'}:{user_agent or 'unknown'}:{lat or 0}:{lng or 0}"
        session_id = hashlib.md5(hash_string.encode('utf-8')).hexdigest()[:8]

        # Extract destination information
        destination_city = aircraft.get("destination_city", "unknown")
        destination_country = aircraft.get("destination_country", "unknown")
        destination_state = None

        # For US destinations, try to get state information
        if destination_country == "the United States":
            destination_airport = aircraft.get("destination_airport")
            if destination_airport:
                airport_data = get_airport_by_iata(destination_airport)
                if airport_data and airport_data.get("country") == "US":
                    destination_state = airport_data.get("state")

        # Extract origin information
        origin_city = aircraft.get("origin_city", "unknown")
        origin_country = aircraft.get("origin_country", "unknown")
        origin_state = None

        # For US origins, try to get state information
        if origin_country == "the United States":
            origin_airport = aircraft.get("origin_airport")
            if origin_airport:
                airport_data = get_airport_by_iata(origin_airport)
                if airport_data and airport_data.get("country") == "US":
                    origin_state = airport_data.get("state")

        # Extract other flight information
        aircraft_name = aircraft.get("aircraft", "unknown")

        # Check if fun fact was included (look for fun fact openings in the sentence)
        fun_fact_openings = ["Fun fact.", "Guess what?", "Did you know?", "A tidbit for you."]
        has_fun_fact = any(opening in sentence for opening in fun_fact_openings)

        analytics.track_event("generate:audio", {
            "ip": client_ip,
            "$user_agent": user_agent,
            "$session_id": session_id,
            "$insert_id": f"mp3_gen_{subscription}_{session_id}_{plane_index}",  # Prevents duplicates
            "browser": browser_info["browser"],
            "browser_version": browser_info["browser_version"],
            "os": browser_info["os"],
            "os_version": browser_info["os_version"],
            "device": browser_info["device"],
            "user_lat": round(lat, 2),
            "user_lng": round(lng, 2),
            "user_city": city,
            "plane_index": plane_index,
            "aircraft_name": aircraft_name,
            "origin_city": origin_city,
            "origin_state": origin_state,
            "origin_country": origin_country,
            "destination_city": destination_city,
            "destination_state": destination_state,
            "destination_country": destination_country,
            "fun_fact_source": fun_fact_source if fun_fact_source else "none",
            "has_fun_fact": has_fun_fact,
            "generation_time_ms": generation_time_ms,
            "audio_size_bytes": audio_size_bytes,
            "text_length": len(sentence),
            "tts_provider": tts_provider,
            "audio_format": audio_format,
            "model": "eleven_turbo_v2" if tts_provider == "elevenlabs" else "gemini-2.5-flash-preview-tts" if tts_provider == "google" else "unknown",
            "subscription": subscription,
        })
    except Exception as e:
        logger.error(f"Failed to track generate:audio event: {e}", exc_info=True)

def select_diverse_aircraft(
    aircraft_list: List[Dict[str, Any]],
    user_lat: Optional[float] = None,
    user_lng: Optional[float] = None,
    user_city: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Select diverse aircraft using multiple strategies for educational value and interest

    Selection strategies:
    - Geographic diversity: Prioritizes different countries and cities for destination variety
    - Cargo/private inclusion: Places one cargo or private flight in position 2 (if available)
    - Distance from user: Deprioritizes destinations within 100 miles of user's location

    Args:
        aircraft_list: List of aircraft data with destination information
        user_lat: Optional user latitude for destination distance filtering
        user_lng: Optional user longitude for destination distance filtering
        user_city: Optional city name for logging/analytics context

    Returns:
        List of up to 3 aircraft selected for maximum diversity and educational value
    """
    if not aircraft_list:
        return []

    NEARBY_THRESHOLD_KM = 160  # 100 miles
    airline_db = AirlineDatabase()

    # Step 1: Enrich aircraft with destination distance from user
    _add_destination_distance_from_user(aircraft_list, user_lat, user_lng)

    # Step 2: Categorize aircraft by operator type and destination distance
    cargo_private = []
    passenger_far = []  # Destinations > 100 miles from user
    passenger_near = []  # Destinations <= 100 miles from user

    for aircraft in aircraft_list:
        airline_icao = aircraft.get("airline_icao")

        # TODO: Remove this skip once cargo testing is complete
        # Currently excluding cargo aircraft completely for testing purposes
        if airline_icao and airline_db.is_cargo_airline(airline_icao):
            continue  # Skip cargo aircraft entirely

        # TODO: Add back cargo to this check once testing is complete
        # Currently limited to private only for additional cargo testing
        if airline_icao and airline_db.is_private_airline(airline_icao):
            cargo_private.append(aircraft)
        else:
            # Categorize passenger flights by destination distance
            dest_distance = aircraft.get("destination_distance_from_user_km")
            if dest_distance is not None and dest_distance < NEARBY_THRESHOLD_KM:
                passenger_near.append(aircraft)
            else:
                passenger_far.append(aircraft)

    # Step 3: Select diverse passenger flights (prioritize far destinations)
    passenger_pool = passenger_far + passenger_near
    selected = _select_by_destination_diversity(passenger_pool, max_count=3)

    # Step 4: Sort by proximity (closest aircraft first)
    selected.sort(key=lambda x: x.get("distance_km", float('inf')))

    # Step 5: Insert cargo/private flights intelligently
    if cargo_private:
        cargo_private.sort(key=lambda x: x.get("distance_km", float('inf')))

        if len(selected) >= 2:
            # We have 2+ passenger flights: insert cargo/private in position 2
            selected.insert(1, cargo_private[0])
            selected = selected[:3]
        elif len(selected) == 1:
            # Only 1 passenger flight: add up to 2 cargo/private
            selected.append(cargo_private[0])
            if len(cargo_private) > 1:
                selected.append(cargo_private[1])
        else:
            # No passenger flights: use up to 3 cargo/private
            selected = cargo_private[:3]

    final_selection = selected[:3]
    dest_iatas = [plane.get("destination_airport") or "UNK" for plane in final_selection]
    display_city = user_city or "Unknown"
    logger.info(
        "Diversity selection complete for city=%s; destination IATAs=%s",
        display_city,
        ", ".join(dest_iatas) if dest_iatas else "none",
    )

    return final_selection


def _add_destination_distance_from_user(aircraft_list: List[Dict[str, Any]], user_lat: Optional[float], user_lng: Optional[float]) -> None:
    """Add destination_distance_from_user_km to each aircraft"""
    if user_lat is None or user_lng is None:
        return

    for aircraft in aircraft_list:
        dest_airport_iata = aircraft.get("destination_airport")
        if not dest_airport_iata:
            aircraft["destination_distance_from_user_km"] = None
            continue

        dest_airport = get_airport_by_iata(dest_airport_iata)
        if not dest_airport:
            aircraft["destination_distance_from_user_km"] = None
            continue

        dest_lat = dest_airport.get("lat")
        dest_lng = dest_airport.get("lon")
        if dest_lat is None or dest_lng is None:
            aircraft["destination_distance_from_user_km"] = None
            continue

        try:
            dest_distance = calculate_distance(user_lat, user_lng, dest_lat, dest_lng)
            aircraft["destination_distance_from_user_km"] = dest_distance
        except Exception as e:
            logger.debug(f"Failed to calculate destination distance: {e}")
            aircraft["destination_distance_from_user_km"] = None


def _select_by_destination_diversity(aircraft_list: List[Dict[str, Any]], max_count: int = 3) -> List[Dict[str, Any]]:
    """Select aircraft ensuring diverse destinations (different countries, then cities)"""
    selected = []
    selected_indices = set()  # Track indices instead of relying on flight_id
    used_countries = set()
    used_cities = set()

    # Pass 1: Select one aircraft per unique country
    for idx, aircraft in enumerate(aircraft_list):
        if len(selected) >= max_count:
            break

        dest_country = aircraft.get("destination_country")
        dest_city = aircraft.get("destination_city")

        if dest_country and dest_country not in used_countries:
            selected.append(aircraft)
            selected_indices.add(idx)
            used_countries.add(dest_country)
            if dest_city:
                used_cities.add(dest_city)

    # Pass 2: If still need more, select aircraft with unused cities (same country OK)
    if len(selected) < max_count:
        for idx, aircraft in enumerate(aircraft_list):
            if len(selected) >= max_count:
                break

            # Skip if already selected
            if idx in selected_indices:
                continue

            dest_city = aircraft.get("destination_city")
            if dest_city and dest_city not in used_cities:
                selected.append(aircraft)
                selected_indices.add(idx)
                used_cities.add(dest_city)

    # Pass 3: Fill remaining slots with any aircraft not yet selected
    if len(selected) < max_count:
        for idx, aircraft in enumerate(aircraft_list):
            if len(selected) >= max_count:
                break

            if idx not in selected_indices:
                selected.append(aircraft)
                selected_indices.add(idx)

    return selected

async def get_nearby_aircraft(
    lat: float,
    lng: float,
    radius_km: float = 100,
    limit: int = 3,
    request: Optional[Request] = None,
    provider_override: Optional[str] = None,
    user_city: Optional[str] = None,
) -> tuple[List[Dict[str, Any]], str]:
    """Get aircraft near the given coordinates using configured providers with caching"""

    provider_sequence = get_live_aircraft_providers(request, provider_override)
    if not provider_sequence:
        logger.error("No aircraft providers are configured")
        if request:
            track_scan_complete(request, lat, lng, "Unknown", from_cache=False, nearby_aircraft=0, provider="unknown")
        return [], "No aircraft providers configured"

    provider_errors: List[str] = []
    provider_fetch_limit = max(limit + 2, 5)

    for provider_name in provider_sequence:
        provider_def = get_provider_definition(provider_name)
        if not provider_def:
            logger.warning(f"Requested aircraft provider '{provider_name}' is not registered")
            provider_errors.append(f"Provider '{provider_name}' is not registered")
            continue

        display_name = provider_def.get("display_name", provider_name)

        is_configured, config_error = provider_def["is_configured"]()
        if not is_configured:
            logger.warning(f"{display_name} is not configured: {config_error}")
            provider_errors.append(config_error or f"{display_name} is not configured")
            continue

        cache_key = s3_cache.generate_cache_key(
            lat,
            lng,
            content_type="json",
            namespace=f"provider:{provider_name}",
        )
        cached_aircraft = await s3_cache.get(cache_key, content_type="json")

        if cached_aircraft is not None:
            full_aircraft_list = cached_aircraft.get("aircraft", [])
            if full_aircraft_list:
                logger.info(f"Using cached aircraft data from {display_name}")
                if request:
                    track_scan_complete(
                        request,
                        lat,
                        lng,
                        "Unknown",
                        from_cache=True,
                        nearby_aircraft=len(full_aircraft_list),
                        provider=provider_name,
                    )
                return full_aircraft_list[:limit], ""
            else:
                logger.info(
                    f"Cache hit for {display_name} but no aircraft available; trying next provider"
                )
                provider_errors.append(f"{display_name} cache had no aircraft")
                continue

        try:
            aircraft_list, provider_error = await provider_def["fetch"](
                lat, lng, radius_km, provider_fetch_limit
            )
        except Exception as exc:
            logger.error(f"{display_name} provider raised exception: {exc}", exc_info=True)
            provider_errors.append(f"{display_name} exception: {exc}")
            continue

        if aircraft_list:
            aircraft_list.sort(key=lambda x: x.get("distance_km", float("inf")))
            aircraft_list = select_diverse_aircraft(
                aircraft_list,
                user_lat=lat,
                user_lng=lng,
                user_city=user_city,
            )

            cache_data = {"provider": provider_name, "aircraft": aircraft_list}
            asyncio.create_task(s3_cache.set(cache_key, cache_data, content_type="json"))
            logger.info(
                f"Cached {len(aircraft_list)} aircraft from {display_name} for lat={lat}, lng={lng}"
            )

            if request:
                track_scan_complete(
                    request,
                    lat,
                    lng,
                    "Unknown",
                    from_cache=False,
                    nearby_aircraft=len(aircraft_list),
                    provider=provider_name,
                )

            return aircraft_list[:limit], ""

        # No aircraft returned, cache the empty response to avoid rapid retries
        cache_data = {"provider": provider_name, "aircraft": []}
        asyncio.create_task(s3_cache.set(cache_key, cache_data, content_type="json"))
        logger.info(f"{display_name} returned no aircraft; trying next provider if available")
        provider_errors.append(provider_error or f"{display_name} returned no aircraft")

    final_error = "; ".join(error for error in provider_errors if error) or "No aircraft providers available"

    if request:
        fallback_provider = provider_sequence[-1] if provider_sequence else "unknown"
        track_scan_complete(
            request,
            lat,
            lng,
            "Unknown",
            from_cache=False,
            nearby_aircraft=0,
            provider=fallback_provider,
        )

    return [], final_error


register_test_live_aircraft_routes(
    app,
    get_user_location_fn=get_user_location,
    get_nearby_aircraft_fn=get_nearby_aircraft,
    get_provider_definition_fn=get_provider_definition,
    provider_override_secret_getter=lambda: PROVIDER_OVERRIDE_SECRET,
    select_diverse_aircraft_fn=select_diverse_aircraft,
    calculate_min_distance_to_route_fn=calculate_min_distance_to_route,
    get_airport_by_iata_fn=get_airport_by_iata,
)


async def handle_plane_endpoint(
    request: Request,
    plane_index: int,
    lat: float = None,
    lng: float = None,
    secret: Optional[str] = None,
    provider: Optional[str] = None,
    country: Optional[str] = None,
):
    """Handle individual plane endpoints (/plane/1, /plane/2, /plane/3)

    Args:
        request: FastAPI request object
        plane_index: 1-based plane index (1, 2, 3)
        lat: Optional latitude override
        lng: Optional longitude override
        secret: Secret key for provider overrides
        provider: Aircraft data provider override (requires secret)
        country: Optional country code override (e.g., "FR", "GB", "US") for testing metric/imperial units
    """
    from .free_pool import stitch_audio

    logger.info(f"Request to /plane/{plane_index}")
    validate_flight_position_override(lat, lng, secret)

    forced_provider = None
    if provider:
        ensure_override_secret(secret)
        forced_provider = provider.lower()

    # Get user location using shared function
    user_lat, user_lng, user_country_code, user_city, user_region, user_country_name = await get_user_location(request, lat, lng, country)
    country_code = user_country_code  # Keep for backwards compatibility

    # Get TTS provider override from query parameters
    tts_override = get_tts_provider_override(request)
    effective_provider = tts_override if tts_override else TTS_PROVIDER

    # Convert to 0-based index
    zero_based_index = plane_index - 1

    # Get audio format for the effective provider
    file_ext, mime_type = get_audio_format_for_provider(effective_provider)

    # Check cache first for the specific plane (include TTS provider and format in cache key)
    cache_key = s3_cache.generate_cache_key(user_lat, user_lng, plane_index=plane_index, tts_provider=effective_provider, audio_format=file_ext)
    cached_audio = await s3_cache.get(cache_key)

    if cached_audio:
        logger.info(f"Serving cached audio for plane {plane_index} at location: lat={user_lat}, lng={user_lng}, format={file_ext}")

        # Track plane request analytics for cache hit
        track_plane_request(request, user_lat, user_lng, user_city, plane_index, from_cache=True)

        response_headers = {
            "Content-Type": mime_type,
            "Content-Length": str(len(cached_audio)),
            "Accept-Ranges": "bytes",
            "Cache-Control": "public, max-age=3600",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
            "Access-Control-Allow-Headers": "Range, Content-Range, Content-Length",
            "Access-Control-Expose-Headers": "Content-Length, Content-Range, Accept-Ranges"
        }

        return StreamingResponse(
            iter([cached_audio]),
            status_code=200,
            media_type=mime_type,
            headers=response_headers
        )

    # Cache miss - get aircraft data (this will use cached API data if available)
    aircraft, error_message = await get_nearby_aircraft(
        user_lat,
        user_lng,
        limit=max(3, plane_index),
        request=request,
        provider_override=forced_provider,
        user_city=user_city,
    )


    # Check if we have the requested plane
    fun_fact_source = None  # Initialize for all cases
    opening_text = None
    body_text = None
    use_split_tts = False  # Flag to track if we can use split TTS

    if aircraft and len(aircraft) > zero_based_index:
        selected_aircraft = aircraft[zero_based_index]
        # Use split text generation for free pool support
        opening_text, body_text, fun_fact_source = generate_flight_text_for_aircraft(
            selected_aircraft, user_lat, user_lng, plane_index, country_code, split_text=True
        )
        sentence = f"{opening_text} {body_text}"
        use_split_tts = True

    elif aircraft and len(aircraft) > 0:
        # Not enough planes, return an appropriate message for this plane index
        if plane_index == 2:
            sentence = "I'm sorry my old chum but I couldn't find any more jet planes. Try firing up the scanner again soon."
        elif plane_index == 3:
            plane_count = len(aircraft)
            if plane_count == 1:
                sentence = "I'm sorry my old chum but I couldn't find any more jet planes. Try firing up the scanner again soon."
            else:
                sentence = "I'm sorry my old chum but I couldn't find any more jet planes. Try firing up the scanner again soon."
    else:
        # No aircraft found at all
        sentence = generate_flight_text([], error_message, user_lat, user_lng, country_code=country_code, user_city=user_city, user_region=user_region, user_country_name=user_country_name)

    override_sentence = get_plane_sentence_override(plane_index)
    if override_sentence:
        sentence = override_sentence
        use_split_tts = False  # Don't use split TTS for override sentences

    # Generate TTS
    import time
    tts_start_time = time.time()

    if use_split_tts and opening_text and body_text:
        # Split TTS: generate opening and body separately for free pool support
        opening_audio, opening_error, _, _, _ = await convert_text_to_speech(opening_text, tts_override=tts_override)
        body_audio, body_error, tts_provider_used, actual_file_ext, actual_mime_type = await convert_text_to_speech(body_text, tts_override=tts_override)

        if opening_audio and body_audio and not opening_error and not body_error:
            # Stitch opening + body with 1s silence at start
            audio_content = await stitch_audio(opening_audio, body_audio, add_silence=True)
            tts_error = ""

            # Cache body audio separately for free pool reuse (pre-generation handles populate_free_pool)
            # Generate location hash for body cache key
            import hashlib
            location_str = f"{round(user_lat, 2)},{round(user_lng, 2)}"
            location_hash = hashlib.md5(location_str.encode()).hexdigest()
            body_cache_key = f"cache/{location_hash}_plane{plane_index}_body_{tts_provider_used}.mp3"
            asyncio.create_task(s3_cache.set(body_cache_key, body_audio))
        else:
            # Fallback to combined sentence if split fails
            audio_content, tts_error, tts_provider_used, actual_file_ext, actual_mime_type = await convert_text_to_speech(sentence, tts_override=tts_override)
    else:
        # Single TTS call for non-split cases
        audio_content, tts_error, tts_provider_used, actual_file_ext, actual_mime_type = await convert_text_to_speech(sentence, tts_override=tts_override)

    tts_generation_time_ms = int((time.time() - tts_start_time) * 1000)

    if audio_content and not tts_error:
        # Cache the newly generated audio (don't await - do in background)
        asyncio.create_task(s3_cache.set(cache_key, audio_content))

        # Track audio generation analytics if we have aircraft data
        if aircraft and len(aircraft) > zero_based_index:
            selected_aircraft = aircraft[zero_based_index]
            track_audio_generation(request, user_lat, user_lng, user_city, plane_index, selected_aircraft, sentence, tts_generation_time_ms, len(audio_content), tts_provider_used, actual_file_ext, fun_fact_source)

        # Track plane request analytics for cache miss
        track_plane_request(request, user_lat, user_lng, user_city, plane_index, from_cache=False)

        # Return audio with correct format
        response_headers = {
            "Content-Type": actual_mime_type,
            "Content-Length": str(len(audio_content)),
            "Accept-Ranges": "bytes",
            "Cache-Control": "public, max-age=3600",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
            "Access-Control-Allow-Headers": "Range, Content-Range, Content-Length",
            "Access-Control-Expose-Headers": "Content-Length, Content-Range, Accept-Ranges"
        }

        return StreamingResponse(
            iter([audio_content]),
            status_code=200,
            media_type=actual_mime_type,
            headers=response_headers
        )
    else:
        # Fall back to text if TTS fails
        return {"message": sentence, "tts_error": tts_error}


@app.get("/intro.mp3")
async def intro_endpoint(request: Request, lat: float = None, lng: float = None):
    """Stream MP3 file from S3"""
    return await stream_intro(request, lat, lng)

@app.options("/intro.mp3") 
async def intro_options_endpoint():
    """Handle CORS preflight requests for /intro.mp3 endpoint"""
    return await intro_options()

@app.get("/overandout.mp3")
async def overandout_endpoint(request: Request, lat: float = None, lng: float = None):
    """Stream MP3 file from S3"""
    return await stream_overandout(request, lat, lng)

@app.options("/overandout.mp3") 
async def overandout_options_endpoint():
    """Handle CORS preflight requests for /overandout.mp3 endpoint"""
    return await overandout_options()

@app.get("/scanning-again.mp3")
async def scanning_again_endpoint(request: Request, lat: float = None, lng: float = None):
    """Stream MP3 file from S3"""
    logger.info("Request to /scanning-again.mp3")
    return await stream_scanning_again(request, lat, lng)

@app.options("/scanning-again.mp3") 
async def scanning_again_options_endpoint():
    """Handle CORS preflight requests for /scanning-again.mp3 endpoint"""
    return await scanning_again_options()

@app.get("/scanning.mp3")
async def scanning_endpoint(request: Request, lat: float = None, lng: float = None):
    """Stream scanning MP3 file from S3"""
    logger.info("Request to /scanning.mp3")
    return await stream_scanning(request, lat, lng)

@app.options("/scanning.mp3") 
async def scanning_options_endpoint():
    """Handle CORS preflight requests for /scanning.mp3 endpoint"""
    return await scanning_options()


@app.get("/plane/1")
async def plane_1_endpoint(
    request: Request,
    lat: float = None,
    lng: float = None,
    tts: str = None,
    secret: str = None,
    provider: str = None,
    country: str = None,
):
    """Get MP3 for the closest aircraft

    Query Parameters:
        lat: Optional latitude override (requires secret)
        lng: Optional longitude override (requires secret)
        tts: TTS provider override (requires secret)
        provider: Aircraft data provider override (requires secret)
        country: Country code override for testing metric/imperial units (e.g., "FR", "US")
        secret: Secret key for TTS/provider overrides
    """
    return await handle_plane_endpoint(request, 1, lat, lng, secret, provider, country)

@app.get("/plane/2")
async def plane_2_endpoint(
    request: Request,
    lat: float = None,
    lng: float = None,
    tts: str = None,
    secret: str = None,
    provider: str = None,
    country: str = None,
):
    """Get MP3 for the second closest aircraft

    Query Parameters:
        lat: Optional latitude override (requires secret)
        lng: Optional longitude override (requires secret)
        tts: TTS provider override (requires secret)
        provider: Aircraft data provider override (requires secret)
        country: Country code override for testing metric/imperial units (e.g., "FR", "US")
        secret: Secret key for TTS/provider overrides
    """
    return await handle_plane_endpoint(request, 2, lat, lng, secret, provider, country)

@app.get("/plane/3")
async def plane_3_endpoint(
    request: Request,
    lat: float = None,
    lng: float = None,
    tts: str = None,
    secret: str = None,
    provider: str = None,
    country: str = None,
):
    """Get MP3 for the third closest aircraft

    Query Parameters:
        lat: Optional latitude override (requires secret)
        lng: Optional longitude override (requires secret)
        tts: TTS provider override (requires secret)
        provider: Aircraft data provider override (requires secret)
        country: Country code override for testing metric/imperial units (e.g., "FR", "US")
        secret: Secret key for TTS/provider overrides
    """
    return await handle_plane_endpoint(request, 3, lat, lng, secret, provider, country)

@app.options("/plane/1")
async def plane_1_options():
    """Handle CORS preflight requests for /plane/1 endpoint"""
    return StreamingResponse(
        iter([b""]),
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
            "Access-Control-Allow-Headers": "Range, Content-Range, Content-Length",
            "Access-Control-Max-Age": "3600"
        }
    )

@app.options("/plane/2")
async def plane_2_options():
    """Handle CORS preflight requests for /plane/2 endpoint"""
    return StreamingResponse(
        iter([b""]),
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
            "Access-Control-Allow-Headers": "Range, Content-Range, Content-Length",
            "Access-Control-Max-Age": "3600"
        }
    )

@app.options("/plane/3")
async def plane_3_options():
    """Handle CORS preflight requests for /plane/3 endpoint"""
    return StreamingResponse(
        iter([b""]),
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
            "Access-Control-Allow-Headers": "Range, Content-Range, Content-Length",
            "Access-Control-Max-Age": "3600"
        }
    )


# =============================================================================
# FREE TIER ENDPOINTS
# =============================================================================

from fastapi.responses import JSONResponse

from .free_pool import (
    get_free_pool_index,
    get_session_for_free_user,
    check_free_tier_rate_limit,
    get_empty_pool_audio,
    stitch_audio,
)

# Free tier S3 base URL
FREE_TIER_S3_BASE = "https://dreaming-of-a-jet-plane.s3.us-east-2.amazonaws.com/free"


async def stream_free_static_mp3(request: Request, filename: str):
    """Stream a static MP3 file from the free tier S3 folder

    Args:
        request: FastAPI request object
        filename: MP3 filename (e.g., "scanning.mp3", "overandout.mp3")

    Returns:
        StreamingResponse with the MP3 content
    """
    mp3_url = f"{FREE_TIER_S3_BASE}/{filename}"

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
                content = response.content
                content_length = len(content)

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
                return JSONResponse(
                    {"error": f"MP3 file not accessible. Status: {response.status_code}"},
                    status_code=response.status_code
                )

    except httpx.TimeoutException:
        return JSONResponse({"error": "Timeout accessing MP3 file"}, status_code=504)
    except Exception as e:
        logger.error(f"Error streaming free tier MP3 {filename}: {e}")
        return JSONResponse({"error": f"Failed to stream MP3: {str(e)}"}, status_code=500)


import random as _random

async def fetch_random_free_intro() -> Optional[bytes]:
    """Fetch a random intro audio file from S3 (flight-intro-1 through flight-intro-6)

    Returns:
        Audio bytes if successful, None if all intros fail to load
    """
    intro_number = _random.randint(1, 6)
    intro_key = f"free/intros/flight-intro-{intro_number}.mp3"

    intro_audio = await s3_cache.get_raw(intro_key)
    if intro_audio:
        return intro_audio

    # If the random one failed, try others
    for fallback_num in range(1, 7):
        if fallback_num == intro_number:
            continue
        fallback_key = f"free/intros/flight-intro-{fallback_num}.mp3"
        intro_audio = await s3_cache.get_raw(fallback_key)
        if intro_audio:
            logger.warning(f"Free intro {intro_number} not found, using fallback {fallback_num}")
            return intro_audio

    logger.error("No free intro files found in S3")
    return None


async def handle_free_plane_endpoint(request: Request, plane_index: int):
    """Handle free tier requests - planes 1, 2, and 3

    Free users hear pre-generated audio from paid scans, without real-time API calls.
    All planes get a random static intro (from flight-intro-1 to flight-intro-6) + cached body.
    """
    # Free tier limited to 3 planes
    if plane_index > 3:
        return JSONResponse(
            {"error": "Free tier limited to 3 planes"},
            status_code=400
        )

    client_ip = extract_client_ip(request)

    # Check rate limit
    is_allowed, retry_after = check_free_tier_rate_limit(client_ip)
    if not is_allowed:
        return JSONResponse(
            {"error": "Rate limit exceeded", "retry_after": retry_after},
            status_code=429,
            headers={"Retry-After": str(retry_after)}
        )

    # Get free pool index
    index = await get_free_pool_index()
    if not index or not index.get("entries"):
        # Empty pool - return friendly message
        empty_audio = await get_empty_pool_audio(convert_text_to_speech)
        if empty_audio:
            return StreamingResponse(
                iter([empty_audio]),
                media_type="audio/mpeg",
                headers={
                    "Content-Type": "audio/mpeg",
                    "Content-Length": str(len(empty_audio)),
                    "Access-Control-Allow-Origin": "*",
                    "Cache-Control": "public, max-age=60"
                }
            )
        return JSONResponse(
            {"error": "Free pool is warming up, check back soon"},
            status_code=503
        )

    # Select consistent session for this user
    session = get_session_for_free_user(client_ip, index)
    if not session:
        return JSONResponse(
            {"error": "No sessions available"},
            status_code=503
        )

    planes = session.get("planes", [])
    plane_data = None
    for p in planes:
        if p.get("index") == plane_index:
            plane_data = p
            break

    if not plane_data:
        # This plane not available in this session
        empty_audio = await get_empty_pool_audio(convert_text_to_speech)
        if empty_audio:
            return StreamingResponse(
                iter([empty_audio]),
                media_type="audio/mpeg",
                headers={
                    "Content-Type": "audio/mpeg",
                    "Access-Control-Allow-Origin": "*"
                }
            )
        return JSONResponse(
            {"error": f"Plane {plane_index} not available in this session"},
            status_code=404
        )

    # Fetch cached body audio from free pool
    body_audio = await s3_cache.get_raw(plane_data["body_cache_key"])

    if not body_audio:
        logger.warning(f"Free pool body audio missing for session {session.get('id')}, plane {plane_index}")
        empty_audio = await get_empty_pool_audio(convert_text_to_speech)
        if empty_audio:
            return StreamingResponse(
                iter([empty_audio]),
                media_type="audio/mpeg",
                headers={
                    "Content-Type": "audio/mpeg",
                    "Access-Control-Allow-Origin": "*"
                }
            )
        return JSONResponse(
            {"error": "Audio temporarily unavailable"},
            status_code=503
        )

    # Fetch random static intro from S3
    intro_audio = await fetch_random_free_intro()

    if not intro_audio:
        # No intro available, just return body with silence
        logger.warning("No free intro audio available, serving body only")
        from pydub import AudioSegment
        import io
        silence = AudioSegment.silent(duration=1000)
        body_seg = AudioSegment.from_file(io.BytesIO(body_audio), format="mp3")
        combined_seg = silence + body_seg
        output = io.BytesIO()
        combined_seg.export(output, format="mp3")
        combined = output.getvalue()
    else:
        # Stitch: silence + random intro + body
        combined = await stitch_audio(intro_audio, body_audio, add_silence=True)

    # Get user location for tracking
    user_lat, user_lng, _, user_city, _, _ = await get_user_location(request)

    # Track analytics using unified event with subscription=free
    track_plane_request(
        request=request,
        lat=user_lat,
        lng=user_lng,
        city=user_city,
        plane_index=plane_index,
        from_cache=True,  # Free tier always serves cached content
        subscription="free",
        free_pool_entry_id=session.get("id"),
    )

    return StreamingResponse(
        iter([combined]),
        media_type="audio/mpeg",
        headers={
            "Content-Type": "audio/mpeg",
            "Content-Length": str(len(combined)),
            "Accept-Ranges": "bytes",
            "Cache-Control": "public, max-age=3600",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
            "Access-Control-Allow-Headers": "Range, Content-Range, Content-Length",
            "Access-Control-Expose-Headers": "Content-Length, Content-Range, Accept-Ranges"
        }
    )


@app.get("/free/scan")
async def free_scan_endpoint(request: Request):
    """Free tier scan intro - serves static audio from S3, NO pre-caching

    This endpoint serves a pre-generated static intro audio file for free users.
    Unlike paid /scan, this does not trigger any pre-caching or API calls.
    """
    client_ip = extract_client_ip(request)

    # Check rate limit
    is_allowed, retry_after = check_free_tier_rate_limit(client_ip)
    if not is_allowed:
        return JSONResponse(
            {"error": "Rate limit exceeded", "retry_after": retry_after},
            status_code=429,
            headers={"Retry-After": str(retry_after)}
        )

    # Track analytics using unified event with subscription=free
    track_scan_start(request, subscription="free")

    # Serve static file from S3 free folder
    return await stream_free_static_mp3(request, "scanning.mp3")


@app.get("/free/scanning")
async def free_scanning_endpoint(request: Request):
    """Free tier scanning audio - serves static file from S3"""
    client_ip = extract_client_ip(request)

    # Check rate limit
    is_allowed, retry_after = check_free_tier_rate_limit(client_ip)
    if not is_allowed:
        return JSONResponse(
            {"error": "Rate limit exceeded", "retry_after": retry_after},
            status_code=429,
            headers={"Retry-After": str(retry_after)}
        )

    # Track analytics
    track_scan_start(request, subscription="free")

    return await stream_free_static_mp3(request, "scanning.mp3")


@app.get("/free/scanning-again")
async def free_scanning_again_endpoint(request: Request):
    """Free tier scanning-again audio - serves static file from S3"""
    client_ip = extract_client_ip(request)

    # Check rate limit
    is_allowed, retry_after = check_free_tier_rate_limit(client_ip)
    if not is_allowed:
        return JSONResponse(
            {"error": "Rate limit exceeded", "retry_after": retry_after},
            status_code=429,
            headers={"Retry-After": str(retry_after)}
        )

    return await stream_free_static_mp3(request, "scanning-again.mp3")


@app.get("/free/overandout")
async def free_overandout_endpoint(request: Request):
    """Free tier overandout audio - serves static file from S3"""
    client_ip = extract_client_ip(request)

    # Check rate limit
    is_allowed, retry_after = check_free_tier_rate_limit(client_ip)
    if not is_allowed:
        return JSONResponse(
            {"error": "Rate limit exceeded", "retry_after": retry_after},
            status_code=429,
            headers={"Retry-After": str(retry_after)}
        )

    return await stream_free_static_mp3(request, "overandout.mp3")


@app.options("/free/scan")
async def free_scan_options():
    """Handle CORS preflight requests for /free/scan endpoint"""
    return StreamingResponse(
        iter([b""]),
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
            "Access-Control-Allow-Headers": "Range, Content-Range, Content-Length",
            "Access-Control-Max-Age": "3600"
        }
    )


@app.get("/free/plane/1")
async def free_plane_1_endpoint(request: Request):
    """Get MP3 for free tier plane 1

    Free tier plane 1 includes a dynamic distance intro calculated from
    the free user's location to the cached flight position.
    """
    return await handle_free_plane_endpoint(request, 1)


@app.get("/free/plane/2")
async def free_plane_2_endpoint(request: Request):
    """Get MP3 for free tier plane 2

    Free tier plane 2 includes a generic opening (no distance) + cached body.
    """
    return await handle_free_plane_endpoint(request, 2)


@app.get("/free/plane/3")
async def free_plane_3_endpoint(request: Request):
    """Get MP3 for free tier plane 3

    Free tier plane 3 includes a generic opening (no distance) + cached body.
    """
    return await handle_free_plane_endpoint(request, 3)


@app.options("/free/plane/1")
async def free_plane_1_options():
    """Handle CORS preflight requests for /free/plane/1 endpoint"""
    return StreamingResponse(
        iter([b""]),
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
            "Access-Control-Allow-Headers": "Range, Content-Range, Content-Length",
            "Access-Control-Max-Age": "3600"
        }
    )


@app.options("/free/plane/2")
async def free_plane_2_options():
    """Handle CORS preflight requests for /free/plane/2 endpoint"""
    return StreamingResponse(
        iter([b""]),
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
            "Access-Control-Allow-Headers": "Range, Content-Range, Content-Length",
            "Access-Control-Max-Age": "3600"
        }
    )


@app.options("/free/plane/3")
async def free_plane_3_options():
    """Handle CORS preflight requests for /free/plane/3 endpoint"""
    return StreamingResponse(
        iter([b""]),
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
            "Access-Control-Allow-Headers": "Range, Content-Range, Content-Length",
            "Access-Control-Max-Age": "3600"
        }
    )


@app.options("/free/scanning")
async def free_scanning_options():
    """Handle CORS preflight requests for /free/scanning endpoint"""
    return StreamingResponse(
        iter([b""]),
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
            "Access-Control-Allow-Headers": "Range, Content-Range, Content-Length",
            "Access-Control-Max-Age": "3600"
        }
    )


@app.options("/free/scanning-again")
async def free_scanning_again_options():
    """Handle CORS preflight requests for /free/scanning-again endpoint"""
    return StreamingResponse(
        iter([b""]),
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
            "Access-Control-Allow-Headers": "Range, Content-Range, Content-Length",
            "Access-Control-Max-Age": "3600"
        }
    )


@app.options("/free/overandout")
async def free_overandout_options():
    """Handle CORS preflight requests for /free/overandout endpoint"""
    return StreamingResponse(
        iter([b""]),
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
            "Access-Control-Allow-Headers": "Range, Content-Range, Content-Length",
            "Access-Control-Max-Age": "3600"
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
