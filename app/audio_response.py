"""Responses for dynamically generated plane audio: Range support, a
short-lived in-process cache, and single-flight generation.

Why this exists (DOJP-22, revisited for the new Yoto players): the dynamic
tracks used to answer every request with a 200 and the whole file, and the
July 2026 outage was newer firmware issuing several range requests per play
against handlers that re-fetched S3 (or re-ran TTS) for each one. The fix
then was to stop advertising Accept-Ranges. The new players need real range
support - Ogg Opus carries no duration in its header, so a player that wants
the track length seeks to the last Ogg page - so the dynamic endpoints now
serve genuine 206 slices, and the amplification is prevented at the source:

- RecentAudioCache keeps the bytes of recently served tracks in memory for
  the same TTL the S3 cache uses, so a burst of range requests for one play
  costs one S3 fetch at most.
- SingleFlight collapses concurrent generations of the same cache key into
  one TTS run; the requests that arrived while it was running are answered
  from its result.
"""

import asyncio
import re
import time
from collections import OrderedDict
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple, TypeVar

from fastapi import Request
from fastapi.responses import Response

from .s3_cache import s3_cache

# Client-side caching of dynamic plane audio must not outlive the server's own
# S3 TTL, or any intermediary that honors the header re-creates the rescan
# staleness DOJP-27 fixed. Derived, so the two can never drift apart (DOJP-39).
PLANE_AUDIO_CACHE_MAX_AGE_S = s3_cache.ttl_minutes * 60

_RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")


def parse_range(header: Optional[str], size: int) -> Tuple[str, Optional[Tuple[int, int]]]:
    """Interpret a Range header against a body of `size` bytes.

    Returns one of:
        ("full", None)                 - no header, or one we may ignore
                                         (malformed, multi-range): serve 200
        ("partial", (start, end))      - inclusive byte offsets: serve 206
        ("unsatisfiable", None)        - serve 416

    Only single byte ranges are honoured. RFC 9110 lets a server ignore a
    Range it does not support, and no Yoto client sends multi-range requests.
    """
    if not header or size <= 0:
        return "full", None
    match = _RANGE_RE.match(header.strip())
    if not match:
        return "full", None
    first, last = match.groups()

    if first == "" and last == "":
        return "full", None
    if first == "":
        # Suffix range: the last N bytes
        suffix = int(last)
        if suffix == 0:
            return "unsatisfiable", None
        return "partial", (max(0, size - suffix), size - 1)

    start = int(first)
    if start >= size:
        return "unsatisfiable", None
    if last == "":
        return "partial", (start, size - 1)
    end = int(last)
    if end < start:
        return "full", None
    return "partial", (start, min(end, size - 1))


def plane_audio_response_headers(mime_type: str, content_length: int) -> Dict[str, str]:
    """Headers shared by every dynamic plane-audio response.

    Accept-Ranges is advertised again because the handlers now honour Range
    (plane_audio_response); it must never be advertised on a handler that
    does not, which is what caused DOJP-22.
    """
    return {
        "Content-Type": mime_type,
        "Content-Length": str(content_length),
        "Accept-Ranges": "bytes",
        "Cache-Control": f"public, max-age={PLANE_AUDIO_CACHE_MAX_AGE_S}",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
        "Access-Control-Allow-Headers": "Range, Content-Range, Content-Length",
        "Access-Control-Expose-Headers": "Content-Length, Content-Range, Accept-Ranges",
    }


def plane_audio_response(request: Request, audio: bytes, mime_type: str) -> Response:
    """Serve `audio` honouring the request's Range header: 200, 206, or 416."""
    size = len(audio)
    kind, byte_range = parse_range(request.headers.get("range"), size)

    if kind == "unsatisfiable":
        headers = plane_audio_response_headers(mime_type, 0)
        headers["Content-Range"] = f"bytes */{size}"
        return Response(b"", status_code=416, headers=headers, media_type=mime_type)

    if kind == "partial":
        start, end = byte_range
        body = audio[start:end + 1]
        headers = plane_audio_response_headers(mime_type, len(body))
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
        return Response(body, status_code=206, headers=headers, media_type=mime_type)

    headers = plane_audio_response_headers(mime_type, size)
    return Response(audio, status_code=200, headers=headers, media_type=mime_type)


class RecentAudioCache:
    """Bounded, TTL'd in-memory cache of recently served audio.

    Values are opaque (bytes, or a dict carrying bytes plus their MIME type).

    Per container, not shared across replicas - that is fine, its job is to
    make the several requests one player issues for one play hit memory
    instead of S3 or TTS. Bounded so it can never grow without limit (DOJP-42).
    """

    def __init__(self, ttl_seconds: float, max_entries: int):
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._entries: "OrderedDict[str, Tuple[float, Any]]" = OrderedDict()

    def get(self, key: str) -> Optional[Any]:
        entry = self._entries.get(key)
        if entry is None:
            return None
        stored_at, data = entry
        if time.monotonic() - stored_at > self.ttl_seconds:
            del self._entries[key]
            return None
        self._entries.move_to_end(key)
        return data

    def put(self, key: str, data: Any) -> None:
        if not data:
            return
        self._entries[key] = (time.monotonic(), data)
        self._entries.move_to_end(key)
        while len(self._entries) > self.max_entries:
            self._entries.popitem(last=False)

    def clear(self) -> None:
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)


T = TypeVar("T")


class SingleFlight:
    """Run one producer per key at a time; concurrent callers share its result."""

    def __init__(self):
        self._inflight: Dict[str, "asyncio.Future"] = {}

    def is_inflight(self, key: str) -> bool:
        return key in self._inflight

    async def run(self, key: str, producer: Callable[[], Awaitable[T]]) -> T:
        existing = self._inflight.get(key)
        if existing is not None:
            return await existing

        future = asyncio.get_running_loop().create_future()
        # A waiter always retrieves the exception; when there is none, mark it
        # retrieved so asyncio does not log "exception was never retrieved"
        future.add_done_callback(lambda f: None if f.cancelled() else f.exception())
        self._inflight[key] = future
        try:
            result = await producer()
        except asyncio.CancelledError:
            future.cancel()
            raise
        except BaseException as exc:
            future.set_exception(exc)
            raise
        else:
            future.set_result(result)
            return result
        finally:
            self._inflight.pop(key, None)


# Paid tracks, keyed by the S3 cache key (location + plane + provider + format)
recent_plane_audio = RecentAudioCache(ttl_seconds=PLANE_AUDIO_CACHE_MAX_AGE_S, max_entries=64)
# Free tracks are stitched per request from a random intro, so range slices of
# one play must all come from the same bytes: memoised per client + plane
recent_free_audio = RecentAudioCache(ttl_seconds=120, max_entries=128)
plane_generation = SingleFlight()
