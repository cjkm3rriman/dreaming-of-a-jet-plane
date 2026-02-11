"""
Seasonal text overrides for flight descriptions (e.g. Christmas, holidays)
"""

from datetime import datetime, timezone
from typing import Optional


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


def get_plane_sentence_override(plane_index: int) -> Optional[str]:
    """Return special holiday copy when applicable (7am GMT Dec 24 to 7am GMT Dec 25)"""
    now_utc = datetime.now(timezone.utc)
    if plane_index == 5 and now_utc.month == 12:
        # Active from 7am GMT Dec 24 to 7am GMT Dec 25
        if (now_utc.day == 24 and now_utc.hour >= 7) or (now_utc.day == 25 and now_utc.hour < 7):
            return CHRISTMAS_SANTA_TEXT
    return None
