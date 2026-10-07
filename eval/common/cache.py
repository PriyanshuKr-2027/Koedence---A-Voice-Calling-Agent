"""VoCall API Call Disk Cache.

Provides a persistent disk cache keyed by sha256 of (provider, model, input).
Prevents repeated paid external API calls (Groq LLM, judge model, Hume AI, Sarvam STT, Cartesia TTS).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Optional, Union


def compute_cache_key(provider: str, model: str, input_payload: Any) -> str:
    """
    Computes deterministic SHA-256 hash for (provider, model, input).

    Handles bytes (e.g. raw audio for STT), strings, lists, and dicts.
    """
    prov_str = str(provider).strip().lower()
    mod_str = str(model).strip().lower()

    if isinstance(input_payload, bytes):
        payload_repr = {"_type": "bytes", "sha256": hashlib.sha256(input_payload).hexdigest(), "length": len(input_payload)}
    elif isinstance(input_payload, (dict, list, tuple)):
        payload_repr = input_payload
    else:
        payload_repr = str(input_payload)

    canonical = json.dumps(
        [prov_str, mod_str, payload_repr],
        sort_keys=True,
        ensure_ascii=True,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class DiskCache:
    """Persistent filesystem cache for API responses."""

    def __init__(self, cache_dir: Union[str, Path] = ".eval_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _entry_path(self, provider: str, cache_key: str) -> Path:
        safe_provider = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in provider.lower())
        provider_dir = self.cache_dir / safe_provider
        provider_dir.mkdir(parents=True, exist_ok=True)
        return provider_dir / f"{cache_key}.json"

    def has(self, provider: str, model: str, input_payload: Any) -> bool:
        """Checks if a response is already cached."""
        key = compute_cache_key(provider, model, input_payload)
        return self._entry_path(provider, key).exists()

    def get(self, provider: str, model: str, input_payload: Any) -> Optional[Any]:
        """Retrieves cached response if present, otherwise None."""
        key = compute_cache_key(provider, model, input_payload)
        path = self._entry_path(provider, key)
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("response")
        except Exception:
            return None

    def set(self, provider: str, model: str, input_payload: Any, response: Any) -> str:
        """
        Stores response to disk cache atomically.

        Returns:
            str: SHA-256 cache key.
        """
        key = compute_cache_key(provider, model, input_payload)
        path = self._entry_path(provider, key)
        record = {
            "key": key,
            "provider": provider,
            "model": model,
            "response": response,
            "cached_at": datetime.now(timezone.utc).isoformat(),
        }
        temp_path = path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2, default=str)
        temp_path.replace(path)
        return key

    def cached_call(
        self,
        provider: str,
        model: str,
        input_payload: Any,
        fn: Callable[[], Any],
    ) -> Any:
        """Executes fn only on cache miss; otherwise returns cached response."""
        cached = self.get(provider, model, input_payload)
        if cached is not None:
            return cached
        result = fn()
        self.set(provider, model, input_payload, result)
        return result

    async def cached_call_async(
        self,
        provider: str,
        model: str,
        input_payload: Any,
        coro_fn: Callable[[], Awaitable[Any]],
    ) -> Any:
        """Executes async coroutine only on cache miss; otherwise returns cached response."""
        cached = self.get(provider, model, input_payload)
        if cached is not None:
            return cached
        result = await coro_fn()
        self.set(provider, model, input_payload, result)
        return result


default_cache = DiskCache()


def get_cached(provider: str, model: str, input_payload: Any) -> Optional[Any]:
    return default_cache.get(provider, model, input_payload)


def set_cached(provider: str, model: str, input_payload: Any, response: Any) -> str:
    return default_cache.set(provider, model, input_payload, response)


def cached_call(provider: str, model: str, input_payload: Any, fn: Callable[[], Any]) -> Any:
    return default_cache.cached_call(provider, model, input_payload, fn)


async def cached_call_async(
    provider: str,
    model: str,
    input_payload: Any,
    coro_fn: Callable[[], Awaitable[Any]],
) -> Any:
    return await default_cache.cached_call_async(provider, model, input_payload, coro_fn)
