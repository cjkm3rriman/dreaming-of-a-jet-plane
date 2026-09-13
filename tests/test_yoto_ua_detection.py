"""Tests for Yoto client user-agent detection (DOJP-34)

The DOJP-34 header sampling found the player uses TWO user agents: the
long-known "ESP32 HTTP Client/1.0" (original firmware, and v2's HEAD probes)
and "Yoto v2 FW; version v2.23.4" (v2 firmware's streaming requests - the
ones that fire analytics). Only the ESP32 string was matched before, so v2
players were labeled "Other" in Mixpanel, and the mislabeled share grows with
the v2 rollout. The Yoto *mobile app* sends "Yoto/..." UAs and must NOT be
labeled as a player.
"""

import pytest

from app.location_utils import parse_user_agent

# Real user agents captured from production traffic, 2026-09-13 (DOJP-34)
ESP32_UA = "ESP32 HTTP Client/1.0"
V2_FW_UA = "Yoto v2 FW; version v2.23.4"
IOS_APP_UA = "Yoto/21858 CFNetwork/3860.700.2 Darwin/25.6.0"
ANDROID_APP_UA = "Dalvik/2.1.0 (Linux; U; Android 16; SM-S916U Build/BP4A.251205.006)"
BROWSER_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"


@pytest.mark.unit
def test_original_firmware_ua_is_a_yoto_player():
    info = parse_user_agent(ESP32_UA)
    assert info["device"] == "Yoto Player"
    assert info["browser"] == "Yoto"
    assert info["os"] == "Yoto"


@pytest.mark.unit
def test_v2_firmware_streaming_ua_is_a_yoto_player():
    """The v2 UA fires the actual analytics events; it was 'Other' before"""
    info = parse_user_agent(V2_FW_UA)
    assert info["device"] == "Yoto Player"
    assert info["browser"] == "Yoto"


@pytest.mark.unit
def test_v2_firmware_version_is_extracted():
    """Firmware version becomes a fleet dimension in analytics"""
    assert parse_user_agent(V2_FW_UA)["browser_version"] == "v2.23.4"


@pytest.mark.unit
def test_future_firmware_versions_also_match():
    info = parse_user_agent("Yoto v3 FW; version v3.0.1")
    assert info["device"] == "Yoto Player"
    assert info["browser_version"] == "v3.0.1"


@pytest.mark.unit
def test_ios_app_is_not_a_yoto_player():
    """'Yoto/21858 CFNetwork/...' is the mobile app - a phone, not a player"""
    info = parse_user_agent(IOS_APP_UA)
    assert info["device"] != "Yoto Player"


@pytest.mark.unit
def test_android_app_is_not_a_yoto_player():
    info = parse_user_agent(ANDROID_APP_UA)
    assert info["device"] != "Yoto Player"


@pytest.mark.unit
def test_browsers_are_untouched():
    info = parse_user_agent(BROWSER_UA)
    assert info["device"] != "Yoto Player"
    assert info["browser"] == "Chrome"
