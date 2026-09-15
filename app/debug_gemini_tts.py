from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
import os
import logging

logger = logging.getLogger(__name__)


def register_test_gemini_tts_routes(app: FastAPI):
    """Register test Gemini TTS routes to the FastAPI app"""

    @app.get("/test-gemini-tts")
    async def test_gemini_tts_endpoint(secret: str = None):
        """
        Test endpoint for Gemini 2.5 Pro Preview TTS using google-genai SDK

        Query Parameters:
        - secret: Required authentication secret for accessing this test endpoint

        Returns:
        - MP3 audio file on success (converted from PCM)
        - JSON error message on failure
        """
        # Check secret requirement
        PROVIDER_OVERRIDE_SECRET = os.getenv("PROVIDER_OVERRIDE_SECRET")
        if not PROVIDER_OVERRIDE_SECRET:
            raise HTTPException(status_code=403, detail="Provider override secret is not configured")

        if secret != PROVIDER_OVERRIDE_SECRET:
            raise HTTPException(status_code=403, detail="Invalid or missing secret")

        GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

        if not GOOGLE_API_KEY:
            logger.warning("Google API key not configured")
            return {"error": "GOOGLE_API_KEY environment variable not set"}

        # text = "Great job my old chum! We spotted some absolutely delightful jet planes. Start up your Yoto jet plane scanner again soon, becuase you never know what celestial surprises we might find up there. Hugo out for now..."
        text = "Greetings! It is I, Air Traffic Controller Hugo, who shall be manning the jet plane scanner today. I am standing in for Hamish, who has, rather wisely, taken himself off to the Maldivian archipelago for a brief respite. Lets spot some jet planes shall we?"
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
            VOICE_PROMPT = "Read the text in a posh British male voice, rich baritone with a low pitch. Use precise articulation and a refined, formal delivery with minimal inflection."

            logger.info(f"Gemini TTS Test Request: Model={MODEL_ID}, Voice={VOICE_NAME}, Text='{text[:50]}...'")

            # Start timing
            start_time = time.time()

            # Prepend voice prompt to the text content with colon separator
            prompt_with_text = f"{VOICE_PROMPT}: {text}"

            # Generate audio using Gemini (not truly streaming, sends all at once)
            response = client.models.generate_content(
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

            # Extract PCM data from response
            pcm_data = response.candidates[0].content.parts[0].inline_data.data
            api_time = time.time() - start_time
            logger.info(f"Gemini API complete: {len(pcm_data)} bytes PCM in {api_time:.2f}s")

            # Convert PCM to MP3 using ffmpeg
            ffmpeg_process = subprocess.Popen(
                [
                    'ffmpeg',
                    '-f', 's16le',  # 16-bit little-endian PCM
                    '-ar', '24000',  # 24kHz sample rate
                    '-ac', '1',  # mono
                    '-i', 'pipe:0',  # input from stdin
                    '-af', 'asetrate=24000*0.94,aresample=24000,atempo=1.1',  # Lower pitch 6% + speed up 10%
                    '-c:a', 'libmp3lame',  # MP3 codec
                    '-b:a', '128k',  # bitrate
                    '-f', 'mp3',  # MP3 format
                    'pipe:1'  # output to stdout
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

            mp3_data, ffmpeg_error = ffmpeg_process.communicate(input=pcm_data)

            total_time = time.time() - start_time
            logger.info(f"Conversion complete: {len(mp3_data)} bytes MP3 in {total_time:.2f}s total")

            # Return MP3 audio
            return Response(
                content=mp3_data,
                media_type="audio/mpeg",
                headers={
                    "Content-Disposition": "inline; filename=test-gemini-tts.mp3",
                    "Access-Control-Allow-Origin": "*"
                }
            )

        except ImportError as e:
            logger.error(f"Gemini TTS Test ImportError: {str(e)}")
            return {"error": f"Import error: {str(e)}", "hint": "Install google-genai"}

        except Exception as e:
            logger.error(f"Gemini TTS Test Error: {str(e)}")
            return {"error": str(e), "model": "gemini-2.5-pro-preview-tts"}
