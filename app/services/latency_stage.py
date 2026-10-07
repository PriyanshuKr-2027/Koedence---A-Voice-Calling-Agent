"""Low-overhead latency stage instrumentation.

Provides a context manager stage(name, call_id, turn_idx) that records
wall-clock duration in milliseconds with nanosecond precision.
When the environment variable LATENCY_LOG is set, appends JSON records to that path.
When LATENCY_LOG is unset or empty, executes with negligible overhead.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Optional


def _append_record(path: str, record: dict[str, Any]) -> None:
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
    except Exception:
        pass


class stage:
    """Context manager measuring execution latency per pipeline stage.

    Supports both synchronous ('with stage(...)') and asynchronous ('async with stage(...)').
    Appends {"call_id": ..., "turn_idx": ..., "stage": ..., "ms": ...} to LATENCY_LOG.
    """

    __slots__ = ("name", "call_id", "turn_idx", "log_path", "t0")

    def __init__(self, name: str, call_id: str, turn_idx: int) -> None:
        self.name = name
        self.call_id = call_id
        self.turn_idx = turn_idx
        self.log_path: Optional[str] = os.environ.get("LATENCY_LOG")
        self.t0: int = 0

    def __enter__(self) -> "stage":
        if self.log_path:
            self.t0 = time.perf_counter_ns()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self.log_path and self.t0:
            t1 = time.perf_counter_ns()
            ms = round((t1 - self.t0) / 1_000_000.0, 3)
            record = {
                "call_id": str(self.call_id),
                "turn_idx": int(self.turn_idx),
                "stage": str(self.name),
                "ms": ms,
            }
            _append_record(self.log_path, record)

    async def __aenter__(self) -> "stage":
        return self.__enter__()

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.__exit__(exc_type, exc_val, exc_tb)
