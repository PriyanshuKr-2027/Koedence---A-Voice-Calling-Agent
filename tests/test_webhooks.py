"""
test_webhooks.py — Tests for /api/v1/webhooks/* endpoints.
"""
import pytest
from unittest.mock import patch, MagicMock

BASE = "/api/v1/webhooks"


@pytest.fixture
def client():
    with patch("app.services.supabase_client.supabase", None):
        from fastapi.testclient import TestClient
        from app.main import app
        with TestClient(app) as c:
            yield c


class TestTwilioInboundWebhook:
    """TC-WEBHOOKS-TWILIO-INBOUND-*"""

    def test_twilio_inbound_dev_mode_returns_twiml(self, client):
        """TC-WEBHOOKS-TWILIO-01: Inbound call without auth token skips signature check and returns TwiML."""
        with patch("app.routers.webhooks.settings") as mock_settings:
            mock_settings.TWILIO_AUTH_TOKEN = ""
            mock_settings.BACKEND_PUBLIC_URL = "https://test.vocall.ai"

            res = client.post(
                f"{BASE}/twilio/inbound",
                data={"CallSid": "CA12345", "From": "+19876543210", "To": "+11234567890"}
            )
            assert res.status_code == 200
            assert "text/xml" in res.headers["content-type"]
            assert "<Response>" in res.text
            assert "<Stream url=" in res.text

    def test_livekit_events_room_finished(self, client):
        """TC-WEBHOOKS-LIVEKIT-01: LiveKit room_finished event processed without error."""
        res = client.post(
            f"{BASE}/livekit/events",
            json={"event": "room_finished", "room": {"name": "call-12345"}}
        )
        assert res.status_code == 200
        assert res.json()["status"] == "received"
