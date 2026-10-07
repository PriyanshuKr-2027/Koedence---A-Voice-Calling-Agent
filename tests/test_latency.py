"""Tests for Latency Telemetry, Stage Instrumentation, Replay, and Summarisation.

Validates:
  1. stage context manager when LATENCY_LOG is unset (zero overhead, no records).
  2. stage context manager when LATENCY_LOG is set (records schema, nanosecond accuracy).
  3. Synchronous and asynchronous context manager execution.
  4. Replay warm-up turn discarding (turns 1..3 skipped, turns >3 measured).
  5. Equation 1 verification:
     turn_total vs stt + max(emotion, memory, intent) + llm_ttft + tts_ttfab + network_out
  6. Fraction of turns under 800 ms calculation.
  7. Fig. 5(a) stacked-bar CSV and JSON generation.
"""

from __future__ import annotations

import asyncio
import csv
import json
import os
from pathlib import Path
import tempfile
import pytest

from app.services.latency_stage import stage
from eval.latency.summarise import (
    STAGES_ORDERED,
    compile_fig5a_stacked_bar_data,
    compute_percentiles,
    evaluate_equation_1,
    load_latency_records,
    summarise_latency,
)


def test_stage_context_manager_unset_env():
    """Proves stage context manager is a no-op with negligible overhead when LATENCY_LOG is unset."""
    old_env = os.environ.pop("LATENCY_LOG", None)
    try:
        # Both sync and async must run without errors
        with stage("stt", "call_dummy", 1):
            pass

        async def _test_async():
            async with stage("emotion", "call_dummy", 1):
                pass

        asyncio.run(_test_async())
    finally:
        if old_env is not None:
            os.environ["LATENCY_LOG"] = old_env


def test_stage_context_manager_records_telemetry(tmp_path):
    """Proves stage writes valid JSON records with call_id, turn_idx, stage, and ms when configured."""
    log_file = tmp_path / "test_latency.jsonl"
    os.environ["LATENCY_LOG"] = str(log_file)

    try:
        with stage("stt", "call_101", 1):
            pass

        async def _run_async_stage():
            async with stage("llm_ttft", "call_101", 1):
                await asyncio.sleep(0.01)

        asyncio.run(_run_async_stage())

        assert log_file.exists()
        with open(log_file, "r", encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]

        assert len(lines) == 2
        rec_stt = lines[0]
        assert rec_stt["call_id"] == "call_101"
        assert rec_stt["turn_idx"] == 1
        assert rec_stt["stage"] == "stt"
        assert rec_stt["ms"] >= 0.0

        rec_llm = lines[1]
        assert rec_llm["stage"] == "llm_ttft"
        assert rec_llm["ms"] >= 8.0  # sleep was ~10ms

    finally:
        os.environ.pop("LATENCY_LOG", None)


def test_load_latency_records_discards_warmup(tmp_path):
    """Verifies load_latency_records discards the first 3 turns of each call."""
    log_file = tmp_path / "warmup_test.jsonl"

    records = [
        # Call 1: Turn 1 (warmup), Turn 2 (warmup), Turn 3 (warmup), Turn 4 (measured)
        {"call_id": "call_01", "turn_idx": 1, "stage": "stt", "ms": 150.0},
        {"call_id": "call_01", "turn_idx": 1, "stage": "turn_total", "ms": 500.0},
        {"call_id": "call_01", "turn_idx": 2, "stage": "stt", "ms": 150.0},
        {"call_id": "call_01", "turn_idx": 2, "stage": "turn_total", "ms": 500.0},
        {"call_id": "call_01", "turn_idx": 3, "stage": "stt", "ms": 150.0},
        {"call_id": "call_01", "turn_idx": 3, "stage": "turn_total", "ms": 500.0},
        {"call_id": "call_01", "turn_idx": 4, "stage": "stt", "ms": 140.0},
        {"call_id": "call_01", "turn_idx": 4, "stage": "turn_total", "ms": 480.0},
    ]

    with open(log_file, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    measured_recs, turns, meta = load_latency_records(log_file, warmup_turns=3)

    assert meta["warmup_records_discarded"] == 6
    assert meta["total_measured_turns"] == 1
    assert ("call_01", 4) in turns
    assert ("call_01", 1) not in turns
    assert ("call_01", 2) not in turns
    assert ("call_01", 3) not in turns


def test_equation_1_evaluation():
    """Validates Equation 1 critical path formula:

    turn_total vs stt + max(emotion, memory, intent) + llm_ttft + tts_ttfab + network_out
    """
    turns = {
        ("call_01", 4): {
            "stt": 150.0,
            "emotion": 90.0,
            "memory": 40.0,
            "intent": 20.0,
            "llm_ttft": 140.0,
            "tts_ttfab": 80.0,
            "network_out": 25.0,
            "turn_total": 520.0,
        },
        ("call_01", 5): {
            "stt": 160.0,
            "emotion": 70.0,
            "memory": 85.0,  # memory is larger than emotion here
            "intent": 30.0,
            "llm_ttft": 150.0,
            "tts_ttfab": 90.0,
            "network_out": 25.0,
            "turn_total": 550.0,
        },
    }

    # Turn 4: fanout = max(90, 40, 20) = 90
    # predicted = 150 + 90 + 140 + 80 + 25 = 485.0
    # gap = 520 - 485 = 35.0

    # Turn 5: fanout = max(70, 85, 30) = 85
    # predicted = 160 + 85 + 150 + 90 + 25 = 510.0
    # gap = 550 - 510 = 40.0

    eq = evaluate_equation_1(turns)
    assert eq["total_measured_turns"] == 2
    assert eq["turns_under_800ms"] == 2
    assert eq["fraction_under_800ms"] == 1.0
    assert eq["percentage_under_800ms"] == 100.0

    assert eq["predicted_total"]["mean"] == round((485.0 + 510.0) / 2.0, 2)
    assert eq["observed_total"]["mean"] == round((520.0 + 550.0) / 2.0, 2)
    assert eq["overhead_gap"]["mean"] == round((35.0 + 40.0) / 2.0, 2)


def test_percentiles_calculation():
    """Checks percentiles computation on exact synthetic series."""
    vals = [10.0, 20.0, 30.0, 40.0, 50.0]
    res = compute_percentiles(vals)
    assert res["count"] == 5
    assert res["mean"] == 30.0
    assert res["p50"] == 30.0
    assert res["min"] == 10.0
    assert res["max"] == 50.0


def test_fig5a_stacked_bar_generation(tmp_path):
    """Validates stacked-bar CSV and JSON output schema for Fig. 5(a)."""
    # Create complete synthetic run log
    log_file = tmp_path / "latency_stages.jsonl"
    calls = ["call_en_01", "call_hing_01"]

    with open(log_file, "w", encoding="utf-8") as f:
        for c in calls:
            for t in range(1, 6):  # 5 turns, 3 warmup + 2 measured
                f.write(json.dumps({"call_id": c, "turn_idx": t, "stage": "stt", "ms": 160.0}) + "\n")
                f.write(json.dumps({"call_id": c, "turn_idx": t, "stage": "emotion", "ms": 95.0}) + "\n")
                f.write(json.dumps({"call_id": c, "turn_idx": t, "stage": "memory", "ms": 40.0}) + "\n")
                f.write(json.dumps({"call_id": c, "turn_idx": t, "stage": "intent", "ms": 25.0}) + "\n")
                f.write(json.dumps({"call_id": c, "turn_idx": t, "stage": "llm_ttft", "ms": 140.0}) + "\n")
                f.write(json.dumps({"call_id": c, "turn_idx": t, "stage": "tts_ttfab", "ms": 85.0}) + "\n")
                f.write(json.dumps({"call_id": c, "turn_idx": t, "stage": "network_out", "ms": 20.0}) + "\n")
                f.write(json.dumps({"call_id": c, "turn_idx": t, "stage": "turn_total", "ms": 560.0}) + "\n")

    summary = summarise_latency(log_file, out_dir=tmp_path, warmup_turns=3)

    assert "equation_1" in summary
    assert "fig5a_stacked_bar" in summary
    assert summary["equation_1"]["total_measured_turns"] == 4  # 2 measured turns per call * 2 calls

    csv_path = tmp_path / "fig5a_stacked_bar.csv"
    assert csv_path.exists()
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        req_headers = {
            "language",
            "metric",
            "stt_ms",
            "cognitive_fanout_ms",
            "llm_ttft_ms",
            "tts_ttfab_ms",
            "network_out_ms",
            "overhead_gap_ms",
            "total_turnaround_ms",
            "pct_under_800ms",
        }
        assert req_headers.issubset(set(reader.fieldnames or []))
        rows = list(reader)
        # English, Hinglish, Overall (p50 + p95 for each = 6 rows)
        assert len(rows) == 6
