"""Shared streaming for pre-recorded audio clips proxied from S3 (DOJP-46).

intro.py, overandout.py and scanning_again.py were ~140-line clones of each
other, and the same ~55-line proxy block appeared twice more in scanning.py
and once (free-tier variant) in main.py. The whole surface now lives here;
those modules are thin wrappers.
"""

import asyncio
import hashlib
import logging
from typing import Optional

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse, StreamingResponse

from .analytics import analytics
from .location_utils import (
    extract_client_ip,
    extract_user_agent,
    get_user_location,
    parse_user_agent,
)

logger = logging.getLogger(__name__)

_UNSET = object()


def _track_static_event(request: Request, event_name: str, user_lat, user_lng, user_city, location_source: str):
    """Fire the per-clip analytics event, never breaking the response"""
    try:
        client_ip = extract_client_ip(request)
        user_agent = extract_user_agent(request)
        browser_info = parse_user_agent(user_agent)

        hash_string = f"{client_ip or 'unknown'}:{user_agent or 'unknown'}:{user_lat or 0}:{user_lng or 0}"
        session_id = hashlib.md5(hash_string.encode('utf-8')).hexdigest()[:8]

        analytics.track_event(event_name, {
            "ip": client_ip,
            "$user_agent": user_agent,
            "$session_id": session_id,
            "$insert_id": f"{event_name}_{session_id}",
            "browser": browser_info["browser"],
            "browser_version": browser_info["browser_version"],
            "os": browser_info["os"],
            "os_version": browser_info["os_version"],
            "device": browser_info["device"],
            "user_lat": round(user_lat, 2),
            "user_lng": round(user_lng, 2),
            "user_city": user_city,
            "location_source": location_source,
        })
    except Exception as e:
        logger.error(f"Analytics tracking failed: {e}")
        try:
            analytics.track_event(event_name, {
                "lat": round(user_lat, 2),
                "lng": round(user_lng, 2),
                "location_source": location_source,
            })
        except Exception:
            pass  # Silently fail if analytics completely broken


async def proxy_s3_audio(request: Request, audio_url: str, mime_type: str,
                         on_success=None, error_style: str = "dict"):
    """Proxy an S3-hosted clip through to the client with range support.

    Args:
        on_success: optional zero-arg callable fired just before a successful
            response is returned (analytics hook)
        error_style: "dict" preserves the voice-clip endpoints' historical
            behavior of returning a plain dict (a 200 with a JSON body);
            "json" returns JSONResponse with real error status codes, as the
            free-tier endpoints always have
    """
    try:
        request_headers = {}
        range_header = request.headers.get("range")
        if range_header:
            request_headers["Range"] = range_header

        async with httpx.AsyncClient(timeout=30.0) as client:
            # One retry on transport errors (connection reset, read error):
            # a transient blip on the Railway<->S3 path failed a real request
            # once (Sentry DREAMING-OF-A-JETPLANE-21), where an immediate
            # reconnect would almost certainly have served the clip
            try:
                response = await client.get(audio_url, headers=request_headers)
            except httpx.TimeoutException:
                # TimeoutException subclasses TransportError - re-raise so a
                # 30s timeout keeps its historical 504 and never doubles
                raise
            except httpx.TransportError as e:
                logger.warning(
                    f"Transport error fetching {audio_url} ({type(e).__name__}: {e}), retrying once"
                )
                await asyncio.sleep(0.3)
                response = await client.get(audio_url, headers=request_headers)

            if response.status_code in [200, 206]:
                content = response.content
                response_headers = {
                    "Content-Type": mime_type,
                    "Content-Length": str(len(content)),
                    "Accept-Ranges": "bytes",
                    "Cache-Control": "public, max-age=3600",
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
                    "Access-Control-Allow-Headers": "Range, Content-Range, Content-Length",
                    "Access-Control-Expose-Headers": "Content-Length, Content-Range, Accept-Ranges"
                }

                if range_header and response.status_code == 206:
                    content_range = response.headers.get("content-range")
                    if content_range:
                        response_headers["Content-Range"] = content_range

                if response.headers.get("etag"):
                    response_headers["ETag"] = response.headers["etag"]
                if response.headers.get("last-modified"):
                    response_headers["Last-Modified"] = response.headers["last-modified"]

                if on_success:
                    on_success()

                return StreamingResponse(
                    iter([content]),
                    status_code=response.status_code,
                    media_type=mime_type,
                    headers=response_headers
                )

            if error_style == "json":
                return JSONResponse(
                    {"error": f"Audio file not accessible. Status: {response.status_code}"},
                    status_code=response.status_code
                )
            return {"error": f"Audio file not accessible. Status: {response.status_code}", "url": audio_url}

    except httpx.TimeoutException:
        if error_style == "json":
            return JSONResponse({"error": "Timeout accessing audio file"}, status_code=504)
        return {"error": "Timeout accessing audio file", "url": audio_url}
    except Exception as e:
        # Always log the exception TYPE: httpx transport errors stringify to
        # an empty message, which made the original Sentry event undiagnosable
        # from its text alone
        logger.error(f"Error streaming audio {audio_url}: {type(e).__name__}: {e}")
        if error_style == "json":
            return JSONResponse({"error": f"Failed to stream audio: {str(e)}"}, status_code=500)
        return {"error": f"Failed to stream audio: {str(e)}", "url": audio_url}


async def stream_voice_clip(request: Request, filename: str, event_name: Optional[str],
                            lat: float = None, lng: float = None, tts_override=_UNSET):
    """Stream a per-voice static clip (intro.mp3, scanning.mp3, ...).

    With an event_name, geolocates the listener and fires the clip's
    analytics event on success; with None (scanning's debounced replays),
    it is a pure proxy.
    """
    # Deferred to avoid the circular import with main (same pattern the
    # original clone modules used)
    from .main import get_static_audio_mime_type, get_tts_provider_override, get_voice_specific_s3_url

    if tts_override is _UNSET:
        tts_override = get_tts_provider_override(request)

    audio_url = get_voice_specific_s3_url(filename, tts_override)
    mime_type = get_static_audio_mime_type(tts_override)

    on_success = None
    if event_name:
        user_lat, user_lng, _, user_city, _, _, _ = await get_user_location(request, lat, lng)
        location_source = "params" if (lat is not None and lng is not None) else "ip"

        def on_success():
            _track_static_event(request, event_name, user_lat, user_lng, user_city, location_source)

    return await proxy_s3_audio(request, audio_url, mime_type, on_success=on_success)


async def static_audio_options():
    """Shared CORS preflight response for the static audio endpoints"""
    return StreamingResponse(
        iter([b""]),
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
            "Access-Control-Allow-Headers": "Range, Content-Range, Content-Length",
            "Access-Control-Max-Age": "3600"
        }
    )
