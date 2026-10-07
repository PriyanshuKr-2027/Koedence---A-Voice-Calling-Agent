"""
test_contacts.py — Tests for /api/v1/contacts/* routes.
"""
import pytest
from uuid import uuid4
from unittest.mock import patch

# Shared Supabase mock factory — previously duplicated in each test module.
# Centralised in tests/fixtures/supabase_mocks.py to eliminate phantom graph
# edges detected by the Graphify knowledge-graph audit (betweenness 0.033).
from tests.fixtures.supabase_mocks import make_supabase_mock

FAKE_ORG_ID = "00000000-0000-0000-0000-000000000001"
FAKE_CONTACT_ID = str(uuid4())
BASE = "/api/v1/contacts"

CONTACT_RESPONSE = {
    "id": FAKE_CONTACT_ID,
    "org_id": FAKE_ORG_ID,
    "name": "John Doe",
    "phone": "+919876543210",
    "email": "john@example.com",
    "tags": ["vip"],
    "created_at": "2024-01-01T00:00:00",
}



@pytest.fixture
def client_no_db():
    with patch("app.services.supabase_client.supabase", None), \
         patch("app.routers.contacts.supabase", None):
        from fastapi.testclient import TestClient
        from app.main import app
        with TestClient(app) as c:
            yield c


@pytest.fixture
def client_with_db():
    mock_sb = make_supabase_mock(table_data=[CONTACT_RESPONSE], single_row=CONTACT_RESPONSE)
    with patch("app.routers.contacts.supabase", mock_sb):
        from fastapi.testclient import TestClient
        from app.main import app
        with TestClient(app) as c:
            yield c



class TestListContacts:
    """TC-CONTACTS-LIST-*"""

    def test_list_contacts_no_db_returns_empty(self, client_no_db):
        """TC-CONTACTS-LIST-01: No DB → empty list."""
        res = client_no_db.get(f"{BASE}?org_id={FAKE_ORG_ID}")
        assert res.status_code == 200
        assert res.json() == []

    def test_list_contacts_requires_org_id(self, client_no_db):
        """TC-CONTACTS-LIST-02: Missing org_id → 422."""
        res = client_no_db.get(BASE)
        assert res.status_code == 422

    def test_list_contacts_with_db(self, client_with_db):
        """TC-CONTACTS-LIST-03: With DB → list returned."""
        res = client_with_db.get(f"{BASE}?org_id={FAKE_ORG_ID}")
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)


class TestCreateContact:
    """TC-CONTACTS-CREATE-*"""

    def test_create_contact_no_db_raises_500(self, client_no_db):
        """TC-CONTACTS-CREATE-01: No DB → 500."""
        res = client_no_db.post(BASE, json={
            "org_id": FAKE_ORG_ID,
            "name": "Jane Doe",
            "phone": "+919876543210",
        })
        assert res.status_code == 500

    def test_create_contact_missing_org_id_returns_422(self, client_no_db):
        """TC-CONTACTS-CREATE-02: Missing org_id → 422."""
        res = client_no_db.post(BASE, json={"name": "Jane Doe"})
        assert res.status_code == 422

    def test_create_contact_with_db(self, client_with_db):
        """TC-CONTACTS-CREATE-03: With DB → 201."""
        res = client_with_db.post(BASE, json={
            "org_id": FAKE_ORG_ID,
            "name": "John Doe",
            "phone": "+919876543210",
        })
        assert res.status_code == 201
        assert res.json()["name"] == "John Doe"


class TestGetContact:
    """TC-CONTACTS-GET-*"""

    def test_get_contact_no_db_raises_500(self, client_no_db):
        """TC-CONTACTS-GET-01: No DB → 500."""
        res = client_no_db.get(f"{BASE}/{FAKE_CONTACT_ID}")
        assert res.status_code == 500

    def test_get_contact_invalid_uuid(self, client_no_db):
        """TC-CONTACTS-GET-02: Invalid UUID → 422."""
        res = client_no_db.get(f"{BASE}/not-a-uuid")
        assert res.status_code == 422

    def test_get_contact_with_db(self, client_with_db):
        """TC-CONTACTS-GET-03: With DB → 200."""
        res = client_with_db.get(f"{BASE}/{FAKE_CONTACT_ID}")
        assert res.status_code == 200


class TestUpdateContact:
    """TC-CONTACTS-UPDATE-*"""

    def test_update_contact_no_db_raises_500(self, client_no_db):
        """TC-CONTACTS-UPDATE-01: No DB → 500."""
        res = client_no_db.put(f"{BASE}/{FAKE_CONTACT_ID}", json={"name": "Updated Name"})
        assert res.status_code == 500

    def test_patch_contact_no_db_raises_500(self, client_no_db):
        """TC-CONTACTS-UPDATE-02: PATCH without DB → 500."""
        res = client_no_db.patch(f"{BASE}/{FAKE_CONTACT_ID}", json={"name": "Patched Name"})
        assert res.status_code == 500


class TestDeleteContact:
    """TC-CONTACTS-DELETE-*"""

    def test_delete_contact_no_db_raises_500(self, client_no_db):
        """TC-CONTACTS-DELETE-01: No DB → 500."""
        res = client_no_db.delete(f"{BASE}/{FAKE_CONTACT_ID}")
        assert res.status_code == 500

    def test_delete_contact_invalid_uuid(self, client_no_db):
        """TC-CONTACTS-DELETE-02: Invalid UUID → 422."""
        res = client_no_db.delete(f"{BASE}/not-a-uuid")
        assert res.status_code == 422
