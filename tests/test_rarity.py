"""Aircraft rarity tiers (DOJP-32)

Three tiers: common / rare / legendary. Rarity lives in aircraft.json (only
non-common entries carry it), the rarity line replaces the scanner
sentence's lead-in, the legendary fanfare is stitched between opening and
body on the paid path only, and selection never drops a rare/legendary
candidate. The variant tests render every template combination and check
for the two failure modes a listener notices: repetition and non-sequiturs.
"""

import itertools
import random
import re

import pytest

import app.flight_text as ft
import app.plane_audio as pa
from app.aircraft_database import get_rarity, get_rarity_blurb


# ---------------------------------------------------------------------------
# Data + accessors
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("icao,tier", [
    ("A388", "legendary"), ("B744", "legendary"), ("B748", "legendary"), ("A3ST", "legendary"),
    ("B752", "rare"), ("B712", "rare"), ("A346", "rare"), ("MD88", "rare"), ("B722", "rare"),
    ("B738", "common"), ("B77W", "common"), ("B789", "common"), ("A320", "common"),
    ("ZZZZ", "common"), (None, "common"), ("", "common"), ("a388", "legendary"),  # case-insensitive
])
def test_get_rarity(icao, tier):
    assert get_rarity(icao) == tier


@pytest.mark.unit
def test_every_legendary_has_a_blurb_and_rare_does_not():
    import json
    data = json.load(open("app/aircraft.json"))
    for icao, entry in data.items():
        if entry.get("rarity") == "legendary":
            assert entry.get("rarity_blurb"), f"{icao} legendary without blurb"
            assert get_rarity_blurb(icao) == entry["rarity_blurb"]
        elif entry.get("rarity") == "rare":
            assert not entry.get("rarity_blurb"), f"{icao} rare types don't carry blurbs"
        else:
            assert "rarity" not in entry, f"{icao}: common entries must not carry the field"


@pytest.mark.unit
def test_tier_frequencies_match_the_calibration():
    """The 2026-07..10 Mixpanel calibration put legendary at ~1.1% and rare at
    ~2.4% of narrated planes. Guard the type lists against drift: 777/787
    must stay common (a tenth of all traffic), A380/747 legendary."""
    import json
    data = json.load(open("app/aircraft.json"))
    tiers = {k: v.get("rarity", "common") for k, v in data.items()}
    assert tiers["A388"] == "legendary" and tiers["B744"] == "legendary"
    assert all(tiers[k] == "common" for k in ("B77W", "B773", "B789", "B788", "B738", "A321", "A20N") if k in tiers)
    assert 8 <= sum(1 for t in tiers.values() if t == "legendary") <= 20
    assert 8 <= sum(1 for t in tiers.values() if t == "rare") <= 25


# ---------------------------------------------------------------------------
# Template variants: every combination, checked for repetition / non-sequiturs
# ---------------------------------------------------------------------------

OPENING_WORDS = {w.rstrip("!").lower() for w in
                 ["Marvelous!", "Good Heavens!", "Fantastic!", "Splendid!", "What Luck!", "Wow!",
                  "Remarkable!", "Tremendous!", "Brilliant!", "By Jove!"]}


def _aircraft(icao, name, capacity=200, velocity=480, altitude=35000):
    return {"aircraft_icao": icao, "aircraft": name, "passenger_capacity": capacity,
            "velocity": velocity, "altitude": altitude, "flight_number": "DL4999",
            "airline_name": "Delta Air Lines", "origin_city": "New York City",
            "origin_country": "the United States", "destination_city": "Lisbon",
            "destination_country": "Portugal", "destination_airport": "LIS", "origin_airport": "JFK",
            "distance_km": 14.5, "eta": None}


def _scanner_sentences(icao, name, n=60):
    """Render the split body many times and return the distinct scanner
    sentences (the first sentence(s) of the body, before flight details)."""
    seen = set()
    for seed in range(n):
        random.seed(seed)
        opening, body, *_ = ft.generate_flight_text_for_aircraft(
            _aircraft(icao, name), 40.7, -74.0, 1, "US", split_text=True)
        seen.add((opening, body))
    return seen


INTENTIONAL_DOUBLES = ("boo boo butt", "hold on... hold on")  # a pilot's name, a stammer


def _no_adjacent_duplicate_words(text):
    """Accidental word doubling ("the the", "rare rare") - excluding the
    doubles the scripts do on purpose"""
    cleaned = text.lower()
    for phrase in INTENTIONAL_DOUBLES:
        cleaned = cleaned.replace(phrase, "")
    words = re.findall(r"[a-z']+", cleaned)
    return all(a != b for a, b in zip(words, words[1:]))


@pytest.mark.unit
def test_legendary_variants_name_the_aircraft_once_and_read_clean():
    renders = _scanner_sentences("A388", "Airbus A380 Super Jumbo")
    intros_seen, closers_seen = set(), set()
    for opening, body in renders:
        scanner = body.split(" This flight ")[0]
        # the legendary line replaces the lead-in: aircraft named exactly once
        assert scanner.count("A three eighty") == 1, scanner
        assert "piloting this" not in scanner, "legendary must not also use the common lead-in"
        assert "LEGENDARY" in scanner
        assert "biggest passenger plane" in scanner, "blurb must be present"
        assert "Captain" in scanner and "at the controls" in scanner
        assert _no_adjacent_duplicate_words(scanner), scanner
        # no echo of the opening exclamation one sentence later
        first_word = opening.split("!")[0].lower()
        assert first_word not in scanner.lower(), f"opener echoed: {opening} / {scanner}"
        intros_seen.add(next(i for i in ft.LEGENDARY_INTROS if scanner.startswith(i)))
        closers_seen.add(next(c for c in ft.LEGENDARY_CLOSERS if scanner.endswith(c)))
    assert intros_seen == set(ft.LEGENDARY_INTROS), "every intro variant must be reachable"
    assert closers_seen == set(ft.LEGENDARY_CLOSERS), "every closer variant must be reachable"


@pytest.mark.unit
def test_rare_variants_keep_the_normal_sentence_and_read_clean():
    renders = _scanner_sentences("B752", "Boeing 757")
    intros_seen = set()
    for opening, body in renders:
        scanner = body.split(" This flight ")[0]
        assert scanner.count("seven five seven") == 1, scanner
        assert "piloting this" in scanner, "rare keeps the ordinary captain sentence after its intro"
        assert "LEGENDARY" not in scanner and "legendary" not in scanner.lower()
        assert scanner.lower().count("rare") <= 1, f"'rare' repeated: {scanner}"
        assert _no_adjacent_duplicate_words(scanner), scanner
        first_word = opening.split("!")[0].lower()
        assert first_word not in scanner.lower(), f"opener echoed: {opening} / {scanner}"
        intros_seen.add(next(i for i in ft.RARE_INTROS if scanner.startswith(i)))
    assert intros_seen == set(ft.RARE_INTROS)


@pytest.mark.unit
def test_common_is_byte_identical_to_before():
    """No rarity text leaks into common planes - the overwhelming majority"""
    for opening, body in _scanner_sentences("B738", "Boeing 737", n=30):
        scanner = body.split(" This flight ")[0]
        assert scanner.startswith("Captain "), scanner
        assert "rare" not in scanner.lower() and "LEGENDARY" not in scanner
        for intro in ft.RARE_INTROS + ft.LEGENDARY_INTROS:
            assert intro not in body


@pytest.mark.unit
def test_rarity_intros_avoid_the_opening_exclamation_pool():
    """A legendary intro of 'Good heavens' right after an opener of 'Good
    Heavens!' is the kind of repetition a child notices instantly"""
    for line in ft.RARE_INTROS + ft.LEGENDARY_INTROS + ft.LEGENDARY_CLOSERS:
        head = re.split(r"[!.\-,]", line)[0].strip().lower()
        assert head not in OPENING_WORDS, f"{line!r} collides with the opening pool"


@pytest.mark.unit
def test_legendary_article_agrees_with_the_name():
    for opening, body in _scanner_sentences("A388", "Airbus A380 Super Jumbo", n=6):
        assert "That is an Airbus" in body
    for opening, body in _scanner_sentences("B744", "Boeing 747 Jumbo Jet", n=6):
        assert "That is a Boeing" in body


# ---------------------------------------------------------------------------
# Fanfare: paid path only, between opening and body, never in the pool body
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_legendary_fanfare_sits_between_opening_and_body(monkeypatch):
    calls = []

    async def fake_tts(text, tts_override=None):
        return f"tts:{text[:12]}".encode(), "", "inworld", "opus", "audio/opus"

    async def fake_stitch_multi(segments, add_silence=True, audio_format="mp3", gap_durations=None):
        calls.append((list(segments), gap_durations))
        return b"stitched"

    async def fake_set(key, data, content_type="audio"):
        return True

    import app.main as main
    monkeypatch.setattr(main, "convert_text_to_speech", fake_tts)
    import app.free_pool as fp
    monkeypatch.setattr(fp, "stitch_audio_multi", fake_stitch_multi)
    monkeypatch.setattr(pa, "_fanfare_bytes", lambda ext: b"FANFARE")
    monkeypatch.setattr(pa.s3_cache, "set", fake_set)

    result = await pa.generate_plane_audio(
        "full sentence", opening_text="What luck!", body_text="Hold on...",
        fun_fact_opening_text="Did you know?", fun_fact_body_text="Lisbon has tiles.",
        location_hash="abc", plane_index=1, rarity="legendary")
    assert result["audio"] == b"stitched"

    paid, body_pool = calls[0], calls[1]
    assert paid[0][0].startswith(b"tts:What luck") and paid[0][1] == b"FANFARE", \
        "fanfare must follow the opening"
    assert paid[0][2].startswith(b"tts:Hold on"), "body follows the fanfare"
    assert paid[1][:2] == [300, 300], "tight gaps around the fanfare"
    assert b"FANFARE" not in body_pool[0], "the free-pool body must never carry the fanfare"


@pytest.mark.unit
async def test_common_plane_has_no_fanfare(monkeypatch):
    calls = []

    async def fake_tts(text, tts_override=None):
        return b"tts", "", "inworld", "opus", "audio/opus"

    async def fake_stitch_multi(segments, add_silence=True, audio_format="mp3", gap_durations=None):
        calls.append(list(segments))
        return b"stitched"

    async def fake_set(key, data, content_type="audio"):
        return True

    import app.main as main
    import app.free_pool as fp
    monkeypatch.setattr(main, "convert_text_to_speech", fake_tts)
    monkeypatch.setattr(fp, "stitch_audio_multi", fake_stitch_multi)
    monkeypatch.setattr(pa, "_fanfare_bytes", lambda ext: (_ for _ in ()).throw(AssertionError("fanfare loaded for common")))
    monkeypatch.setattr(pa.s3_cache, "set", fake_set)

    await pa.generate_plane_audio("s", opening_text="o", body_text="b",
                                  fun_fact_opening_text="f", fun_fact_body_text="g",
                                  location_hash="abc", plane_index=1, rarity="common")
    assert len(calls[0]) == 4, "opening, body, fact opener, fact body - no fanfare slot"


@pytest.mark.unit
def test_fanfare_asset_renders_in_both_formats():
    for ext in ("opus", "mp3"):
        data = pa._fanfare_bytes(ext)
        assert len(data) > 5000
    from pydub import AudioSegment
    import io
    clip = AudioSegment.from_file(io.BytesIO(pa._fanfare_bytes("opus")), format="ogg")
    assert 2.5 <= clip.duration_seconds <= 3.2 and clip.channels == 2 and clip.dBFS > -40


# ---------------------------------------------------------------------------
# Selection: never drop a lottery win
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_selection_keeps_a_legendary_that_diversity_would_have_dropped():
    import app.main as main
    # six passenger flights all to the same destination; the A380 is farthest,
    # so pure distance/diversity ordering would leave it out of the five
    planes = [_aircraft("B738", "Boeing 737") | {"distance_km": d} for d in (5, 9, 14, 20, 27)]
    legendary = _aircraft("A388", "Airbus A380 Super Jumbo") | {"distance_km": 60}
    chosen = main.select_diverse_aircraft(planes + [legendary], 40.7, -74.0, "New York City")
    assert len(chosen) == 5
    assert any(p["aircraft_icao"] == "A388" for p in chosen), "legendary was dropped on the floor"


@pytest.mark.unit
def test_selection_unchanged_when_everything_is_common():
    import app.main as main
    planes = [_aircraft("B738", "Boeing 737") | {"distance_km": d} for d in (5, 9, 14, 20, 27, 33)]
    chosen = main.select_diverse_aircraft(planes, 40.7, -74.0, "New York City")
    assert [p["distance_km"] for p in chosen] == [5, 9, 14, 20, 27]
