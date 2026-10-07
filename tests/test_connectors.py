"""
test_connectors.py — Tests for /api/connectors/* routes and connector dispatcher.
"""
import pytest
from uuid import uuid4
from unittest.mock import patch, AsyncMock

BASE = "/api/connectors"
FAKE_ORG_ID = "00000000-0000-0000-0000-000000000001"
FAKE_AGENT_ID = str(uuid4())


@pytest.fixture
def client_no_db():
    with patch("app.services.supabase_client.supabase", None), \
         patch("app.services.supabase_client.get_supabase_client", return_value=None), \
         patch("app.routers.connectors._safe_get_supabase_client", return_value=None):
        from fastapi.testclient import TestClient
        from app.main import app
        with TestClient(app) as c:
            yield c


class TestConnectorsRouter:
    """TC-CONNECTORS-*"""

    def test_list_connectors_no_db_returns_empty(self, client_no_db):
        """TC-CONNECTORS-LIST-01: GET /api/connectors with no DB returns empty list."""
        res = client_no_db.get(BASE)
        assert res.status_code == 200
        assert res.json() == []

    def test_get_connector_not_found_returns_404(self, client_no_db):
        """TC-CONNECTORS-GET-01: GET /api/connectors/{type} without DB returns 500 or 404."""
        res = client_no_db.get(f"{BASE}/google_calendar")
        assert res.status_code in (404, 500)

    def test_test_connector_unknown_type(self, client_no_db):
        """TC-CONNECTORS-TEST-01: POST /api/connectors/unknown_type/test returns success=False."""
        res = client_no_db.post(f"{BASE}/unknown_type/test")
        assert res.status_code == 200
        body = res.json()
        assert body["success"] is False
        assert "Unknown connector type" in body["error"]


class TestConnectorDispatcher:
    """TC-DISPATCHER-* — Tests for fire_connector dispatcher."""

    @pytest.mark.asyncio
    async def test_dispatch_slack_connector(self):
        """TC-DISPATCHER-SLACK-01: Slack connector dispatch calls send_call_summary."""
        from app.services.connectors.dispatcher import fire_connector

        with patch("app.services.connectors.slack.send_call_summary", new_callable=AsyncMock) as mock_slack:
            mock_slack.return_value = {"success": True, "ts": "12345.678"}
            result = await fire_connector(
                connector_type="slack",
                config={"bot_token": "xoxb-test", "channel_id": "C12345"},
                payload={"agent_name": "Sales Bot", "call_summary": "Successful demo call"},
            )
            assert result["success"] is True
            mock_slack.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatch_hubspot_connector(self):
        """TC-DISPATCHER-HUBSPOT-01: HubSpot connector dispatch calls log_lead."""
        from app.services.connectors.dispatcher import fire_connector

        with patch("app.services.connectors.hubspot.log_lead", new_callable=AsyncMock) as mock_hs:
            mock_hs.return_value = {"success": True, "lead_id": "999"}
            result = await fire_connector(
                connector_type="hubspot",
                config={"access_token": "pat-test", "pipeline_id": "1"},
                payload={"contact_name": "Lead User", "contact_phone": "+123456"},
            )
            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_dispatch_unknown_type(self):
        """TC-DISPATCHER-UNKNOWN-01: Unknown connector type returns success=False."""
        from app.services.connectors.dispatcher import fire_connector

        result = await fire_connector("non_existent_type", {}, {})
        assert result["success"] is False
        assert "Unknown" in result["error"]
