"""Inworld TTS provider implementation"""

import base64
import binascii
import io
import logging
import os
from typing import Optional, Tuple

import httpx
from pydub import AudioSegment

DISPLAY_NAME = "Inworld TTS"

logger = logging.getLogger(__name__)

INWORLD_API_KEY = os.getenv("INWORLD_API_KEY")
INWORLD_MODEL_ID = os.getenv("INWORLD_MODEL_ID", "inworld-tts-1.5-max")
INWORLD_VOICE_ID = os.getenv("INWORLD_VOICE_ID", "Ronald")
INWORLD_AUDIO_ENCODING = os.getenv("INWORLD_AUDIO_ENCODING", "MP3")
INWORLD_SPEAKING_RATE = float(os.getenv("INWORLD_SPEAKING_RATE", "0.92"))
INWORLD_TEMPERATURE = float(os.getenv("INWORLD_TEMPERATURE", "1.2"))
INWORLD_BASE_URL = os.getenv("INWORLD_TTS_BASE_URL", "https://api.inworld.ai/tts/v1/voice")


def is_configured() -> Tuple[bool, Optional[str]]:
    """Check whether the provider can be used"""
    if not INWORLD_API_KEY:
        return False, "Inworld API key not configured"
    return True, None


def _build_authorization_header() -> str:
    key = (INWORLD_API_KEY or "").strip()
    if not key:
        return ""

    try:
        base64.b64decode(key, validate=True)
        is_base64 = True
    except binascii.Error:
        is_base64 = False

    if not is_base64 or ":" in key:
        key_bytes = key.encode("utf-8")
        key = base64.b64encode(key_bytes).decode("ascii")

    return f"Basic {key}"


def _build_payload(text: str) -> dict:
    return {
        "text": text,
        "voice_id": INWORLD_VOICE_ID,
        "audio_config": {
            "audio_encoding": INWORLD_AUDIO_ENCODING,
            "speaking_rate": INWORLD_SPEAKING_RATE,
        },
        "temperature": INWORLD_TEMPERATURE,
        "model_id": INWORLD_MODEL_ID,
    }


async def generate_audio(text: str) -> Tuple[bytes, str]:
    """Convert text to speech using Inworld's TTS API"""
    configured, reason = is_configured()
    if not configured:
        logger.warning(reason)
        return b"", reason or "Inworld provider unavailable"

    headers = {
        "Authorization": _build_authorization_header(),
        "Content-Type": "application/json",
    }

    payload = _build_payload(text)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(INWORLD_BASE_URL, headers=headers, json=payload)
            if response.status_code != 200:
                logger.error("Inworld API error: %s - %s", response.status_code, response.text)
                return b"", f"Inworld API returned status {response.status_code}"

            data = response.json()
            audio_content = data.get("audioContent")
            if not audio_content:
                logger.error("Inworld API response missing audioContent")
                return b"", "Inworld API response missing audioContent"

            try:
                audio_bytes = base64.b64decode(audio_content)

                # Prepend 1 second of silence to the audio
                audio = AudioSegment.from_file(io.BytesIO(audio_bytes), format="mp3")
                silence = AudioSegment.silent(duration=1000)  # 1000ms = 1 second
                audio_with_pause = silence + audio

                # Export back to bytes
                output_buffer = io.BytesIO()
                audio_with_pause.export(output_buffer, format="mp3")
                return output_buffer.getvalue(), ""

            except binascii.Error as exc:
                logger.error("Failed to decode Inworld audio: %s", exc)
                return b"", "Failed to decode Inworld audio"
            except Exception as exc:
                logger.error("Failed to process Inworld audio with silence: %s", exc)
                return b"", f"Failed to process Inworld audio: {exc}"

    except httpx.TimeoutException:
        logger.error("Inworld API timeout")
        return b"", "Inworld API timeout (30 seconds exceeded)"
    except httpx.RequestError as exc:
        logger.error("Inworld API connection error: %s", exc)
        return b"", f"Inworld API connection error: {exc}"
    except Exception as exc:
        logger.error("Inworld API error: %s", exc)
        return b"", f"Inworld API unexpected error: {exc}"
