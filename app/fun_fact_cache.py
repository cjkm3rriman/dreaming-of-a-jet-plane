"""
Cache layer for fun fact audio segments.

Fun fact audio is cached by content hash so that:
- Adding/editing a fact naturally causes a cache miss
- Removing a fact lets the old cache expire via S3 lifecycle rules
- Different TTS providers have separate cache entries

Opening phrases ("Did you know?", "Guess what?", etc.) are cached
separately since there are only 4 of them per provider.
"""

import hashlib
import logging
from typing import Optional

from .s3_cache import s3_cache

logger = logging.getLogger(__name__)


def _content_hash(text: str) -> str:
    """Generate a short content hash for cache key derivation."""
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def get_fun_fact_cache_key(fun_fact_text: str, tts_provider: str, audio_format: str) -> str:
    """Generate S3 cache key for a fun fact audio segment.

    Args:
        fun_fact_text: The fun fact text (without opening phrase)
        tts_provider: TTS provider name (e.g., "elevenlabs", "google")
        audio_format: Audio file extension (e.g., "mp3", "opus")

    Returns:
        S3 key like "cache/fun_facts/a1b2c3d4e5f67890_elevenlabs.opus"
    """
    return f"cache/fun_facts/{_content_hash(fun_fact_text)}_{tts_provider}.{audio_format}"


def get_opening_phrase_cache_key(phrase_text: str, tts_provider: str, audio_format: str) -> str:
    """Generate S3 cache key for a fun fact opening phrase audio segment.

    Args:
        phrase_text: The opening phrase (e.g., "Did you know?")
        tts_provider: TTS provider name
        audio_format: Audio file extension

    Returns:
        S3 key like "cache/fun_facts/openings/abcd1234_google.mp3"
    """
    return f"cache/fun_facts/openings/{_content_hash(phrase_text)}_{tts_provider}.{audio_format}"


async def get_cached_fun_fact_audio(fun_fact_text: str, tts_provider: str, audio_format: str) -> Optional[bytes]:
    """Retrieve cached fun fact audio from S3.

    Uses get_raw() (no TTL check) since content hashing provides natural invalidation.

    Returns:
        Audio bytes if cached, None otherwise
    """
    key = get_fun_fact_cache_key(fun_fact_text, tts_provider, audio_format)
    audio = await s3_cache.get_raw(key)
    if audio:
        logger.info(f"Fun fact cache hit: {key}")
    return audio


async def cache_fun_fact_audio(fun_fact_text: str, audio: bytes, tts_provider: str, audio_format: str) -> bool:
    """Store fun fact audio in S3 cache.

    Returns:
        True if successfully cached
    """
    key = get_fun_fact_cache_key(fun_fact_text, tts_provider, audio_format)
    success = await s3_cache.set(key, audio)
    if success:
        logger.info(f"Cached fun fact audio: {key}")
    return success


async def get_cached_opening_phrase_audio(phrase_text: str, tts_provider: str, audio_format: str) -> Optional[bytes]:
    """Retrieve cached opening phrase audio from S3.

    Returns:
        Audio bytes if cached, None otherwise
    """
    key = get_opening_phrase_cache_key(phrase_text, tts_provider, audio_format)
    audio = await s3_cache.get_raw(key)
    if audio:
        logger.info(f"Opening phrase cache hit: {key}")
    return audio


async def cache_opening_phrase_audio(phrase_text: str, audio: bytes, tts_provider: str, audio_format: str) -> bool:
    """Store opening phrase audio in S3 cache.

    Returns:
        True if successfully cached
    """
    key = get_opening_phrase_cache_key(phrase_text, tts_provider, audio_format)
    success = await s3_cache.set(key, audio)
    if success:
        logger.info(f"Cached opening phrase audio: {key}")
    return success
