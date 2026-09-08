"""Tests for cache-key file extensions (DOJP-26 item 1)

generate_cache_key used to carry its own provider->format map, which claimed
ElevenLabs produced mp3 when it produces opus. Nothing hit that branch because
every live call site passes audio_format explicitly, but a caller that omitted
it would have written and read mismatched extensions - a permanent cache miss
that looks like a TTS fault. The extension now comes from the TTS registry, and
these tests pin the two to each other.
"""

import pytest

from app.s3_cache import S3MP3Cache
from app.tts_providers import TTS_PROVIDERS, get_audio_format

LAT, LNG = 40.7128, -74.0060


@pytest.fixture
def cache():
    return S3MP3Cache()


@pytest.mark.unit
def test_elevenlabs_key_without_explicit_format_is_opus(cache):
    """The exact case the stale map got wrong"""
    key = cache.generate_cache_key(LAT, LNG, plane_index=1, tts_provider="elevenlabs")
    assert key.endswith(".opus")


@pytest.mark.unit
@pytest.mark.parametrize("provider", sorted(TTS_PROVIDERS))
def test_derived_extension_matches_the_registry(cache, provider):
    """Every registered provider keys on the extension the registry declares"""
    expected, _ = get_audio_format(provider)
    key = cache.generate_cache_key(LAT, LNG, plane_index=1, tts_provider=provider)
    assert key.endswith(f".{expected}")


@pytest.mark.unit
def test_explicit_format_still_wins(cache):
    """Callers that pass audio_format keep controlling the extension"""
    key = cache.generate_cache_key(
        LAT, LNG, plane_index=1, tts_provider="elevenlabs", audio_format="mp3"
    )
    assert key.endswith(".mp3")


@pytest.mark.unit
def test_unknown_provider_falls_back_to_mp3(cache):
    """An unregistered provider must not raise"""
    key = cache.generate_cache_key(LAT, LNG, plane_index=1, tts_provider="nonesuch")
    assert key.endswith(".mp3")


@pytest.mark.unit
def test_provider_name_is_case_insensitive(cache):
    """Mixed-case provider names resolve the same as lowercase"""
    lower = cache.generate_cache_key(LAT, LNG, plane_index=1, tts_provider="inworld")
    upper = cache.generate_cache_key(LAT, LNG, plane_index=1, tts_provider="Inworld")
    assert lower.endswith(".opus")
    assert upper.endswith(".opus")
