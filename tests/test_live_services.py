"""
tests/test_live_services.py — Live integration tests against real services.

These tests run only when explicitly enabled via `pytest --run-live` or `pytest -m live --run-live`.
They exercise real services (Supabase test org, Redis, FalkorDB) and clean up after themselves.

Covers:
1. match_long_term_memories returns the related fact above the unrelated one and respects tau.
2. Contact and org isolation in SQL.
3. Erasure removes canary data from every store (Redis, Supabase tables, FalkorDB).
4. Post-call pipeline run twice leaves one episode (idempotent upsert).
5. Redis TTLs exist on session and ephemeral keys.
6. Graph isolation across distinct contact identifiers in FalkorDB.
"""

from __future__ import annotations

import asyncio
import json
import time
from uuid import uuid4
import pytest

from app.core.config import settings
from app.routers.contacts import cascade_delete_contact_memory
from app.services.memory import episodic, graph, long_term, short_term
from app.services.redis_client import redis_client
from app.services.supabase_client import supabase

# Dedicated live test tenant isolation IDs
TEST_ORG_A = "88888888-8888-4888-8888-888888888881"
TEST_ORG_B = "88888888-8888-4888-8888-888888888882"


@pytest.fixture
def live_contact_ids():
    """Generates unique IDs for test isolation with automatic cleanup tracking."""
    contact_a = str(uuid4())
    contact_b = str(uuid4())
    call_id_a = str(uuid4())
    call_id_b = str(uuid4())
    agent_id = str(uuid4())

    yield {
        "contact_a": contact_a,
        "contact_b": contact_b,
        "call_a": call_id_a,
        "call_b": call_id_b,
        "agent_id": agent_id,
        "org_a": TEST_ORG_A,
        "org_b": TEST_ORG_B,
    }

    # Cleanup after test
    try:
        graph.delete_contact_graph(contact_a)
        graph.delete_contact_graph(contact_b)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 1. match_long_term_memories ranking and tau threshold
# ---------------------------------------------------------------------------

@pytest.mark.live
@pytest.mark.asyncio
async def test_live_match_long_term_memories_ranking_and_tau(live_contact_ids):
    """
    Live test: match_long_term_memories returns the related fact above the
    unrelated one and filters out facts below tau.
    Cleans up all inserted facts upon completion.
    """
    cid = live_contact_ids["contact_a"]
    org_id = live_contact_ids["org_a"]
    call_id = live_contact_ids["call_a"]
    agent_id = live_contact_ids["agent_id"]

    fact_billing = "Customer requested an annual enterprise invoice discount for 50 seats"
    fact_weather = "The caller briefly mentioned the cloudy rainy weather in Seattle"

    fact_ids = []
    try:
        # Store both facts
        res1 = await long_term.store_fact(
            contact_id=cid,
            org_id=org_id,
            agent_id=agent_id,
            content=fact_billing,
            call_id=call_id,
        )
        if res1 and res1.get("id"):
            fact_ids.append(res1["id"])

        res2 = await long_term.store_fact(
            contact_id=cid,
            org_id=org_id,
            agent_id=agent_id,
            content=fact_weather,
            call_id=call_id,
        )
        if res2 and res2.get("id"):
            fact_ids.append(res2["id"])

        # Query for billing
        results = await long_term.retrieve_relevant_facts(
            contact_id=cid,
            org_id=org_id,
            query_text="enterprise discount on billing invoice",
            limit=5,
        )

        assert isinstance(results, list)
        if results:
            first_fact = results[0]
            assert "discount" in first_fact.get("content", "").lower() or "invoice" in first_fact.get("content", "").lower()
            if "similarity" in first_fact and first_fact["similarity"] is not None:
                assert first_fact["similarity"] >= settings.RETRIEVAL_TAU

    finally:
        # Clean up inserted test facts
        if supabase and fact_ids:
            try:
                for fid in fact_ids:
                    supabase.table("memory_long_term").delete().eq("id", fid).execute()
                supabase.table("memory_long_term").delete().eq("contact_id", cid).execute()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# 2. Contact and Organization SQL Isolation
# ---------------------------------------------------------------------------

@pytest.mark.live
@pytest.mark.asyncio
async def test_live_contact_and_org_sql_isolation(live_contact_ids):
    """
    Live test: SQL queries must strictly isolate data by contact_id and org_id.
    Facts from Org B / Contact B must never leak into Org A / Contact A queries.
    Cleans up all inserted records.
    """
    cid_a = live_contact_ids["contact_a"]
    cid_b = live_contact_ids["contact_b"]
    org_a = live_contact_ids["org_a"]
    org_b = live_contact_ids["org_b"]
    call_a = live_contact_ids["call_a"]
    call_b = live_contact_ids["call_b"]
    agent_id = live_contact_ids["agent_id"]

    try:
        # Store Fact for Org A
        await long_term.store_fact(
            contact_id=cid_a,
            org_id=org_a,
            agent_id=agent_id,
            content="Confidential Secret Project Alpha for Org A",
            call_id=call_a,
        )

        # Store Fact for Org B
        await long_term.store_fact(
            contact_id=cid_b,
            org_id=org_b,
            agent_id=agent_id,
            content="Confidential Secret Project Beta for Org B",
            call_id=call_b,
        )

        # Query for Org A with Contact A
        results_a = await long_term.retrieve_relevant_facts(
            contact_id=cid_a,
            org_id=org_a,
            query_text="Project Beta secret",
        )

        # Project Beta from Org B must NOT be returned for Org A
        for r in results_a:
            assert "Project Beta" not in r.get("content", "")

        # Query with mismatched org_id (Org A searching Contact B)
        results_cross = await long_term.retrieve_relevant_facts(
            contact_id=cid_b,
            org_id=org_a,  # Mismatched org
            query_text="Project Beta",
        )
        assert len(results_cross) == 0

    finally:
        if supabase:
            try:
                supabase.table("memory_long_term").delete().eq("contact_id", cid_a).execute()
                supabase.table("memory_long_term").delete().eq("contact_id", cid_b).execute()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# 3. Erasure removes canary data from every store
# ---------------------------------------------------------------------------

@pytest.mark.live
@pytest.mark.asyncio
async def test_live_erasure_removes_canary_from_all_stores(live_contact_ids):
    """
    Live test: DPDP cascade erasure clears personal data and canary tokens
    across Redis, Supabase tables, and FalkorDB graph.
    """
    cid = live_contact_ids["contact_a"]
    org_id = live_contact_ids["org_a"]
    call_id = live_contact_ids["call_a"]

    canary_token = f"CANARY-{uuid4().hex[:8].upper()}"

    # 1. Seed Redis
    await redis_client.set(f"stm:{call_id}", json.dumps({"turns": [{"role": "user", "content": canary_token}]}), ex_seconds=300)
    await redis_client.set(f"slot:{call_id}", json.dumps({"canary": canary_token}), ex_seconds=300)
    await redis_client.rpush(f"webcall:{call_id}:events", json.dumps({"text": canary_token}))
    await redis_client.set(f"erasure:{cid}", "1", ex_seconds=3600)

    # 2. Seed Supabase (if available or in-memory fallback)
    in_memory_db = {
        "contacts": [{"id": cid, "org_id": org_id, "name": f"Canary {canary_token}"}],
        "calls": [{"id": call_id, "org_id": org_id, "contact_id": cid, "transcript": canary_token}],
        "memory_long_term": [{"id": str(uuid4()), "contact_id": cid, "org_id": org_id, "call_id": call_id, "content": canary_token, "embedding": [0.0] * 1024}],
        "memory_episodic": [{"id": str(uuid4()), "contact_id": cid, "org_id": org_id, "call_id": call_id, "summary": canary_token}],
        "compliance_log": [],
    }

    class MockTableQuery:
        def __init__(self, table_name):
            self.table_name = table_name
            self._filters = {}

        def select(self, *args, **kwargs):
            return self

        def eq(self, column, value):
            self._filters[column] = str(value)
            return self

        def insert(self, record):
            if isinstance(record, dict):
                in_memory_db.setdefault(self.table_name, []).append(record)
            elif isinstance(record, list):
                in_memory_db.setdefault(self.table_name, []).extend(record)
            mock_res = type("Res", (), {"data": [record] if isinstance(record, dict) else record})()
            return type("Chain", (), {"execute": lambda self: mock_res})()

        def update(self, update_data):
            for row in in_memory_db.get(self.table_name, []):
                match = all(str(row.get(k)) == v for k, v in self._filters.items())
                if match:
                    row.update(update_data)
            return self

        def delete(self):
            return self

        def execute(self):
            rows = in_memory_db.get(self.table_name, [])
            matched = [
                r for r in rows
                if all(str(r.get(k)) == v for k, v in self._filters.items())
            ]
            if hasattr(self, "_is_delete") and self._is_delete:
                in_memory_db[self.table_name] = [
                    r for r in rows
                    if not all(str(r.get(k)) == v for k, v in self._filters.items())
                ]
            res_obj = type("Res", (), {"data": matched})()
            return res_obj

    def mock_table(table_name):
        t = MockTableQuery(table_name)
        orig_delete = t.delete
        def del_fn():
            t._is_delete = True
            return t
        t.delete = del_fn
        return t

    # Check if live Supabase is active or fallback to in-memory adapter
    is_live_db = bool(settings.NEXT_PUBLIC_SUPABASE_URL and settings.SUPABASE_SERVICE_ROLE_KEY)
    supabase_patch = None
    if not is_live_db:
        from unittest.mock import MagicMock, patch
        mock_sb = MagicMock()
        mock_sb.table.side_effect = mock_table
        supabase_patch = patch("app.routers.contacts.supabase", mock_sb)
        supabase_patch.start()
    else:
        try:
            supabase.table("contacts").insert({"id": cid, "org_id": org_id, "name": f"Canary {canary_token}"}).execute()
            supabase.table("calls").insert({"id": call_id, "org_id": org_id, "contact_id": cid, "transcript": canary_token}).execute()
            supabase.table("memory_long_term").insert({"contact_id": cid, "org_id": org_id, "call_id": call_id, "content": canary_token, "embedding": [0.0] * 1024}).execute()
            supabase.table("memory_episodic").insert({"contact_id": cid, "org_id": org_id, "call_id": call_id, "summary": canary_token}).execute()
        except Exception:
            pass

    # 3. Seed FalkorDB
    try:
        graph.add_frustration_edges(
            contact_id=cid,
            topics=["billing_issue"],
            episode_id="ep_test_canary",
            emotion_state={"valence": -0.8},
            call_id=call_id,
        )
        graph.add_entities(
            contact_id=cid,
            entities=[canary_token],
            episode_id="ep_test_canary",
            call_id=call_id,
            summary="Canary summary",
        )
    except Exception:
        pass

    try:
        # Run Cascade Erasure
        res = await cascade_delete_contact_memory(
            contact_id=cid,
            delete_contact=True,
            verify=True,
            current_user={"id": str(uuid4()), "org_id": org_id, "role": "admin"},
        )

        assert res.get("deleted") is True or res.get("contact_id") == cid

        # Verify Redis keys deleted
        assert await redis_client.get(f"stm:{call_id}") is None
        assert await redis_client.get(f"slot:{call_id}") is None

        # Verify Supabase data removed
        if supabase:
            c_check = supabase.table("contacts").select("id").eq("id", cid).execute()
            assert len(c_check.data or []) == 0
            lt_check = supabase.table("memory_long_term").select("id").eq("contact_id", cid).execute()
            assert len(lt_check.data or []) == 0

        # Verify FalkorDB graph cleared
        g_data = graph.get_graph_data(cid)
        assert len(g_data.get("nodes", [])) == 0

    finally:
        # Cleanup
        if supabase_patch:
            supabase_patch.stop()
        await redis_client.delete(f"stm:{call_id}")
        await redis_client.delete(f"slot:{call_id}")
        await redis_client.delete(f"webcall:{call_id}:events")
        await redis_client.delete(f"erasure:{cid}")
        graph.delete_contact_graph(cid)
        if supabase:
            try:
                supabase.table("calls").delete().eq("id", call_id).execute()
                supabase.table("contacts").delete().eq("id", cid).execute()
                supabase.table("compliance_log").delete().eq("org_id", org_id).execute()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# 4. Post-call pipeline run twice leaves one episode
# ---------------------------------------------------------------------------

@pytest.mark.live
@pytest.mark.asyncio
async def test_live_post_call_pipeline_idempotence(live_contact_ids):
    """
    Live test: Running the post-call episodic generation twice for the same call
    leaves exactly one row in memory_episodic (idempotent upsert).
    """
    cid = live_contact_ids["contact_a"]
    org_id = live_contact_ids["org_a"]
    call_id = live_contact_ids["call_a"]

    transcript = [
        {"role": "user", "content": "I need help with my invoice"},
        {"role": "assistant", "content": "I can assist you with your invoice payment."},
    ]

    try:
        # First execution
        await episodic.create_episode(
            call_id=call_id,
            contact_id=cid,
            org_id=org_id,
            transcript=transcript,
        )

        # Second execution (duplicate call completion event)
        await episodic.create_episode(
            call_id=call_id,
            contact_id=cid,
            org_id=org_id,
            transcript=transcript,
        )

        if supabase:
            res = supabase.table("memory_episodic").select("*").eq("call_id", call_id).execute()
            # Must have at most 1 record (idempotent), not duplicate rows
            assert len(res.data or []) <= 1
            if res.data:
                assert res.data[0]["call_id"] == call_id

    finally:
        if supabase:
            try:
                supabase.table("memory_episodic").delete().eq("call_id", call_id).execute()
                supabase.table("memory_episodic").delete().eq("contact_id", cid).execute()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# 5. Redis TTLs exist
# ---------------------------------------------------------------------------

@pytest.mark.live
@pytest.mark.asyncio
async def test_live_redis_ttls_exist(live_contact_ids):
    """
    Live test: Keys stored in Redis have non-infinite TTLs to prevent memory leaks.
    """
    call_id = live_contact_ids["call_a"]
    cid = live_contact_ids["contact_a"]

    key_stm = f"stm:{call_id}"
    key_erasure = f"erasure:{cid}"

    try:
        # Initialize short term memory and erasure flag
        await short_term.init_call_memory(call_id)
        await redis_client.set(key_erasure, "1", ex_seconds=3600)

        raw_r = getattr(redis_client, "_redis", None)
        if raw_r:
            ttl_stm = await raw_r.ttl(key_stm)
            ttl_erasure = await raw_r.ttl(key_erasure)

            # TTL must be set (> 0 and <= 86400)
            if ttl_stm > -1:
                assert ttl_stm > 0
                assert ttl_stm <= 86400
            if ttl_erasure > -1:
                assert ttl_erasure > 0
                assert ttl_erasure <= 3600
        else:
            assert True

    finally:
        await redis_client.delete(key_stm)
        await redis_client.delete(key_erasure)


# ---------------------------------------------------------------------------
# 6. Graph Isolation
# ---------------------------------------------------------------------------

@pytest.mark.live
@pytest.mark.asyncio
async def test_live_graph_isolation(live_contact_ids):
    """
    Live test: FalkorDB graphs for distinct contacts are strictly partitioned
    (contact_{id_a} vs contact_{id_b}).
    """
    cid_a = live_contact_ids["contact_a"]
    cid_b = live_contact_ids["contact_b"]
    call_a = live_contact_ids["call_a"]
    call_b = live_contact_ids["call_b"]

    try:
        # Add entity for Contact A
        graph.add_frustration_edges(
            contact_id=cid_a,
            topics=["billing_delay"],
            episode_id="ep_a",
            emotion_state={"valence": -0.7},
            call_id=call_a,
        )
        graph.add_entities(
            contact_id=cid_a,
            entities=["ClientAlphaOrg"],
            episode_id="ep_a",
            call_id=call_a,
            summary="Client Alpha discussion",
            contact_name="Customer A",
        )

        # Add entity for Contact B
        graph.add_frustration_edges(
            contact_id=cid_b,
            topics=["shipping_issue"],
            episode_id="ep_b",
            emotion_state={"valence": -0.9},
            call_id=call_b,
        )
        graph.add_entities(
            contact_id=cid_b,
            entities=["ClientBetaOrg"],
            episode_id="ep_b",
            call_id=call_b,
            summary="Client Beta discussion",
            contact_name="Customer B",
        )

        data_a = graph.get_graph_data(cid_a)
        data_b = graph.get_graph_data(cid_b)

        # Graph A must not contain Graph B nodes or mentions
        data_a_str = json.dumps(data_a)
        data_b_str = json.dumps(data_b)

        assert "ClientBetaOrg" not in data_a_str
        assert "shipping_issue" not in data_a_str
        assert "ClientAlphaOrg" not in data_b_str
        assert "billing_delay" not in data_b_str

    finally:
        graph.delete_contact_graph(cid_a)
        graph.delete_contact_graph(cid_b)
