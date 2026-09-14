"""scanning-again endpoint - thin wrapper over the shared static-audio streamer.

This module was a ~140-line clone of its two siblings; the implementation
now lives in static_audio.py (DOJP-46).
"""

from fastapi import Request

from .static_audio import static_audio_options, stream_voice_clip


async def stream_scanning_again(request: Request, lat: float = None, lng: float = None):
    """Stream the scanning-again.mp3 clip and fire the 'scanning-again' analytics event"""
    return await stream_voice_clip(request, "scanning-again.mp3", "scanning-again", lat, lng)


async def scanning_again_options():
    """Handle CORS preflight requests"""
    return await static_audio_options()
