"""Tests for S3 cache TTL invariants

/plane/N serves cached audio before consulting flight data, so audio that
outlives the flight JSON TTL replays a stale snapshot on rescan (DOJP-27).
These tests pin the audio TTL to the flight-data TTL so the two cannot
silently drift apart again.
"""

import pytest

from app.s3_cache import S3MP3Cache, s3_cache


@pytest.mark.unit
def test_audio_ttl_does_not_exceed_flight_data_ttl():
    """Default audio TTL must not outlive the flight JSON it was generated from"""
    cache = S3MP3Cache()
    assert cache.ttl_minutes <= cache.api_ttl_minutes


@pytest.mark.unit
def test_shared_cache_instance_ttls_aligned():
    """The module-level singleton used by the app must obey the same invariant"""
    assert s3_cache.ttl_minutes <= s3_cache.api_ttl_minutes
