"""Tests for dynamic plane-audio response headers (DOJP-39, DOJP-22, DOJP-56)

Plane audio used to be served with Cache-Control: max-age=3600 against a
3-minute server TTL - any intermediary honoring the header re-created the
rescan staleness DOJP-27 fixed (DOJP-39).

It then advertised Accept-Ranges on responses that ignored Range, which made
newer Yoto firmware issue multiple range requests per play (the origin
amplification behind the July 2026 outage, DOJP-22). Range support is now
real (DOJP-56): the handlers serve genuine 206 slices through
plane_audio_response, so Accept-Ranges is advertised again - and the
amplification is prevented by the in-memory cache and single-flight
generation tested in test_audio_response.py.
"""

import inspect

import pytest

import app.main as main
from app.main import PLANE_AUDIO_CACHE_MAX_AGE_S, plane_audio_response_headers
from app.s3_cache import s3_cache


@pytest.mark.unit
def test_max_age_is_derived_from_the_server_ttl():
    """Client caching must never outlive the S3 audio TTL (DOJP-39)"""
    assert PLANE_AUDIO_CACHE_MAX_AGE_S == s3_cache.ttl_minutes * 60
    # and therefore also within the flight-data TTL, per tests/test_cache_ttl.py
    assert PLANE_AUDIO_CACHE_MAX_AGE_S <= s3_cache.api_ttl_minutes * 60


@pytest.mark.unit
def test_headers_carry_the_derived_max_age():
    headers = plane_audio_response_headers("audio/opus", 12345)
    assert headers["Cache-Control"] == f"public, max-age={PLANE_AUDIO_CACHE_MAX_AGE_S}"
    assert headers["Content-Type"] == "audio/opus"
    assert headers["Content-Length"] == "12345"


@pytest.mark.unit
def test_range_support_is_advertised_because_it_is_honoured():
    """Accept-Ranges is only acceptable alongside real 206 handling (DOJP-22);
    plane_audio_response provides it, so the static and dynamic tracks now
    present the same contract to the player (DOJP-56)"""
    headers = plane_audio_response_headers("audio/opus", 1)
    assert headers["Accept-Ranges"] == "bytes"
    assert "Range" in headers["Access-Control-Allow-Headers"]
    assert "Content-Range" in headers["Access-Control-Expose-Headers"]
    assert "Accept-Ranges" in headers["Access-Control-Expose-Headers"]


@pytest.mark.unit
@pytest.mark.parametrize("handler_name", ["handle_plane_endpoint", "handle_free_plane_endpoint"])
def test_dynamic_handlers_respond_through_the_range_aware_helper(handler_name):
    """Both dynamic audio handlers must build every audio response through
    plane_audio_response - a hand-rolled StreamingResponse is how the
    3600/Accept-Ranges pair got in originally, and would silently drop
    Range handling again"""
    source = inspect.getsource(getattr(main, handler_name))
    assert "plane_audio_response(" in source
    assert "StreamingResponse(" not in source
    assert "max-age=3600" not in source
    assert '"Accept-Ranges"' not in source
