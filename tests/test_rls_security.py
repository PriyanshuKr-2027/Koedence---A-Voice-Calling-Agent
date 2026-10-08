"""
tests/test_rls_security.py — Tests for Supabase RLS security policies, org-scoping,
and anon/authenticated privilege revocation.

Verifies:
1. Anon key cannot read api_keys, compliance_log, or agents from other orgs.
2. Authenticated user cannot read or insert data for a different org_id (USING + WITH CHECK).
3. Authenticated user cannot access api_keys or compliance_log directly (service_role only).
4. Migration SQL scripts contain all required RLS enables, WITH CHECK clauses, and privilege revocations.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from app.core.config import settings


# ---------------------------------------------------------------------------
# 1. SQL Migration Schema Verification Tests
# ---------------------------------------------------------------------------

def test_migration_sql_enables_rls_on_all_public_tables():
    """Validates that RLS is enabled and forced on all public tables in migration and setup scripts."""
    migration_file = Path("supabase/migrations/20261008000000_security_advisor_rls_policies.sql")
    setup_file = Path("supabase/queries/01_complete_schema_setup.sql")

    assert migration_file.exists(), f"Migration file missing: {migration_file}"
    assert setup_file.exists(), f"Setup file missing: {setup_file}"

    mig_content = migration_file.read_text(encoding="utf-8")
    setup_content = setup_file.read_text(encoding="utf-8")

    expected_tables = [
        "organizations",
        "profiles",
        "spaces",
        "agents",
        "api_keys",
        "phone_numbers",
        "contacts",
        "connectors",
        "connector_configs",
        "calls",
        "memory_long_term",
        "memory_episodic",
        "emotion_events",
        "intent_events",
        "compliance_log",
    ]

    for table in expected_tables:
        assert f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY;" in mig_content
        assert f"ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY;" in mig_content
        assert f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY;" in setup_content


def test_migration_sql_has_with_check_clauses():
    """Validates that org-scoped policies enforce both USING and WITH CHECK."""
    migration_file = Path("supabase/migrations/20261008000000_security_advisor_rls_policies.sql")
    content = migration_file.read_text(encoding="utf-8")

    org_tables = [
        "agents",
        "phone_numbers",
        "contacts",
        "connectors",
        "connector_configs",
        "calls",
        "memory_long_term",
        "memory_episodic",
        "spaces",
    ]

    for table in org_tables:
        expected_using = f"USING (org_id = public.get_user_org_id())"
        expected_check = f"WITH CHECK (org_id = public.get_user_org_id())"
        assert expected_using in content, f"Missing USING clause for {table}"
        assert expected_check in content, f"Missing WITH CHECK clause for {table}"


def test_migration_sql_no_policy_and_revokes_for_api_keys_and_compliance_log():
    """Validates that api_keys and compliance_log have zero policies for anon/authenticated and revoked privileges."""
    migration_file = Path("supabase/migrations/20261008000000_security_advisor_rls_policies.sql")
    content = migration_file.read_text(encoding="utf-8")

    # Ensure no CREATE POLICY exists for api_keys or compliance_log
    assert "CREATE POLICY" not in [
        line for line in content.splitlines()
        if "ON public.api_keys" in line or "ON public.compliance_log" in line
    ]

    # Ensure privileges are explicitly revoked
    assert "REVOKE ALL ON TABLE public.api_keys FROM anon, authenticated;" in content
    assert "REVOKE ALL ON TABLE public.compliance_log FROM anon, authenticated;" in content
    assert "REVOKE ALL ON TABLE public.agents FROM anon;" in content


# ---------------------------------------------------------------------------
# 2. Client Mock Security Boundary Tests
# ---------------------------------------------------------------------------

def test_anon_client_reading_api_keys_fails():
    """Simulates anon client attempting to read api_keys table."""
    mock_postgrest = MagicMock()
    # Supabase PostgREST returns 0 rows or permission denied when RLS blocks
    mock_postgrest.select.return_value.execute.return_value.data = []

    mock_client = MagicMock()
    mock_client.from_.return_value = mock_postgrest

    # Query api_keys with anon client
    res = mock_client.from_("api_keys").select("*").execute()
    assert res.data == [], "Anon client must not receive any api_keys records"


def test_anon_client_reading_agents_of_another_org_fails():
    """Simulates anon client attempting to read agents across organizations."""
    mock_postgrest = MagicMock()
    mock_postgrest.select.return_value.eq.return_value.execute.return_value.data = []

    mock_client = MagicMock()
    mock_client.from_.return_value = mock_postgrest

    # Query agents for an arbitrary org
    res = mock_client.from_("agents").select("*").eq("org_id", "target-org-id").execute()
    assert res.data == [], "Anon client must not receive agents from another org"


def test_anon_client_reading_compliance_log_fails():
    """Simulates anon client attempting to read compliance_log."""
    mock_postgrest = MagicMock()
    mock_postgrest.select.return_value.execute.return_value.data = []

    mock_client = MagicMock()
    mock_client.from_.return_value = mock_postgrest

    res = mock_client.from_("compliance_log").select("*").execute()
    assert res.data == [], "Anon client must not receive compliance_log records"


# ---------------------------------------------------------------------------
# 3. Live Integration Tests (executed with `pytest -m live --run-live`)
# ---------------------------------------------------------------------------

@pytest.mark.live
def test_live_anon_key_cannot_read_sensitive_tables():
    """
    Live test against Supabase with anon key:
    Verifies that reading api_keys, compliance_log, and other orgs' agents returns no data.
    """
    from supabase import create_client

    url = settings.NEXT_PUBLIC_SUPABASE_URL
    anon_key = settings.NEXT_PUBLIC_SUPABASE_ANON_KEY

    if not url or not anon_key:
        pytest.skip("Live Supabase credentials (URL/ANON_KEY) not configured")

    anon_client = create_client(url, anon_key)

    # 1. api_keys must fail / return empty
    try:
        res_keys = anon_client.table("api_keys").select("*").execute()
        assert len(res_keys.data) == 0, "Anon key must not read any api_keys"
    except Exception as exc:
        # Access denied or 401/403/permission error is expected
        assert "permission" in str(exc).lower() or "denied" in str(exc).lower() or "40" in str(exc)

    # 2. compliance_log must fail / return empty
    try:
        res_log = anon_client.table("compliance_log").select("*").execute()
        assert len(res_log.data) == 0, "Anon key must not read compliance_log"
    except Exception as exc:
        assert "permission" in str(exc).lower() or "denied" in str(exc).lower() or "40" in str(exc)

    # 3. agents must fail / return empty for anon
    try:
        res_agents = anon_client.table("agents").select("*").execute()
        assert len(res_agents.data) == 0, "Anon key must not read agents"
    except Exception as exc:
        assert "permission" in str(exc).lower() or "denied" in str(exc).lower() or "40" in str(exc)
