"""
Voice test endpoint for text-to-speech using ElevenLabs API
"""

from fastapi import Request
from fastapi.responses import StreamingResponse
import httpx
import os
import logging

logger = logging.getLogger(__name__)

# ElevenLabs API configuration
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_TEXT_TO_VOICE_API_KEY")
ELEVENLABS_BASE_URL = "https://api.elevenlabs.io/v1"

# Default voice ID (you can change this to any ElevenLabs voice ID)
DEFAULT_VOICE_ID = "JBFqnCBsd6RMkjVDRZzb"  # George voice


async def stream_voice_test(request: Request):
    """Convert text to speech using ElevenLabs API and stream the audio"""
    
    if not ELEVENLABS_API_KEY:
        return {"error": "ElevenLabs API key not configured"}
    
    # Text to convert to speech
    text = "i am a robot"
    
    try:
        # Prepare the request to ElevenLabs API
        url = f"{ELEVENLABS_BASE_URL}/text-to-speech/{DEFAULT_VOICE_ID}"
        
        headers = {
            "xi-api-key": ELEVENLABS_API_KEY,
            "Content-Type": "application/json"
        }
        
        payload = {
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.5
            }
        }
        
        logger.info(f"ElevenLabs API Request: URL={url}")
        logger.info(f"ElevenLabs API Text: {text}")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            
            logger.info(f"ElevenLabs API Response: Status={response.status_code}")
            
            if response.status_code == 200:
                # Get the audio content
                audio_content = response.content
                content_length = len(audio_content)
                
                # Build response headers for audio streaming
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
                
                # Return the audio content as a stream
                return StreamingResponse(
                    iter([audio_content]),
                    status_code=200,
                    media_type="audio/mpeg",
                    headers=response_headers
                )
            else:
                # Log error response for debugging
                try:
                    error_body = response.text
                    logger.error(f"ElevenLabs API Error: Status={response.status_code}, Body={error_body}")
                except:
                    logger.error(f"ElevenLabs API Error: Status={response.status_code}, Body=<unable to read>")
                
                return {"error": f"ElevenLabs API returned status {response.status_code}", "text": text}
                
    except httpx.TimeoutException:
        logger.error(f"ElevenLabs API Timeout: Request timed out after 30 seconds")
        return {"error": "ElevenLabs API timeout (30 seconds exceeded)", "text": text}
    except httpx.RequestError as e:
        logger.error(f"ElevenLabs API Connection Error: {str(e)}")
        return {"error": f"ElevenLabs API connection error: {str(e)}", "text": text}
    except Exception as e:
        logger.error(f"ElevenLabs API Unexpected Error: {str(e)}")
        return {"error": f"ElevenLabs API unexpected error: {str(e)}", "text": text}


async def voice_test_options():
    """Handle CORS preflight requests for /voice-test endpoint"""
    return StreamingResponse(
        iter([b""]),
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
            "Access-Control-Allow-Headers": "Range, Content-Range, Content-Length",
            "Access-Control-Max-Age": "3600"
        }
    )