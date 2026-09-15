"""Provider selection is single-voice and format-consistent (DOJP-43)

The cross-provider "fallback" mode is gone: switching voices mid-session is
bad UX, and it conflated formats/voices across providers. These tests pin two
things: convert_text_to_speech routes to exactly one registered provider and
derives format from it, and flipping TTS_PROVIDER to elevenlabs yields opus
end to end (the switch Callum wanted to be sure of).
"""

from unittest.mock import AsyncMock

import pytest

import app.main as main


@pytest.fixture
def stub_providers(monkeypatch):
    """Replace each provider's generate_audio with a labelled stub"""
    calls = []

    def _make(provider):
        async def _gen(text):
            calls.append(provider)
            return f"{provider}-audio".encode(), ""
        return _gen

    import app.tts_providers as tts
    for name in ("elevenlabs", "google", "inworld"):
        monkeypatch.setitem(tts.TTS_PROVIDERS[name], "generate_audio", _make(name))
    return calls


@pytest.mark.unit
async def test_elevenlabs_produces_opus_end_to_end(stub_providers, monkeypatch):
    """The Railway-switch case: TTS_PROVIDER=elevenlabs -> opus, audio/opus,
    provider tag 'elevenlabs' - all consistent so cache keys and headers agree"""
    monkeypatch.setattr(main, "TTS_PROVIDER", "elevenlabs")

    audio, error, provider, ext, mime = await main.convert_text_to_speech("hi")

    assert error == ""
    assert audio == b"elevenlabs-audio"
    assert provider == "elevenlabs"
    assert ext == "opus"
    assert mime == "audio/opus"
    assert stub_providers == ["elevenlabs"], "exactly one provider call, no fallback"


@pytest.mark.unit
@pytest.mark.parametrize("provider,ext,mime", [
    ("elevenlabs", "opus", "audio/opus"),
    ("inworld", "opus", "audio/opus"),
    ("google", "mp3", "audio/mpeg"),
])
async def test_each_provider_reports_its_own_format(stub_providers, monkeypatch, provider, ext, mime):
    monkeypatch.setattr(main, "TTS_PROVIDER", provider)
    _, _, used, got_ext, got_mime = await main.convert_text_to_speech("hi")
    assert (used, got_ext, got_mime) == (provider, ext, mime)


@pytest.mark.unit
async def test_a_failing_provider_is_not_silently_retried_elsewhere(stub_providers, monkeypatch):
    """No fallback: an ElevenLabs failure surfaces as an ElevenLabs failure,
    it does not quietly become Inworld audio in a different voice"""
    async def _fail(text):
        stub_providers.append("elevenlabs")
        return b"", "ElevenLabs API returned status 403"

    import app.tts_providers as tts
    monkeypatch.setitem(tts.TTS_PROVIDERS["elevenlabs"], "generate_audio", _fail)
    monkeypatch.setattr(main, "TTS_PROVIDER", "elevenlabs")

    audio, error, provider, _, _ = await main.convert_text_to_speech("hi")

    assert audio == b""
    assert "403" in error
    assert provider == "elevenlabs"
    assert stub_providers == ["elevenlabs"], "inworld must not have been called"


@pytest.mark.unit
async def test_fallback_is_no_longer_an_accepted_provider(stub_providers, monkeypatch):
    """TTS_PROVIDER=fallback (a stale Railway value) now fails loudly as an
    unknown provider rather than running the broken fallback path"""
    monkeypatch.setattr(main, "TTS_PROVIDER", "fallback")

    audio, error, provider, _, _ = await main.convert_text_to_speech("hi")

    assert audio == b""
    assert "Unknown TTS provider" in error
    assert provider == "unknown"
    assert stub_providers == [], "no provider should have been invoked"


@pytest.mark.unit
def test_fallback_is_rejected_as_a_query_override():
    assert main.normalize_tts_provider_override("fallback") is None
    assert "fallback" not in main.TTS_OVERRIDE_PROVIDERS


@pytest.mark.unit
@pytest.mark.parametrize("provider,folder", [
    ("elevenlabs", "edward"),
    ("google", "sadachbia"),
    ("inworld", "ronald"),
])
def test_voice_folder_and_static_extension_match_the_provider(monkeypatch, provider, folder):
    """Static clip URL uses the provider's own voice folder and audio
    extension - the edward/*.opus assets exist for exactly this path"""
    monkeypatch.setattr(main, "TTS_PROVIDER", provider)
    url = main.get_voice_specific_s3_url("scanning.mp3")
    ext = "opus" if provider in ("elevenlabs", "inworld") else "mp3"
    assert url.endswith(f"/{folder}/scanning.{ext}")
