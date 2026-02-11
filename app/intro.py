"""
Intro endpoint for streaming MP3 file from S3
"""

from fastapi import Request
from fastapi.responses import StreamingResponse
import httpx
import hashlib
import uuid
from .location_utils import get_user_location, extract_client_ip, extract_user_agent, parse_user_agent
from .analytics import analytics


async def stream_intro(request: Request, lat: float = None, lng: float = None):
    """Stream MP3 file from S3 with proper headers for browser playback"""
    # Get user location using shared function
    user_lat, user_lng, user_country_code, user_city, _, _ = await get_user_location(request, lat, lng)

    # Import here to avoid circular imports
    from .main import get_voice_specific_s3_url, get_tts_provider_override, get_static_audio_mime_type

    # Get TTS provider override from query parameters
    tts_override = get_tts_provider_override(request)

    # Audio file hosted on S3 with voice-specific folder
    audio_url = get_voice_specific_s3_url("intro.mp3", tts_override)
    mime_type = get_static_audio_mime_type(tts_override)

    try:
        # Prepare headers for the S3 request
        request_headers = {}

        # Handle Range requests for seeking/partial content
        range_header = request.headers.get("range")
        if range_header:
            request_headers["Range"] = range_header

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(audio_url, headers=request_headers)

            if response.status_code in [200, 206]:
                # Get content details
                content = response.content
                content_length = len(content)

                # Build response headers
                response_headers = {
                    "Content-Type": mime_type,
                    "Content-Length": str(content_length),
                    "Accept-Ranges": "bytes",
                    "Cache-Control": "public, max-age=3600",
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
                    "Access-Control-Allow-Headers": "Range, Content-Range, Content-Length",
                    "Access-Control-Expose-Headers": "Content-Length, Content-Range, Accept-Ranges"
                }
                
                # Handle range requests
                if range_header and response.status_code == 206:
                    content_range = response.headers.get("content-range")
                    if content_range:
                        response_headers["Content-Range"] = content_range
                
                # Copy important S3 headers if present
                if response.headers.get("etag"):
                    response_headers["ETag"] = response.headers["etag"]
                if response.headers.get("last-modified"):
                    response_headers["Last-Modified"] = response.headers["last-modified"]
                
                # Track successful intro event (only once per user session)
                try:
                    client_ip = extract_client_ip(request)
                    user_agent = extract_user_agent(request)
                    browser_info = parse_user_agent(user_agent)
                    
                    # Create unique session identifier for session tracking
                    # Use simpler approach with UUID based on user data
                    hash_string = f"{client_ip or 'unknown'}:{user_agent or 'unknown'}:{user_lat or 0}:{user_lng or 0}"
                    # Generate a consistent but shorter session ID using first 8 chars of hash
                    session_id = hashlib.md5(hash_string.encode('utf-8')).hexdigest()[:8]
                    
                    analytics.track_event("intro", {
                        "ip": client_ip,
                        "$user_agent": user_agent,
                        "$session_id": session_id,  # Use $session_id label
                        "$insert_id": f"intro_{session_id}",  # Prevents duplicates
                        "browser": browser_info["browser"],
                        "browser_version": browser_info["browser_version"],
                        "os": browser_info["os"],
                        "os_version": browser_info["os_version"],
                        "device": browser_info["device"],
                        "user_lat": round(user_lat, 2),
                        "user_lng": round(user_lng, 2),
                        "user_city": user_city,
                        "location_source": "params" if (lat is not None and lng is not None) else "ip"
                    })
                except Exception as e:
                    # Log error but don't break the response
                    import logging
                    logging.getLogger(__name__).error(f"Analytics tracking failed: {e}")
                    # Still try to track without session data
                    try:
                        analytics.track_event("intro", {
                            "lat": round(user_lat, 2),
                            "lng": round(user_lng, 2),
                            "location_source": "params" if (lat is not None and lng is not None) else "ip"
                        })
                    except:
                        pass  # Silently fail if analytics completely broken
                
                # Return the content directly
                return StreamingResponse(
                    iter([content]),
                    status_code=response.status_code,
                    media_type=mime_type,
                    headers=response_headers
                )
            else:
                return {"error": f"Audio file not accessible. Status: {response.status_code}", "url": audio_url}

    except httpx.TimeoutException:
        return {"error": "Timeout accessing audio file", "url": audio_url}
    except Exception as e:
        return {"error": f"Failed to stream audio: {str(e)}", "url": audio_url}


async def intro_options():
    """Handle CORS preflight requests for /intro endpoint"""
    return StreamingResponse(
        iter([b""]),
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
            "Access-Control-Allow-Headers": "Range, Content-Range, Content-Length",
            "Access-Control-Max-Age": "3600"
        }
    )