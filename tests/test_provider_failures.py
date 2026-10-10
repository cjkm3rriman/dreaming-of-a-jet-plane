"""Provider failures: retry transient 5xx, and page only when the whole chain fails.

Sentry DREAMING-OF-A-JETPLANE-23: Airlabs's edge returned a bare nginx 500
twice in 22 seconds. The provider logged it at error level (so Sentry paged)
and did not retry, even though a second attempt a second later would very
likely have succeeded and FR24 was configured as a fallback anyway. Now a
5xx gets one retry, a single provider failing is a warning, and the error is
reserved for the outcome that actually matters: every provider failed.
"""

import logging

import httpx
import pytest
import respx

import app.aircraft_providers.airlabs as airlabs
import app.aircraft_providers.fr24 as fr24
from app import main

NGINX_500 = "<html><head><title>500 Internal Server Error</title></head></html>"
LAT, LNG = 40.7128, -74.0060


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(fr24, "FR24_API_KEY", "test-key")
    monkeypatch.setattr(airlabs, "AIRLABS_API_KEY", "test-key")
    monkeypatch.setattr(airlabs, "RETRY_BACKOFF", 0.0)


@pytest.mark.unit
async def test_airlabs_retries_a_5xx_once_and_recovers(configured, caplog):
    calls = {"n": 0}

    def flaky(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(500, text=NGINX_500)
        return httpx.Response(200, json={"response": []})

    with respx.mock:
        respx.get(url__startswith="https://airlabs.co").mock(side_effect=flaky)
        with caplog.at_level(logging.WARNING, logger="app.aircraft_providers.airlabs"):
            aircraft, error, _ = await airlabs.fetch_aircraft(LAT, LNG, 100, 5)

    assert calls["n"] == 2
    assert error == "" or "No" in error  # an empty sky, not a failure
    assert any("HTTP 500" in r.message and "retrying" in r.message for r in caplog.records)
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


@pytest.mark.unit
async def test_airlabs_persistent_5xx_is_a_warning_not_an_error(configured, caplog):
    calls = {"n": 0}

    def always_500(request):
        calls["n"] += 1
        return httpx.Response(500, text=NGINX_500)

    with respx.mock:
        respx.get(url__startswith="https://airlabs.co").mock(side_effect=always_500)
        with caplog.at_level(logging.WARNING, logger="app.aircraft_providers.airlabs"):
            aircraft, error, _ = await airlabs.fetch_aircraft(LAT, LNG, 100, 5)

    assert calls["n"] == 2  # exactly one retry, not a loop
    assert aircraft == [] and error == "Airlabs API returned HTTP 500"
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert any("HTTP 500" in r.message and "Body=" in r.message for r in caplog.records)


@pytest.mark.unit
async def test_airlabs_does_not_retry_a_4xx(configured):
    calls = {"n": 0}

    def forbidden(request):
        calls["n"] += 1
        return httpx.Response(403, json={"error": "bad key"})

    with respx.mock:
        respx.get(url__startswith="https://airlabs.co").mock(side_effect=forbidden)
        aircraft, error, _ = await airlabs.fetch_aircraft(LAT, LNG, 100, 5)

    assert calls["n"] == 1
    assert error == "Airlabs API returned HTTP 403"


@pytest.mark.unit
async def test_fr24_non_200_is_a_warning(configured, caplog):
    with respx.mock:
        respx.get(url__startswith="https://fr24api.flightradar24.com").mock(
            return_value=httpx.Response(503, text="upstream unavailable")
        )
        with caplog.at_level(logging.WARNING, logger="app.aircraft_providers.fr24"):
            aircraft, error, _ = await fr24.fetch_aircraft(LAT, LNG, 100, 5)

    assert aircraft == [] and "HTTP 503" in error
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert any(r.levelno == logging.WARNING and "HTTP 503" in r.message for r in caplog.records)


@pytest.mark.unit
async def test_whole_chain_failing_logs_one_error(configured, monkeypatch, caplog):
    """Airlabs primary, FR24 fallback, both down: that is the error"""
    monkeypatch.setattr(main, "LIVE_AIRCRAFT_PROVIDER", "airlabs")
    monkeypatch.setattr(main, "LIVE_AIRCRAFT_PROVIDER_FALLBACKS", ["fr24"])

    with respx.mock:
        respx.get(url__startswith="https://airlabs.co").mock(return_value=httpx.Response(500, text=NGINX_500))
        respx.get(url__startswith="https://fr24api.flightradar24.com").mock(return_value=httpx.Response(502))
        with caplog.at_level(logging.WARNING):
            aircraft, error = await main.get_nearby_aircraft(LAT, LNG, limit=5)

    assert aircraft == []
    assert "Airlabs API returned HTTP 500" in error and "FlightRadar24 API returned HTTP 502" in error
    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert len(errors) == 1 and errors[0].name == "app.main"
    assert "All aircraft providers failed" in errors[0].message


@pytest.mark.unit
async def test_fallback_serving_is_not_an_error(configured, monkeypatch, caplog):
    """The DREAMING-OF-A-JETPLANE-23 shape: Airlabs 500s, FR24 answers -
    warnings only, and the chain returns the FR24 result"""
    monkeypatch.setattr(main, "LIVE_AIRCRAFT_PROVIDER", "airlabs")
    monkeypatch.setattr(main, "LIVE_AIRCRAFT_PROVIDER_FALLBACKS", ["fr24"])

    with respx.mock:
        respx.get(url__startswith="https://airlabs.co").mock(return_value=httpx.Response(500, text=NGINX_500))
        fr = respx.get(url__startswith="https://fr24api.flightradar24.com").mock(
            return_value=httpx.Response(200, json={"data": []})
        )
        with caplog.at_level(logging.WARNING):
            await main.get_nearby_aircraft(LAT, LNG, limit=5)

    assert fr.called
    airlabs_errors = [r for r in caplog.records if r.levelno >= logging.ERROR and "airlabs" in r.name]
    assert airlabs_errors == []


@pytest.mark.unit
async def test_empty_sky_from_every_provider_is_a_warning(configured, monkeypatch, caplog):
    """DREAMING-OF-A-JETPLANE-24: a rural listener, both providers answer 200
    with nothing in range. Nothing broke, so nobody gets paged"""
    monkeypatch.setattr(main, "LIVE_AIRCRAFT_PROVIDER", "airlabs")
    monkeypatch.setattr(main, "LIVE_AIRCRAFT_PROVIDER_FALLBACKS", ["fr24"])

    with respx.mock:
        respx.get(url__startswith="https://airlabs.co").mock(return_value=httpx.Response(200, json={"response": []}))
        respx.get(url__startswith="https://fr24api.flightradar24.com").mock(
            return_value=httpx.Response(200, json={"data": []})
        )
        with caplog.at_level(logging.WARNING):
            aircraft, error = await main.get_nearby_aircraft(LAT, LNG, limit=5)

    assert aircraft == []
    assert airlabs.EMPTY_SKY in error and fr24.EMPTY_SKY in error
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING and r.name == "app.main"]
    assert len(warnings) == 1 and "Empty sky from every aircraft provider" in warnings[0].message


@pytest.mark.unit
async def test_one_broken_provider_plus_an_empty_fallback_is_still_an_error(configured, monkeypatch, caplog):
    """Airlabs 500s and FR24 finds nothing: the child hears no planes and a
    provider broke on the way, so this one still pages"""
    monkeypatch.setattr(main, "LIVE_AIRCRAFT_PROVIDER", "airlabs")
    monkeypatch.setattr(main, "LIVE_AIRCRAFT_PROVIDER_FALLBACKS", ["fr24"])

    with respx.mock:
        respx.get(url__startswith="https://airlabs.co").mock(return_value=httpx.Response(500, text=NGINX_500))
        respx.get(url__startswith="https://fr24api.flightradar24.com").mock(
            return_value=httpx.Response(200, json={"data": []})
        )
        with caplog.at_level(logging.WARNING):
            aircraft, error = await main.get_nearby_aircraft(LAT, LNG, limit=5)

    assert aircraft == []
    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert len(errors) == 1 and errors[0].name == "app.main"
    assert "All aircraft providers failed" in errors[0].message
