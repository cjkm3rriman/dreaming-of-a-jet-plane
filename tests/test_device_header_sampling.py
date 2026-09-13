"""Tests for the DOJP-34 device-header sampling middleware

The middleware exists to answer one question from production logs: does the
Yoto player (or mobile app) send anything usable as a device identifier?
These tests pin the safety properties - bounded volume, browser traffic
untouched, secrets redacted - so the sampler can sit in production without
becoming a firehose or a leak.
"""

import logging

import pytest
from fastapi.testclient import TestClient

import app.main as main

YOTO_UA = "ESP32 HTTP Client/1.0"
BROWSER_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/128.0"


@pytest.fixture
def client(monkeypatch):
    """Fresh sampling budget per test"""
    monkeypatch.setattr(
        main, "_device_header_budget",
        {marker: 2 for marker in main.DEVICE_HEADER_UA_MARKERS},
    )
    return TestClient(main.app)


def _sample_lines(caplog):
    return [r.message for r in caplog.records if "DOJP-34" in r.message]


@pytest.mark.unit
def test_player_request_headers_are_logged(client, caplog):
    with caplog.at_level(logging.INFO, logger="app.main"):
        client.get("/no-such-path", headers={
            "User-Agent": YOTO_UA,
            "X-Device-Serial": "y0T0-1234",
        })

    lines = _sample_lines(caplog)
    assert len(lines) == 1
    assert "x-device-serial" in lines[0]
    assert "y0T0-1234" in lines[0]


@pytest.mark.unit
def test_browser_traffic_is_never_sampled(client, caplog):
    with caplog.at_level(logging.INFO, logger="app.main"):
        client.get("/no-such-path", headers={"User-Agent": BROWSER_UA})
        client.get("/no-such-path")  # TestClient default UA

    assert _sample_lines(caplog) == []


@pytest.mark.unit
def test_budget_bounds_the_volume(client, caplog):
    """Per-marker budget: the sampler must go quiet, not firehose"""
    with caplog.at_level(logging.INFO, logger="app.main"):
        for _ in range(5):
            client.get("/no-such-path", headers={"User-Agent": YOTO_UA})

    assert len(_sample_lines(caplog)) == 2  # fixture budget


@pytest.mark.unit
def test_each_client_type_gets_its_own_budget(client, caplog):
    """Player traffic must not exhaust the mobile app's samples"""
    with caplog.at_level(logging.INFO, logger="app.main"):
        for _ in range(5):
            client.get("/no-such-path", headers={"User-Agent": YOTO_UA})
        client.get("/no-such-path", headers={"User-Agent": "Yoto/3.2 (iPhone)"})

    lines = _sample_lines(caplog)
    assert len(lines) == 3
    assert any("(Yoto," in line for line in lines)


@pytest.mark.unit
def test_sensitive_headers_are_redacted(client, caplog):
    with caplog.at_level(logging.INFO, logger="app.main"):
        client.get("/no-such-path", headers={
            "User-Agent": YOTO_UA,
            "Authorization": "Bearer super-secret",
            "Cookie": "session=abc",
        })

    line = _sample_lines(caplog)[0]
    assert "super-secret" not in line
    assert "session=abc" not in line
    assert "<redacted>" in line


@pytest.mark.unit
def test_sampling_can_be_disabled_by_budget_zero(monkeypatch, caplog):
    monkeypatch.setattr(
        main, "_device_header_budget",
        {marker: 0 for marker in main.DEVICE_HEADER_UA_MARKERS},
    )
    client = TestClient(main.app)
    with caplog.at_level(logging.INFO, logger="app.main"):
        client.get("/no-such-path", headers={"User-Agent": YOTO_UA})

    assert _sample_lines(caplog) == []
