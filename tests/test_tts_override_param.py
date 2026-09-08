"""Tests for the /plane/N tts override parameter (DOJP-26 item 4)

The five plane routes used to declare `tts` and never forward it; the override
worked only because a helper re-read the raw query string behind the handler's
back. It is now passed through the signature like `provider` already was, so
these tests pin the wiring and the secret check that guards it.
"""

import inspect

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.main import app, handle_plane_endpoint, normalize_tts_provider_override

SECRET = "test-override-secret"


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def override_secret(monkeypatch):
    """Configure a known override secret for the duration of a test"""
    monkeypatch.setattr(main, "PROVIDER_OVERRIDE_SECRET", SECRET)
    return SECRET


@pytest.mark.unit
def test_handler_accepts_a_tts_argument():
    """The parameter the routes forward must exist on the handler"""
    assert "tts" in inspect.signature(handle_plane_endpoint).parameters


@pytest.mark.unit
@pytest.mark.parametrize("plane_index", [1, 2, 3, 4, 5])
def test_every_plane_route_forwards_tts(plane_index):
    """A route that declares tts but drops it is the bug this fixes"""
    source = inspect.getsource(getattr(main, f"plane_{plane_index}_endpoint"))
    assert "tts" in source.split("handle_plane_endpoint")[1], \
        f"/plane/{plane_index} declares tts but does not forward it"


@pytest.mark.unit
@pytest.mark.parametrize("provider", ["elevenlabs", "google", "inworld", "fallback"])
def test_supported_providers_normalize(provider):
    assert normalize_tts_provider_override(provider.upper()) == provider


@pytest.mark.unit
def test_unsupported_provider_falls_back_rather_than_failing():
    """An unknown name yields None so the caller uses the configured provider"""
    assert normalize_tts_provider_override("not-a-provider") is None


@pytest.mark.unit
def test_absent_provider_is_none():
    assert normalize_tts_provider_override(None) is None


@pytest.mark.unit
def test_tts_override_without_secret_is_rejected(client, override_secret):
    """Requesting an override with no secret must 403, not silently proceed"""
    response = client.get("/plane/1?tts=google")
    assert response.status_code == 403


@pytest.mark.unit
def test_tts_override_with_wrong_secret_is_rejected(client, override_secret):
    response = client.get("/plane/1?tts=google&secret=wrong")
    assert response.status_code == 403


@pytest.mark.unit
def test_request_without_tts_is_not_rejected(client, override_secret):
    """The guard must only fire when an override is actually requested"""
    response = client.get("/plane/1")
    assert response.status_code != 403
