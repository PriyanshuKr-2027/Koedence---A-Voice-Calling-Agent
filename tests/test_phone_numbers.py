"""
test_phone_numbers.py — Tests for /api/v1/phone-numbers/* routes.
"""
import pytest
from uuid import uuid4
from unittest.mock import patch

BASE = "/api/v1/phone-numbers"
FAKE_ORG_ID = "00000000-0000-0000-0000-000000000001"
FAKE_PHONE_ID = str(uuid4())


@pytest.fixture
def client_no_db():
    with patch("app.services.supabase_client.supabase", None), \
         patch("app.routers.phone_numbers.supabase", None):
        from fastapi.testclient import TestClient
        from app.main import app
        with TestClient(app) as c:
            yield c


class TestPhoneNumbersRouter:
    """TC-PHONE-*"""

    def test_list_phone_numbers_no_db_returns_empty(self, client_no_db):
        """TC-PHONE-LIST-01: No DB returns empty list."""
        res = client_no_db.get(f"{BASE}?org_id={FAKE_ORG_ID}")
        assert res.status_code == 200
        assert res.json() == []

    def test_provision_phone_number_no_db_raises_500(self, client_no_db):
        """TC-PHONE-PROVISION-01: Provisioning without DB raises 500."""
        res = client_no_db.post(BASE, json={"org_id": FAKE_ORG_ID, "number": "+12025550199"})
        assert res.status_code == 500

    def test_get_phone_number_no_db_raises_500(self, client_no_db):
        """TC-PHONE-GET-01: Get without DB raises 500."""
        res = client_no_db.get(f"{BASE}/{FAKE_PHONE_ID}")
        assert res.status_code == 500

    def test_delete_phone_number_no_db_raises_500(self, client_no_db):
        """TC-PHONE-DELETE-01: Delete without DB raises 500."""
        res = client_no_db.delete(f"{BASE}/{FAKE_PHONE_ID}")
        assert res.status_code == 500
