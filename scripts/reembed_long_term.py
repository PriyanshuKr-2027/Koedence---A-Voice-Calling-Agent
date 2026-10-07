"""Batch Re-embedding Utility for Long-Term Memory (memory_long_term).

Queries rows in public.memory_long_term with NULL embeddings,
generates vectors via app.services.memory.long_term.generate_embedding,
and updates each row in batches.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path
import sys

# Ensure repository root is on sys.path
_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.core.config import settings
from app.services.memory.long_term import generate_embedding
from app.services.supabase_client import supabase

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


async def reembed_batch(batch_size: int = 50, max_rows: int = 0) -> int:
    if not supabase:
        logger.error("Supabase client is not configured. Check NEXT_PUBLIC_SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")
        sys.exit(1)

    total_reembedded = 0
    logger.info(
        "Starting re-embedding with provider=%s, model=%s, dim=%d",
        settings.EMBEDDING_PROVIDER,
        settings.EMBEDDING_MODEL,
        settings.EMBEDDING_DIM,
    )

    while True:
        limit = batch_size
        if max_rows > 0:
            remaining = max_rows - total_reembedded
            if remaining <= 0:
                break
            limit = min(batch_size, remaining)

        res = (
            supabase.table("memory_long_term")
            .select("id, content")
            .is_("embedding", "null")
            .limit(limit)
            .execute()
        )

        rows = res.data or []
        if not rows:
            logger.info("No more rows with NULL embedding found.")
            break

        logger.info("Processing batch of %d rows...", len(rows))
        for row in rows:
            row_id = row["id"]
            content = row.get("content", "")
            if not content.strip():
                logger.warning("Row %s has empty content; skipping.", row_id)
                continue

            try:
                emb = await generate_embedding(content)
                supabase.table("memory_long_term").update({"embedding": emb}).eq("id", row_id).execute()
                total_reembedded += 1
            except Exception as exc:
                logger.error("Failed to re-embed row %s: %s", row_id, exc)

        logger.info("Progress: %d rows re-embedded so far.", total_reembedded)

    logger.info("Completed re-embedding. Total rows processed: %d", total_reembedded)
    return total_reembedded


def main() -> None:
    parser = argparse.ArgumentParser(description="Re-embed rows with NULL embedding in memory_long_term")
    parser.add_argument("--batch-size", type=int, default=50, help="Batch size for fetching rows (default: 50)")
    parser.add_argument("--max-rows", type=int, default=0, help="Maximum rows to process (0 = all, default: 0)")
    args = parser.parse_args()

    asyncio.run(reembed_batch(batch_size=args.batch_size, max_rows=args.max_rows))


if __name__ == "__main__":
    main()
