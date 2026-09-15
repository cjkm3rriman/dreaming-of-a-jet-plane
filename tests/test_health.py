"""Health endpoint for zero-downtime deploys (DOJP-49)

Railway holds the old deployment until the new one passes /health, so the
endpoint must be up-and-cheap: 200 with no S3/provider/analytics dependency,
or a degraded upstream would block deploys instead of enabling clean cutover.
"""

from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

import app.main as main


@pytest.fixture
def client():
    return TestClient(main.app)


@pytest.mark.unit
def test_health_returns_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


@pytest.mark.unit
def test_health_touches_no_dependencies(client, monkeypatch):
    """No S3, no analytics - so a degraded backend can't fail the deploy probe"""
    s3_get = Mock(side_effect=AssertionError("health hit S3"))
    track = Mock(side_effect=AssertionError("health fired analytics"))
    monkeypatch.setattr(main.s3_cache, "get", s3_get)
    monkeypatch.setattr(main.analytics, "track_event", track)

    assert client.get("/health").status_code == 200


@pytest.mark.unit
def test_health_is_configured_as_the_railway_probe():
    """The endpoint and railway.toml must agree, or cutover probes the wrong path"""
    import tomllib
    from pathlib import Path

    cfg = tomllib.loads((Path(__file__).parent.parent / "railway.toml").read_text())
    assert cfg["deploy"]["healthcheckPath"] == "/health"
    assert {r.path for r in main.app.routes if getattr(r, "path", None) == "/health"}
