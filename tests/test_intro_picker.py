"""Club intro picker (DOJP-61): which pre-rendered /scanning clip plays.

Pins the daypart / weekday table, the real-timezone (DST) behaviour, the
"unknown listener -> plain intro" rule, and that every variant the picker
can return has a manifest entry and a fallback path when its file is
missing from a voice folder.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
import respx
from starlette.requests import Request

from app import location_utils
from app.intro_picker import (
    SCANNING_DEFAULT, SCANNING_EVENING, SCANNING_FRIDAY, SCANNING_MORNING, SCANNING_VARIANTS,
    SCANNING_WEEKEND, animal_friday_enabled, pick_scanning_variant,
)

MANIFEST = Path(__file__).parent.parent / "audio_build" / "static_audio.json"


def _utc(y, m, d, hh, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=timezone.utc)


# 2026-10-05 is a Monday; 2026-10-09 a Friday; 2026-10-10 a Saturday.
@pytest.mark.unit
@pytest.mark.parametrize("utc, tz, expected", [
    # London in October is BST (UTC+1): local = utc + 1
    (_utc(2026, 10, 5, 3, 59), "Europe/London", SCANNING_DEFAULT),   # 04:59 local - night
    (_utc(2026, 10, 5, 4, 0), "Europe/London", SCANNING_MORNING),    # 05:00 local - first morning minute
    (_utc(2026, 10, 5, 9, 59), "Europe/London", SCANNING_MORNING),   # 10:59 local
    (_utc(2026, 10, 5, 10, 0), "Europe/London", SCANNING_DEFAULT),   # 11:00 local - midday is the plain intro
    (_utc(2026, 10, 5, 15, 59), "Europe/London", SCANNING_DEFAULT),  # 16:59 local
    (_utc(2026, 10, 5, 16, 0), "Europe/London", SCANNING_EVENING),   # 17:00 local - evening starts at 5pm
    (_utc(2026, 10, 5, 21, 59), "Europe/London", SCANNING_EVENING),  # 22:59 local
    (_utc(2026, 10, 5, 22, 0), "Europe/London", SCANNING_DEFAULT),   # 23:00 local - late night is plain
    (_utc(2026, 10, 10, 12, 0), "Europe/London", SCANNING_WEEKEND),  # Saturday midday
    (_utc(2026, 10, 11, 7, 0), "Europe/London", SCANNING_WEEKEND),   # Sunday 08:00 - weekend outranks morning
])
def test_weekday_daypart_table(utc, tz, expected):
    assert pick_scanning_variant(utc, tz, is_fallback=False, friday_enabled=False) == expected


@pytest.mark.unit
def test_daylight_saving_moves_the_edges():
    """15:00 UTC is 11:00 in New York in summer (EDT) but 10:00 in winter
    (EST): the longitude guess would get one of these wrong"""
    summer = _utc(2026, 7, 6, 15, 0)   # Monday, EDT
    winter = _utc(2026, 12, 7, 15, 0)  # Monday, EST
    assert pick_scanning_variant(summer, "America/New_York", False, friday_enabled=False) == SCANNING_DEFAULT
    assert pick_scanning_variant(winter, "America/New_York", False, friday_enabled=False) == SCANNING_MORNING


@pytest.mark.unit
def test_weekday_is_judged_in_local_time():
    """23:30 UTC Friday is already Saturday morning in Tokyo"""
    friday_night_utc = _utc(2026, 10, 9, 23, 30)
    assert pick_scanning_variant(friday_night_utc, "Asia/Tokyo", False, friday_enabled=False) == SCANNING_WEEKEND
    assert pick_scanning_variant(friday_night_utc, "America/Los_Angeles", False, friday_enabled=False) == SCANNING_DEFAULT  # 16:30 Friday, midday


@pytest.mark.unit
def test_friday_variant_is_gated_by_flag():
    friday_morning = _utc(2026, 10, 9, 8, 0)  # 09:00 London
    assert pick_scanning_variant(friday_morning, "Europe/London", False, friday_enabled=True) == SCANNING_FRIDAY
    # flag off: Friday is an ordinary weekday, so the daypart rules apply
    assert pick_scanning_variant(friday_morning, "Europe/London", False, friday_enabled=False) == SCANNING_MORNING


@pytest.mark.unit
def test_flag_reads_environment(monkeypatch):
    monkeypatch.delenv("ANIMAL_FRIDAY_ENABLED", raising=False)
    assert animal_friday_enabled() is False
    for value in ("1", "true", "True", "yes", "on"):
        monkeypatch.setenv("ANIMAL_FRIDAY_ENABLED", value)
        assert animal_friday_enabled() is True, value
    monkeypatch.setenv("ANIMAL_FRIDAY_ENABLED", "false")
    assert animal_friday_enabled() is False
    # and the picker consults it when no override is passed
    monkeypatch.setenv("ANIMAL_FRIDAY_ENABLED", "1")
    assert pick_scanning_variant(_utc(2026, 10, 9, 8, 0), "Europe/London", False) == SCANNING_FRIDAY


@pytest.mark.unit
@pytest.mark.parametrize("tz, is_fallback", [
    (None, False),                 # no timezone known (lat/lng params, localhost)
    ("Not/AZone", False),          # garbage from the geolocation provider
    ("", False),
    ("Europe/London", True),       # geolocation fell back to NYC: we know nothing
])
def test_unknown_listener_gets_the_plain_intro(tz, is_fallback):
    saturday_morning = _utc(2026, 10, 10, 7, 0)  # would be weekend AND morning if trusted
    assert pick_scanning_variant(saturday_morning, tz, is_fallback, friday_enabled=True) == SCANNING_DEFAULT


@pytest.mark.unit
def test_naive_datetime_is_treated_as_utc():
    naive = datetime(2026, 10, 5, 4, 0)  # 05:00 London
    assert pick_scanning_variant(naive, "Europe/London", False, friday_enabled=False) == SCANNING_MORNING


@pytest.mark.unit
def test_every_variant_has_a_manifest_entry():
    """The picker can never name a clip the build pipeline does not know"""
    entries = json.loads(MANIFEST.read_text())["entries"]
    for variant in SCANNING_VARIANTS:
        assert variant in entries, f"{variant} missing from audio_build/static_audio.json"
        assert any("robot_tts" in step for step in entries[variant]["timeline"]), \
            f"{variant} should share the robot tail with scanning"


# --- timezone through the location cache -----------------------------------

def _request(ip="203.0.113.50"):
    return Request({"type": "http", "method": "GET", "path": "/scanning",
                    "query_string": b"", "headers": [], "client": (ip, 1)})


@pytest.mark.unit
async def test_ip_lookup_caches_the_timezone(monkeypatch):
    ip = "203.0.113.51"
    monkeypatch.setattr(location_utils, "_ip_cache", {})
    monkeypatch.delenv("IPAPI_API_KEY", raising=False)
    with respx.mock as router:
        router.get(f"https://ipapi.co/{ip}/json/").mock(return_value=httpx.Response(200, json={
            "latitude": 51.5, "longitude": -0.12, "country_code": "GB", "city": "London",
            "region": "England", "country_name": "United Kingdom", "timezone": "Europe/London",
        }))
        result = await location_utils.get_location_from_ip(ip)
    assert result[:3] == (51.5, -0.12, "GB")
    assert location_utils.get_timezone_for_ip(ip) == "Europe/London"
    assert location_utils.get_timezone_for_request(_request(ip)) == "Europe/London"


@pytest.mark.unit
async def test_fallback_lookup_has_no_timezone(monkeypatch):
    ip = "203.0.113.52"
    monkeypatch.setattr(location_utils, "_ip_cache", {})
    monkeypatch.delenv("IPAPI_API_KEY", raising=False)
    with respx.mock as router:
        router.get(f"https://ipapi.co/{ip}/json/").mock(return_value=httpx.Response(200, json={
            "latitude": None, "longitude": None, "timezone": "America/New_York",
        }))
        result = await location_utils.get_location_from_ip(ip)
    assert result[-1] is True  # fell back to NYC
    assert location_utils.get_timezone_for_ip(ip) is None


@pytest.mark.unit
def test_unknown_ip_and_explicit_coords_have_no_timezone(monkeypatch):
    monkeypatch.setattr(location_utils, "_ip_cache", {})
    assert location_utils.get_timezone_for_ip("198.51.100.9") is None
    assert location_utils.get_timezone_for_request(_request("198.51.100.9")) is None
    location_utils._ip_cache["198.51.100.9"] = (1.0, 2.0, "GB", "", "", "", False, "Europe/London", 0.0)
    assert location_utils.get_timezone_for_request(_request("198.51.100.9")) == "Europe/London"
    # explicit coordinates skip the IP lookup, so there is nothing to report
    assert location_utils.get_timezone_for_request(_request("198.51.100.9"), lat=1.0, lng=2.0) is None


# --- missing variant falls back to the plain clip ----------------------------

@pytest.mark.unit
async def test_missing_variant_file_falls_back_to_scanning():
    from app.static_audio import proxy_s3_audio
    base = "https://dreaming-of-a-jet-plane.s3.us-east-2.amazonaws.com/ronald/"
    hits = []
    with respx.mock as router:
        router.get(base + "scanning-morning.opus").mock(return_value=httpx.Response(404))
        router.get(base + "scanning.opus").mock(side_effect=lambda r: (hits.append(str(r.url)), httpx.Response(200, content=b"opus"))[1])
        response = await proxy_s3_audio(_request(), base + "scanning-morning.opus", "audio/opus",
                                        fallback_url=base + "scanning.opus")
    assert response.status_code == 200
    assert hits == [base + "scanning.opus"]


@pytest.mark.unit
async def test_fallback_is_one_hop_only():
    """A missing default still errors - the fallback never chases itself"""
    from app.static_audio import proxy_s3_audio
    base = "https://dreaming-of-a-jet-plane.s3.us-east-2.amazonaws.com/ronald/"
    with respx.mock as router:
        router.get(base + "scanning-morning.opus").mock(return_value=httpx.Response(404))
        router.get(base + "scanning.opus").mock(return_value=httpx.Response(404))
        response = await proxy_s3_audio(_request(), base + "scanning-morning.opus", "audio/opus",
                                        fallback_url=base + "scanning.opus", error_style="json")
    assert response.status_code == 404


# --- the endpoint streams the picked variant --------------------------------

@pytest.mark.unit
async def test_stream_scanning_serves_the_picked_variant(monkeypatch):
    """Monday 08:00 in London -> /scanning streams ronald/scanning-morning
    and tags scan:start with the variant"""
    from datetime import datetime as _dt
    from app import scanning as scanning_mod
    from app import main as main_mod

    ip = "203.0.113.60"
    monkeypatch.setattr(location_utils, "_ip_cache",
                        {ip: (51.5, -0.12, "GB", "London", "England", "United Kingdom", False, "Europe/London", 1e12)})
    monkeypatch.setattr(scanning_mod, "_scanning_request_cache", {})
    monkeypatch.setattr(scanning_mod, "spawn", lambda coro, name: coro.close())
    monkeypatch.setattr(main_mod, "TTS_PROVIDER", "inworld")

    class FrozenDatetime(_dt):
        @classmethod
        def now(cls, tz=None):
            return _dt(2026, 10, 5, 7, 0, tzinfo=tz)  # Monday 07:00 UTC = 08:00 BST
    monkeypatch.setattr(scanning_mod, "datetime", FrozenDatetime)

    tracked = {}
    monkeypatch.setattr(main_mod, "track_scan_start",
                        lambda request, subscription="yoto-club", intro_variant=None: tracked.update(variant=intro_variant))

    url = "https://dreaming-of-a-jet-plane.s3.us-east-2.amazonaws.com/ronald/scanning-morning.opus"
    with respx.mock as router:
        route = router.get(url).mock(return_value=httpx.Response(200, content=b"opus"))
        response = await scanning_mod.stream_scanning(_request(ip))
    assert route.called
    assert response.status_code == 200
    assert tracked["variant"] == SCANNING_MORNING
