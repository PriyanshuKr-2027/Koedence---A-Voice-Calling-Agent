"""
test_agents.py — Tests for /api/v1/agents/* routes.

NOTE on Stubs detected:
  - POST /{agent_id}/run-analysis is explicitly commented as a stub that returns
    "stub" values. No real post-call analysis happens.
  - POST /{agent_id}/enhance-prompt falls back to template formatting when
    GROQ_API_KEY is not set (which it won't be in tests).
"""
import pytest
from uuid import uuid4
from unittest.mock import patch, MagicMock, AsyncMock


FAKE_ORG_ID = "00000000-0000-0000-0000-000000000001"
FAKE_AGENT_ID = str(uuid4())
BASE = "/api/v1/agents"

AGENT_PAYLOAD = {
    "org_id": FAKE_ORG_ID,
    "name": "Test Agent",
    "system_prompt": "You are a helpful assistant.",
    "language": "en",
    "published": False,
    "enable_memory": False,
    "enable_emotion": False,
    "config": {},
}

AGENT_RESPONSE = {
    "id": FAKE_AGENT_ID,
    "org_id": FAKE_ORG_ID,
    "name": "Test Agent",
    "system_prompt": "You are a helpful assistant.",
    "language": "en",
    "published": False,
    "enable_memory": False,
    "enable_emotion": False,
    "config": {},
    "space_id": None,
    "voice_id": None,
    "voice_provider": None,
    "created_at": "2024-01-01T00:00:00",
    "updated_at": "2024-01-01T00:00:00",
}


def make_supabase_mock(return_data=None, single_data=None):
    sb = MagicMock()
    data_list = return_data if return_data is not None else []
    single = single_data if single_data is not None else (data_list[0] if data_list else None)

    chain = MagicMock()
    chain.execute.return_value = MagicMock(data=data_list)
    chain.eq.return_value = chain
    chain.single.return_value.execute.return_value = MagicMock(data=single)
    chain.order.return_value = chain

    sb.table.return_value.select.return_value = chain
    sb.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[AGENT_RESPONSE])
    sb.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[AGENT_RESPONSE])
    sb.table.return_value.delete.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
    return sb


@pytest.fixture
def client_no_db():
    """Client with supabase=None — tests the 'no database' code paths."""
    with patch("app.services.supabase_client.supabase", None), \
         patch("app.routers.agents.supabase", None):
        from fastapi.testclient import TestClient
        from app.main import app
        with TestClient(app) as c:
            yield c


@pytest.fixture
def client_with_db():
    """Client with a mocked Supabase returning agent data."""
    mock_sb = make_supabase_mock(return_data=[AGENT_RESPONSE], single_data=AGENT_RESPONSE)
    with patch("app.routers.agents.supabase", mock_sb):
        from fastapi.testclient import TestClient
        from app.main import app
        with TestClient(app) as c:
            yield c


class TestListAgents:
    """TC-AGENTS-LIST-*"""

    def test_list_agents_no_supabase_returns_empty(self, client_no_db):
        """TC-AGENTS-LIST-01: GET /agents with no DB returns empty list, not 500."""
        res = client_no_db.get(f"{BASE}?org_id={FAKE_ORG_ID}")
        assert res.status_code == 200
        assert res.json() == []

    def test_list_agents_requires_org_id(self, client_no_db):
        """TC-AGENTS-LIST-02: GET /agents without org_id returns 422."""
        res = client_no_db.get(BASE)
        assert res.status_code == 422

    def test_list_agents_with_db_returns_list(self, client_with_db):
        """TC-AGENTS-LIST-03: GET /agents with DB returns list of agents."""
        res = client_with_db.get(f"{BASE}?org_id={FAKE_ORG_ID}")
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)


class TestCreateAgent:
    """TC-AGENTS-CREATE-*"""

    def test_create_agent_no_db_raises_500(self, client_no_db):
        """TC-AGENTS-CREATE-01: POST /agents without DB returns 500."""
        res = client_no_db.post(BASE, json=AGENT_PAYLOAD)
        assert res.status_code == 500
        assert "unavailable" in res.json()["detail"].lower()

    def test_create_agent_missing_required_fields(self, client_no_db):
        """TC-AGENTS-CREATE-02: POST /agents without required name/org_id returns 422."""
        res = client_no_db.post(BASE, json={"system_prompt": "hello"})
        assert res.status_code == 422

    def test_create_agent_with_db(self, client_with_db):
        """TC-AGENTS-CREATE-03: POST /agents with mocked DB returns 201 + agent data."""
        res = client_with_db.post(BASE, json=AGENT_PAYLOAD)
        assert res.status_code == 201
        body = res.json()
        assert body["name"] == "Test Agent"
        assert "id" in body


class TestGetAgent:
    """TC-AGENTS-GET-*"""

    def test_get_agent_no_db_raises_500(self, client_no_db):
        """TC-AGENTS-GET-01: GET /agents/{id} without DB returns 500."""
        res = client_no_db.get(f"{BASE}/{FAKE_AGENT_ID}")
        assert res.status_code == 500

    def test_get_agent_with_db(self, client_with_db):
        """TC-AGENTS-GET-02: GET /agents/{id} with mocked DB returns agent."""
        res = client_with_db.get(f"{BASE}/{FAKE_AGENT_ID}")
        assert res.status_code == 200
        assert res.json()["id"] == FAKE_AGENT_ID

    def test_get_agent_invalid_uuid(self, client_no_db):
        """TC-AGENTS-GET-03: GET /agents/invalid-uuid returns 422."""
        res = client_no_db.get(f"{BASE}/not-a-uuid")
        assert res.status_code == 422


class TestEnhancePrompt:
    """TC-AGENTS-ENHANCE-*"""

    def test_enhance_prompt_empty_string_returns_400(self, client_no_db):
        """TC-AGENTS-ENHANCE-01: Empty system prompt returns 400."""
        res = client_no_db.post(
            f"{BASE}/{FAKE_AGENT_ID}/enhance-prompt",
            json={"system_prompt": "   "}
        )
        assert res.status_code == 400
        assert "empty" in res.json()["detail"].lower()

    def test_enhance_prompt_no_groq_returns_fallback(self, client_no_db):
        """
        TC-AGENTS-ENHANCE-02: Without GROQ_API_KEY, enhance-prompt returns a
        template-formatted fallback (not a real AI enhancement).
        This is graceful degradation but should be flagged for production readiness.
        """
        with patch("app.routers.agents.settings") as mock_settings:
            mock_settings.GROQ_API_KEY = ""  # Simulate no API key
            res = client_no_db.post(
                f"{BASE}/{FAKE_AGENT_ID}/enhance-prompt",
                json={"system_prompt": "You are a sales agent."}
            )
        assert res.status_code == 200
        body = res.json()
        assert "enhanced_prompt" in body
        assert len(body["enhanced_prompt"]) > 0

    def test_enhance_prompt_missing_body_returns_422(self, client_no_db):
        """TC-AGENTS-ENHANCE-03: enhance-prompt with no body returns 422."""
        res = client_no_db.post(f"{BASE}/{FAKE_AGENT_ID}/enhance-prompt", json={})
        assert res.status_code == 422


class TestRunAnalysis:
    """TC-AGENTS-ANALYSIS-* — Real analysis execution."""

    def test_run_analysis_returns_analysis_results(self, client_no_db):
        """
        TC-AGENTS-ANALYSIS-01: POST /{agent_id}/run-analysis executes analysis
        and returns structured call summary & resolution status.
        """
        with patch("trigger.post_call_pipeline.llm_service.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = '''{
                "summary": "Customer inquired about voice agent capabilities.",
                "sentiment": "Positive",
                "action_items": [],
                "user_intent": "Inquiry",
                "resolution_status": "resolved"
            }'''
            res = client_no_db.post(f"{BASE}/{FAKE_AGENT_ID}/run-analysis")
            assert res.status_code == 200
            body = res.json()
            assert "summary" in body
            assert body["summary"] != "stub"
            assert "success_eval" in body
            assert body["success_eval"] != "stub"
            assert "structured_data" in body


class TestPublishAgent:
    """TC-AGENTS-PUBLISH-*"""

    def test_publish_agent_no_db_raises_500(self, client_no_db):
        """TC-AGENTS-PUBLISH-01: Publish without DB raises 500."""
        res = client_no_db.post(f"{BASE}/{FAKE_AGENT_ID}/publish")
        assert res.status_code == 500
