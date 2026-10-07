"""
test_emotion.py — Tests for /api/v1/emotion/* routes.
"""
import pytest
from uuid import uuid4
from unittest.mock import patch, AsyncMock

BASE = "/api/v1/emotion"
FAKE_CALL_ID = str(uuid4())


@pytest.fixture
def client():
    with patch("app.services.supabase_client.supabase", None):
        from fastapi.testclient import TestClient
        from app.main import app
        with TestClient(app) as c:
            yield c


class TestEmotionEndpoints:
    """TC-EMOTION-*"""

    def test_get_emotion_events_empty_redis_no_db(self, client):
        """TC-EMOTION-GET-01: Empty Redis and no Supabase returns source='none'."""
        with patch("app.services.memory.short_term.get_call_memory", new_callable=AsyncMock) as mock_mem:
            mock_mem.return_value = None
            res = client.get(f"{BASE}/events/{FAKE_CALL_ID}")
            assert res.status_code == 200
            body = res.json()
            assert body["events"] == []
            assert body["source"] == "none"

    def test_get_emotion_events_from_redis(self, client):
        """TC-EMOTION-GET-02: Returns emotion events from Redis when available."""
        fake_events = [{"timestamp_ms": 1000, "valence": 0.5, "dominant": "happy"}]
        with patch("app.services.memory.short_term.get_call_memory", new_callable=AsyncMock) as mock_mem:
            mock_mem.return_value = {"emotion_events": fake_events}
            res = client.get(f"{BASE}/events/{FAKE_CALL_ID}")
            assert res.status_code == 200
            body = res.json()
            assert body["source"] == "redis"
            assert body["events"] == fake_events

    def test_record_emotion_event_missing_call_id(self, client):
        """TC-EMOTION-RECORD-01: Missing call_id returns 400."""
        res = client.post(f"{BASE}/events", json={"valence": 0.5})
        assert res.status_code == 400
        assert "call_id is required" in res.json()["detail"]
