"""
Tests for long-term memory retrieval, embedding generation, deduplication, and isolation.

Covers:
  1. Related fact ranks above unrelated fact via cosine similarity.
  2. Facts below tau (RETRIEVAL_TAU=0.75) are excluded.
  3. Empty result is a valid answer and returns [].
  4. RPC error raises when fallback is off (ALLOW_RECENCY_FALLBACK=False).
  5. RPC error falls back to recency (with similarity=None) when fallback is on.
  6. Contact and organization isolation parameters in match RPC.
  7. Empty query returns [] immediately without generating an embedding.
  8. store_fact is idempotent per (contact_id, call_id, content).
  9. generate_embedding raises on empty text, wrong dimension, or zero vector.
 10. Live embedding generation test with real configured provider (BAAI/bge-m3).
"""

from __future__ import annotations

import math
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.config import settings
from app.services.memory import long_term


# ---------------------------------------------------------------------------
# Helpers & Deterministic Fake Embedder
# ---------------------------------------------------------------------------

def fake_deterministic_embedder(text: str, dim: int = 1024) -> List[float]:
    """Generates deterministic unit-normalized 1024-dim vectors based on token clusters."""
    clean = text.lower().strip()
    if not clean:
        raise ValueError("Cannot generate embedding for empty text")

    vec = [0.0] * dim
    words = clean.split()
    for w in words:
        if any(kw in w for kw in ("bill", "invoice", "charge", "refund", "receipt")):
            # Billing cluster: indices 0..255
            for idx in range(0, 256):
                vec[idx] += 1.0
        elif any(kw in w for kw in ("weather", "sunny", "rain", "forecast", "cloud")):
            # Weather cluster: indices 256..511
            for idx in range(256, 512):
                vec[idx] += 1.0
        else:
            # General cluster: indices 512..1023
            for idx in range(512, 1024):
                vec[idx] += 1.0

    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0.0:
        return [1.0 / math.sqrt(dim)] * dim
    return [x / norm for x in vec]


@pytest.fixture
def mock_supabase():
    mock_client = MagicMock()
    with patch("app.services.memory.long_term.supabase", mock_client):
        yield mock_client


@pytest.fixture
def patch_fake_embedding():
    with patch(
        "app.services.memory.long_term.generate_embedding",
        side_effect=fake_deterministic_embedder,
    ) as p:
        yield p


# ---------------------------------------------------------------------------
# Unit Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_related_fact_ranks_above_unrelated(mock_supabase, patch_fake_embedding):
    """Related billing fact ranks above unrelated weather fact."""
    contact_id = str(uuid4())
    org_id = str(uuid4())

    mock_rpc = MagicMock()
    # RPC returns records ordered by similarity descending
    mock_rpc.execute.return_value.data = [
        {"id": str(uuid4()), "content": "customer disputed previous invoice", "similarity": 0.88},
        {"id": str(uuid4()), "content": "caller commented on sunny weather", "similarity": 0.32},
    ]
    mock_supabase.rpc.return_value = mock_rpc

    facts = await long_term.retrieve_relevant_facts(
        contact_id=contact_id,
        org_id=org_id,
        query_text="my bill is wrong",
    )

    assert len(facts) == 2
    assert facts[0]["content"] == "customer disputed previous invoice"
    assert facts[0]["similarity"] > facts[1]["similarity"]
    assert facts[0]["similarity"] >= 0.75


@pytest.mark.asyncio
async def test_facts_below_tau_are_excluded(mock_supabase, patch_fake_embedding):
    """Facts below threshold tau (default 0.75) are filtered out by RPC."""
    contact_id = str(uuid4())
    org_id = str(uuid4())

    mock_rpc = MagicMock()
    # The RPC server-side filters >= match_threshold, so only high similarities return
    mock_rpc.execute.return_value.data = [
        {"id": str(uuid4()), "content": "billing error reported on march 1", "similarity": 0.84}
    ]
    mock_supabase.rpc.return_value = mock_rpc

    facts = await long_term.retrieve_relevant_facts(
        contact_id=contact_id,
        org_id=org_id,
        query_text="my invoice has an error",
        threshold=0.75,
    )

    # Verify RPC called with threshold=0.75
    mock_supabase.rpc.assert_called_once()
    args, kwargs = mock_supabase.rpc.call_args
    params = args[1] if len(args) > 1 else kwargs
    assert params["match_threshold"] == 0.75
    assert len(facts) == 1
    assert facts[0]["similarity"] >= 0.75


@pytest.mark.asyncio
async def test_empty_result_returns_empty_list(mock_supabase, patch_fake_embedding):
    """When no facts meet similarity threshold, returns [] without errors."""
    contact_id = str(uuid4())
    org_id = str(uuid4())

    mock_rpc = MagicMock()
    mock_rpc.execute.return_value.data = []
    mock_supabase.rpc.return_value = mock_rpc

    facts = await long_term.retrieve_relevant_facts(
        contact_id=contact_id,
        org_id=org_id,
        query_text="unrelated topic with no matches",
    )

    assert facts == []


@pytest.mark.asyncio
async def test_rpc_error_raises_when_fallback_is_off(mock_supabase, patch_fake_embedding):
    """When ALLOW_RECENCY_FALLBACK is False, an RPC error raises immediately."""
    contact_id = str(uuid4())
    org_id = str(uuid4())

    mock_supabase.rpc.side_effect = RuntimeError("Postgres connection dropped")

    with patch.object(settings, "ALLOW_RECENCY_FALLBACK", False):
        with pytest.raises(RuntimeError, match="Postgres connection dropped"):
            await long_term.retrieve_relevant_facts(
                contact_id=contact_id,
                org_id=org_id,
                query_text="check account status",
            )


@pytest.mark.asyncio
async def test_rpc_error_falls_back_when_enabled(mock_supabase, patch_fake_embedding):
    """When ALLOW_RECENCY_FALLBACK is True, logs warning and returns recency rows with similarity=None."""
    contact_id = str(uuid4())
    org_id = str(uuid4())

    mock_supabase.rpc.side_effect = RuntimeError("Function match_long_term_memories does not exist")

    # Table mock for recency fallback
    mock_table = MagicMock()
    mock_select = MagicMock()
    mock_select.eq.return_value = mock_select
    mock_select.order.return_value = mock_select
    mock_select.limit.return_value = mock_select
    mock_select.execute.return_value.data = [
        {"id": str(uuid4()), "content": "Recent note", "emotion_state": {}, "created_at": "2026-10-07T10:00:00Z"}
    ]
    mock_table.select.return_value = mock_select
    mock_supabase.table.return_value = mock_table

    with patch.object(settings, "ALLOW_RECENCY_FALLBACK", True):
        facts = await long_term.retrieve_relevant_facts(
            contact_id=contact_id,
            org_id=org_id,
            query_text="any query",
        )

        assert len(facts) == 1
        assert facts[0]["content"] == "Recent note"
        assert facts[0]["similarity"] is None


@pytest.mark.asyncio
async def test_contact_and_org_isolation(mock_supabase, patch_fake_embedding):
    """RPC call strictly enforces p_contact_id and p_org_id parameters."""
    contact_id = str(uuid4())
    org_id = str(uuid4())

    mock_rpc = MagicMock()
    mock_rpc.execute.return_value.data = []
    mock_supabase.rpc.return_value = mock_rpc

    await long_term.retrieve_relevant_facts(
        contact_id=contact_id,
        org_id=org_id,
        query_text="billing question",
    )

    args, kwargs = mock_supabase.rpc.call_args
    assert args[0] == "match_long_term_memories"
    params = args[1] if len(args) > 1 else kwargs
    assert params["p_contact_id"] == contact_id
    assert params["p_org_id"] == org_id


@pytest.mark.asyncio
async def test_empty_query_returns_empty_list_without_embedding(mock_supabase):
    """Empty query text returns [] immediately without generating an embedding."""
    contact_id = str(uuid4())
    org_id = str(uuid4())

    with patch("app.services.memory.long_term.generate_embedding") as mock_embed:
        facts_empty = await long_term.retrieve_relevant_facts(
            contact_id=contact_id,
            org_id=org_id,
            query_text="",
        )
        assert facts_empty == []

        facts_spaces = await long_term.retrieve_relevant_facts(
            contact_id=contact_id,
            org_id=org_id,
            query_text="    ",
        )
        assert facts_spaces == []

        mock_embed.assert_not_called()


@pytest.mark.asyncio
async def test_store_fact_idempotent_per_call_id_and_content(mock_supabase, patch_fake_embedding):
    """store_fact skips insert when duplicate (contact_id, call_id, content) exists."""
    contact_id = str(uuid4())
    org_id = str(uuid4())
    agent_id = str(uuid4())
    call_id = str(uuid4())
    content = "Customer prefers communication in Hinglish"

    mock_table = MagicMock()

    # Call 1: Duplicate check finds nothing -> inserts
    existing_check_1 = MagicMock()
    existing_check_1.eq.return_value = existing_check_1
    existing_check_1.limit.return_value = existing_check_1
    existing_check_1.execute.return_value.data = []

    mock_insert = MagicMock()
    mock_insert.execute.return_value.data = [
        {"id": str(uuid4()), "contact_id": contact_id, "content": content, "call_id": call_id}
    ]

    mock_table.select.return_value = existing_check_1
    mock_table.insert.return_value = mock_insert
    mock_supabase.table.return_value = mock_table

    res1 = await long_term.store_fact(
        contact_id=contact_id,
        org_id=org_id,
        agent_id=agent_id,
        content=content,
        call_id=call_id,
    )
    assert res1 is not None
    assert mock_table.insert.call_count == 1

    # Call 2: Duplicate check finds existing record -> skips insert
    existing_check_2 = MagicMock()
    existing_check_2.eq.return_value = existing_check_2
    existing_check_2.limit.return_value = existing_check_2
    existing_check_2.execute.return_value.data = [
        {"id": res1["id"], "contact_id": contact_id, "content": content, "call_id": call_id}
    ]
    mock_table.select.return_value = existing_check_2

    res2 = await long_term.store_fact(
        contact_id=contact_id,
        org_id=org_id,
        agent_id=agent_id,
        content=content,
        call_id=call_id,
    )
    assert res2 is not None
    assert res2["id"] == res1["id"]
    # Insert call count remains 1 (no second insert performed)
    assert mock_table.insert.call_count == 1


@pytest.mark.asyncio
async def test_generate_embedding_raises_on_empty_text():
    """generate_embedding raises ValueError on empty or whitespace string."""
    with pytest.raises(ValueError, match="Cannot generate embedding for empty"):
        await long_term.generate_embedding("")

    with pytest.raises(ValueError, match="Cannot generate embedding for empty"):
        await long_term.generate_embedding("   \n\t  ")


@pytest.mark.asyncio
async def test_generate_embedding_never_returns_zero_vector():
    """generate_embedding raises ValueError if embedder returns all zeros."""
    with patch(
        "app.services.memory.long_term._encode_sentence_transformer",
        return_value=[0.0] * 1024,
    ):
        with pytest.raises(ValueError, match="invalid zero vector"):
            await long_term.generate_embedding("valid non-empty text")


@pytest.mark.asyncio
async def test_generate_embedding_wrong_dimension_raises():
    """generate_embedding raises ValueError if dimension does not match EMBEDDING_DIM."""
    with patch(
        "app.services.memory.long_term._encode_sentence_transformer",
        return_value=[0.1] * 512,  # 512 != 1024
    ):
        with pytest.raises(ValueError, match="dimension mismatch"):
            await long_term.generate_embedding("valid text")


# ---------------------------------------------------------------------------
# Live Integration Test (Uses real downloaded BAAI/bge-m3 model)
# ---------------------------------------------------------------------------

@pytest.mark.live
@pytest.mark.asyncio
async def test_live_embedding_generation():
    """Real live test using BAAI/bge-m3 sentence_transformers provider."""
    text = "customer reported overcharge on quarterly billing cycle"
    emb = await long_term.generate_embedding(text)

    assert isinstance(emb, list)
    assert len(emb) == settings.EMBEDDING_DIM
    assert len(emb) == 1024

    norm = math.sqrt(sum(x * x for x in emb))
    assert 0.99 <= norm <= 1.01  # Normalized unit vector
    assert not all(abs(x) < 1e-9 for x in emb)
