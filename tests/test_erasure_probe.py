"""
tests/test_erasure_probe.py — Pytest suite for DPDP Act 2023 memory erasure probe.

Verifies canary seeding, multi-store probe retrieval, complete cascade erasure (zero residue),
multi-status 207 on failing tiers, idempotent repeat calls, active-call memory suppression,
graph isolation, tenant security (401/403), and pseudonymized compliance logging.
"""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
from unittest.mock import AsyncMock, patch
import uuid

from fastapi import HTTPException, Response
import pytest

from app.routers.contacts import cascade_delete_contact_memory, compute_contact_hash
from eval.erasure.run_probe import (
    CanaryRecord,
    ErasureStore,
    SupabaseStoreAdapter,
    call_erasure_endpoint,
    evaluate_idempotence,
    evaluate_in_progress_call,
    evaluate_shared_graph_node,
    generate_residue_report_md,
    generate_table_viii_csv,
    probe,
    run_erasure_benchmark,
    seed_contact_data,
    verify_audit_logs,
)


@pytest.fixture
def erasure_store() -> ErasureStore:
    """Provides a fresh in-memory ErasureStore."""
    return ErasureStore(mock=True)


@pytest.fixture
def sample_record() -> CanaryRecord:
    """Generates a single canary test identity."""
    canary = f"CANARY-{uuid.uuid4().hex[:8].upper()}"
    return CanaryRecord(
        contact_id=str(uuid.uuid4()),
        call_id=str(uuid.uuid4()),
        org_id="00000000-0000-4000-8000-000000000001",
        agent_id=str(uuid.uuid4()),
        canary_token=canary,
        caller_name=f"Caller {canary}",
        caller_phone="+919876543210",
        caller_email=f"{canary.lower()}@test.vocall.ai",
    )


class TestCanaryGeneration:
    """Verifies canary generation properties."""

    def test_canary_uniqueness_across_contacts(self):
        """TC-CANARY-01: Every generated canary token must be globally unique."""
        tokens = set()
        for _ in range(50):
            token = f"CANARY-{uuid.uuid4().hex[:8].upper()}"
            assert token.startswith("CANARY-")
            assert token not in tokens
            tokens.add(token)
        assert len(tokens) == 50


class TestSeedingAndProbe:
    """Verifies seeding and pre-erasure probe detection."""

    @pytest.mark.asyncio
    async def test_seeding_populates_all_stores(self, erasure_store: ErasureStore, sample_record: CanaryRecord):
        """TC-SEED-01: Seeder must write records containing the canary to all stores."""
        await seed_contact_data(erasure_store, sample_record)

        # Redis verification
        stm_key = f"stm:{sample_record.call_id}"
        webcall_key = f"webcall:{sample_record.call_id}:events"
        slot_key = f"slot:{sample_record.call_id}"

        assert stm_key in erasure_store.redis_kv
        assert sample_record.canary_token in erasure_store.redis_kv[stm_key]
        assert webcall_key in erasure_store.redis_lists
        assert slot_key in erasure_store.redis_kv

        # Postgres verification
        assert len(erasure_store.tables["contacts"]) == 1
        assert len(erasure_store.tables["calls"]) == 1
        assert len(erasure_store.tables["call_turns"]) == 1
        assert len(erasure_store.tables["call_transcripts"]) == 1
        assert len(erasure_store.tables["emotion_events"]) == 1
        assert len(erasure_store.tables["intent_events"]) == 1
        assert len(erasure_store.tables["memory_long_term"]) == 1
        assert len(erasure_store.tables["memory_episodic"]) == 1
        assert len(erasure_store.tables["memory_graph_nodes"]) == 1

        # FalkorDB verification
        graph_name = f"contact_{sample_record.contact_id.replace('-', '_')}"
        assert graph_name in erasure_store.graphs
        nodes = erasure_store.graphs[graph_name]["nodes"]
        assert len(nodes) == 5

    @pytest.mark.asyncio
    async def test_probe_detects_all_items_without_threshold(
        self,
        erasure_store: ErasureStore,
        sample_record: CanaryRecord,
    ):
        """TC-PROBE-01: Pre-erasure probe must retrieve all seeded items."""
        await seed_contact_data(erasure_store, sample_record)
        found = await probe(erasure_store, sample_record)

        assert found["redis_stm"] == 1
        assert found["redis_webcall"] == 2
        assert found["redis_slot"] == 1
        assert found["contacts"] == 1
        assert found["calls"] == 1
        assert found["call_turns"] == 1
        assert found["call_transcripts"] == 1
        assert found["emotion_events"] == 1
        assert found["intent_events"] == 1
        assert found["memory_long_term"] == 1
        assert found["memory_episodic"] == 1
        assert found["memory_graph_nodes"] == 1
        assert found["falkordb_nodes"] == 5


class TestCascadeErasureCompleteness:
    """Verifies complete erasure with zero residue and completeness 1.0."""

    @pytest.mark.asyncio
    async def test_cascade_erasure_zero_residue_and_completeness_one(
        self,
        erasure_store: ErasureStore,
        sample_record: CanaryRecord,
    ):
        """TC-ERASURE-01: Complete erasure leaves zero residue across all stores (C = 1.0)."""
        await seed_contact_data(erasure_store, sample_record)
        before = await probe(erasure_store, sample_record)
        assert sum(before.values()) > 0

        res = await call_erasure_endpoint(
            erasure_store,
            sample_record.contact_id,
            user_org_id=sample_record.org_id,
            verify=True,
        )

        assert res.get("deleted") is True
        assert res.get("tiers_cleared") >= 6
        assert res.get("audit_status") == "ok"

        after = await probe(erasure_store, sample_record)

        # Assert zero residue in every store and table
        assert after["redis_stm"] == 0
        assert after["redis_webcall"] == 0
        assert after["redis_slot"] == 0
        assert after["redis_extra_keys"] == 0
        assert after["contacts"] == 0
        assert after["calls"] == 0
        assert after["call_turns"] == 0
        assert after["call_transcripts"] == 0
        assert after["emotion_events"] == 0
        assert after["intent_events"] == 0
        assert after["memory_long_term"] == 0
        assert after["memory_episodic"] == 0
        assert after["memory_graph_nodes"] == 0
        assert after["falkordb_nodes"] == 0
        assert after["falkordb_global_canary"] == 0

        total_residue = sum(after.values())
        assert total_residue == 0

        completeness = 1.0 - (total_residue / sum(before.values()))
        assert completeness == 1.0

    @pytest.mark.asyncio
    async def test_failing_tier_returns_207_and_names_tier(
        self,
        erasure_store: ErasureStore,
        sample_record: CanaryRecord,
    ):
        """TC-ERASURE-02: A failing tier sets status 207, deleted=False, and names the tier."""
        await seed_contact_data(erasure_store, sample_record)

        sb_adapter = SupabaseStoreAdapter(erasure_store)
        response = Response()
        user = {"id": str(uuid.uuid4()), "org_id": sample_record.org_id, "role": "admin"}

        # Simulate FalkorDB failure
        with patch("app.routers.contacts.supabase", sb_adapter), \
             patch("app.routers.contacts.redis_client.set", new_callable=AsyncMock), \
             patch("app.routers.contacts.redis_client.get", new_callable=AsyncMock, return_value=None), \
             patch("app.routers.contacts.redis_client.delete", new_callable=AsyncMock, return_value=True), \
             patch("app.routers.contacts.redis_client.keys", new_callable=AsyncMock, return_value=[]), \
             patch("app.services.memory.short_term.clear_call_memory", new_callable=AsyncMock, return_value=True), \
             patch("app.routers.contacts.graph.delete_contact_graph", return_value=False):
            res = await cascade_delete_contact_memory(
                contact_id=uuid.UUID(sample_record.contact_id),
                response=response,
                current_user=user,
            )

        assert response.status_code == 207
        assert res["deleted"] is False
        failed_tiers = [t for t in res["tiers"] if t["status"] == "failed"]
        assert len(failed_tiers) >= 1
        assert failed_tiers[0]["tier"] == "falkordb"
        assert failed_tiers[0]["error"] is not None

    @pytest.mark.asyncio
    async def test_idempotent_second_call_returns_200_with_zero_counts(
        self,
        erasure_store: ErasureStore,
        sample_record: CanaryRecord,
    ):
        """TC-ERASURE-03: Repeating erasure is idempotent and returns 200 with zero deleted counts."""
        await seed_contact_data(erasure_store, sample_record)

        # Pass 1
        res1 = await call_erasure_endpoint(erasure_store, sample_record.contact_id, user_org_id=sample_record.org_id)
        assert res1["deleted"] is True

        # Pass 2
        res2 = await call_erasure_endpoint(erasure_store, sample_record.contact_id, user_org_id=sample_record.org_id)
        assert res2["deleted"] is True

        # All tiers in pass 2 should report 0 deleted items
        for t in res2["tiers"]:
            assert t["status"] == "ok"
            assert t["deleted_count"] == 0

    @pytest.mark.asyncio
    async def test_call_in_progress_post_call_pipeline_skips_memory(
        self,
        erasure_store: ErasureStore,
        sample_record: CanaryRecord,
    ):
        """TC-ERASURE-04: Active call flagged for erasure prevents post_call_pipeline memory writes."""
        await seed_contact_data(erasure_store, sample_record, is_active=True)

        # Trigger erasure mid-call
        res = await call_erasure_endpoint(erasure_store, sample_record.contact_id, user_org_id=sample_record.org_id)
        assert res["deleted"] is True

        # When post_call_pipeline executes, it must detect erasure:{cid} and skip
        from trigger.post_call_pipeline import post_call_pipeline
        with patch("app.services.redis_client.redis_client.get", new_callable=AsyncMock, return_value="true"):
            pipeline_res = await post_call_pipeline(
                call_id=sample_record.call_id,
                agent_id=sample_record.agent_id,
                contact_id=sample_record.contact_id,
                org_id=sample_record.org_id,
            )
        assert pipeline_res.get("status") == "skipped"

    @pytest.mark.asyncio
    async def test_another_contacts_graph_untouched(self, erasure_store: ErasureStore):
        """TC-ERASURE-05: Deleting Contact A leaves Contact B graph nodes untouched."""
        res = await evaluate_shared_graph_node(erasure_store)
        assert res["shared_node_survived"] is True
        assert res["contact_b_survived"] is True

    @pytest.mark.asyncio
    async def test_org_mismatch_rejected_with_403(
        self,
        erasure_store: ErasureStore,
        sample_record: CanaryRecord,
    ):
        """TC-ERASURE-06: Mismatched tenant org_id is rejected with HTTP 403 Forbidden."""
        await seed_contact_data(erasure_store, sample_record)
        sb_adapter = SupabaseStoreAdapter(erasure_store)

        foreign_user = {
            "id": str(uuid.uuid4()),
            "org_id": "00000000-9999-4000-8000-999999999999",
            "role": "admin",
        }

        with patch("app.routers.contacts.supabase", sb_adapter):
            with pytest.raises(HTTPException) as exc_info:
                await cascade_delete_contact_memory(
                    contact_id=uuid.UUID(sample_record.contact_id),
                    current_user=foreign_user,
                )
            assert exc_info.value.status_code == 403
            assert "organization" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_unauthenticated_request_rejected_with_401(
        self,
        sample_record: CanaryRecord,
    ):
        """TC-ERASURE-07: Request without authenticated user is rejected with HTTP 401."""
        with pytest.raises(HTTPException) as exc_info:
            await cascade_delete_contact_memory(
                contact_id=uuid.UUID(sample_record.contact_id),
                current_user=None,
            )
        assert exc_info.value.status_code == 401
        assert "Authentication token required" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_audit_row_contains_no_raw_contact_id(
        self,
        erasure_store: ErasureStore,
        sample_record: CanaryRecord,
    ):
        """TC-ERASURE-08: Compliance audit row contains HMAC hash and no raw contact ID or PII."""
        await seed_contact_data(erasure_store, sample_record)
        await call_erasure_endpoint(erasure_store, sample_record.contact_id, user_org_id=sample_record.org_id)

        audit_check = verify_audit_logs(erasure_store, [sample_record])
        assert audit_check["is_safe"] is True
        assert audit_check["audit_logs_found"] == 1
        assert audit_check["pii_leak_count"] == 0

        # Direct row inspection
        log_entry = erasure_store.tables["compliance_log"][0]
        assert log_entry["action"] == "forget_me"
        assert log_entry["contact_id"] is None
        assert log_entry["contact_hash"] == compute_contact_hash(sample_record.contact_id)

        serialized = json.dumps(log_entry)
        assert sample_record.contact_id not in serialized
        assert sample_record.canary_token not in serialized
        assert sample_record.caller_phone not in serialized
        assert sample_record.caller_name not in serialized
        assert sample_record.caller_email not in serialized


class TestBenchmarkPipeline:
    """Verifies full benchmark run and artifact generation."""

    @pytest.mark.asyncio
    async def test_run_erasure_benchmark_small_split(self):
        """TC-BENCH-01: Benchmark runs across N contacts and computes complete stats."""
        res = await run_erasure_benchmark(n_contacts=5, seed=123, mock=True)

        assert res["n_contacts"] == 5
        assert res["total_seeded_before"] > 0
        assert res["total_retrievable_after"] == 0
        assert res["overall_completeness"] == 1.0
        assert res["audit_verification"]["is_safe"] is True

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "table_viii.csv"
            md_path = Path(tmpdir) / "residue_report.md"

            generate_table_viii_csv(res, str(csv_path))
            generate_residue_report_md(res, str(md_path))

            assert csv_path.exists()
            assert md_path.exists()

            csv_text = csv_path.read_text(encoding="utf-8")
            assert "Store / Table" in csv_text
            assert "TOTAL / COMPOSITE" in csv_text

            md_text = md_path.read_text(encoding="utf-8")
            assert "DPDP Act 2023" in md_text
            assert "Table VIII" in md_text
