"""Google Gemini TTS provider implementation"""

import asyncio
import logging
import os
import subprocess
import time
from typing import Optional, Tuple

DISPLAY_NAME = "Google Gemini"

logger = logging.getLogger(__name__)

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")


def is_configured() -> Tuple[bool, Optional[str]]:
    """Check whether the provider can be used"""
    if not GOOGLE_API_KEY:
        return False, "Google API key not configured"
    return True, None


async def generate_audio(text: str) -> Tuple[bytes, str]:
    """Convert text to speech using Google Gemini 2.5 Flash Preview TTS

    Returns:
        tuple: (audio_content, error_message)
        - audio_content: MP3 audio bytes if successful, empty bytes if failed
        - error_message: Empty string if successful, error description if failed
    """
    configured, reason = is_configured()
    if not configured:
        logger.warning(reason)
        return b"", reason or "Google Gemini provider unavailable"

    try:
        # Import Google GenAI SDK
        from google import genai
        from google.genai import types

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
        # Adds 1 second of silence at the start for Yoto player compatibility
        def _convert_pcm_to_mp3():
            ffmpeg_process = subprocess.Popen(
                [
                    'ffmpeg',
                    '-f', 's16le',  # 16-bit little-endian PCM
                    '-ar', '24000',  # 24kHz sample rate
                    '-ac', '1',  # mono
                    '-i', 'pipe:0',  # input from stdin
                    '-af', 'asetrate=24000*0.94,aresample=24000,atempo=1.1,adelay=1000|1000',  # Lower pitch 6% + speed up 10% + add 1s delay
                    '-c:a', 'libmp3lame',  # MP3 codec
                    '-b:a', '128k',  # bitrate (increased from 64k for better MP3 quality)
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
