"""
test_health.py — Tests for root & health-check endpoints.
"""
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def client():
    with patch("app.services.supabase_client.supabase", None):
        from fastapi.testclient import TestClient
        from app.main import app
        with TestClient(app) as c:
            yield c


class TestHealthEndpoints:
    """TC-HEALTH-*: Basic liveness & readiness checks."""

    def test_root_returns_healthy_status(self, client):
        """TC-HEALTH-01: GET / returns 200 with status=healthy."""
        res = client.get("/")
        assert res.status_code == 200, f"Expected 200, got {res.status_code}"
        body = res.json()
        assert body["status"] == "healthy"
        assert "service" in body
        assert "version" in body

    def test_health_endpoint_returns_ok(self, client):
        """TC-HEALTH-02: GET /health returns 200 with status=ok."""
        res = client.get("/health")
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "ok"
        assert "version" in body

    def test_root_service_name(self, client):
        """TC-HEALTH-03: Root endpoint includes correct service name."""
        res = client.get("/")
        assert "VoCall" in res.json()["service"]

    def test_root_version_format(self, client):
        """TC-HEALTH-04: Version string follows semver pattern."""
        import re
        res = client.get("/")
        version = res.json()["version"]
        assert re.match(r"^\d+\.\d+\.\d+", version), f"Invalid version format: {version}"
