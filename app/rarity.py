"""Rarity decisions that need more than the aircraft type (DOJP-32).

The tier table in aircraft.json is global, but A380s cluster at a handful of
hubs - a child under the Heathrow or LAX approach could hear "LEGENDARY" most
days, and the word would mean nothing by week two. So the legendary
*treatment* is rate-limited per location: once a location has been awarded a
legendary, further legendaries inside the cooldown window are served with the
rare treatment instead (still special, no fanfare, no LEGENDARY).

"Location" is the household, approximated by the hashed client IP - each home
router has its own public IP, whereas IP *geolocation* collapses whole
neighbourhoods onto one centroid and would make the cooldown shared across
families. The coordinate cell is only the fallback when no request is in
hand. The marker is a tiny S3 object under its own prefix (not cache/, which a
lifecycle rule wipes nightly), judged by Last-Modified like every other
freshness check. With S3 disabled (tests, local) the cooldown never engages.
"""

import hashlib
import logging
from typing import Optional, Tuple

from .aircraft_database import get_rarity
from .location_utils import extract_client_ip
from .s3_cache import s3_cache

logger = logging.getLogger(__name__)

LEGENDARY_COOLDOWN_MINUTES = 3 * 24 * 60


def cooldown_scope(request, fallback_hash: Optional[str]) -> Optional[str]:
    """The identity the cooldown is keyed on: hashed client IP (per household)
    when a request is available, else the coordinate cell hash."""
    if request is not None:
        ip = extract_client_ip(request)
        if ip:
            return "ip-" + hashlib.md5(ip.encode("utf-8")).hexdigest()[:16]
    return fallback_hash


def _cooldown_key(scope: str) -> str:
    return f"rarity/legendary_{scope}"


async def effective_rarity(icao: Optional[str], scope: Optional[str]) -> Tuple[str, str]:
    """Return (served_tier, base_tier) for an aircraft within a cooldown scope
    (see cooldown_scope).

    served_tier is what the child should hear; base_tier is the type's own
    tier. They differ only when a legendary is downgraded by the cooldown.
    Awarding a legendary writes the cooldown marker (awaited, so two planes in
    one sequentially-built scan can't both win).
    """
    base = get_rarity(icao)
    if base != "legendary" or not scope:
        return base, base

    key = _cooldown_key(scope)
    if await s3_cache.exists_and_fresh(key, ttl_minutes=LEGENDARY_COOLDOWN_MINUTES):
        logger.info(f"Legendary {icao} downgraded to rare: cooldown active for {scope}")
        return "rare", base

    await s3_cache.set(key, b"legendary")
    return "legendary", base
