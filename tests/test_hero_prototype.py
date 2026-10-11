"""The /prototype/hero page: a CSS-animated Yoto Mini, served but not indexed.

A smoke test only. The page is a static HTML string, so the properties worth
pinning are that it serves, points at assets the app really ships, and never
leaks into search results while it is a prototype.
"""

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.website_hero_prototype import SCANNING_CLIP


@pytest.fixture
def client():
    return TestClient(main.app)


@pytest.mark.unit
def test_hero_prototype_serves_and_is_noindex(client):
    r = client.get("/prototype/hero")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert 'name="robots" content="noindex' in r.text
    assert SCANNING_CLIP in r.text


@pytest.mark.unit
def test_hero_prototype_assets_exist(client):
    """The wordmark and smiley it references are real files under /assets"""
    for path in ("/assets/img/wordmark.png", "/assets/img/yoto.png"):
        assert client.get(path).status_code == 200, path


@pytest.mark.unit
def test_hero_prototype_is_not_in_the_sitemap(client):
    assert "/prototype/hero" not in client.get("/sitemap.xml").text
