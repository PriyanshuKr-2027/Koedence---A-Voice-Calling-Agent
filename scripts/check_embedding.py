"""Check embedding provider for long-term memory retrieval.

Embeds test phrases:
  1. "my bill is wrong"
  2. "my invoice has an error"
  3. "the weather is sunny"

Prints provider, model, vector length, L2 norm, and pairwise cosines.
Reports exact HTTP status and error body if provider fails.
"""

from __future__ import annotations

import argparse
import asyncio
import math
import os
from pathlib import Path
import sys
from typing import List, Tuple

# Ensure repo root is on sys.path
_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import httpx
from app.core.config import settings


TEST_PHRASES = [
    "my bill is wrong",
    "my invoice has an error",
    "the weather is sunny",
]


def l2_norm(vec: List[float]) -> float:
    return math.sqrt(sum(x * x for x in vec))


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = l2_norm(v1)
    norm2 = l2_norm(v2)
    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0
    return dot / (norm1 * norm2)


async def check_groq_embedding(model: str = "nomic-embed-text-v1_5") -> Tuple[bool, List[List[float]], str]:
    api_key = settings.GROQ_API_KEY or os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        return False, [], "GROQ_API_KEY is not set."

    url = "https://api.groq.com/openai/v1/embeddings"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    vectors = []
    async with httpx.AsyncClient(timeout=20.0) as client:
        for phrase in TEST_PHRASES:
            try:
                res = await client.post(url, headers=headers, json={"input": phrase, "model": model})
                if res.status_code != 200:
                    return False, [], f"Status: {res.status_code}\nBody: {res.text}"
                data = res.json()
                emb = data.get("data", [{}])[0].get("embedding", [])
                vectors.append(emb)
            except Exception as e:
                return False, [], f"Request exception: {e}"
    return True, vectors, "Success"


async def check_openai_embedding(model: str = "text-embedding-3-small") -> Tuple[bool, List[List[float]], str]:
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return False, [], "OPENAI_API_KEY is not set."

    url = "https://api.openai.com/v1/embeddings"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    vectors = []
    async with httpx.AsyncClient(timeout=20.0) as client:
        for phrase in TEST_PHRASES:
            try:
                res = await client.post(url, headers=headers, json={"input": phrase, "model": model})
                if res.status_code != 200:
                    return False, [], f"Status: {res.status_code}\nBody: {res.text}"
                data = res.json()
                emb = data.get("data", [{}])[0].get("embedding", [])
                vectors.append(emb)
            except Exception as e:
                return False, [], f"Request exception: {e}"
    return True, vectors, "Success"


def check_sentence_transformers(model_name: str = "BAAI/bge-m3") -> Tuple[bool, List[List[float]], str]:
    try:
        from sentence_transformers import SentenceTransformer
        print(f"Loading SentenceTransformer model '{model_name}'...")
        st_model = SentenceTransformer(model_name)
        embeddings = st_model.encode(TEST_PHRASES, normalize_embeddings=True)
        vectors = [emb.tolist() for emb in embeddings]
        return True, vectors, "Success"
    except Exception as e:
        return False, [], f"SentenceTransformer error: {e}"


async def main_async(provider: str, model: str) -> None:
    print("=" * 70)
    print("VoCall Embedding Check (Step 0)")
    print("=" * 70)
    print(f"Testing provider: {provider}")
    print(f"Testing model:    {model}")
    print(f"Phrases to embed:")
    for i, p in enumerate(TEST_PHRASES, 1):
        print(f"  [{i}] {p}")
    print("-" * 70)

    success = False
    vectors: List[List[float]] = []
    msg = ""

    if provider == "groq":
        success, vectors, msg = await check_groq_embedding(model=model)
    elif provider == "openai":
        success, vectors, msg = await check_openai_embedding(model=model)
    elif provider == "sentence_transformers":
        success, vectors, msg = check_sentence_transformers(model_name=model)
    else:
        print(f"Unknown provider: {provider}")
        sys.exit(1)

    if not success:
        print(f"\nEmbedding failed with provider '{provider}':")
        print(msg)
        return

    print("\nEmbedding succeeded!")
    for i, (phrase, vec) in enumerate(zip(TEST_PHRASES, vectors), 1):
        norm = l2_norm(vec)
        print(f"Phrase [{i}]: \"{phrase}\"")
        print(f"  Vector length: {len(vec)}")
        print(f"  L2 norm:       {norm:.6f}")

    sim_1_2 = cosine_similarity(vectors[0], vectors[1])
    sim_1_3 = cosine_similarity(vectors[0], vectors[2])
    sim_2_3 = cosine_similarity(vectors[1], vectors[2])

    print("-" * 70)
    print("Pairwise Cosine Similarities:")
    print(f"  cos([1] bill,    [2] invoice): {sim_1_2:.4f}  (related billing query)")
    print(f"  cos([1] bill,    [3] weather): {sim_1_3:.4f}  (unrelated topic)")
    print(f"  cos([2] invoice, [3] weather): {sim_2_3:.4f}  (unrelated topic)")
    print("-" * 70)

    if sim_1_2 > sim_1_3 and sim_1_2 > sim_2_3 and sim_1_2 > 0.5:
        print("PASS: Related pair has clearly higher cosine similarity than unrelated pairs.")
    else:
        print("WARN: Similarity gap is not clearly distinguished.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Check Embedding Provider")
    parser.add_argument(
        "--provider",
        choices=["groq", "openai", "sentence_transformers"],
        default="groq",
        help="Embedding provider to test (default: groq, as currently in long_term.py)",
    )
    parser.add_argument(
        "--model",
        default="",
        help="Model name (defaults: groq -> nomic-embed-text-v1_5, openai -> text-embedding-3-small, sentence_transformers -> BAAI/bge-m3)",
    )
    args = parser.parse_args()

    model = args.model
    if not model:
        if args.provider == "groq":
            model = "nomic-embed-text-v1_5"
        elif args.provider == "openai":
            model = "text-embedding-3-small"
        elif args.provider == "sentence_transformers":
            model = "BAAI/bge-m3"

    asyncio.run(main_async(provider=args.provider, model=model))


if __name__ == "__main__":
    main()
