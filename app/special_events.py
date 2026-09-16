"""Special Signal Events calendar (DOJP-33).

Generalises the old hardcoded Santa module (`flight_text_seasonal.py`) into a
data-driven event table. During an event window the event takes over track 1
and the real planes shift down one slot - the child hears the special signal
first, then the sky as normal, with the fifth aircraft dropping off the end:

    /plane/1 -> the event        /plane/2 -> closest aircraft
    /plane/3 -> 2nd aircraft ... /plane/5 -> 4th aircraft

Event audio is location-independent, so it is cached once per event per TTS
provider under the durable `special-events/` prefix (content-hashed, so a
script edit invalidates cleanly) - not regenerated per location hash the way
the old override was, and not under `cache/`, which an S3 lifecycle rule
wipes daily (DOJP-50).

Events are Club-only: track 1 writes no free-pool body cache, and
`populate_free_pool`'s slot_offset keeps the shifted planes' metadata aligned,
so event audio can never leak into the free tier.
"""

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .s3_cache import s3_cache

logger = logging.getLogger(__name__)


CHRISTMAS_SANTA_TEXT = (
    "Incredible! My radar just picked up something truly extraordinary, gliding silently through the clouds! "
    "It's not a jet, and it's not a bird - it's a wooden sleigh being pulled by a team of eight... no, wait... "
    "nine flying reindeer!\n\n"
    "My scanner is showing a very mysterious figure at the reigns, wearing a bright red suit and navigating with a "
    "glowing red light right at the front of the pack. This unusual craft doesn't have a flight number, but it's moving "
    "at incredible speeds, zig-zagging across the globe and carrying a massive sack overflowing with colorful packages.\n\n"
    "Fun fact: Reindeer are the only deer species where both the males and females grow antlers, and they are excellent "
    "swimmers, able to cross wide rivers and even parts of the ocean!\n\n"
    "This magical team seems to be on a very tight schedule tonight, stopping at every rooftop before whisking away into "
    "the starry night."
)


# Annual recurring windows in UTC, as (month, day, hour) start/end tuples.
# A window may wrap the year boundary (start > end, e.g. New Year's Eve).
# Adding an event is adding a row; no code changes needed.
EVENTS = [
    {
        "name": "santa",
        "start": (12, 24, 7),  # 7am GMT Dec 24
        "end": (12, 25, 7),    # 7am GMT Dec 25
        "text": CHRISTMAS_SANTA_TEXT,
    },
]


def get_active_event(now: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
    """Return the active event for `now` (UTC), or None outside any window.

    Windows compare as (month, day, hour) tuples; a start greater than its
    end means the window wraps the year boundary. Earlier table rows win if
    windows ever overlap.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    now_key = (now.month, now.day, now.hour)

    for event in EVENTS:
        start, end = event["start"], event["end"]
        if start <= end:
            active = start <= now_key < end
        else:  # wraps the year boundary
            active = now_key >= start or now_key < end
        if active:
            return event
    return None


def aircraft_slot_for_plane(plane_index: int, event_active: bool) -> Optional[int]:
    """Map a plane track (1-based) to its zero-based aircraft index.

    Without an event, track N serves aircraft N-1. During an event the event
    owns track 1, so track N serves aircraft N-2 and the fifth aircraft
    drops. Returns None for the event track itself.
    """
    if not event_active:
        return plane_index - 1
    if plane_index == 1:
        return None
    return plane_index - 2


def event_cache_key(event: Dict[str, Any], provider: str, file_ext: str) -> str:
    """Durable S3 key for one event's audio under one provider.

    Content-hashed on the script text: editing an event's copy produces a new
    key, so stale audio can never play after a script change. The old key's
    single small file is left behind, which is fine.
    """
    text_hash = hashlib.md5(event["text"].encode("utf-8")).hexdigest()[:8]
    return f"special-events/{event['name']}_{text_hash}_{provider}.{file_ext}"


async def ensure_event_audio(event: Dict[str, Any], tts_override: Optional[str] = None) -> Dict[str, Any]:
    """Fetch the event's audio from its shared cache, generating it once if absent.

    Unlike plane audio this is keyed per event+provider, not per location -
    the first scan of the window pays one TTS call and every listener
    worldwide reuses it. The cache write is awaited (not fire-and-forget):
    one write serves the entire window, so losing it to a crashed task would
    cost a regeneration per replica.
    """
    # Deferred to avoid the circular import with main (same pattern as plane_audio)
    from .main import convert_text_to_speech, TTS_PROVIDER, get_audio_format_for_provider

    provider = (tts_override or TTS_PROVIDER).lower()
    file_ext, mime_type = get_audio_format_for_provider(provider)
    key = event_cache_key(event, provider, file_ext)

    cached = await s3_cache.get_raw(key)
    if cached:
        return {"audio": cached, "error": "", "provider": provider,
                "file_ext": file_ext, "mime_type": mime_type, "from_cache": True}

    audio, error, provider_used, actual_ext, actual_mime = await convert_text_to_speech(event["text"], tts_override)
    if audio and not error:
        await s3_cache.set(key, audio)
        logger.info(f"Generated and cached event audio: {key} ({len(audio)} bytes)")
    else:
        logger.error(f"Event audio generation failed for '{event['name']}': {error}")
    return {"audio": audio, "error": error, "provider": provider_used,
            "file_ext": actual_ext, "mime_type": actual_mime, "from_cache": False}
