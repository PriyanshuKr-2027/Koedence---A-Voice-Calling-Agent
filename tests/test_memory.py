"""
test_memory.py — Tests for /api/v1/memory/* routes.
"""
import pytest
from uuid import uuid4
from unittest.mock import patch, AsyncMock

BASE = "/api/v1/memory"
FAKE_CONTACT_ID = str(uuid4())
FAKE_ORG_ID = str(uuid4())
FAKE_AGENT_ID = str(uuid4())


@pytest.fixture
def client():
    with patch("app.services.supabase_client.supabase", None):
        from fastapi.testclient import TestClient
        from app.main import app
        with TestClient(app) as c:
            yield c


class TestMemoryEndpoints:
    """TC-MEMORY-*: Memory routes testing."""

    def test_get_long_term_memory_returns_200(self, client):
        """TC-MEMORY-01: GET /memory/long-term returns 200 with facts list."""
        with patch("app.services.memory.long_term.retrieve_relevant_facts", new_callable=AsyncMock) as mock_retrieve:
            mock_retrieve.return_value = [{"content": "Customer prefers Hinglish", "similarity": 0.95}]
            res = client.get(f"{BASE}/long-term?contact_id={FAKE_CONTACT_ID}&org_id={FAKE_ORG_ID}")
            assert res.status_code == 200
            body = res.json()
            assert body["contact_id"] == FAKE_CONTACT_ID
            assert body["org_id"] == FAKE_ORG_ID
            assert len(body["facts"]) == 1
            assert body["facts"][0]["content"] == "Customer prefers Hinglish"

    def test_post_long_term_memory_returns_201(self, client):
        """TC-MEMORY-02: POST /memory/long-term creates persistent long-term fact."""
        fake_result = {
            "id": str(uuid4()),
            "contact_id": FAKE_CONTACT_ID,
            "org_id": FAKE_ORG_ID,
            "content": "Prefers email notifications",
        }
        with patch("app.services.memory.long_term.store_fact", new_callable=AsyncMock) as mock_store:
            mock_store.return_value = fake_result
            res = client.post(
                f"{BASE}/long-term",
                json={
                    "contact_id": FAKE_CONTACT_ID,
                    "org_id": FAKE_ORG_ID,
                    "agent_id": FAKE_AGENT_ID,
                    "content": "Prefers email notifications",
                },
            )
            assert res.status_code == 201
            body = res.json()
            assert body["content"] == "Prefers email notifications"

    def test_get_episodic_memory_returns_200(self, client):
        """TC-MEMORY-03: GET /memory/episodic returns recent call summaries."""
        with patch("app.services.memory.episodic.get_recent_episodes", new_callable=AsyncMock) as mock_get_ep:
            mock_get_ep.return_value = [{"id": "ep-1", "summary": "Discussed plan upgrade"}]
            res = client.get(f"{BASE}/episodic?contact_id={FAKE_CONTACT_ID}&org_id={FAKE_ORG_ID}")
            assert res.status_code == 200
            body = res.json()
            assert len(body["episodes"]) == 1
            assert body["episodes"][0]["summary"] == "Discussed plan upgrade"
