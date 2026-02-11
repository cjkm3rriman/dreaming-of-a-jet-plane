"""Endpoint tests using FastAPI TestClient to catch runtime errors"""

import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    """Create a test client for the FastAPI app"""
    return TestClient(app)


class TestFreeEndpoints:
    """Tests for free tier endpoints"""

    def test_free_scanning_endpoint_no_500(self, client):
        """Test /free/scanning doesn't return 500 error"""
        response = client.get("/free/scanning")
        # Should return 200 (success) or 429 (rate limited), not 500
        assert response.status_code != 500, f"Server error: {response.text}"

    def test_free_scanning_again_endpoint_no_500(self, client):
        """Test /free/scanning-again doesn't return 500 error"""
        response = client.get("/free/scanning-again")
        assert response.status_code != 500, f"Server error: {response.text}"

    def test_free_overandout_endpoint_no_500(self, client):
        """Test /free/overandout doesn't return 500 error"""
        response = client.get("/free/overandout")
        assert response.status_code != 500, f"Server error: {response.text}"

    def test_free_plane_1_endpoint_no_500(self, client):
        """Test /free/plane/1 doesn't return 500 error"""
        response = client.get("/free/plane/1")
        # May return 200 (audio), 404 (no pool), or 429 (rate limited)
        # Should never return 500
        assert response.status_code != 500, f"Server error: {response.text}"

    def test_free_plane_2_endpoint_no_500(self, client):
        """Test /free/plane/2 doesn't return 500 error"""
        response = client.get("/free/plane/2")
        assert response.status_code != 500, f"Server error: {response.text}"

    def test_free_plane_3_endpoint_no_500(self, client):
        """Test /free/plane/3 doesn't return 500 error"""
        response = client.get("/free/plane/3")
        assert response.status_code != 500, f"Server error: {response.text}"


class TestPremiumEndpoints:
    """Tests for premium endpoints"""

    def test_scanning_mp3_endpoint_no_500(self, client):
        """Test /scanning.mp3 doesn't return 500 error"""
        response = client.get("/scanning.mp3")
        assert response.status_code != 500, f"Server error: {response.text}"

    def test_intro_mp3_endpoint_no_500(self, client):
        """Test /intro.mp3 doesn't return 500 error"""
        response = client.get("/intro.mp3")
        assert response.status_code != 500, f"Server error: {response.text}"

    def test_scanning_again_mp3_endpoint_no_500(self, client):
        """Test /scanning-again.mp3 doesn't return 500 error"""
        response = client.get("/scanning-again.mp3")
        assert response.status_code != 500, f"Server error: {response.text}"

    def test_overandout_mp3_endpoint_no_500(self, client):
        """Test /overandout.mp3 doesn't return 500 error"""
        response = client.get("/overandout.mp3")
        assert response.status_code != 500, f"Server error: {response.text}"


    def test_plane_4_endpoint_no_500(self, client):
        """Test /plane/4 doesn't return 500 error"""
        response = client.get("/plane/4")
        assert response.status_code != 500, f"Server error: {response.text}"

    def test_plane_5_endpoint_no_500(self, client):
        """Test /plane/5 doesn't return 500 error"""
        response = client.get("/plane/5")
        assert response.status_code != 500, f"Server error: {response.text}"


class TestHealthEndpoints:
    """Tests for health/utility endpoints"""

    def test_root_endpoint(self, client):
        """Test root endpoint returns 200"""
        response = client.get("/")
        assert response.status_code == 200
