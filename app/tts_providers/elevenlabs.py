"""ElevenLabs TTS provider implementation"""

import logging
import os
from typing import Optional, Tuple

import httpx

DISPLAY_NAME = "ElevenLabs"

logger = logging.getLogger(__name__)

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_TEXT_TO_VOICE_API_KEY")
ELEVENLABS_BASE_URL = "https://api.elevenlabs.io/v1"
DEFAULT_VOICE_ID = "goT3UYdM9bhm0n2lmKQx"  # Edward voice - British, Dark, Seductive, Low


def is_configured() -> Tuple[bool, Optional[str]]:
    """Check whether the provider can be used"""
    if not ELEVENLABS_API_KEY:
        return False, "ElevenLabs API key not configured"
    return True, None


async def generate_audio(text: str) -> Tuple[bytes, str]:
    """Convert text to speech using ElevenLabs API

    Returns:
        tuple: (audio_content, error_message)
        - audio_content: MP3 audio bytes if successful, empty bytes if failed
        - error_message: Empty string if successful, error description if failed
    """
    configured, reason = is_configured()
    if not configured:
        logger.warning(reason)
        return b"", reason or "ElevenLabs provider unavailable"

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
