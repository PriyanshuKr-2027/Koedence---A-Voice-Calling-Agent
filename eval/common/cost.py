"""VoCall Call Cost and Latency Tracker.

Logs input tokens, output tokens, wall time, and estimated financial cost per API call.
Supports Groq LLMs, Whisper, Hume emotion TTS, Sarvam STT/TTS, and Cartesia Sonic-2.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from typing import Any, Dict, Iterator, List, Optional, Union

# Model pricing rates in USD: (input_cost_per_1m_tokens, output_cost_per_1m_tokens)
# Or per-unit estimates where applicable.
MODEL_PRICING: Dict[str, Dict[str, float]] = {
    # Groq LLMs
    "llama-3.3-70b-versatile": {"input_per_m": 0.59, "output_per_m": 0.79},
    "llama-3.1-8b-instant": {"input_per_m": 0.05, "output_per_m": 0.08},
    "llama-3.1-70b-versatile": {"input_per_m": 0.59, "output_per_m": 0.79},
    "mixtral-8x7b-32768": {"input_per_m": 0.24, "output_per_m": 0.24},
    # Embeddings
    "nomic-embed-text-v1_5": {"input_per_m": 0.10, "output_per_m": 0.0},
    "text-embedding-3-small": {"input_per_m": 0.02, "output_per_m": 0.0},
    # Audio STT / TTS fallback rates
    "whisper-large-v3": {"input_per_m": 0.10, "output_per_m": 0.0},
    "saarika:v2": {"input_per_m": 0.10, "output_per_m": 0.0},
    "sonic-2": {"input_per_m": 0.10, "output_per_m": 0.0},
}


def estimate_call_cost(
    model: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
) -> float:
    """Estimates financial cost in USD from token counts."""
    pricing = MODEL_PRICING.get(model.lower())
    if not pricing:
        return 0.0
    in_cost = (prompt_tokens / 1_000_000.0) * pricing.get("input_per_m", 0.0)
    out_cost = (completion_tokens / 1_000_000.0) * pricing.get("output_per_m", 0.0)
    return round(in_cost + out_cost, 6)


class CallRecord:
    """Stores token count, execution latency, and cost for a single invocation."""

    def __init__(
        self,
        provider: str,
        model: str,
        wall_time_s: float,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cost_usd: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.provider = provider
        self.model = model
        self.wall_time_s = round(float(wall_time_s), 4)
        self.prompt_tokens = int(prompt_tokens)
        self.completion_tokens = int(completion_tokens)
        self.total_tokens = self.prompt_tokens + self.completion_tokens
        self.cost_usd = (
            round(float(cost_usd), 6)
            if cost_usd is not None
            else estimate_call_cost(model, self.prompt_tokens, self.completion_tokens)
        )
        self.metadata = metadata or {}
        self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "wall_time_s": self.wall_time_s,
            "cost_usd": self.cost_usd,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


class CostTracker:
    """Aggregates cost and latency records across an evaluation run."""

    def __init__(self):
        self.records: List[CallRecord] = []

    def log(
        self,
        provider: str,
        model: str,
        wall_time_s: float,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cost_usd: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> CallRecord:
        """Records metrics for an individual call."""
        record = CallRecord(
            provider=provider,
            model=model,
            wall_time_s=wall_time_s,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost_usd,
            metadata=metadata,
        )
        self.records.append(record)
        return record

    @contextmanager
    def track(
        self,
        provider: str,
        model: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Iterator[_CallTrackerScope]:
        """Context manager to measure wall time and accept token logs."""
        scope = _CallTrackerScope(provider=provider, model=model, metadata=metadata)
        start_t = time.perf_counter()
        try:
            yield scope
        finally:
            elapsed = time.perf_counter() - start_t
            record = self.log(
                provider=provider,
                model=model,
                wall_time_s=elapsed,
                prompt_tokens=scope.prompt_tokens,
                completion_tokens=scope.completion_tokens,
                cost_usd=scope.cost_usd,
                metadata=scope.metadata,
            )
            scope.record = record

    def summary(self) -> Dict[str, Any]:
        """Returns aggregate totals and averages."""
        if not self.records:
            return {
                "total_calls": 0,
                "total_prompt_tokens": 0,
                "total_completion_tokens": 0,
                "total_tokens": 0,
                "total_cost_usd": 0.0,
                "total_wall_time_s": 0.0,
                "mean_wall_time_s": 0.0,
            }

        prompt_tot = sum(r.prompt_tokens for r in self.records)
        comp_tot = sum(r.completion_tokens for r in self.records)
        wall_tot = sum(r.wall_time_s for r in self.records)
        cost_tot = sum(r.cost_usd for r in self.records)

        return {
            "total_calls": len(self.records),
            "total_prompt_tokens": prompt_tot,
            "total_completion_tokens": comp_tot,
            "total_tokens": prompt_tot + comp_tot,
            "total_cost_usd": round(cost_tot, 6),
            "total_wall_time_s": round(wall_tot, 4),
            "mean_wall_time_s": round(wall_tot / len(self.records), 4),
        }

    def save(self, path: Union[str, Path]) -> None:
        """Writes all records and summary to a JSON file."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "summary": self.summary(),
            "calls": [r.to_dict() for r in self.records],
        }
        with open(target, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)


class _CallTrackerScope:
    """Internal scope helper for tracking context manager."""

    def __init__(self, provider: str, model: str, metadata: Optional[Dict[str, Any]] = None):
        self.provider = provider
        self.model = model
        self.metadata = metadata or {}
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.cost_usd: Optional[float] = None
        self.record: Optional[CallRecord] = None

    def set_tokens(self, prompt_tokens: int = 0, completion_tokens: int = 0) -> None:
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens

    def set_cost(self, cost_usd: float) -> None:
        self.cost_usd = cost_usd


# Alias TokenTracker to CostTracker for unified API
TokenTracker = CostTracker

# Module-level default tracker
global_tracker = CostTracker()


def log_call(
    provider: str,
    model: str,
    wall_time_s: float,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    cost_usd: Optional[float] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> CallRecord:
    """Module-level helper to log an API call to the global tracker."""
    return global_tracker.log(
        provider=provider,
        model=model,
        wall_time_s=wall_time_s,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=cost_usd,
        metadata=metadata,
    )
