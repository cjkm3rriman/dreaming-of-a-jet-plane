"""Club intro picker (DOJP-61): which pre-rendered /scanning clip to stream.

The warm-up intro is static audio, but *which* static clip plays is chosen
per request from the listener's local day and hour. Nothing is synthesized
at request time: every variant is a manifest entry rendered through the
DOJP-35 pipeline and uploaded per voice folder alongside the plain
`scanning` clip, which stays the default.

    Friday (any hour)            -> scanning-friday   (Animal Friday, DOJP-52;
                                                      gated by ANIMAL_FRIDAY_ENABLED
                                                      until the birds data lands)
    Saturday / Sunday (any hour) -> scanning-weekend
    05:00-11:00 local            -> scanning-morning
    17:00-23:00 local            -> scanning-evening
    otherwise                    -> scanning

Local time comes from the IANA timezone ipapi.co reports for the listener's
IP (threaded through the location cache), never from a longitude guess:
daylight saving moves the 11:00 and 17:00 edges by an hour for half the
year. No timezone, an unparseable one, or a geolocation fallback (we know
nothing about the listener) all mean the plain intro. Free tier never calls
this - its intros come from a separate static path.

The function is pure and deterministic from its inputs, so the debounced
replay path picks the same clip and siblings scanning together hear the
same intro.
"""

import os
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

SCANNING_DEFAULT = "scanning"
SCANNING_MORNING = "scanning-morning"
SCANNING_EVENING = "scanning-evening"
SCANNING_WEEKEND = "scanning-weekend"
SCANNING_FRIDAY = "scanning-friday"

# Every value the picker can return. A test pins each one to a manifest
# entry so a variant can never be picked without a clip behind it.
SCANNING_VARIANTS = (
    SCANNING_DEFAULT, SCANNING_MORNING, SCANNING_EVENING, SCANNING_WEEKEND, SCANNING_FRIDAY,
)

MORNING_HOURS = range(5, 11)    # 05:00 <= local < 11:00
EVENING_HOURS = range(17, 23)   # 17:00 <= local < 23:00

_FRIDAY, _SATURDAY, _SUNDAY = 4, 5, 6


def animal_friday_enabled() -> bool:
    """Feature flag: the Friday intro promises a bird on plane 3, so it stays
    off until the local-birds data (DOJP-52) can keep that promise."""
    return os.getenv("ANIMAL_FRIDAY_ENABLED", "").strip().lower() in ("1", "true", "yes", "on")


def pick_scanning_variant(now_utc: datetime, tz_name: Optional[str], is_fallback: bool,
                          friday_enabled: Optional[bool] = None) -> str:
    """Return the manifest entry name of the intro to stream.

    Args:
        now_utc: the current time; naive values are treated as UTC
        tz_name: the listener's IANA timezone, or None when unknown
        is_fallback: True when geolocation fell back to the NYC default
        friday_enabled: override for the ANIMAL_FRIDAY_ENABLED flag (tests)
    """
    if is_fallback or not tz_name:
        return SCANNING_DEFAULT
    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        return SCANNING_DEFAULT

    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    local = now_utc.astimezone(tz)

    if friday_enabled is None:
        friday_enabled = animal_friday_enabled()
    if local.weekday() == _FRIDAY and friday_enabled:
        return SCANNING_FRIDAY
    if local.weekday() in (_SATURDAY, _SUNDAY):
        return SCANNING_WEEKEND
    if local.hour in MORNING_HOURS:
        return SCANNING_MORNING
    if local.hour in EVENING_HOURS:
        return SCANNING_EVENING
    return SCANNING_DEFAULT


def variant_filename(variant: str) -> str:
    """The static-clip filename the voice-folder streamer expects; it swaps
    the extension for the provider's real format."""
    return f"{variant}.mp3"
