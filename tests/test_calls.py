"""
test_calls.py — Tests for /api/v1/calls/* routes.

NOTE on stubs/placeholders detected:
  - webcall/sse endpoint uses `redis_client` that is NOT imported in calls.py
    (it would raise NameError at runtime).
  - LiveKit token falls back to a dev_token_ when credentials are missing.
  - WebSocket stream delegates to voice_pipeline which requires heavy deps.
"""
import pytest
from uuid import uuid4
from unittest.mock import patch, MagicMock, AsyncMock

FAKE_ORG_ID = "00000000-0000-0000-0000-000000000001"
FAKE_AGENT_ID = str(uuid4())
FAKE_CALL_ID = str(uuid4())
BASE = "/api/v1/calls"

CALL_RESPONSE = {
    "id": FAKE_CALL_ID,
    "org_id": FAKE_ORG_ID,
    "agent_id": FAKE_AGENT_ID,
    "contact_id": None,
    "direction": "inbound",
    "from_number": "+11234567890",
    "to_number": "+10987654321",
    "status": "completed",
    "duration_seconds": 60,
    "transcript": None,
    "is_test": False,
    "emotion_score": None,
    "analysis": {},
    "created_at": "2024-01-01T00:00:00",
    "updated_at": "2024-01-01T00:00:00",
}


def make_calls_supabase_mock(data=None, single=None):
    sb = MagicMock()
    data = data or []
    single = single or (data[0] if data else None)

    chain = MagicMock()
    chain.execute.return_value = MagicMock(data=data)
    chain.eq.return_value = chain
    chain.order.return_value = chain
    chain.single.return_value.execute.return_value = MagicMock(data=single)

    sb.table.return_value.select.return_value = chain
    sb.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[CALL_RESPONSE])
    sb.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[CALL_RESPONSE])
    return sb


@pytest.fixture
def client_no_db():
    with patch("app.services.supabase_client.supabase", None), \
         patch("app.routers.calls.supabase", None):
        from fastapi.testclient import TestClient
        from app.main import app
        with TestClient(app) as c:
            yield c


@pytest.fixture
def client_with_db():
    mock_sb = make_calls_supabase_mock(data=[CALL_RESPONSE], single=CALL_RESPONSE)
    with patch("app.routers.calls.supabase", mock_sb):
        from fastapi.testclient import TestClient
        from app.main import app
        with TestClient(app) as c:
            yield c


class TestListCalls:
    """TC-CALLS-LIST-*"""

    def test_list_calls_no_db_returns_empty(self, client_no_db):
        """TC-CALLS-LIST-01: No DB → returns empty list."""
        res = client_no_db.get(f"{BASE}?org_id={FAKE_ORG_ID}")
        assert res.status_code == 200
        assert res.json() == []

    def test_list_calls_requires_org_id(self, client_no_db):
        """TC-CALLS-LIST-02: Missing org_id → 422."""
        res = client_no_db.get(BASE)
        assert res.status_code == 422

    def test_list_calls_with_direction_filter(self, client_no_db):
        """TC-CALLS-LIST-03: Direction filter is accepted without error."""
        res = client_no_db.get(f"{BASE}?org_id={FAKE_ORG_ID}&direction=inbound")
        assert res.status_code == 200

    def test_list_calls_with_all_direction(self, client_no_db):
        """TC-CALLS-LIST-04: direction=all is accepted."""
        res = client_no_db.get(f"{BASE}?org_id={FAKE_ORG_ID}&direction=all")
        assert res.status_code == 200


class TestCreateCall:
    """TC-CALLS-CREATE-*"""

    def test_create_call_no_db_raises_500(self, client_no_db):
        """TC-CALLS-CREATE-01: No DB → 500."""
        res = client_no_db.post(BASE, json={
            "org_id": FAKE_ORG_ID,
            "agent_id": FAKE_AGENT_ID,
            "direction": "inbound",
            "from_number": "+11234567890",
            "to_number": "+10987654321",
        })
        assert res.status_code == 500

    def test_create_call_with_db(self, client_with_db):
        """TC-CALLS-CREATE-02: With DB → 201 + call data."""
        res = client_with_db.post(BASE, json={
            "org_id": FAKE_ORG_ID,
            "agent_id": FAKE_AGENT_ID,
            "direction": "inbound",
            "from_number": "+11234567890",
            "to_number": "+10987654321",
        })
        assert res.status_code == 201

    def test_create_call_missing_org_id(self, client_no_db):
        """TC-CALLS-CREATE-03: Missing org_id → 422."""
        res = client_no_db.post(BASE, json={"direction": "inbound"})
        assert res.status_code == 422


class TestGetCall:
    """TC-CALLS-GET-*"""

    def test_get_call_no_db_raises_500(self, client_no_db):
        """TC-CALLS-GET-01: No DB → 500."""
        res = client_no_db.get(f"{BASE}/{FAKE_CALL_ID}")
        assert res.status_code == 500

    def test_get_call_with_db(self, client_with_db):
        """TC-CALLS-GET-02: With DB → 200 + call data."""
        res = client_with_db.get(f"{BASE}/{FAKE_CALL_ID}")
        assert res.status_code == 200

    def test_get_call_invalid_uuid(self, client_no_db):
        """TC-CALLS-GET-03: Invalid UUID → 422."""
        res = client_no_db.get(f"{BASE}/not-a-uuid")
        assert res.status_code == 422


class TestLiveKitToken:
    """TC-CALLS-TOKEN-*"""

    def test_token_no_credentials_returns_dev_token(self, client_no_db):
        """
        TC-CALLS-TOKEN-01: Without LiveKit credentials, returns a dev_token_ placeholder.
        This is acceptable for dev but must be gated in production.
        """
        with patch("app.routers.calls.settings") as mock_s:
            mock_s.LIVEKIT_API_KEY = ""
            mock_s.LIVEKIT_API_SECRET = ""
            mock_s.LIVEKIT_URL = ""
            res = client_no_db.post(f"{BASE}/token", json={
                "room_name": "test-room",
                "participant_name": "tester",
            })
        assert res.status_code == 200
        body = res.json()
        assert body["token"].startswith("dev_token_")
        assert body["room_name"] == "test-room"

    def test_token_missing_room_name_returns_422(self, client_no_db):
        """TC-CALLS-TOKEN-02: Missing room_name → 422."""
        res = client_no_db.post(f"{BASE}/token", json={"participant_name": "tester"})
        assert res.status_code == 422

    def test_token_missing_participant_returns_422(self, client_no_db):
        """TC-CALLS-TOKEN-03: Missing participant_name → 422."""
        res = client_no_db.post(f"{BASE}/token", json={"room_name": "test-room"})
        assert res.status_code == 422


class TestWebcallSSERedisImport:
    """TC-CALLS-SSE-* — Redis import resolution verification."""

    def test_webcall_sse_redis_import_present(self, client_no_db):
        """
        TC-CALLS-SSE-01: Verify `redis_client` is imported in app.routers.calls
        so webcall SSE generator does not raise NameError at runtime.
        """
        import app.routers.calls as calls_module
        assert hasattr(calls_module, "redis_client"), (
            "redis_client must be imported in app/routers/calls.py"
        )


class TestOutboundCall:
    """TC-CALLS-OUTBOUND-*"""

    def test_outbound_missing_to_number_returns_400(self, client_no_db):
        """TC-CALLS-OUTBOUND-01: Missing to_number → 400."""
        res = client_no_db.post(f"{BASE}/outbound", json={
            "org_id": FAKE_ORG_ID,
            "agent_id": FAKE_AGENT_ID,
            "from_number": "+11234567890",
        })
        assert res.status_code == 400

    def test_outbound_missing_from_number_returns_400(self, client_no_db):
        """TC-CALLS-OUTBOUND-02: Missing from_number → 400."""
        res = client_no_db.post(f"{BASE}/outbound", json={
            "org_id": FAKE_ORG_ID,
            "agent_id": FAKE_AGENT_ID,
            "to_number": "+10987654321",
        })
        assert res.status_code == 400

    def test_outbound_missing_agent_id_returns_400(self, client_no_db):
        """TC-CALLS-OUTBOUND-03: Missing agent_id → 400."""
        res = client_no_db.post(f"{BASE}/outbound", json={
            "org_id": FAKE_ORG_ID,
            "to_number": "+10987654321",
            "from_number": "+11234567890",
        })
        assert res.status_code == 400

    def test_outbound_twilio_not_configured_raises_503(self, client_no_db):
        """TC-CALLS-OUTBOUND-04: No Twilio credentials → 503."""
        with patch("app.routers.calls.telephony_service") as mock_tel:
            mock_tel.initiate_outbound_call = AsyncMock(
                side_effect=RuntimeError("Twilio credentials not configured.")
            )
            res = client_no_db.post(f"{BASE}/outbound", json={
                "org_id": FAKE_ORG_ID,
                "agent_id": FAKE_AGENT_ID,
                "to_number": "+10987654321",
                "from_number": "+11234567890",
            })
        assert res.status_code == 503
