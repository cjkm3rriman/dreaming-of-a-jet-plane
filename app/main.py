from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, HTMLResponse
import httpx
import math
import os
import sys
import asyncio
import logging
import boto3
from botocore.exceptions import BotoCoreError, ClientError
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

from .aircraft_database import get_aircraft_name, get_passenger_capacity
from .airport_database import get_city_country, get_airport_by_iata
from .airline_database import get_airline_name
from .intro import stream_intro, intro_options
from .overandout import stream_overandout, overandout_options
from .scanning_again import stream_scanning_again, scanning_again_options
from .scanning import stream_scanning, scanning_options
from .s3_cache import s3_cache
from .flight_text import generate_flight_text, generate_flight_text_for_aircraft
from .location_utils import get_user_location, extract_client_ip, extract_user_agent, parse_user_agent
from .analytics import analytics
from .website_home import register_website_home_routes
from .test_gemini_tts import register_test_gemini_tts_routes

app = FastAPI()

# Register website home routes
register_website_home_routes(app)

# Register test Gemini TTS routes
register_test_gemini_tts_routes(app)

# Flightradar24 API configuration
FR24_API_KEY = os.getenv("FR24_API_KEY")
FR24_BASE_URL = "https://fr24api.flightradar24.com"

# TTS Configuration
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "elevenlabs")  # Options: "elevenlabs", "polly", "google", "fallback"

# ElevenLabs API configuration
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_TEXT_TO_VOICE_API_KEY")
ELEVENLABS_BASE_URL = "https://api.elevenlabs.io/v1"
DEFAULT_VOICE_ID = "goT3UYdM9bhm0n2lmKQx"  # Edward voice - British, Dark, Seductive, Low

# AWS Polly configuration
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_POLLY_REGION = os.getenv("AWS_POLLY_REGION", "us-east-1")

# Google Gemini TTS configuration
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# TTS Provider Override configuration
TTS_PROVIDER_OVERRIDE_SECRET = os.getenv("TTS_PROVIDER_OVERRIDE_SECRET")

def get_tts_provider_override(request: Request) -> Optional[str]:
    """Extract and validate TTS provider override from query parameters

    Allows testing different TTS providers via query parameters:
    Example: ?tts=google&secret=your_secret_key

    Args:
        request: FastAPI Request object

    Returns:
        str: Provider name if valid override, None otherwise
    """
    if not TTS_PROVIDER_OVERRIDE_SECRET:
        return None

    # Extract query parameters
    tts_param = request.query_params.get("tts")
    secret_param = request.query_params.get("secret")

    # Validate both parameters are present
    if not tts_param or not secret_param:
        return None

    # Validate secret
    if secret_param != TTS_PROVIDER_OVERRIDE_SECRET:
        logger.warning(f"Invalid TTS override secret attempt from IP: {extract_client_ip(request)}")
        return None

    # Validate provider is supported
    valid_providers = ["elevenlabs", "polly", "google", "fallback"]
    if tts_param.lower() not in valid_providers:
        logger.warning(f"Invalid TTS provider override: {tts_param}")
        return None

    logger.info(f"TTS provider override: {tts_param} from IP: {extract_client_ip(request)}")
    return tts_param.lower()

def get_audio_format_for_provider(provider: str) -> tuple[str, str]:
    """Get audio file extension and MIME type for TTS provider

    Args:
        provider: TTS provider name (elevenlabs, polly, google)

    Returns:
        tuple: (file_extension, mime_type)
        - file_extension: "mp3" or "ogg"
        - mime_type: "audio/mpeg" or "audio/ogg"
    """
    format_map = {
        "elevenlabs": ("mp3", "audio/mpeg"),
        "polly": ("mp3", "audio/mpeg"),
        "google": ("mp3", "audio/mpeg"),  # TODO: Switch back to OGG later
    }
    return format_map.get(provider.lower(), ("mp3", "audio/mpeg"))

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

def get_voice_folder() -> str:
    """Get the voice folder name based on TTS provider configuration

    Returns:
        str: "edward" for ElevenLabs, "amy" for AWS Polly, "sadachbia" for Google TTS
    """
    provider = TTS_PROVIDER.lower()
    if provider in ["elevenlabs", "fallback"]:
        return "edward"
    elif provider == "polly":
        return "amy"
    elif provider == "google":
        return "sadachbia"
    else:
        # Default to edward for unknown providers
        return "edward"

def get_voice_specific_s3_url(filename: str) -> str:
    """Generate voice-specific S3 URL for static MP3 files
    
    Args:
        filename: The MP3 filename (e.g., "scanning.mp3")
        
    Returns:
        str: Full S3 URL with voice folder (e.g., "https://.../edward/scanning.mp3")
    """
    voice_folder = get_voice_folder()
    return f"https://dreaming-of-a-jet-plane.s3.us-east-2.amazonaws.com/{voice_folder}/{filename}"


async def convert_text_to_speech_polly(text: str) -> tuple[bytes, str]:
    """Convert text to speech using AWS Polly with Arthur voice
    
    Returns:
        tuple: (audio_content, error_message)
        - audio_content: MP3 audio bytes if successful, empty bytes if failed
        - error_message: Empty string if successful, error description if failed
    """
    if not AWS_ACCESS_KEY_ID or not AWS_SECRET_ACCESS_KEY:
        logger.warning("AWS credentials not configured for Polly")
        return b"", "AWS credentials not configured"
    
    try:
        # Create Polly client
        polly_client = boto3.client(
            'polly',
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            region_name=AWS_POLLY_REGION
        )
        
        # Wrap text in SSML with prosody for medium rate and 1 second pause
        ssml_text = f'<speak><break time="1s"/><prosody rate="medium">{text}</prosody></speak>'
        
        logger.info(f"AWS Polly Request: Voice=Amy, Engine=neural")
        
        # Synthesize speech
        response = polly_client.synthesize_speech(
            Text=ssml_text,
            TextType='ssml',
            OutputFormat='mp3',
            VoiceId='Amy',
            Engine='neural',
            SampleRate='24000'
        )
        
        # Read audio stream
        audio_content = response['AudioStream'].read()
        
        logger.info(f"AWS Polly Response: Success, {len(audio_content)} bytes")
        return audio_content, ""
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_msg = e.response['Error']['Message']
        logger.error(f"AWS Polly ClientError: {error_code} - {error_msg}")
        return b"", f"AWS Polly error: {error_code} - {error_msg}"
    except BotoCoreError as e:
        logger.error(f"AWS Polly BotoCoreError: {str(e)}")
        return b"", f"AWS Polly connection error: {str(e)}"
    except Exception as e:
        logger.error(f"AWS Polly Unexpected Error: {str(e)}")
        return b"", f"AWS Polly unexpected error: {str(e)}"

async def convert_text_to_speech_google(text: str) -> tuple[bytes, str]:
    """Convert text to speech using Google Gemini 2.5 Flash Preview TTS

    Returns:
        tuple: (audio_content, error_message)
        - audio_content: OGG Opus audio bytes if successful, empty bytes if failed
        - error_message: Empty string if successful, error description if failed
    """
    if not GOOGLE_API_KEY:
        logger.warning("Google API key not configured")
        return b"", "Google API key not configured"

    try:
        # Import Google GenAI SDK
        from google import genai
        from google.genai import types
        import subprocess
        import time

        # Initialize Gemini client
        client = genai.Client(api_key=GOOGLE_API_KEY)

        # Gemini TTS configuration
        MODEL_ID = "gemini-2.5-flash-preview-tts"
        VOICE_NAME = "Sadachbia"
        VOICE_PROMPT = "Read the text in a posh British male voice, with a deep, rich baritone tone. Use precise articulation and a refined, formal delivery with minimal inflection and a very even pitch."

        logger.info(f"Gemini TTS Request: Model={MODEL_ID}, Voice={VOICE_NAME}, Text='{text[:50]}...'")

        # Start timing
        start_time = time.time()

        # Prepend voice prompt to the text content with colon separator
        prompt_with_text = f"{VOICE_PROMPT}: {text}"

        # Generate audio using Gemini (run in thread pool to avoid blocking event loop)
        def _generate_gemini_audio():
            return client.models.generate_content(
                model=MODEL_ID,
                contents=prompt_with_text,
                config=types.GenerateContentConfig(
                    temperature=1.1,
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        language_code="en-GB",
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name=VOICE_NAME
                            )
                        )
                    )
                )
            )

        response = await asyncio.to_thread(_generate_gemini_audio)

        # Extract PCM data from response
        pcm_data = response.candidates[0].content.parts[0].inline_data.data
        api_time = time.time() - start_time
        logger.info(f"Gemini API complete: {len(pcm_data)} bytes PCM in {api_time:.2f}s")

        # Convert PCM to MP3 using ffmpeg (run in thread pool to avoid blocking event loop)
        def _convert_pcm_to_mp3():
            ffmpeg_process = subprocess.Popen(
                [
                    'ffmpeg',
                    '-f', 's16le',  # 16-bit little-endian PCM
                    '-ar', '24000',  # 24kHz sample rate
                    '-ac', '1',  # mono
                    '-i', 'pipe:0',  # input from stdin
                    '-af', 'asetrate=24000*0.97,aresample=24000,atempo=1.2',  # Lower pitch 3% + speed up 20%
                    '-c:a', 'libmp3lame',  # MP3 codec
                    '-b:a', '64k',  # bitrate
                    '-f', 'mp3',  # MP3 format
                    'pipe:1'  # output to stdout
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            return ffmpeg_process.communicate(input=pcm_data)

        mp3_data, ffmpeg_error = await asyncio.to_thread(_convert_pcm_to_mp3)

        total_time = time.time() - start_time
        logger.info(f"Conversion complete: {len(mp3_data)} bytes MP3 in {total_time:.2f}s total")

        return mp3_data, ""

    except ImportError as e:
        logger.error(f"Gemini TTS ImportError: {str(e)}")
        return b"", f"Gemini TTS import error: {str(e)}"
    except Exception as e:
        logger.error(f"Gemini TTS Error: {str(e)}")
        return b"", f"Gemini TTS unexpected error: {str(e)}"

async def convert_text_to_speech_elevenlabs(text: str) -> tuple[bytes, str]:
    """Convert text to speech using ElevenLabs API
    
    Returns:
        tuple: (audio_content, error_message)
        - audio_content: MP3 audio bytes if successful, empty bytes if failed
        - error_message: Empty string if successful, error description if failed
    """
    if not ELEVENLABS_API_KEY:
        logger.warning("ElevenLabs API key not configured")
        return b"", "ElevenLabs API key not configured"
    
    try:
        # Add 1 second pause at the start of the text
        text_with_pause = '<break time="1s"/>' + text
        
        # Prepare the request to ElevenLabs API
        url = f"{ELEVENLABS_BASE_URL}/text-to-speech/{DEFAULT_VOICE_ID}"
        
        headers = {
            "xi-api-key": ELEVENLABS_API_KEY,
            "Content-Type": "application/json"
        }
        
        payload = {
            "text": text_with_pause,
            "model_id": "eleven_turbo_v2",
            "voice_settings": {
                "stability": 0.6,
                "similarity_boost": 0.5
            }
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            
            if response.status_code == 200:
                return response.content, ""
            else:
                logger.error(f"ElevenLabs API error: {response.status_code}")
                
                return b"", f"ElevenLabs API returned status {response.status_code}"
                
    except httpx.TimeoutException:
        logger.error("ElevenLabs API timeout")
        return b"", "ElevenLabs API timeout (30 seconds exceeded)"
    except httpx.RequestError as e:
        logger.error(f"ElevenLabs API connection error: {str(e)}")
        return b"", f"ElevenLabs API connection error: {str(e)}"
    except Exception as e:
        logger.error(f"ElevenLabs API error: {str(e)}")
        return b"", f"ElevenLabs API unexpected error: {str(e)}"

async def convert_text_to_speech(text: str, tts_override: Optional[str] = None) -> tuple[bytes, str, str, str, str]:
    """Convert text to speech using configured or overridden TTS provider

    Supports multiple providers based on TTS_PROVIDER environment variable:
    - "elevenlabs": Use ElevenLabs (default)
    - "polly": Use AWS Polly
    - "google": Use Google Gemini Flash TTS
    - "fallback": Try ElevenLabs first, fallback to Polly on error

    Args:
        text: Text to convert to speech
        tts_override: Optional TTS provider override (from query params)

    Returns:
        tuple: (audio_content, error_message, provider_used, file_extension, mime_type)
        - audio_content: Audio bytes if successful, empty bytes if failed
        - error_message: Empty string if successful, error description if failed
        - provider_used: Which provider was actually used ("elevenlabs", "polly", or "google")
        - file_extension: File extension for the audio format ("mp3" or "ogg")
        - mime_type: MIME type for the audio format ("audio/mpeg" or "audio/ogg")
    """
    provider = tts_override.lower() if tts_override else TTS_PROVIDER.lower()

    audio_content = b""
    error = ""
    provider_used = ""

    if provider == "elevenlabs":
        audio_content, error = await convert_text_to_speech_elevenlabs(text)
        provider_used = "elevenlabs"
    elif provider == "polly":
        audio_content, error = await convert_text_to_speech_polly(text)
        provider_used = "polly"
    elif provider == "google":
        audio_content, error = await convert_text_to_speech_google(text)
        provider_used = "google"
    elif provider == "fallback":
        # Try ElevenLabs first, fallback to Polly on error
        logger.info("Using fallback strategy: trying ElevenLabs first")
        audio_content, error = await convert_text_to_speech_elevenlabs(text)
        if audio_content and not error:
            provider_used = "elevenlabs"
        else:
            logger.info(f"ElevenLabs failed ({error}), falling back to AWS Polly")
            audio_content, error = await convert_text_to_speech_polly(text)
            provider_used = "polly"
    else:
        error_msg = f"Unknown TTS provider: {provider}. Use 'elevenlabs', 'polly', 'google', or 'fallback'"
        logger.error(error_msg)
        return b"", error_msg, "unknown", "mp3", "audio/mpeg"

    # Get format info for the provider that was used
    file_ext, mime_type = get_audio_format_for_provider(provider_used)
    return audio_content, error, provider_used, file_ext, mime_type

def track_scan_complete(request: Request, lat: float, lng: float, from_cache: bool, nearby_aircraft: int):
    """Track scan:complete analytics event with flight data results"""
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
            "$insert_id": f"scan_complete_{session_id}",  # Prevents duplicates
            "browser": browser_info["browser"],
            "browser_version": browser_info["browser_version"],
            "os": browser_info["os"],
            "os_version": browser_info["os_version"],
            "device": browser_info["device"],
            "lat": round(lat, 3),
            "lng": round(lng, 3),
            "from_cache": from_cache,
            "nearby_aircraft": nearby_aircraft
        })
    except Exception as e:
        logger.error(f"Failed to track scan:complete event: {e}", exc_info=True)

def track_plane_request(request: Request, lat: float, lng: float, plane_index: int, from_cache: bool):
    """Track plane:request analytics event for plane endpoint requests"""
    try:
        import hashlib
        
        client_ip = extract_client_ip(request)
        user_agent = extract_user_agent(request)
        browser_info = parse_user_agent(user_agent)
        
        # Create consistent session ID
        hash_string = f"{client_ip or 'unknown'}:{user_agent or 'unknown'}:{lat or 0}:{lng or 0}"
        session_id = hashlib.md5(hash_string.encode('utf-8')).hexdigest()[:8]
        
        analytics.track_event("plane:request", {
            "ip": client_ip,
            "$user_agent": user_agent,
            "$session_id": session_id,
            "$insert_id": f"plane_req_{session_id}_{plane_index}",  # Prevents duplicates
            "browser": browser_info["browser"],
            "browser_version": browser_info["browser_version"],
            "os": browser_info["os"],
            "os_version": browser_info["os_version"],
            "device": browser_info["device"],
            "lat": round(lat, 3),
            "lng": round(lng, 3),
            "plane_index": plane_index,
            "from_cache": from_cache
        })
    except Exception as e:
        logger.error(f"Failed to track plane:request event: {e}", exc_info=True)

def track_audio_generation(request: Request, lat: float, lng: float, plane_index: int, aircraft: Dict[str, Any], sentence: str, generation_time_ms: int, audio_size_bytes: int, tts_provider: str = "elevenlabs", audio_format: str = "mp3"):
    """Track generate:audio analytics event with flight and audio details"""
    try:
        import hashlib
        
        client_ip = extract_client_ip(request)
        user_agent = extract_user_agent(request)
        browser_info = parse_user_agent(user_agent)
        
        # Create consistent session ID
        hash_string = f"{client_ip or 'unknown'}:{user_agent or 'unknown'}:{lat or 0}:{lng or 0}"
        session_id = hashlib.md5(hash_string.encode('utf-8')).hexdigest()[:8]
        
        # Extract flight information
        aircraft_name = aircraft.get("aircraft", "unknown")
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
        
        # Check if fun fact was included (look for fun fact openings in the sentence)
        fun_fact_openings = ["Fun fact.", "Guess what?", "Did you know?", "A tidbit for you."]
        has_fun_fact = any(opening in sentence for opening in fun_fact_openings)
        
        analytics.track_event("generate:audio", {
            "ip": client_ip,
            "$user_agent": user_agent,
            "$session_id": session_id,
            "$insert_id": f"mp3_gen_{session_id}_{plane_index}",  # Prevents duplicates
            "browser": browser_info["browser"],
            "browser_version": browser_info["browser_version"],
            "os": browser_info["os"],
            "os_version": browser_info["os_version"],
            "device": browser_info["device"],
            "lat": round(lat, 3),
            "lng": round(lng, 3),
            "plane_index": plane_index,
            "aircraft_name": aircraft_name,
            "destination_city": destination_city,
            "destination_state": destination_state,
            "destination_country": destination_country,
            "has_fun_fact": has_fun_fact,
            "generation_time_ms": generation_time_ms,
            "audio_size_bytes": audio_size_bytes,
            "text_length": len(sentence),
            "tts_provider": tts_provider,
            "audio_format": audio_format,
            "model": "eleven_turbo_v2" if tts_provider == "elevenlabs" else "amy_neural" if tts_provider == "polly" else "gemini-2.5-flash-preview-tts" if tts_provider == "google" else "unknown"
        })
    except Exception as e:
        logger.error(f"Failed to track generate:audio event: {e}", exc_info=True)

def select_geographically_diverse_aircraft(aircraft_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Select aircraft prioritizing destination diversity (city + country) over proximity
    
    Args:
        aircraft_list: List of aircraft data with destination information
    
    Returns:
        List of aircraft sorted by destination diversity first, then proximity
    """
    if not aircraft_list:
        return aircraft_list
    
    # Group aircraft by destination city, then by country as fallback
    city_groups = {}
    country_groups = {}
    
    for aircraft in aircraft_list:
        dest_city = aircraft.get("destination_city")
        dest_country = aircraft.get("destination_country")
        
        # Group by city (most specific)
        if dest_city:
            if dest_city not in city_groups:
                city_groups[dest_city] = []
            city_groups[dest_city].append(aircraft)
        
        # Also group by country for fallback
        if dest_country:
            if dest_country not in country_groups:
                country_groups[dest_country] = []
            country_groups[dest_country].append(aircraft)
        
    # Sort aircraft within each group by distance (closest first)
    for city, planes in city_groups.items():
        planes.sort(key=lambda x: x.get("distance_km", float('inf')))
    for country, planes in country_groups.items():
        planes.sort(key=lambda x: x.get("distance_km", float('inf')))
    
    selected_aircraft = []
    used_cities = set()
    used_countries = set()
    
    # First pass: select one aircraft per destination COUNTRY (prioritize country diversity)
    for country, planes in country_groups.items():
        if len(selected_aircraft) < 3:
            selected_aircraft.append(planes[0])  # Closest plane to this country
            used_countries.add(country)
            # Also track the city to avoid duplicate cities when possible
            dest_city = planes[0].get("destination_city")
            if dest_city:
                used_cities.add(dest_city)
    
    # Second pass: if we still need more aircraft, select from unused cities (within used countries)
    if len(selected_aircraft) < 3:
        for city, planes in city_groups.items():
            if city not in used_cities and len(selected_aircraft) < 3:
                # Add this plane even if the country is already used (city diversity within countries)
                selected_aircraft.append(planes[0])
                used_cities.add(city)
                dest_country = planes[0].get("destination_country")
                if dest_country:
                    used_countries.add(dest_country)
    
    # Third pass: if we still need more aircraft, add more from any city/country
    if len(selected_aircraft) < 3:
        for city, planes in city_groups.items():
            for plane in planes[1:]:  # Skip the first plane (may already be selected)
                if len(selected_aircraft) >= 3:
                    break
                # Check if this specific plane is already selected
                if not any(p.get("flight_id") == plane.get("flight_id") for p in selected_aircraft):
                    selected_aircraft.append(plane)
            if len(selected_aircraft) >= 3:
                break
    
    # Fourth pass: add aircraft without destination cities/countries if still needed
    if len(selected_aircraft) < 3:
        aircraft_without_dest = [a for a in aircraft_list if not a.get("destination_city") and not a.get("destination_country")]
        aircraft_without_dest.sort(key=lambda x: x.get("distance_km", float('inf')))
        for plane in aircraft_without_dest:
            if len(selected_aircraft) >= 3:
                break
            selected_aircraft.append(plane)
    
    # Sort final selection by distance to maintain proximity logic
    selected_aircraft.sort(key=lambda x: x.get("distance_km", float('inf')))
    
    return selected_aircraft[:3]  # Ensure we never return more than 3

async def get_nearby_aircraft(lat: float, lng: float, radius_km: float = 100, limit: int = 3, request: Optional[Request] = None) -> tuple[List[Dict[str, Any]], str]:
    """Get aircraft near the given coordinates using Flightradar24 API with caching
    
    Args:
        lat: Latitude
        lng: Longitude
        radius_km: Search radius in kilometers
        limit: Maximum number of aircraft to return (default 3)
    
    Returns:
        tuple: (aircraft_list, error_message)
        - aircraft_list: List of aircraft data
        - error_message: Empty string if successful, error description if failed
    """
    if not FR24_API_KEY:
        logger.warning("Flightradar24 API key not configured")
        return [], "Flightradar24 API key not configured"
    
    # Check API response cache first
    api_cache_key = s3_cache.generate_cache_key(lat, lng, content_type="json")
    cached_aircraft = await s3_cache.get(api_cache_key, content_type="json")
    
    if cached_aircraft:
        # Get full cached aircraft list
        full_aircraft_list = cached_aircraft.get('aircraft', [])
        
        # Track analytics for cache hit with total count if request is provided
        if request:
            track_scan_complete(request, lat, lng, from_cache=True, nearby_aircraft=len(full_aircraft_list))
        
        # Return up to limit aircraft from cached data
        return full_aircraft_list[:limit], ""
    
    try:
        # Create bounding box for location filtering
        lat_delta = radius_km / 111.0  # 1 degree lat ≈ 111 km
        lon_delta = radius_km / (111.0 * math.cos(math.radians(lat)))  # Adjust for longitude
        
        bounds = {
            "south": lat - lat_delta,
            "north": lat + lat_delta, 
            "west": lng - lon_delta,
            "east": lng + lon_delta
        }
        
        url = f"{FR24_BASE_URL}/api/live/flight-positions/full"
        headers = {
            "Authorization": f"Bearer {FR24_API_KEY}",
            "Accept": "application/json",
            "Accept-Version": "v1"
        }
        
        params = {
            "bounds": f"{bounds['north']:.3f},{bounds['south']:.3f},{bounds['west']:.3f},{bounds['east']:.3f}",
            "limit": 5,  # Get multiple aircraft to find the actual nearest
            "categories": "P"  # Filter to passenger aircraft only
        }
        
        
        async with httpx.AsyncClient() as client:
            import time
            start_time = time.time()
            response = await client.get(url, headers=headers, params=params, timeout=10.0)
            api_response_time_ms = int((time.time() - start_time) * 1000)
            
            if response.status_code == 200:
                data = response.json()
                
                flights = data.get('data', [])
                aircraft_list = []
                
                for flight in flights:
                    try:
                        # Extract position data using Flightradar24 field names
                        aircraft_lat = flight.get('lat')
                        aircraft_lon = flight.get('lon')
                        
                        
                        if aircraft_lat is None or aircraft_lon is None:
                            continue
                            
                        distance = calculate_distance(lat, lng, aircraft_lat, aircraft_lon)
                        
                        # Skip if outside radius (API bounds are approximate)
                        if distance > radius_km:
                            continue
                        
                        callsign = flight.get('callsign', '').strip() or "Unknown"
                        
                        # Get origin and destination airport information
                        origin_iata = flight.get('orig_iata')
                        dest_iata = flight.get('dest_iata')
                        
                        origin_city, origin_country = get_city_country(origin_iata) if origin_iata else (None, None)
                        dest_city, dest_country = get_city_country(dest_iata) if dest_iata else (None, None)
                        
                        # Get airline information from painted_as field (ICAO code)
                        airline_icao = flight.get('painted_as')
                        airline_name = get_airline_name(airline_icao) if airline_icao else None
                        
                        aircraft_info = {
                            "icao24": flight.get('hex'),
                            "callsign": callsign,
                            "flight_number": flight.get('flight'),
                            "airline_icao": airline_icao,
                            "airline_name": airline_name,
                            "aircraft_registration": flight.get('reg'),
                            "aircraft_icao": flight.get('type'),
                            "aircraft": get_aircraft_name(flight.get('type', '')),
                            "passenger_capacity": get_passenger_capacity(flight.get('type', '')),
                            "origin_airport": origin_iata,
                            "origin_city": origin_city,
                            "origin_country": origin_country,
                            "destination_airport": dest_iata,
                            "destination_city": dest_city,
                            "destination_country": dest_country,
                            "country": None,  # Not available in this API response
                            "latitude": aircraft_lat,
                            "longitude": aircraft_lon,
                            "altitude": flight.get('alt', 0),
                            "velocity": flight.get('gspeed', 0),
                            "heading": flight.get('track', 0),
                            "distance_km": round(distance),
                            "distance_miles": round(distance * 0.621371),
                            "status": None,  # Not available in this API response
                            "eta": flight.get('eta'),
                            "fr24_id": flight.get('fr24_id')
                        }
                        
                        aircraft_list.append(aircraft_info)
                        
                    except Exception as e:
                        logger.warning(f"Error processing flight data: {e}")
                        continue
                
                # Sort by distance first for logging comparison  
                aircraft_list.sort(key=lambda x: x["distance_km"])
                
                # Log total aircraft returned from FlightRadar24
                logger.info(f"FlightRadar24 returned {len(aircraft_list)} aircraft")
                
                # Select geographically diverse aircraft prioritizing destination diversity
                aircraft_list = select_geographically_diverse_aircraft(aircraft_list)
                
                # Log total aircraft after geographic diversity selection
                logger.info(f"Geographic diversity selected {len(aircraft_list)} aircraft")
                
                if aircraft_list:
                    # Cache the aircraft data for future requests (store all aircraft)
                    cache_data = {"aircraft": aircraft_list}
                    asyncio.create_task(s3_cache.set(api_cache_key, cache_data, content_type="json"))
                    logger.info(f"Cached {len(aircraft_list)} aircraft for location: lat={lat}, lng={lng}")
                    
                    # Track analytics for successful API response with total count if request is provided
                    if request:
                        track_scan_complete(request, lat, lng, from_cache=False, nearby_aircraft=len(aircraft_list))
                    
                    # Return up to limit aircraft
                    return aircraft_list[:limit], ""
                else:
                    # Cache empty result too to avoid repeated API calls
                    cache_data = {"aircraft": []}
                    asyncio.create_task(s3_cache.set(api_cache_key, cache_data, content_type="json"))
                    
                    # Track analytics for empty API response if request is provided
                    if request:
                        track_scan_complete(request, lat, lng, from_cache=False, nearby_aircraft=0)
                    
                    return [], "No passenger aircraft found within 100km radius"
                
            else:
                error_msg = f"Flightradar24 API returned HTTP {response.status_code}"
                logger.error(f"Flightradar24 API Error: Status={response.status_code}, Body={response.text[:500]}")
                return [], error_msg
                
    except httpx.TimeoutException:
        logger.error(f"Flightradar24 API Timeout: Request timed out after 10 seconds")
        return [], "Flightradar24 API request timed out (10 seconds)"
    except httpx.RequestError as e:
        logger.error(f"Flightradar24 API Connection Error: {str(e)}")
        return [], f"Network connection error: {str(e)}"
    except Exception as e:
        logger.error(f"Flightradar24 API Unexpected Error: {str(e)}")
        return [], f"Unexpected error: {str(e)}"
    
    return [], "Unknown error occurred"


async def handle_plane_endpoint(request: Request, plane_index: int, lat: float = None, lng: float = None, debug: int = 0):
    """Handle individual plane endpoints (/plane/1, /plane/2, /plane/3)
    
    Args:
        request: FastAPI request object
        plane_index: 1-based plane index (1, 2, 3)
        lat: Optional latitude override
        lng: Optional longitude override
        debug: Debug mode flag
    """
    logger.info(f"Request to /plane/{plane_index}")
    # Get user location using shared function
    user_lat, user_lng = await get_user_location(request, lat, lng)

    # Get TTS provider override from query parameters
    tts_override = get_tts_provider_override(request)
    effective_provider = tts_override if tts_override else TTS_PROVIDER

    # Convert to 0-based index
    zero_based_index = plane_index - 1
    
    # Debug mode: skip cache and return text only without TTS
    if debug == 1:
        # Get aircraft data for debug display
        aircraft, error_message = await get_nearby_aircraft(user_lat, user_lng, limit=max(3, plane_index), request=request)
        
        # Generate sentence for debug display
        if aircraft and len(aircraft) > zero_based_index:
            selected_aircraft = aircraft[zero_based_index]
            sentence = generate_flight_text_for_aircraft(selected_aircraft, user_lat, user_lng, plane_index)
        elif aircraft and len(aircraft) > 0:
            # Not enough planes, return an appropriate message for this plane index
            if plane_index == 2:
                sentence = "I'm sorry my old chum but scanner bot could only find one jet plane nearby. Try listening to plane 1 instead."
            elif plane_index == 3:
                plane_count = len(aircraft)
                if plane_count == 1:
                    sentence = "I'm sorry my old chum but scanner bot could only find one jet plane nearby. Try listening to plane 1 instead."
                else:
                    sentence = "I'm sorry my old chum but scanner bot could only find two jet planes nearby. Try listening to plane 1 or plane 2 instead."
        else:
            # No aircraft found at all
            sentence = generate_flight_text([], error_message, user_lat, user_lng)
            
        logger.info(f"Debug mode: returning HTML without TTS for plane {plane_index}: {sentence[:50]}...")
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Dreaming of a Jet Plane - Plane {plane_index} Debug</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; background-color: #f5f5f5; }}
                .container {{ background-color: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
                h1 {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }}
                h2 {{ color: #34495e; margin-top: 25px; }}
                table {{ border-collapse: collapse; width: 100%; margin-top: 15px; }}
                th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
                th {{ background-color: #f8f9fa; font-weight: bold; }}
                tr:nth-child(even) {{ background-color: #f8f9fa; }}
                .sentence {{ background-color: #e8f4fd; padding: 20px; border-radius: 5px; margin: 20px 0; font-size: 16px; line-height: 1.5; }}
                .message {{ background-color: #fff3cd; padding: 15px; border-radius: 5px; margin: 15px 0; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>✈️ Plane {plane_index} Debug Mode</h1>
                <div class="sentence">
                    <strong>Generated Text:</strong><br>
                    {sentence}
                </div>
                
                <h2>📍 Location Details</h2>
                <table>
                    <tr><th>Property</th><th>Value</th></tr>
                    <tr><td>User Latitude</td><td>{user_lat}</td></tr>
                    <tr><td>User Longitude</td><td>{user_lng}</td></tr>
                    <tr><td>Plane Index</td><td>{plane_index}</td></tr>
                    <tr><td>Aircraft Found</td><td>{len(aircraft) if aircraft else 0}</td></tr>
        """
        
        if error_message:
            html_content += f"""
                    <tr><td>Error Message</td><td>{error_message}</td></tr>
            """
        
        html_content += """
                </table>
        """
        
        # Add aircraft details if found
        if aircraft and len(aircraft) > zero_based_index:
            selected_aircraft = aircraft[zero_based_index]
            
            # Get aircraft coordinates for Google Maps link
            aircraft_lat = selected_aircraft.get('latitude')
            aircraft_lng = selected_aircraft.get('longitude')
            
            html_content += f"""
                <h2>🛫 Plane {plane_index} Details</h2>
                <table>
                    <tr><th>Property</th><th>Value</th></tr>
            """
            
            for key, value in selected_aircraft.items():
                if value is not None and value != "":
                    html_content += f"<tr><td>{key.replace('_', ' ').title()}</td><td>{value}</td></tr>"
            
            html_content += "</table>"
            
            # Add Google Maps directions link if we have aircraft coordinates
            if aircraft_lat and aircraft_lng:
                maps_url = f"https://www.google.com/maps/dir/?api=1&origin={user_lat},{user_lng}&destination={aircraft_lat},{aircraft_lng}&travelmode=driving"
                html_content += f"""
                <h2>🗺️ Google Maps</h2>
                <div class="message">
                    <a href="{maps_url}" target="_blank" style="color: #3498db; text-decoration: none; font-weight: bold;">
                        📍 View Directions from Your Location to Plane {plane_index} Position
                    </a>
                    <br><br>
                    <small style="color: #666;">
                        Your Location: {user_lat}, {user_lng}<br>
                        Plane {plane_index} Location: {aircraft_lat}, {aircraft_lng}
                    </small>
                </div>
                """
        
        html_content += """
            </div>
        </body>
        </html>
        """
        
        return HTMLResponse(content=html_content)

    # Get audio format for the effective provider
    file_ext, mime_type = get_audio_format_for_provider(effective_provider)

    # Check cache first for the specific plane (include TTS provider and format in cache key)
    cache_key = s3_cache.generate_cache_key(user_lat, user_lng, plane_index=plane_index, tts_provider=effective_provider, audio_format=file_ext)
    cached_audio = await s3_cache.get(cache_key)

    if cached_audio:
        logger.info(f"Serving cached audio for plane {plane_index} at location: lat={user_lat}, lng={user_lng}, format={file_ext}")

        # Track plane request analytics for cache hit
        track_plane_request(request, user_lat, user_lng, plane_index, from_cache=True)

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
    aircraft, error_message = await get_nearby_aircraft(user_lat, user_lng, limit=max(3, plane_index), request=request)
    
    
    # Check if we have the requested plane
    if aircraft and len(aircraft) > zero_based_index:
        selected_aircraft = aircraft[zero_based_index]
        sentence = generate_flight_text_for_aircraft(selected_aircraft, user_lat, user_lng, plane_index)
        
    elif aircraft and len(aircraft) > 0:
        # Not enough planes, return an appropriate message for this plane index
        if plane_index == 2:
            sentence = "I'm sorry my old chum but scanner bot could only find one jet plane nearby. Try listening to plane 1 instead."
        elif plane_index == 3:
            plane_count = len(aircraft)
            if plane_count == 1:
                sentence = "I'm sorry my old chum but scanner bot could only find one jet plane nearby. Try listening to plane 1 instead."
            else:
                sentence = "I'm sorry my old chum but scanner bot could only find two jet planes nearby. Try listening to plane 1 or plane 2 instead."
    else:
        # No aircraft found at all
        sentence = generate_flight_text([], error_message, user_lat, user_lng)
    
    # Generate TTS for the sentence
    import time
    tts_start_time = time.time()
    audio_content, tts_error, tts_provider_used, actual_file_ext, actual_mime_type = await convert_text_to_speech(sentence, tts_override=tts_override)
    tts_generation_time_ms = int((time.time() - tts_start_time) * 1000)

    if audio_content and not tts_error:
        # Cache the newly generated audio (don't await - do in background)
        asyncio.create_task(s3_cache.set(cache_key, audio_content))

        # Track audio generation analytics if we have aircraft data
        if aircraft and len(aircraft) > zero_based_index:
            selected_aircraft = aircraft[zero_based_index]
            track_audio_generation(request, user_lat, user_lng, plane_index, selected_aircraft, sentence, tts_generation_time_ms, len(audio_content), tts_provider_used, actual_file_ext)

        # Track plane request analytics for cache miss
        track_plane_request(request, user_lat, user_lng, plane_index, from_cache=False)

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
async def plane_1_endpoint(request: Request, lat: float = None, lng: float = None, debug: int = 0, tts: str = None, secret: str = None):
    """Get MP3 for the closest aircraft

    Query Parameters:
        lat: Optional latitude override
        lng: Optional longitude override
        debug: Debug mode (1 = return HTML, 0 = return audio)
        tts: TTS provider override (requires secret)
        secret: Secret key for TTS provider override
    """
    return await handle_plane_endpoint(request, 1, lat, lng, debug)

@app.get("/plane/2")
async def plane_2_endpoint(request: Request, lat: float = None, lng: float = None, debug: int = 0, tts: str = None, secret: str = None):
    """Get MP3 for the second closest aircraft

    Query Parameters:
        lat: Optional latitude override
        lng: Optional longitude override
        debug: Debug mode (1 = return HTML, 0 = return audio)
        tts: TTS provider override (requires secret)
        secret: Secret key for TTS provider override
    """
    return await handle_plane_endpoint(request, 2, lat, lng, debug)

@app.get("/plane/3")
async def plane_3_endpoint(request: Request, lat: float = None, lng: float = None, debug: int = 0, tts: str = None, secret: str = None):
    """Get MP3 for the third closest aircraft

    Query Parameters:
        lat: Optional latitude override
        lng: Optional longitude override
        debug: Debug mode (1 = return HTML, 0 = return audio)
        tts: TTS provider override (requires secret)
        secret: Secret key for TTS provider override
    """
    return await handle_plane_endpoint(request, 3, lat, lng, debug)

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)