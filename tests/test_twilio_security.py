"""
tests/test_twilio_security.py — Tests for Twilio webhook signature validation,
proxy URL reconstruction, and production startup enforcement.

Covers:
1. Valid Twilio signature is accepted.
2. Wrong/invalid Twilio signature is rejected (HTTP 403).
3. Proxy scenario: signature computed against forwarded proto/host validates properly.
4. Production without TWILIO_AUTH_TOKEN fails at startup (refuses to start).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient
from twilio.request_validator import RequestValidator

from app.core.config import Settings, settings
from app.main import app, startup_event


AUTH_TOKEN = "test-twilio-auth-token-12345"
PUBLIC_URL = "https://api.vocall.ai"


@pytest.fixture
def webhook_client():
    with patch("app.services.supabase_client.supabase", None):
        with TestClient(app) as client:
            yield client


# ---------------------------------------------------------------------------
# 1. Valid signature accepted
# ---------------------------------------------------------------------------

def test_valid_signature_accepted(webhook_client):
    """A webhook request with a valid Twilio HMAC-SHA1 signature is accepted."""
    endpoint_path = "/api/v1/webhooks/twilio/inbound"
    form_data = {
        "CallSid": "CA1234567890abcdef",
        "From": "+919876543210",
        "To": "+911234567890",
    }

    validation_url = f"{PUBLIC_URL}{endpoint_path}"
    validator = RequestValidator(AUTH_TOKEN)
    valid_signature = validator.compute_signature(validation_url, form_data)

    with patch.object(settings, "TWILIO_AUTH_TOKEN", AUTH_TOKEN), \
         patch.object(settings, "BACKEND_PUBLIC_URL", PUBLIC_URL), \
         patch.object(settings, "ENVIRONMENT", "production"):

        response = webhook_client.post(
            endpoint_path,
            data=form_data,
            headers={"X-Twilio-Signature": valid_signature},
        )

        assert response.status_code == 200
        assert "text/xml" in response.headers["content-type"]
        assert "<Response>" in response.text


# ---------------------------------------------------------------------------
# 2. Wrong signature rejected
# ---------------------------------------------------------------------------

def test_wrong_signature_rejected(webhook_client):
    """A webhook request with an invalid/forged signature is rejected with 403 Forbidden."""
    endpoint_path = "/api/v1/webhooks/twilio/inbound"
    form_data = {
        "CallSid": "CA1234567890abcdef",
        "From": "+919876543210",
        "To": "+911234567890",
    }

    with patch.object(settings, "TWILIO_AUTH_TOKEN", AUTH_TOKEN), \
         patch.object(settings, "BACKEND_PUBLIC_URL", PUBLIC_URL), \
         patch.object(settings, "ENVIRONMENT", "production"):

        response = webhook_client.post(
            endpoint_path,
            data=form_data,
            headers={"X-Twilio-Signature": "invalid-forged-signature-string"},
        )

        assert response.status_code == 403
        assert "Invalid Twilio signature" in response.text


# ---------------------------------------------------------------------------
# 3. Proxy case validates
# ---------------------------------------------------------------------------

def test_proxy_case_validates(webhook_client):
    """
    When behind a reverse proxy (e.g. Cloudflare / ngrok / Load Balancer),
    the validation URL is reconstructed using X-Forwarded-Proto and Host headers,
    and correctly validates the Twilio signature.
    """
    endpoint_path = "/api/v1/webhooks/twilio/inbound"
    proxy_host = "voice-gateway.vocall.internal"
    proxy_proto = "https"
    proxy_url = f"{proxy_proto}://{proxy_host}{endpoint_path}"

    form_data = {
        "CallSid": "CA_PROXY_CALL_999",
        "From": "+15551234567",
        "To": "+15557654321",
    }

    validator = RequestValidator(AUTH_TOKEN)
    proxy_signature = validator.compute_signature(proxy_url, form_data)

    with patch.object(settings, "TWILIO_AUTH_TOKEN", AUTH_TOKEN), \
         patch.object(settings, "BACKEND_PUBLIC_URL", "http://localhost:8000"), \
         patch.object(settings, "ENVIRONMENT", "production"):

        response = webhook_client.post(
            endpoint_path,
            data=form_data,
            headers={
                "X-Twilio-Signature": proxy_signature,
                "X-Forwarded-Proto": proxy_proto,
                "Host": proxy_host,
            },
        )

        assert response.status_code == 200
        assert "<Response>" in response.text


# ---------------------------------------------------------------------------
# 4. Production without token fails at startup
# ---------------------------------------------------------------------------

def test_production_without_token_fails_in_settings():
    """Settings model refuses initialization when ENVIRONMENT=production and TWILIO_AUTH_TOKEN is unset."""
    with pytest.raises(RuntimeError, match="TWILIO_AUTH_TOKEN must be set when ENVIRONMENT=production"):
        Settings(
            ENVIRONMENT="production",
            TWILIO_AUTH_TOKEN="",
            ALLOW_DEV_AUTH=False,
        )


@pytest.mark.asyncio
async def test_production_without_token_fails_at_fastapi_startup():
    """FastAPI startup_event refuses to start when ENVIRONMENT=production and TWILIO_AUTH_TOKEN is unset."""
    with patch.object(settings, "ENVIRONMENT", "production"), \
         patch.object(settings, "TWILIO_AUTH_TOKEN", ""), \
         patch.object(settings, "ALLOW_DEV_AUTH", False):

        with pytest.raises(RuntimeError, match="TWILIO_AUTH_TOKEN must be set when ENVIRONMENT=production"):
            await startup_event()
