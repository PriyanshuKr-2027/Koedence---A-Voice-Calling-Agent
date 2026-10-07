"""
VoCall Long-Term Memory Service (pgvector + Supabase).

Manages persistent facts and user preferences attached to contact records:
  - Vector embedding generation (SentenceTransformers / OpenAI API compatible)
  - pgvector cosine similarity retrieval with threshold filtering
  - Deduplicated fact storage per (contact_id, call_id, content)
  - Contact memory deletion
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Dict, List, Optional
import httpx

from app.core.config import settings
from app.services.supabase_client import supabase

logger = logging.getLogger(__name__)

# Global model instance cache for SentenceTransformer
_st_model = None


def get_sentence_transformer_model() -> Any:
    """Lazily loads and caches the configured SentenceTransformer model."""
    global _st_model
    if _st_model is None:
        from sentence_transformers import SentenceTransformer
        logger.info("Loading SentenceTransformer model '%s'...", settings.EMBEDDING_MODEL)
        _st_model = SentenceTransformer(settings.EMBEDDING_MODEL)
    return _st_model


def _encode_sentence_transformer(model: Any, text: str) -> List[float]:
    embedding = model.encode(text, normalize_embeddings=True)
    if hasattr(embedding, "tolist"):
        return embedding.tolist()
    return list(embedding)


async def _generate_openai_embedding(text: str, api_key: str) -> List[float]:
    url = "https://api.openai.com/v1/embeddings"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        res = await client.post(
            url,
            headers=headers,
            json={
                "input": text,
                "model": settings.EMBEDDING_MODEL,
            },
        )
        if res.status_code != 200:
            raise RuntimeError(f"OpenAI embedding error {res.status_code}: {res.text}")
        data = res.json()
        emb = data.get("data", [{}])[0].get("embedding", [])
        return emb


async def generate_embedding(text: str, api_key: Optional[str] = None) -> List[float]:
    """
    Generates an embedding vector for the given text.

    Raises on any failure, empty text, invalid length, or zero vector.
    Never returns a zero vector or falls back silently.
    """
    clean_text = (text or "").strip()
    if not clean_text:
        raise ValueError("Cannot generate embedding for empty or whitespace-only text.")

    provider = (settings.EMBEDDING_PROVIDER or "sentence_transformers").lower().strip()

    if provider == "sentence_transformers":
        model = get_sentence_transformer_model()
        vec = await asyncio.to_thread(_encode_sentence_transformer, model, clean_text)
    elif provider == "openai":
        key = api_key or os.environ.get("OPENAI_API_KEY", "")
        if not key:
            raise RuntimeError("OPENAI_API_KEY is required for 'openai' embedding provider.")
        vec = await _generate_openai_embedding(clean_text, key)
    else:
        raise ValueError(f"Unsupported embedding provider: '{provider}'")

    if not vec or len(vec) != settings.EMBEDDING_DIM:
        raise ValueError(
            f"Embedding dimension mismatch: expected {settings.EMBEDDING_DIM}, got {len(vec) if vec else 0}"
        )

    # Validate non-zero vector
    if all(abs(x) < 1e-9 for x in vec):
        raise ValueError("Generated embedding is an invalid zero vector.")

    return vec


async def store_fact(
    contact_id: str,
    org_id: str,
    agent_id: Optional[str],
    content: str,
    emotion_state: Optional[Dict[str, Any]] = None,
    call_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Embeds content and inserts a new fact into memory_long_term.
    Skips insert if a record with matching (contact_id, call_id, content) already exists.

    Returns the created (or existing) record dict or None on failure.
    """
    if not supabase or not content.strip():
        return None

    if contact_id:
        try:
            from app.services.redis_client import redis_client
            if await redis_client.get(f"erasure:{contact_id}"):
                logger.info("Contact %s has erasure flag set; skipping store_fact", contact_id)
                return None
        except Exception:
            pass

    clean_content = content.strip()

    # Check for existing duplicate fact
    query = (
        supabase.table("memory_long_term")
        .select("id, content, contact_id, org_id, call_id, created_at, emotion_state")
        .eq("contact_id", contact_id)
        .eq("content", clean_content)
    )
    if call_id is not None:
        query = query.eq("call_id", call_id)
    else:
        query = query.is_("call_id", "null")

    existing = query.limit(1).execute()
    if existing.data:
        logger.info(
            "Fact already exists for contact %s, call %s; skipping duplicate insert.",
            contact_id,
            call_id,
        )
        return existing.data[0]

    embedding = await generate_embedding(clean_content)
    payload = {
        "contact_id": contact_id,
        "org_id": org_id,
        "agent_id": agent_id,
        "content": clean_content,
        "embedding": embedding,
        "emotion_state": emotion_state or {},
        "call_id": call_id,
    }
    res = supabase.table("memory_long_term").insert(payload).execute()
    if res.data:
        logger.info(
            "Stored long-term fact for contact %s in org %s (call_id=%s)",
            contact_id,
            org_id,
            call_id,
        )
        return res.data[0]

    return None


async def retrieve_relevant_facts(
    contact_id: str,
    org_id: str,
    query_text: str,
    limit: Optional[int] = None,
    threshold: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """
    Retrieves facts relevant to query_text using cosine similarity match in pgvector.

    - Empty query_text is not embedded; logs and returns [].
    - An empty RPC match result returns [].
    - An RPC exception raises unless settings.ALLOW_RECENCY_FALLBACK is True.
    """
    if not supabase or not contact_id or not org_id:
        return []

    clean_query = (query_text or "").strip()
    if not clean_query:
        logger.info("retrieve_relevant_facts called with empty query_text; returning [].")
        return []

    match_limit = limit if limit is not None else settings.RETRIEVAL_TOP_K
    match_threshold = threshold if threshold is not None else settings.RETRIEVAL_TAU

    query_vector = await generate_embedding(clean_query)

    try:
        rpc_res = supabase.rpc(
            "match_long_term_memories",
            {
                "query_embedding": query_vector,
                "match_threshold": match_threshold,
                "match_count": match_limit,
                "p_contact_id": contact_id,
                "p_org_id": org_id,
            },
        ).execute()
        return rpc_res.data or []
    except Exception as exc:
        if settings.ALLOW_RECENCY_FALLBACK:
            logger.warning(
                "match_long_term_memories RPC failed; ALLOW_RECENCY_FALLBACK is enabled: %s",
                exc,
            )
            res = (
                supabase.table("memory_long_term")
                .select("id, content, emotion_state, created_at")
                .eq("contact_id", contact_id)
                .eq("org_id", org_id)
                .order("created_at", desc=True)
                .limit(match_limit)
                .execute()
            )
            return [
                {
                    "id": row.get("id"),
                    "content": row.get("content", ""),
                    "emotion_state": row.get("emotion_state", {}),
                    "created_at": row.get("created_at"),
                    "similarity": None,
                }
                for row in (res.data or [])
            ]
        else:
            logger.error(
                "match_long_term_memories RPC failed and ALLOW_RECENCY_FALLBACK is False: %s",
                exc,
            )
            raise exc


async def delete_contact_memory(contact_id: str, org_id: str) -> bool:
    """Deletes all long-term memory facts for the specified contact."""
    if not supabase or not contact_id or not org_id:
        return False

    try:
        supabase.table("memory_long_term").delete().eq("contact_id", contact_id).eq("org_id", org_id).execute()
        logger.info("Deleted long-term memory for contact %s in org %s", contact_id, org_id)
        return True
    except Exception as exc:
        logger.error("Failed to delete_contact_memory for contact %s: %s", contact_id, exc)
        return False


async def delete_all(contact_id: str) -> bool:
    """Deletes all long-term memory facts for the specified contact across all organizations."""
    if not supabase or not contact_id:
        return False

    try:
        supabase.table("memory_long_term").delete().eq("contact_id", contact_id).execute()
        logger.info("Deleted all long-term memory for contact %s", contact_id)
        return True
    except Exception as exc:
        logger.error("Failed to delete_all long-term memory for contact %s: %s", contact_id, exc)
        return False
