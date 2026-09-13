"""Tests for fun-fact cache key placement (DOJP-50)

The bucket's "Cache Clean Up" lifecycle rule expires everything under the
cache/ prefix after one day. The fun-fact cache is designed to be permanent
(content-hashed, no TTL, each fact synthesized once ever) but lived under
cache/fun_facts/ - so S3 silently wiped it nightly for months, holding the
hit rate at ~58% forever. These tests pin the keys outside the reaped prefix
so nobody moves them back.
"""

import pytest

from app.fun_fact_cache import get_fun_fact_cache_key, get_opening_phrase_cache_key

FACT = "Boston built the first subway in America - it opened in 1897!"
OPENER = "Did you know?"


@pytest.mark.unit
def test_fact_keys_live_outside_the_lifecycle_reaped_prefix():
    """Anything under cache/ is deleted nightly by the S3 lifecycle rule.
    A permanent cache must not live there (DOJP-50)."""
    key = get_fun_fact_cache_key(FACT, "inworld", "opus")
    assert not key.startswith("cache/")
    assert key.startswith("tts-cache/fun_facts/")


@pytest.mark.unit
def test_opening_keys_live_outside_the_lifecycle_reaped_prefix():
    key = get_opening_phrase_cache_key(OPENER, "inworld", "opus")
    assert not key.startswith("cache/")
    assert key.startswith("tts-cache/fun_facts/openings/")


@pytest.mark.unit
def test_key_is_content_addressed_and_stable():
    """Same text, provider and format must always produce the same key -
    that is the whole caching mechanism"""
    a = get_fun_fact_cache_key(FACT, "inworld", "opus")
    b = get_fun_fact_cache_key(FACT, "inworld", "opus")
    assert a == b
    assert a.endswith("_inworld.opus")


@pytest.mark.unit
def test_text_provider_and_format_each_change_the_key():
    base = get_fun_fact_cache_key(FACT, "inworld", "opus")
    assert get_fun_fact_cache_key(FACT + " ", "inworld", "opus") != base
    assert get_fun_fact_cache_key(FACT, "google", "opus") != base
    assert get_fun_fact_cache_key(FACT, "inworld", "mp3") != base
