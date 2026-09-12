"""Tests for dynamic plane-audio response headers (DOJP-39 + DOJP-22)

Plane audio used to be served with Cache-Control: max-age=3600 against a
3-minute server TTL - any intermediary honoring the header re-created the
rescan staleness DOJP-27 fixed. It also advertised Accept-Ranges on responses
that ignore Range headers, which made newer Yoto firmware issue multiple range
requests per play (the origin amplification behind the July 2026 outage).

The headers now come from one helper, so the policy is tested here directly.
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
def test_no_range_support_is_advertised():
    """StreamingResponse ignores Range; advertising it caused firmware to
    issue multiple range requests per play (DOJP-22)"""
    headers = plane_audio_response_headers("audio/opus", 1)
    assert "Accept-Ranges" not in headers
    assert "Range" not in headers["Access-Control-Allow-Headers"]
    assert "Content-Range" not in headers["Access-Control-Expose-Headers"]
    assert "Accept-Ranges" not in headers["Access-Control-Expose-Headers"]


@pytest.mark.unit
@pytest.mark.parametrize("handler_name", ["handle_plane_endpoint", "handle_free_plane_endpoint"])
def test_dynamic_handlers_use_the_shared_helper(handler_name):
    """Both dynamic audio handlers must build headers through the helper -
    a hand-rolled dict is how the 3600/Accept-Ranges pair got in originally"""
    source = inspect.getsource(getattr(main, handler_name))
    assert "plane_audio_response_headers(" in source
    assert "max-age=3600" not in source
    assert '"Accept-Ranges"' not in source
