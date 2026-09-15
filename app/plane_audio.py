"""Shared plane-audio generation: split TTS, fun-fact caching, stitching.

This block existed twice - inline in main.py's handle_plane_endpoint and as
scanning.py's _generate_and_cache_plane_audio - and the copies had already
drifted (different apology text, and the fun-fact cache-key bug of DOJP-43
was pasted into both). One implementation now serves both paths (DOJP-46).
"""

import asyncio
import logging
import time
from typing import Any, Dict, Optional

from .s3_cache import s3_cache
from .background import spawn

logger = logging.getLogger(__name__)


async def generate_plane_audio(
    sentence: str,
    opening_text: Optional[str] = None,
    body_text: Optional[str] = None,
    fun_fact_opening_text: Optional[str] = None,
    fun_fact_body_text: Optional[str] = None,
    location_hash: Optional[str] = None,
    plane_index: Optional[int] = None,
    tts_override: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate one plane's narration audio.

    With opening/body text (and a location_hash for the free-pool body cache),
    runs the split-TTS pipeline: opening and body synthesized fresh, fun-fact
    opener and body served from their content-hash caches when possible, all
    segments stitched, and the body(+fact) audio written to the free-pool body
    cache key. Falls back to a single TTS call on the full sentence if the
    split fails or was not requested.

    Returns a dict:
        audio: bytes (empty on failure)
        error: str (empty on success)
        provider: TTS provider that actually produced the audio
        file_ext / mime_type: from that provider
        generation_ms: wall time for the whole generation
        fun_fact_cache_hit: True/False when a fact was processed, else None
    """
    # Deferred to avoid the circular import with main
    from .main import convert_text_to_speech
    from .free_pool import stitch_audio, stitch_audio_multi
    from .fun_fact_cache import (
        get_cached_fun_fact_audio, cache_fun_fact_audio,
        get_cached_opening_phrase_audio, cache_opening_phrase_audio,
    )

    start = time.time()
    audio_content = None
    tts_error = None
    tts_provider_used = None
    file_ext = None
    mime_type = None
    fun_fact_cache_hit = None

    if opening_text and body_text and location_hash:
        opening_audio, opening_error, _, _, _ = await convert_text_to_speech(opening_text, tts_override=tts_override)
        body_audio, body_error, tts_provider_used, file_ext, mime_type = await convert_text_to_speech(body_text, tts_override=tts_override)

        if opening_audio and body_audio and not opening_error and not body_error:
            fun_fact_opening_audio = None
            fun_fact_body_audio = None

            if fun_fact_opening_text and fun_fact_body_text:
                fun_fact_opening_audio = await get_cached_opening_phrase_audio(fun_fact_opening_text, tts_provider_used, file_ext)
                if not fun_fact_opening_audio:
                    fun_fact_opening_audio, ff_open_err, _, _, _ = await convert_text_to_speech(fun_fact_opening_text, tts_override=tts_override)
                    if fun_fact_opening_audio and not ff_open_err:
                        spawn(cache_opening_phrase_audio(fun_fact_opening_text, fun_fact_opening_audio, tts_provider_used, file_ext), "cache fun-fact opener")

                fun_fact_body_audio = await get_cached_fun_fact_audio(fun_fact_body_text, tts_provider_used, file_ext)
                if fun_fact_body_audio:
                    fun_fact_cache_hit = True
                else:
                    fun_fact_cache_hit = False
                    fun_fact_body_audio, ff_body_err, _, _, _ = await convert_text_to_speech(fun_fact_body_text, tts_override=tts_override)
                    if fun_fact_body_audio and not ff_body_err:
                        spawn(cache_fun_fact_audio(fun_fact_body_text, fun_fact_body_audio, tts_provider_used, file_ext), "cache fun-fact body")

            body_cache_key = f"cache/{location_hash}_plane{plane_index}_body_{tts_provider_used}.{file_ext}"
            if fun_fact_opening_audio and fun_fact_body_audio:
                audio_content = await stitch_audio_multi(
                    [opening_audio, body_audio, fun_fact_opening_audio, fun_fact_body_audio],
                    add_silence=True, audio_format=file_ext,
                    gap_durations=[1000, 1000, 500]
                )
                # Cache body+fact stitched together for free pool reuse
                body_with_fact = await stitch_audio_multi(
                    [body_audio, fun_fact_opening_audio, fun_fact_body_audio],
                    add_silence=False, audio_format=file_ext,
                    gap_durations=[1000, 500]
                )
                await s3_cache.set(body_cache_key, body_with_fact)
                logger.info(f"Cached body+fact audio at {body_cache_key}")
            else:
                audio_content = await stitch_audio(opening_audio, body_audio, add_silence=True, audio_format=file_ext)
                await s3_cache.set(body_cache_key, body_audio)
                logger.info(f"Cached body audio at {body_cache_key}")

            tts_error = ""
        else:
            logger.warning(f"Split TTS failed for plane {plane_index}, falling back to single TTS. Opening error: {opening_error}, Body error: {body_error}")

    if not audio_content:
        audio_content, tts_error, tts_provider_used, file_ext, mime_type = await convert_text_to_speech(sentence, tts_override=tts_override)

    return {
        "audio": audio_content,
        "error": tts_error,
        "provider": tts_provider_used,
        "file_ext": file_ext,
        "mime_type": mime_type,
        "generation_ms": int((time.time() - start) * 1000),
        "fun_fact_cache_hit": fun_fact_cache_hit,
    }
