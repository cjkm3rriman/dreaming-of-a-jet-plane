"""Animal Friday (DOJP-52): the fifth track is a local bird on Fridays.

Pins region matching against what ipapi.co reports, the deterministic
week-based bird and line rotation, every gate that turns the egg off, the
track-5 slot shift (alone and combined with a Special Signal Event), the
shared content-hashed audio cache, the plane endpoint serving the bird, and
the intro picker's Friday gate following coverage.
"""

import json
from datetime import date, datetime, timezone

import httpx
import pytest
import respx
from starlette.requests import Request

from app import animal_friday as af
from app import location_utils
from app.intro_picker import SCANNING_FRIDAY, SCANNING_MORNING
from app.special_events import aircraft_slot_for_plane

FRIDAY_UTC = datetime(2026, 10, 9, 8, 0, tzinfo=timezone.utc)   # Friday 09:00 London
THURSDAY_UTC = datetime(2026, 10, 8, 8, 0, tzinfo=timezone.utc)


@pytest.fixture
def birds(tmp_path, monkeypatch):
    """A tiny birds.json + bird_lines.json pair standing in for the real files"""
    data = {
        "regions": {
            "US-Virginia": {"country": "US", "name": "Virginia", "aliases": ["VA", "Va."],
                            "months": {"10": [1, 2, 3], "11": [2]}},
            "GB-England": {"country": "GB", "name": "England", "aliases": [],
                           "months": {"10": [4]}},
            "CA-Quebec": {"country": "CA", "name": "Québec", "aliases": ["QC"],
                          "months": {"10": [1]}},
            "FR": {"country": "FR", "name": "France", "aliases": [], "months": {"10": [4]}},
            "JP": {"country": "JP", "name": "Japan", "aliases": [], "months": {"10": [1]}},
        },
        "species": {
            "1": {"name": "Northern Cardinal", "scientific": "Cardinalis cardinalis"},
            "2": {"name": "Mystery Thrush", "scientific": "Turdus ignotus"},   # no lines written
            "3": {"name": "Blue Jay", "scientific": "Cyanocitta cristata"},
            "4": {"name": "European Robin", "scientific": "Erithacus rubecula"},
        },
    }
    lines = {
        "_comment": "fixture",
        "Northern Cardinal": ["Northern Cardinals are red!", "Northern Cardinals sing in the snow!"],
        "Blue Jay": ["Blue Jays are blue!", "Blue Jays bury acorns!"],
        "European Robin": ["European Robins have an orange chest!"],
    }
    (tmp_path / "birds.json").write_text(json.dumps(data))
    (tmp_path / "bird_lines.json").write_text(json.dumps(lines))
    monkeypatch.setattr(af, "BIRDS_PATH", tmp_path / "birds.json")
    monkeypatch.setattr(af, "LINES_PATH", tmp_path / "bird_lines.json")
    af.reset_cache()
    yield data
    af.reset_cache()


# --- region matching ----------------------------------------------------------

@pytest.mark.unit
@pytest.mark.parametrize("country, region, expected", [
    ("US", "Virginia", "US-Virginia"),
    ("us", "virginia", "US-Virginia"),      # case-insensitive
    ("US", "VA", "US-Virginia"),            # ipapi region_code style alias
    ("GB", "England", "GB-England"),
    ("CA", "Quebec", "CA-Quebec"),          # accent-insensitive
    ("CA", "QC", "CA-Quebec"),
    ("FR", "", "FR"),                       # whole-country table needs no region
    ("FR", "Île-de-France", "FR"),
    ("US", "", None),                       # subdivided country, no region: nothing to say
    ("US", "Narnia", None),
    ("ZZ", "Anywhere", None),
    (None, None, None),
])
def test_region_key(birds, country, region, expected):
    assert af.region_key(country, region) == expected


# --- deterministic rotation ---------------------------------------------------

@pytest.mark.unit
def test_pick_bird_rotates_species_and_lines_by_iso_week(birds):
    """Oct 2026 Virginia: species 1 and 3 have lines, 2 does not. Week 41 ->
    Blue Jay (41 % 2), week 42 -> Cardinal, and the line index advances
    once per full cycle through the species."""
    oct_9 = date(2026, 10, 9)    # ISO week 41
    oct_16 = date(2026, 10, 16)  # ISO week 42
    first = af.pick_bird("US", "Virginia", oct_9)
    second = af.pick_bird("US", "Virginia", oct_16)
    assert (first["name"], first["line"]) == ("Blue Jay", "Blue Jays are blue!")
    assert (second["name"], second["line"]) == ("Northern Cardinal", "Northern Cardinals sing in the snow!")
    assert first["region"] == "US-Virginia" and first["key"] == "3"
    # same inputs, same bird - siblings hear the same egg
    assert af.pick_bird("US", "VA", oct_9) == first


@pytest.mark.unit
def test_pick_bird_skips_species_without_lines_and_empty_months(birds):
    nov = date(2026, 11, 6)  # Virginia November lists only the unwritten thrush
    assert af.pick_bird("US", "Virginia", nov) is None
    assert af.pick_bird("US", "Virginia", date(2026, 7, 3)) is None   # no July table
    assert af.pick_bird("US", "", date(2026, 10, 9)) is None            # no region
    assert af.pick_bird("US", "Virginia", None) is None


# --- the gates ----------------------------------------------------------------

@pytest.mark.unit
def test_bird_served_on_a_local_friday(birds):
    bird = af.animal_friday_bird(FRIDAY_UTC, "Europe/London", False, "GB", "England", enabled=True)
    assert bird and bird["name"] == "European Robin"


@pytest.mark.unit
@pytest.mark.parametrize("kwargs", [
    dict(now_utc=FRIDAY_UTC, tz_name="Europe/London", is_fallback=False, country_code="GB", region="England", enabled=False),  # flag off
    dict(now_utc=FRIDAY_UTC, tz_name="Europe/London", is_fallback=True, country_code="GB", region="England", enabled=True),   # NYC fallback
    dict(now_utc=FRIDAY_UTC, tz_name=None, is_fallback=False, country_code="GB", region="England", enabled=True),             # tz unknown
    dict(now_utc=FRIDAY_UTC, tz_name="Not/AZone", is_fallback=False, country_code="GB", region="England", enabled=True),
    dict(now_utc=THURSDAY_UTC, tz_name="Europe/London", is_fallback=False, country_code="GB", region="England", enabled=True),  # not Friday
    dict(now_utc=FRIDAY_UTC, tz_name="Europe/London", is_fallback=False, country_code="US", region="", enabled=True),         # no region
    dict(now_utc=FRIDAY_UTC, tz_name="Europe/London", is_fallback=False, country_code="DE", region="Bayern", enabled=True),   # no table
])
def test_every_gate_turns_the_egg_off(birds, kwargs):
    assert af.animal_friday_bird(**kwargs) is None


@pytest.mark.unit
def test_friday_is_judged_in_local_time(birds):
    """Thursday 23:30 UTC is already Friday morning in Tokyo, and Friday
    23:30 UTC is still Friday in Los Angeles"""
    assert af.animal_friday_bird(datetime(2026, 10, 8, 23, 30, tzinfo=timezone.utc), "Asia/Tokyo", False, "JP", "", enabled=True)
    assert af.animal_friday_bird(datetime(2026, 10, 9, 23, 30, tzinfo=timezone.utc), "America/Los_Angeles", False, "US", "Virginia", enabled=True)
    assert af.animal_friday_bird(datetime(2026, 10, 9, 23, 30, tzinfo=timezone.utc), "Asia/Tokyo", False, "JP", "", enabled=True) is None  # Saturday there


@pytest.mark.unit
def test_flag_is_read_from_environment(birds, monkeypatch):
    monkeypatch.delenv("ANIMAL_FRIDAY_ENABLED", raising=False)
    assert af.animal_friday_bird(FRIDAY_UTC, "Europe/London", False, "GB", "England") is None
    monkeypatch.setenv("ANIMAL_FRIDAY_ENABLED", "1")
    assert af.animal_friday_bird(FRIDAY_UTC, "Europe/London", False, "GB", "England")


# --- track 5 slot ---------------------------------------------------------------

@pytest.mark.unit
def test_bird_owns_track_two_and_the_fifth_plane_drops():
    """First plane, the bird, then three more planes - the fifth aircraft
    is the one that misses out"""
    assert [aircraft_slot_for_plane(n, False, True) for n in range(1, 6)] == [0, None, 1, 2, 3]


@pytest.mark.unit
def test_bird_and_event_compose():
    """Event on track 1, bird on track 2, planes on 3, 4 and 5"""
    assert [aircraft_slot_for_plane(n, True, True) for n in range(1, 6)] == [None, None, 0, 1, 2]


@pytest.mark.unit
async def test_free_pool_skips_the_bird_track_and_renumbers(monkeypatch):
    """On a Friday the free pool must not try to copy track 2 (the bird has
    no body cache) and free plane 2 must be the Club's track-3 plane"""
    import app.free_pool as fp
    reads, writes, captured = [], [], {}

    async def fake_get_raw(key):
        reads.append(key)
        return b"body"

    async def fake_set(key, data, content_type="audio"):
        writes.append(key)
        return True

    async def fake_update_index(session_id, planes_data, tts_provider):
        captured["planes"] = planes_data
        return True

    monkeypatch.setattr(fp.s3_cache, "get_raw", fake_get_raw)
    monkeypatch.setattr(fp.s3_cache, "set", fake_set)
    monkeypatch.setattr(fp, "update_free_pool_index", fake_update_index)
    aircraft = [{"origin_city": o, "destination_city": d, "airline_name": "X"} for o, d in
                [("A", "Oslo"), ("B", "Lima"), ("C", "Cork"), ("D", "Rome")]]
    assert await fp.populate_free_pool(aircraft, "h", "inworld", bird_active=True)
    assert [p["destination_city"] for p in captured["planes"]] == ["Oslo", "Lima", "Cork"]
    assert [p["index"] for p in captured["planes"]] == [1, 2, 3]
    assert [k.split("_plane")[1][0] for k in reads] == ["1", "3", "4"]
    assert [k.split("_plane")[1][0] for k in writes] == ["1", "2", "3"]
    # and nothing changes for the existing cases
    assert [aircraft_slot_for_plane(n, False, False) for n in range(1, 6)] == [0, 1, 2, 3, 4]
    assert [aircraft_slot_for_plane(n, True, False) for n in range(1, 6)] == [None, 0, 1, 2, 3]


# --- text and audio -----------------------------------------------------------

@pytest.mark.unit
def test_track_text_is_house_style(birds):
    bird = af.pick_bird("GB", "England", date(2026, 10, 9))
    text = af.bird_track_text(bird)
    assert text.startswith("But wait... hold everything!")
    assert "it is a European Robin!" in text
    assert "European Robins have an orange chest!" in text
    assert text.endswith("Happy Animal Friday!")
    assert "Erithacus" not in text  # no Latin for a five-year-old
    assert "old chum" not in text   # the intro and outro already use it
    assert "co-pilot" in text


@pytest.mark.unit
def test_cache_key_is_content_hashed_per_provider():
    a = af.bird_cache_key("text one", "inworld", "opus")
    b = af.bird_cache_key("text two", "inworld", "opus")
    c = af.bird_cache_key("text one", "elevenlabs", "opus")
    assert a.startswith("animal-friday/") and a.endswith("_inworld.opus")
    assert len({a, b, c}) == 3
    assert a == af.bird_cache_key("text one", "inworld", "opus")


@pytest.mark.unit
async def test_ensure_bird_audio_generates_once_then_serves_cached(birds, monkeypatch):
    from app import main
    store = {}

    async def fake_get_raw(key):
        return store.get(key)

    async def fake_set(key, data):
        store[key] = data
        return True

    calls = {"n": 0}

    async def tts(text, tts_override=None):
        calls["n"] += 1
        return b"bird-opus", "", "inworld", "opus", "audio/opus"

    monkeypatch.setattr(af.s3_cache, "get_raw", fake_get_raw)
    monkeypatch.setattr(af.s3_cache, "set", fake_set)
    monkeypatch.setattr(main, "convert_text_to_speech", tts)
    monkeypatch.setattr(main, "TTS_PROVIDER", "inworld")

    bird = af.pick_bird("GB", "England", date(2026, 10, 9))
    first = await af.ensure_bird_audio(bird)
    second = await af.ensure_bird_audio(bird)
    assert first["audio"] == b"bird-opus" and first["from_cache"] is False
    assert second["from_cache"] is True and calls["n"] == 1
    assert list(store) == [first["key"]]


@pytest.mark.unit
async def test_failed_bird_generation_caches_nothing(birds, monkeypatch):
    from app import main
    store = {}

    async def fake_get_raw(key):
        return None

    async def fake_set(key, data):
        store[key] = data

    async def tts(text, tts_override=None):
        return b"", "boom", "inworld", "opus", "audio/opus"

    monkeypatch.setattr(af.s3_cache, "get_raw", fake_get_raw)
    monkeypatch.setattr(af.s3_cache, "set", fake_set)
    monkeypatch.setattr(main, "convert_text_to_speech", tts)
    monkeypatch.setattr(main, "TTS_PROVIDER", "inworld")

    result = await af.ensure_bird_audio(af.pick_bird("GB", "England", date(2026, 10, 9)))
    assert result["audio"] == b"" and result["error"] == "boom" and store == {}


# --- the endpoint and the intro gate ----------------------------------------------

def _request(ip="203.0.113.70", path="/plane/2"):
    return Request({"type": "http", "method": "GET", "path": path,
                    "query_string": b"", "headers": [], "client": (ip, 1)})


class _Frozen(datetime):
    @classmethod
    def now(cls, tz=None):
        return FRIDAY_UTC if tz else FRIDAY_UTC.replace(tzinfo=None)


@pytest.mark.unit
async def test_plane_two_serves_the_bird_on_friday(birds, monkeypatch):
    from app import main

    async def fake_location(request, lat=None, lng=None, country=None):
        return 51.5, -0.12, "GB", "London", "England", "United Kingdom", False

    monkeypatch.setattr(main, "get_user_location", fake_location)
    monkeypatch.setattr(main, "get_timezone_for_request", lambda request, lat=None, lng=None: "Europe/London")
    monkeypatch.setattr(main, "datetime", _Frozen)
    monkeypatch.setattr(main, "TTS_PROVIDER", "inworld")
    monkeypatch.setenv("ANIMAL_FRIDAY_ENABLED", "1")
    monkeypatch.setattr(main, "get_active_event", lambda: None)

    served = {}

    async def fake_ensure(bird, tts_override=None):
        served["bird"] = bird["name"]
        return {"audio": b"robin-opus", "error": "", "provider": "inworld", "file_ext": "opus",
                "mime_type": "audio/opus", "from_cache": False, "key": "animal-friday/x_inworld.opus"}
    monkeypatch.setattr(main, "ensure_bird_audio", fake_ensure)

    tracked = {}
    monkeypatch.setattr(main, "track_plane_request", lambda *a, **kw: tracked.update(kw))

    response = await main.handle_plane_endpoint(_request(), 2)
    assert response.status_code == 200
    assert served["bird"] == "European Robin"
    assert tracked["event_name"] == "animal-friday"


@pytest.mark.unit
async def test_intro_friday_gate_follows_bird_coverage(birds, monkeypatch):
    """Friday morning in London: a listener with a bird gets the Friday
    intro, a listener whose region has nothing to narrate gets the
    ordinary morning intro - the promise is only made when it can be kept"""
    from app import main as main_mod
    from app import scanning as scanning_mod

    monkeypatch.setattr(scanning_mod, "_scanning_request_cache", {})
    monkeypatch.setattr(scanning_mod, "spawn", lambda coro, name: coro.close())
    monkeypatch.setattr(scanning_mod, "datetime", _Frozen)
    monkeypatch.setattr(main_mod, "TTS_PROVIDER", "inworld")
    monkeypatch.setattr(main_mod, "track_scan_start", lambda *a, **kw: None)
    monkeypatch.setenv("ANIMAL_FRIDAY_ENABLED", "1")

    base = "https://dreaming-of-a-jet-plane.s3.us-east-2.amazonaws.com/ronald/"
    cases = [
        ("203.0.113.71", "England", SCANNING_FRIDAY),
        ("203.0.113.72", "Narnia", SCANNING_MORNING),
    ]
    for ip, region, expected in cases:
        monkeypatch.setattr(location_utils, "_ip_cache",
                            {ip: (51.5, -0.12, "GB", "London", region, "United Kingdom", False, "Europe/London", 1e12)})
        with respx.mock as router:
            route = router.get(base + f"{expected}.opus").mock(return_value=httpx.Response(200, content=b"opus"))
            response = await scanning_mod.stream_scanning(_request(ip, "/scanning"))
        assert response.status_code == 200
        assert route.called, f"{region}: expected {expected}"


# --- the real data files -------------------------------------------------------

REAL_LINES = af.LINES_PATH


@pytest.mark.unit
def test_real_bird_lines_follow_the_style_guide():
    """Every line starts with the species name (plural or possessive forms
    allowed) so the TTS always says who it is talking about"""
    lines = {k: v for k, v in json.loads(REAL_LINES.read_text()).items() if not k.startswith("_")}
    assert len(lines) >= 100
    irregular = {"goose": "geese", "titmouse": "titmice"}

    def opens_with(line, name):
        want = name.lower().replace("-", " ").split()
        got = line.lower().replace("-", " ").split()[:len(want)]
        if len(got) < len(want) or got[:-1] != want[:-1]:
            return False
        last, said = want[-1], got[-1]
        return said.startswith(last) or said == irregular.get(last)

    for name, entries in lines.items():
        assert entries, name
        for line in entries:
            assert opens_with(line, name), f"{name!r}: {line[:60]!r}"
            assert line.endswith("!"), f"{name!r}: line should end with an exclamation mark"


@pytest.mark.unit
@pytest.mark.parametrize("gbif_name, key", [
    ("Sandhill crane", "sandhill crane"),
    ("Willie-wagtail", "willie wagtail"),
    ("Canada Goose (canadensis Group)", "canada goose"),
    ("American herring gull, Smithsonian Gull", "american herring gull"),
    ("California/Woodhouse's Scrub-Jay", "california/woodhouse's scrub jay"),
    (None, ""),
])
def test_gbif_names_are_matched_loosely(gbif_name, key):
    assert af._name_key(gbif_name) == key


@pytest.mark.unit
def test_child_hears_our_spelling_not_gbifs(tmp_path, monkeypatch):
    data = {"regions": {"FR": {"country": "FR", "name": "France", "aliases": [], "months": {"10": [9]}}},
            "species": {"9": {"name": "Sandhill crane (lower-case group)", "scientific": "Antigone canadensis"}}}
    (tmp_path / "b.json").write_text(json.dumps(data))
    (tmp_path / "l.json").write_text(json.dumps({"Sandhill Crane": ["Sandhill Cranes dance!"]}))
    monkeypatch.setattr(af, "BIRDS_PATH", tmp_path / "b.json")
    monkeypatch.setattr(af, "LINES_PATH", tmp_path / "l.json")
    af.reset_cache()
    try:
        bird = af.pick_bird("FR", "", date(2026, 10, 9))
        assert bird["name"] == "Sandhill Crane"
        assert "it is a Sandhill Crane!" in af.bird_track_text(bird)
    finally:
        af.reset_cache()


@pytest.mark.unit
def test_aliases_map_gbif_slash_names_to_our_entry(tmp_path, monkeypatch):
    data = {"regions": {"FR": {"country": "FR", "name": "France", "aliases": [], "months": {"10": [7]}}},
            "species": {"7": {"name": "Great Blue/Cocoi Heron", "scientific": "Ardea herodias"}}}
    (tmp_path / "b.json").write_text(json.dumps(data))
    (tmp_path / "l.json").write_text(json.dumps({
        "_aliases": {"Great Blue/Cocoi Heron": "Great Blue Heron"},
        "Great Blue Heron": ["Great Blue Herons stand very still!"],
    }))
    monkeypatch.setattr(af, "BIRDS_PATH", tmp_path / "b.json")
    monkeypatch.setattr(af, "LINES_PATH", tmp_path / "l.json")
    af.reset_cache()
    try:
        bird = af.pick_bird("FR", "", date(2026, 10, 9))
        assert bird["name"] == "Great Blue Heron"
    finally:
        af.reset_cache()
