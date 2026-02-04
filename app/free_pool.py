"""
Free tier pool management for serving cached flight audio to free users.

Free users "tune into" recently scanned flights from paid users, hearing
pre-generated audio without real-time API calls.
"""

import asyncio
import hashlib
import io
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydub import AudioSegment

from .s3_cache import s3_cache

logger = logging.getLogger(__name__)

# In-memory cache for free pool index (refresh every 60 seconds)
_free_pool_index_cache: Optional[Dict] = None
_free_pool_index_timestamp: float = 0
FREE_POOL_INDEX_CACHE_TTL = 60  # seconds

# Rate limiting: track requests per IP
_rate_limit_cache: Dict[str, List[float]] = {}  # {ip: [timestamp, ...]}
FREE_TIER_RATE_LIMIT = 10  # requests per minute
FREE_TIER_RATE_WINDOW = 60  # seconds

# Free pool configuration
FREE_POOL_MAX_SESSIONS = 100
FREE_POOL_INDEX_KEY = "free_pool/index.json"
FREE_POOL_STATIC_INTRO_KEY = "free_pool/static_intro.mp3"


async def get_free_pool_index() -> Optional[Dict]:
    """Fetch free pool index from S3 (cached 60 seconds in memory)

    Returns:
        Dict with structure:
        {
            "version": 1,
            "updated_at": "2025-01-15T10:30:00Z",
            "entries": [
                {
                    "id": "abc123",
                    "created_at": "2025-01-15T10:30:00Z",
                    "planes": [
                        {
                            "index": 1,
                            "flight_lat": 51.5074,
                            "flight_lng": -0.1278,
                            "origin_city": "New York",
                            "destination_city": "London",
                            "airline_name": "British Airways",
                            "body_cache_key": "free_pool/abc123_plane1_body_inworld.mp3",
                            "generic_opening_cache_key": "free_pool/abc123_plane1_opening_inworld.mp3"
                        },
                        ...
                    ],
                    "tts_provider": "inworld"
                },
                ...
            ]
        }
        Returns None if index doesn't exist or error.
    """
    global _free_pool_index_cache, _free_pool_index_timestamp

    current_time = time.time()

    # Return cached index if still fresh
    if _free_pool_index_cache is not None and (current_time - _free_pool_index_timestamp) < FREE_POOL_INDEX_CACHE_TTL:
        return _free_pool_index_cache

    # Fetch from S3
    try:
        index_bytes = await s3_cache.get_raw(FREE_POOL_INDEX_KEY)
        if index_bytes:
            index = json.loads(index_bytes.decode('utf-8'))
            _free_pool_index_cache = index
            _free_pool_index_timestamp = current_time
            logger.info(f"Loaded free pool index with {len(index.get('entries', []))} sessions")
            return index
        else:
            logger.info("Free pool index not found in S3")
            return None
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse free pool index JSON: {e}")
        return None
    except Exception as e:
        logger.error(f"Error fetching free pool index: {e}")
        return None


async def update_free_pool_index(
    session_id: str,
    planes_data: List[Dict],
    tts_provider: str
) -> bool:
    """Add new session to index, remove oldest if >100 sessions (FIFO)

    Args:
        session_id: Unique session identifier
        planes_data: List of plane data dicts with:
            - index: 1-based plane index
            - flight_lat, flight_lng: Aircraft position
            - origin_city, destination_city, airline_name: Flight info
            - body_cache_key, generic_opening_cache_key: S3 keys
        tts_provider: TTS provider used

    Returns:
        True if successful, False otherwise
    """
    global _free_pool_index_cache, _free_pool_index_timestamp

    try:
        # Get current index or create new one
        current_index = await get_free_pool_index()
        if current_index is None:
            current_index = {
                "version": 1,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "entries": []
            }

        # Create new entry
        new_entry = {
            "id": session_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "planes": planes_data,
            "tts_provider": tts_provider
        }

        # Add to entries
        entries = current_index.get("entries", [])
        entries.append(new_entry)

        # Remove oldest entries if over limit (FIFO)
        while len(entries) > FREE_POOL_MAX_SESSIONS:
            removed = entries.pop(0)
            logger.info(f"Removed oldest free pool entry: {removed.get('id')}")
            # Note: We don't delete the S3 files here - they'll naturally expire
            # or can be cleaned up by a separate process

        current_index["entries"] = entries
        current_index["updated_at"] = datetime.now(timezone.utc).isoformat()

        # Save to S3
        index_json = json.dumps(current_index, indent=2)
        success = await s3_cache.set(FREE_POOL_INDEX_KEY, index_json.encode('utf-8'))

        if success:
            # Update cache
            _free_pool_index_cache = current_index
            _free_pool_index_timestamp = time.time()
            logger.info(f"Updated free pool index with session {session_id}, total entries: {len(entries)}")
            return True
        else:
            logger.error("Failed to save free pool index to S3")
            return False

    except Exception as e:
        logger.error(f"Error updating free pool index: {e}", exc_info=True)
        return False


async def populate_free_pool(
    aircraft_list: List[Dict[str, Any]],
    location_hash: str,
    tts_provider: str,
) -> bool:
    """Copy body audio to free pool for reuse with pre-recorded intros

    Called after pre-generation completes. Only populates planes 1 & 2.
    Free tier endpoints use pre-recorded intro audio files, so we only need
    to copy the body audio to the free pool.

    Args:
        aircraft_list: List of aircraft data (all 3 planes)
        location_hash: Hash for the paid user's location (for body cache keys)
        tts_provider: TTS provider being used

    Returns:
        True if successful, False otherwise
    """
    try:
        session_id = str(uuid.uuid4())[:8]
        planes_data = []

        # Only process planes 1 and 2 for free tier
        for plane_index in [1, 2]:
            if plane_index > len(aircraft_list):
                continue

            aircraft = aircraft_list[plane_index - 1]  # 0-indexed

            # Get body audio key from paid cache
            # Format: cache/{hash}_plane{n}_body_{provider}.mp3
            body_cache_key = f"cache/{location_hash}_plane{plane_index}_body_{tts_provider}.mp3"

            # Verify body audio exists
            body_audio = await s3_cache.get_raw(body_cache_key)
            if not body_audio:
                logger.warning(f"Body audio not found for free pool: {body_cache_key}")
                continue

            # Copy body to free pool (for easier management)
            free_body_key = f"free_pool/{session_id}_plane{plane_index}_body_{tts_provider}.mp3"
            await s3_cache.set(free_body_key, body_audio)

            # Build plane data for index (no generic_opening_cache_key - free endpoints use pre-recorded intros)
            plane_data = {
                "index": plane_index,
                "flight_lat": aircraft.get("latitude"),
                "flight_lng": aircraft.get("longitude"),
                "origin_city": aircraft.get("origin_city", "Unknown"),
                "destination_city": aircraft.get("destination_city", "Unknown"),
                "airline_name": aircraft.get("airline_name", "Unknown"),
                "body_cache_key": free_body_key,
            }
            planes_data.append(plane_data)

        if not planes_data:
            logger.warning("No planes data to add to free pool")
            return False

        # Update index
        success = await update_free_pool_index(session_id, planes_data, tts_provider)

        if success:
            logger.info(f"Successfully populated free pool with session {session_id}")

        return success

    except Exception as e:
        logger.error(f"Error populating free pool: {e}", exc_info=True)
        return False


def get_session_for_free_user(client_ip: str, index: Dict) -> Optional[Dict]:
    """Select a random session from the last 5 entries for free users

    Picks randomly from the most recent sessions to ensure fresh, diverse content.

    Args:
        client_ip: Client IP address (unused, kept for API compatibility)
        index: Free pool index dict

    Returns:
        Session entry dict or None if no sessions available
    """
    import random

    entries = index.get("entries", [])
    if not entries:
        return None

    # Pick randomly from the last 5 entries (or fewer if pool is smaller)
    recent_entries = entries[-5:]
    return random.choice(recent_entries)


def check_free_tier_rate_limit(client_ip: str) -> tuple[bool, Optional[int]]:
    """Check if client IP is within rate limit

    Rate limit: 10 requests per minute per IP.

    Args:
        client_ip: Client IP address

    Returns:
        tuple: (is_allowed, retry_after_seconds)
            - is_allowed: True if request is allowed
            - retry_after_seconds: Seconds until rate limit resets (if not allowed)
    """
    global _rate_limit_cache

    current_time = time.time()
    window_start = current_time - FREE_TIER_RATE_WINDOW

    # Get or create request history for this IP
    if client_ip not in _rate_limit_cache:
        _rate_limit_cache[client_ip] = []

    # Filter to only requests within the window
    requests = [t for t in _rate_limit_cache[client_ip] if t > window_start]

    if len(requests) >= FREE_TIER_RATE_LIMIT:
        # Rate limited
        oldest_request = min(requests)
        retry_after = int(oldest_request + FREE_TIER_RATE_WINDOW - current_time) + 1
        return False, max(1, retry_after)

    # Record this request
    requests.append(current_time)
    _rate_limit_cache[client_ip] = requests

    return True, None


def _trim_silence(audio_segment: AudioSegment, silence_threshold: int = -40, min_silence_len: int = 100) -> AudioSegment:
    """Trim leading and trailing silence from an audio segment

    Args:
        audio_segment: Pydub AudioSegment to trim
        silence_threshold: dB threshold below which audio is considered silence (default -40)
        min_silence_len: Minimum length of silence to detect in ms (default 100)

    Returns:
        Trimmed AudioSegment
    """
    from pydub.silence import detect_leading_silence

    # Trim leading silence
    start_trim = detect_leading_silence(audio_segment, silence_threshold=silence_threshold, chunk_size=10)

    # Trim trailing silence (reverse, detect leading, reverse back)
    end_trim = detect_leading_silence(audio_segment.reverse(), silence_threshold=silence_threshold, chunk_size=10)

    # Ensure we don't trim everything
    duration = len(audio_segment)
    if start_trim + end_trim >= duration:
        return audio_segment  # Return original if trimming would remove everything

    return audio_segment[start_trim:duration - end_trim]


async def stitch_audio(opening: bytes, body: bytes, add_silence: bool = True) -> bytes:
    """Combine opening + body audio using pydub

    Trims trailing silence from opening and leading silence from body
    to eliminate gaps between segments.

    Args:
        opening: Opening audio bytes (MP3)
        body: Body audio bytes (MP3)
        add_silence: If True, add 1 second silence at start

    Returns:
        Combined MP3 audio bytes
    """
    try:
        opening_seg = AudioSegment.from_file(io.BytesIO(opening), format="mp3")
        body_seg = AudioSegment.from_file(io.BytesIO(body), format="mp3")

        # Trim trailing silence from opening and leading silence from body
        # to eliminate the gap between segments
        opening_trimmed = _trim_silence(opening_seg)
        body_trimmed = _trim_silence(body_seg)

        # Add half second gap between opening and body for natural pacing
        gap = AudioSegment.silent(duration=500)

        if add_silence:
            silence = AudioSegment.silent(duration=1000)  # 1 second at start
            combined = silence + opening_trimmed + gap + body_trimmed
        else:
            combined = opening_trimmed + gap + body_trimmed

        output = io.BytesIO()
        combined.export(output, format="mp3")
        return output.getvalue()

    except Exception as e:
        logger.error(f"Error stitching audio: {e}", exc_info=True)
        raise


async def stitch_audio_multi(segments: List[bytes], add_silence: bool = True) -> bytes:
    """Combine multiple audio segments using pydub

    Trims silence from each segment to eliminate gaps between them.

    Args:
        segments: List of audio bytes (MP3)
        add_silence: If True, add 1 second silence at start

    Returns:
        Combined MP3 audio bytes
    """
    try:
        if not segments:
            raise ValueError("No audio segments provided")

        combined = AudioSegment.empty()

        if add_silence:
            combined += AudioSegment.silent(duration=1000)  # 1 second

        for segment_bytes in segments:
            segment = AudioSegment.from_file(io.BytesIO(segment_bytes), format="mp3")
            # Trim silence from each segment to eliminate gaps
            trimmed = _trim_silence(segment)
            combined += trimmed

        output = io.BytesIO()
        combined.export(output, format="mp3")
        return output.getvalue()

    except Exception as e:
        logger.error(f"Error stitching multiple audio segments: {e}", exc_info=True)
        raise


async def get_static_intro_audio(convert_text_to_speech_fn) -> Optional[bytes]:
    """Get or generate static intro audio for /free/scan

    Args:
        convert_text_to_speech_fn: Function to convert text to speech

    Returns:
        MP3 audio bytes or None if error
    """
    from .flight_text import FREE_SCAN_INTRO

    # Try to get from cache first
    cached = await s3_cache.get_raw(FREE_POOL_STATIC_INTRO_KEY)
    if cached:
        return cached

    # Generate and cache
    try:
        audio, error, _, _, _ = await convert_text_to_speech_fn(FREE_SCAN_INTRO)
        if audio and not error:
            # Add 1 second silence at start
            silence = AudioSegment.silent(duration=1000)
            intro_seg = AudioSegment.from_file(io.BytesIO(audio), format="mp3")
            combined = silence + intro_seg

            output = io.BytesIO()
            combined.export(output, format="mp3")
            final_audio = output.getvalue()

            # Cache for future use
            asyncio.create_task(s3_cache.set(FREE_POOL_STATIC_INTRO_KEY, final_audio))

            return final_audio
        else:
            logger.error(f"Failed to generate static intro: {error}")
            return None
    except Exception as e:
        logger.error(f"Error generating static intro: {e}", exc_info=True)
        return None


async def get_empty_pool_audio(convert_text_to_speech_fn) -> Optional[bytes]:
    """Get audio message for when free pool is empty (cold start)

    Args:
        convert_text_to_speech_fn: Function to convert text to speech

    Returns:
        MP3 audio bytes or None if error
    """
    empty_pool_key = "free_pool/empty_pool_message.mp3"
    empty_pool_text = "I'm still warming up my scanner! Check back in a few minutes."

    # Try to get from cache first
    cached = await s3_cache.get_raw(empty_pool_key)
    if cached:
        return cached

    # Generate and cache
    try:
        audio, error, _, _, _ = await convert_text_to_speech_fn(empty_pool_text)
        if audio and not error:
            # Add 1 second silence at start
            silence = AudioSegment.silent(duration=1000)
            msg_seg = AudioSegment.from_file(io.BytesIO(audio), format="mp3")
            combined = silence + msg_seg

            output = io.BytesIO()
            combined.export(output, format="mp3")
            final_audio = output.getvalue()

            # Cache for future use
            asyncio.create_task(s3_cache.set(empty_pool_key, final_audio))

            return final_audio
        else:
            logger.error(f"Failed to generate empty pool message: {error}")
            return None
    except Exception as e:
        logger.error(f"Error generating empty pool message: {e}", exc_info=True)
        return None
