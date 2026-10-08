"""
test_auth.py — Tests for /api/v1/auth/* routes.
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

BASE = "/api/v1/auth"


@pytest.fixture
def client():
    with patch("app.services.supabase_client.supabase", None), \
         patch("app.routers.auth.settings.NEXT_PUBLIC_SUPABASE_URL", ""):
        from fastapi.testclient import TestClient
        from app.main import app
        with TestClient(app) as c:
            yield c


class TestAuthLogin:
    """TC-AUTH-LOGIN-*: Login endpoint behaviour."""

    def test_login_returns_token_response(self, client):
        """TC-AUTH-LOGIN-01: POST /auth/login returns token response."""
        mock_auth_resp = {
            "access_token": "mocked_jwt_token_123",
            "token_type": "bearer",
            "expires_in": 3600,
            "refresh_token": "mocked_refresh_token",
            "user": {
                "id": "11111111-1111-1111-1111-111111111111",
                "email": "user@vocall.ai",
                "user_metadata": {"org_id": "22222222-2222-2222-2222-222222222222"},
            },
        }
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_auth_resp

        with patch("app.routers.auth.settings.NEXT_PUBLIC_SUPABASE_URL", "https://mock.supabase.co"), \
             patch("app.routers.auth.settings.NEXT_PUBLIC_SUPABASE_ANON_KEY", "mock-anon-key"), \
             patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            res = client.post(f"{BASE}/login", json={"email": "user@vocall.ai", "password": "password123"})
            assert res.status_code == 200
            body = res.json()
            assert body["access_token"] == "mocked_jwt_token_123"
            assert body["token_type"] == "bearer"
            assert "user" in body
            assert body["user"]["email"] == "user@vocall.ai"

    def test_login_missing_email_fails(self, client):
        """TC-AUTH-LOGIN-02: POST /auth/login without email returns 422."""
        res = client.post(f"{BASE}/login", json={"password": "pass123"})
        assert res.status_code == 422

    def test_login_missing_password_fails(self, client):
        """TC-AUTH-LOGIN-03: POST /auth/login without password returns 422."""
        res = client.post(f"{BASE}/login", json={"email": "user@vocall.ai"})
        assert res.status_code == 422

    def test_login_empty_body_fails(self, client):
        """TC-AUTH-LOGIN-04: POST /auth/login with empty body returns 422."""
        res = client.post(f"{BASE}/login", json={})
        assert res.status_code == 422


class TestAuthMe:
    """TC-AUTH-ME-*: /auth/me profile endpoint."""

    def test_me_dev_mode_returns_dev_user(self, client):
        """TC-AUTH-ME-01: In development mode without header, returns dev user."""
        res = client.get(f"{BASE}/me")
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "authenticated"
        assert body["user"]["email"] == "dev@vocall.ai"

    def test_me_with_invalid_bearer_raises_401(self, client):
        """TC-AUTH-ME-02: Invalid/garbage Bearer token returns HTTP 401 Unauthorized."""
        res = client.get(f"{BASE}/me", headers={"Authorization": "Bearer invalid_garbage_token"})
        assert res.status_code == 401
        assert "Invalid authorization token" in res.json()["detail"]

    def test_me_production_mode_no_header_raises_401(self, client):
        """TC-AUTH-ME-03: Production mode without Authorization header returns 401."""
        with patch("app.routers.auth.settings") as mock_settings:
            mock_settings.ENVIRONMENT = "production"
            res = client.get(f"{BASE}/me")
            assert res.status_code == 401
            assert "Authentication token required" in res.json()["detail"]
