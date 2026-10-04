"""Rarity decisions that need more than the aircraft type (DOJP-32).

The tier table in aircraft.json is global, but A380s cluster at a handful of
hubs - a child under the Heathrow or LAX approach could hear "LEGENDARY" most
days, and the word would mean nothing by week two. So the legendary
*treatment* is rate-limited per location: once a location has been awarded a
legendary, further legendaries inside the cooldown window are served with the
rare treatment instead (still special, no fanfare, no LEGENDARY).

The marker is a tiny S3 object under its own prefix (not cache/, which a
lifecycle rule wipes nightly), judged by Last-Modified like every other
freshness check. With S3 disabled (tests, local) the cooldown never engages.
"""

import logging
from typing import Optional, Tuple

from .aircraft_database import get_rarity
from .s3_cache import s3_cache

logger = logging.getLogger(__name__)

LEGENDARY_COOLDOWN_MINUTES = 3 * 24 * 60


def _cooldown_key(location_hash: str) -> str:
    return f"rarity/legendary_{location_hash}"


async def effective_rarity(icao: Optional[str], location_hash: Optional[str]) -> Tuple[str, str]:
    """Return (served_tier, base_tier) for an aircraft at a location.

    served_tier is what the child should hear; base_tier is the type's own
    tier. They differ only when a legendary is downgraded by the cooldown.
    Awarding a legendary writes the cooldown marker (awaited, so two planes in
    one sequentially-built scan can't both win).
    """
    base = get_rarity(icao)
    if base != "legendary" or not location_hash:
        return base, base

    key = _cooldown_key(location_hash)
    if await s3_cache.exists_and_fresh(key, ttl_minutes=LEGENDARY_COOLDOWN_MINUTES):
        logger.info(f"Legendary {icao} downgraded to rare: cooldown active for {location_hash}")
        return "rare", base

    await s3_cache.set(key, b"legendary")
    return "legendary", base
