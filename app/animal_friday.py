"""Animal Friday (DOJP-52): on Fridays the second track is a local bird, not a plane.

The scanner "picks up a bonus flyer" - a species the listener is genuinely
likely to see in their region this month - as track 2, right after the
first plane, with the remaining planes shifting down so the fifth aircraft
is the one that drops. It mirrors the Special Signal Events mechanism
(which takes track 1 and shifts planes down), so the two compose: on a
Friday inside an event window the child hears the event, the bird, and
three planes.

Data:
  app/birds.json       - built by scripts/build_birds.py from GBIF (the eBird
                         Observation Dataset, CC BY 4.0): per region and
                         calendar month, the most-recorded species.
  app/bird_lines.json  - hand-written kid lines keyed by the species' English
                         name (plus "_aliases" from GBIF's spelling to ours).
                         A species with no lines is never narrated.

Region keys follow what ipapi.co reports for the listener: `{ISO2}` for most
countries, `{ISO2}-{subdivision}` for the US, Canada, the UK and Australia,
matched on the subdivision name or its short code ("VA").

Everything is deterministic from (region, local date): siblings scanning on
the same Friday hear the same bird, and the species and line rotate by ISO
week so the egg does not repeat verbatim week over week. Audio is generated
once per bird text + provider into the durable `animal-friday/` prefix, like
event audio - a region's Friday bird costs one TTS call for everyone there.

Gated by ANIMAL_FRIDAY_ENABLED (see intro_picker) and by coverage: no
region, no narratable species this month, or a geolocation fallback all mean
an ordinary five-plane Friday, and the intro picker makes the same call so
the Friday intro's promise is never broken.
"""

import hashlib
import json
import logging
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .intro_picker import animal_friday_enabled
from .s3_cache import s3_cache

logger = logging.getLogger(__name__)

BIRDS_PATH = Path(__file__).parent / "birds.json"
LINES_PATH = Path(__file__).parent / "bird_lines.json"
EVENT_NAME = "animal-friday"
BIRD_TRACK = 2  # the track the bird owns; the planes after it shift down one
_FRIDAY = 4

_birds: Optional[Dict[str, Any]] = None
_lines: Optional[Dict[str, List[str]]] = None


def _load() -> None:
    global _birds, _lines
    if _birds is None:
        _birds = json.loads(BIRDS_PATH.read_text()) if BIRDS_PATH.exists() else {"regions": {}, "species": {}}
    if _lines is None:
        raw = json.loads(LINES_PATH.read_text()) if LINES_PATH.exists() else {}
        # keyed by the normalised name; the value keeps OUR spelling of the
        # name, which is what the child hears
        _lines = {_name_key(k): (k, v) for k, v in raw.items() if not k.startswith("_") and v}
        # "_aliases": GBIF's spelling -> our key, for slash names like
        # "Great Blue/Cocoi Heron" and regional names like "Mew Gull"
        for gbif_name, ours in (raw.get("_aliases") or {}).items():
            if not gbif_name.startswith("_") and _name_key(ours) in _lines:
                _lines[_name_key(gbif_name)] = _lines[_name_key(ours)]


def _name_key(name: Optional[str]) -> str:
    """Match GBIF's vernacular names to bird_lines.json keys loosely.

    GBIF's spellings are inconsistent: "Sandhill crane", "Willie-wagtail",
    "Canada Goose (canadensis Group)", "American herring gull, Smithsonian
    Gull". Lowercase, drop hyphens and a trailing parenthetical, and keep
    only the first comma-separated name. A slash ("California/Woodhouse's
    Scrub-Jay") is left alone: it is two species and we narrate neither.
    """
    text = (name or "").split(",")[0]
    text = re.sub(r"\s*\([^)]*\)\s*$", "", text)
    return re.sub(r"[\s\-]+", " ", text).strip().lower()


def reset_cache() -> None:
    """Tests swap the data files; drop the module-level copies."""
    global _birds, _lines
    _birds = _lines = None


def _norm(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text or "") if not unicodedata.combining(c)).strip().lower()


def region_key(country_code: Optional[str], region: Optional[str]) -> Optional[str]:
    """The birds.json region for a listener, or None when nothing matches.

    Subdivided countries need a subdivision match (name or alias); a US
    listener with no region never falls back to a whole-US list, because
    there is no such list - cardinals are not Alaskan.
    """
    _load()
    if not country_code:
        return None
    cc = country_code.upper()
    if cc in _birds["regions"]:
        return cc
    wanted = _norm(region)
    if not wanted:
        return None
    for key, table in _birds["regions"].items():
        if table.get("country") != cc:
            continue
        if _norm(table.get("name")) == wanted or any(_norm(a) == wanted for a in table.get("aliases", [])):
            return key
    return None


def local_date(now_utc: datetime, tz_name: Optional[str]):
    """The listener's local date, or None when the timezone is unknown."""
    if not tz_name:
        return None
    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        return None
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    return now_utc.astimezone(tz).date()


def pick_bird(country_code: Optional[str], region: Optional[str], on_date) -> Optional[Dict[str, Any]]:
    """The bird for a region on a date: deterministic by ISO week.

    Returns {"key", "name", "scientific", "line", "region"} or None when the
    region has no narratable species (one with written lines) that month.
    """
    _load()
    key = region_key(country_code, region)
    if not key or on_date is None:
        return None
    month_keys = _birds["regions"][key].get("months", {}).get(str(on_date.month), [])
    candidates = []
    for species_key in month_keys:
        sp = _birds["species"].get(str(species_key)) or {}
        written = _lines.get(_name_key(sp.get("name")))
        if written:
            candidates.append((str(species_key), sp, written))
    if not candidates:
        return None
    _, week, _ = on_date.isocalendar()
    species_key, sp, (spoken_name, lines) = candidates[week % len(candidates)]
    return {
        "key": species_key, "name": spoken_name, "scientific": sp.get("scientific"),
        "line": lines[(week // len(candidates)) % len(lines)], "region": key,
    }


def animal_friday_bird(now_utc: datetime, tz_name: Optional[str], is_fallback: bool,
                       country_code: Optional[str], region: Optional[str],
                       enabled: Optional[bool] = None) -> Optional[Dict[str, Any]]:
    """The bird to serve as the bird track right now, or None for an ordinary scan.

    None whenever any gate fails: the flag is off, geolocation fell back, the
    timezone is unknown, it is not Friday where the listener is, or the
    region has nothing to narrate this month. The intro picker's Friday gate
    is this same function being non-None.
    """
    if enabled is None:
        enabled = animal_friday_enabled()
    if not enabled or is_fallback:
        return None
    today = local_date(now_utc, tz_name)
    if today is None or today.weekday() != _FRIDAY:
        return None
    return pick_bird(country_code, region, today)


def bird_track_text(bird: Dict[str, Any]) -> str:
    """The whole bird-track narration, house style. Plain name only - the
    scientific name is for the data file, not for a five-year-old. No "old
    chum": the intro and outro already lean on it."""
    return (
        "But wait... hold everything! My scanner has just picked up a bonus flyer, "
        "much lower and much smaller than any jet plane. "
        f"Good heavens, it is a {bird['name']}! {bird['line']} "
        "No jet engines on this one, co-pilot, just a pair of very flappy wings. "
        "Happy Animal Friday!"
    )


def bird_cache_key(text: str, provider: str, file_ext: str) -> str:
    """Durable, content-hashed: a line edit or a new week's bird is a new key."""
    text_hash = hashlib.md5(text.encode("utf-8")).hexdigest()[:10]
    return f"{EVENT_NAME}/{text_hash}_{provider}.{file_ext}"


async def ensure_bird_audio(bird: Dict[str, Any], tts_override: Optional[str] = None) -> Dict[str, Any]:
    """Fetch the bird track from its shared cache, generating it once if absent.

    Same shape as special_events.ensure_event_audio: keyed per text +
    provider, not per location, and the cache write is awaited.
    """
    from .main import convert_text_to_speech, TTS_PROVIDER, get_audio_format_for_provider

    provider = (tts_override or TTS_PROVIDER).lower()
    file_ext, mime_type = get_audio_format_for_provider(provider)
    text = bird_track_text(bird)
    key = bird_cache_key(text, provider, file_ext)

    cached = await s3_cache.get_raw(key)
    if cached:
        return {"audio": cached, "error": "", "provider": provider, "file_ext": file_ext,
                "mime_type": mime_type, "from_cache": True, "key": key}

    audio, error, provider_used, actual_ext, actual_mime = await convert_text_to_speech(text, tts_override)
    if audio and not error:
        await s3_cache.set(key, audio)
        logger.info(f"Generated and cached Animal Friday audio: {key} ({bird['name']}, {len(audio)} bytes)")
    else:
        logger.error(f"Animal Friday audio generation failed for {bird['name']}: {error}")
    return {"audio": audio, "error": error, "provider": provider_used, "file_ext": actual_ext,
            "mime_type": actual_mime, "from_cache": False, "key": key}
