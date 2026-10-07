"""
tests/test_unforgeable_auth.py — Tests for unforgeable JWT authentication,
tenant isolation, dev auth gating, and HMAC call stream WebSocket tokens.
"""
import os
import time
from uuid import uuid4
from unittest.mock import MagicMock, patch
import jwt
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, settings
from app.core.tokens import generate_call_stream_token, verify_call_stream_token
from app.main import app

TEST_JWT_SECRET = "test-supabase-jwt-secret-key-32-bytes-long!"
ORG_A = "11111111-1111-1111-1111-111111111111"
ORG_B = "22222222-2222-2222-2222-222222222222"
USER_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def create_token(payload: dict, secret: str = TEST_JWT_SECRET, algorithm: str = "HS256") -> str:
    default_payload = {
        "sub": USER_A,
        "aud": "authenticated",
        "exp": int(time.time()) + 3600,
    }
    default_payload.update(payload)
    return jwt.encode(default_payload, secret, algorithm=algorithm)


@pytest.fixture
def auth_client():
    with patch.object(settings, "SUPABASE_JWT_SECRET", TEST_JWT_SECRET), \
         patch.object(settings, "ALLOW_DEV_AUTH", False), \
         patch.object(settings, "ENVIRONMENT", "development"):
        with TestClient(app) as c:
            yield c


class TestJWTVerification:
    """Tests verifying signature, expiration, and audience requirements."""

    def test_unsigned_jwt_returns_401(self, auth_client):
        """Unsigned JWT (none algorithm or forged token) returns 401."""
        unsigned = jwt.encode(
            {"sub": USER_A, "aud": "authenticated", "exp": int(time.time()) + 3600, "org_id": ORG_A},
            key="",
            algorithm="none",
        )
        res = auth_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {unsigned}"})
        assert res.status_code == 401

    def test_jwt_signed_with_wrong_key_returns_401(self, auth_client):
        """JWT signed with an untrusted or incorrect secret returns 401."""
        forged = create_token({"org_id": ORG_A}, secret="wrong-secret-key-attacker")
        res = auth_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {forged}"})
        assert res.status_code == 401
        assert "signature" in res.json()["detail"].lower()

    def test_expired_token_returns_401(self, auth_client):
        """Expired JWT returns 401."""
        expired = create_token({"org_id": ORG_A, "exp": int(time.time()) - 120})
        res = auth_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired}"})
        assert res.status_code == 401
        assert "expired" in res.json()["detail"].lower()

    def test_invalid_audience_returns_401(self, auth_client):
        """JWT with invalid audience returns 401."""
        bad_aud = create_token({"org_id": ORG_A, "aud": "wrong-audience"})
        res = auth_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {bad_aud}"})
        assert res.status_code == 401
        assert "audience" in res.json()["detail"].lower()

    def test_missing_org_returns_403(self, auth_client):
        """Valid JWT without an org claim and no profile row returns 403 Forbidden."""
        no_org = create_token({})
        with patch("app.services.supabase_client.supabase", None):
            res = auth_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {no_org}"})
            assert res.status_code == 403
            assert "organization" in res.json()["detail"].lower()


class TestTenantIsolation:
    """Tests ensuring Org A cannot read or delete Org B's resources."""

    @pytest.fixture
    def mock_supabase_org_b(self):
        sb = MagicMock()
        agent_row = {"id": str(uuid4()), "org_id": ORG_B, "name": "Org B Agent"}
        call_row = {"id": str(uuid4()), "org_id": ORG_B, "status": "completed"}
        contact_row = {"id": str(uuid4()), "org_id": ORG_B, "name": "Org B Contact"}
        api_key_row = {"id": str(uuid4()), "org_id": ORG_B, "key": "secret"}

        def table_mock(tbl):
            m = MagicMock()
            row_map = {
                "agents": agent_row,
                "calls": call_row,
                "contacts": contact_row,
                "api_keys": api_key_row,
            }
            row = row_map.get(tbl, {"id": str(uuid4()), "org_id": ORG_B})

            chain = MagicMock()
            chain.execute.return_value = MagicMock(data=[row])
            chain.eq.return_value = chain
            chain.single.return_value.execute.return_value = MagicMock(data=row)
            m.select.return_value = chain
            m.delete.return_value = chain
            return m

        sb.table.side_effect = table_mock
        return sb, agent_row, call_row, contact_row, api_key_row

    def test_org_a_cannot_read_or_delete_org_b_agents(self, auth_client, mock_supabase_org_b):
        sb, agent_row, _, _, _ = mock_supabase_org_b
        token_a = create_token({"org_id": ORG_A})
        headers = {"Authorization": f"Bearer {token_a}"}

        with patch("app.services.supabase_client.supabase", sb), \
             patch("app.routers.agents.supabase", sb):
            # GET Org B agent with Org A token
            get_res = auth_client.get(f"/api/v1/agents/{agent_row['id']}", headers=headers)
            assert get_res.status_code == 403

            # DELETE Org B agent with Org A token
            del_res = auth_client.delete(f"/api/v1/agents/{agent_row['id']}", headers=headers)
            assert del_res.status_code == 403

    def test_org_a_cannot_read_org_b_calls(self, auth_client, mock_supabase_org_b):
        sb, _, call_row, _, _ = mock_supabase_org_b
        token_a = create_token({"org_id": ORG_A})
        headers = {"Authorization": f"Bearer {token_a}"}

        with patch("app.services.supabase_client.supabase", sb), \
             patch("app.routers.calls.supabase", sb):
            get_res = auth_client.get(f"/api/v1/calls/{call_row['id']}", headers=headers)
            assert get_res.status_code == 403

    def test_org_a_cannot_read_or_delete_org_b_contacts(self, auth_client, mock_supabase_org_b):
        sb, _, _, contact_row, _ = mock_supabase_org_b
        token_a = create_token({"org_id": ORG_A})
        headers = {"Authorization": f"Bearer {token_a}"}

        with patch("app.services.supabase_client.supabase", sb), \
             patch("app.routers.contacts.supabase", sb):
            get_res = auth_client.get(f"/api/v1/contacts/{contact_row['id']}", headers=headers)
            assert get_res.status_code == 403

            del_res = auth_client.delete(f"/api/v1/contacts/{contact_row['id']}", headers=headers)
            assert del_res.status_code == 403

    def test_org_a_cannot_delete_org_b_api_keys(self, auth_client, mock_supabase_org_b):
        sb, _, _, _, api_key_row = mock_supabase_org_b
        token_a = create_token({"org_id": ORG_A})
        headers = {"Authorization": f"Bearer {token_a}"}

        with patch("app.services.supabase_client.supabase", sb), \
             patch("app.routers.api_keys.supabase", sb):
            del_res = auth_client.delete(f"/api/v1/api-keys/{api_key_row['id']}", headers=headers)
            assert del_res.status_code == 403

    def test_org_a_cannot_read_org_b_memory(self, auth_client, mock_supabase_org_b):
        sb, _, _, contact_row, _ = mock_supabase_org_b
        token_a = create_token({"org_id": ORG_A})
        headers = {"Authorization": f"Bearer {token_a}"}

        with patch("app.services.supabase_client.supabase", sb):
            res_lt = auth_client.get(f"/api/v1/memory/long-term?contact_id={contact_row['id']}", headers=headers)
            assert res_lt.status_code == 403

            res_ep = auth_client.get(f"/api/v1/memory/episodic?contact_id={contact_row['id']}", headers=headers)
            assert res_ep.status_code == 403


class TestDevAuthAndStartup:
    """Tests production refusal and dev auth gating."""

    def test_production_plus_allow_dev_auth_refuses_to_start(self):
        """Settings refuses initialization when ENVIRONMENT=production and ALLOW_DEV_AUTH=True."""
        with pytest.raises(RuntimeError, match="ALLOW_DEV_AUTH cannot be enabled"):
            Settings(ENVIRONMENT="production", ALLOW_DEV_AUTH=True)

    @pytest.mark.asyncio
    async def test_main_startup_refuses_production_allow_dev_auth(self):
        """Main FastAPI startup event refuses to run in production with ALLOW_DEV_AUTH=True."""
        from app.main import startup_event
        with patch.object(settings, "ENVIRONMENT", "production"), \
             patch.object(settings, "ALLOW_DEV_AUTH", True):
            with pytest.raises(RuntimeError, match="ALLOW_DEV_AUTH cannot be enabled"):
                await startup_event()


class TestWebSocketStreamToken:
    """Tests HMAC token verification on /calls/stream/{call_id} WebSocket."""

    def test_websocket_without_token_is_closed(self, auth_client):
        """Connecting to /stream/{call_id} without a token closes the socket."""
        call_id = str(uuid4())
        with pytest.raises(Exception):
            with auth_client.websocket_connect(f"/api/v1/calls/stream/{call_id}") as ws:
                pass

    def test_websocket_with_invalid_token_is_closed(self, auth_client):
        """Connecting with a tampered token closes the socket."""
        call_id = str(uuid4())
        with pytest.raises(Exception):
            with auth_client.websocket_connect(f"/api/v1/calls/stream/{call_id}?token=bad-token&exp=9999999999") as ws:
                pass

    def test_websocket_with_valid_token_is_accepted(self, auth_client):
        """Connecting with a valid HMAC token allows connection."""
        call_id = str(uuid4())
        token, exp = generate_call_stream_token(call_id, ttl_seconds=300)
        assert verify_call_stream_token(call_id, token, exp) is True

        with patch("app.services.voice_pipeline.start_pipeline") as mock_pipeline:
            # We don't need the actual voice pipeline to block
            async def dummy_pipeline(*args, **kwargs):
                return
            mock_pipeline.side_effect = dummy_pipeline

            with auth_client.websocket_connect(f"/api/v1/calls/stream/{call_id}?token={token}&exp={exp}") as ws:
                # Connection was accepted cleanly
                assert ws is not None
