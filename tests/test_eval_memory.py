"""Tests for VoCall memory ablation evaluation and judge agreement checker.

Tests run offline without network or external services using stub mode.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
import sys
import pytest

# Ensure repo root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from eval.memory.judge_check import evaluate_human_judge_agreement, export_judge_samples_for_review
from eval.memory.run_ablation import CONFIGURATIONS, run_ablation_experiment


@pytest.mark.asyncio
async def test_run_ablation_stub_mode(tmp_path):
    """Verifies that run_ablation runs offline in stub mode with expected outputs."""
    out_dir = tmp_path / "ablation_results"

    manifest = await run_ablation_experiment(
        config_path="eval/config.yaml",
        out_dir=str(out_dir),
        limit=1,
        stub_mode=True,
        seed_override=42,
    )

    # 1. Output files exist
    raw_file = out_dir / "raw.jsonl"
    metrics_file = out_dir / "metrics.json"
    table_v_file = out_dir / "table_v.csv"

    assert raw_file.exists()
    assert metrics_file.exists()
    assert table_v_file.exists()

    # 2. Check raw.jsonl schema
    with open(raw_file, "r", encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]

    assert len(records) > 0
    configs_found = set()
    for r in records:
        assert "seed" in r
        assert "config" in r
        assert "dataset" in r
        assert "sample_id" in r
        assert "question" in r
        assert "gold_answer" in r
        assert "candidate_answer" in r
        assert "is_correct" in r
        assert "prompt_tokens" in r
        assert "retrieval_ms" in r
        configs_found.add(r["config"])

    for cfg in CONFIGURATIONS.keys():
        assert cfg in configs_found

    # 3. Check metrics.json schema
    with open(metrics_file, "r", encoding="utf-8") as f:
        metrics = json.load(f)

    assert "configurations" in metrics
    for cfg in CONFIGURATIONS.keys():
        cfg_m = metrics["configurations"][cfg]
        assert "accuracy_d1" in cfg_m
        assert "accuracy_d2" in cfg_m
        assert "recall_at_5" in cfg_m
        assert "tokens_per_call" in cfg_m
        assert "retrieval_ms" in cfg_m
        assert "question_type_accuracy" in cfg_m

    assert "consecutive_paired_differences" in metrics

    # 4. Check table_v.csv columns and rows
    with open(table_v_file, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        expected_header = ["Configuration", "Accuracy D1", "Accuracy D2", "Recall@5", "Tokens per Call", "Retrieval ms"]
        assert header[:6] == expected_header
        assert "MOCK DATA" in header

        rows = list(reader)
        row_cfgs = [row[0] for row in rows]
        assert row_cfgs == list(CONFIGURATIONS.keys())

    # 5. Check judge_check.py export
    review_csv = out_dir / "judge_review.csv"
    exported_count = export_judge_samples_for_review(
        raw_jsonl_path=raw_file,
        out_csv_path=review_csv,
        sample_size=10,
        seed=42,
    )
    assert exported_count > 0
    assert review_csv.exists()

    # Verify review CSV columns
    with open(review_csv, "r", encoding="utf-8") as f:
        c_reader = csv.DictReader(f)
        review_rows = list(c_reader)
        assert len(review_rows) == exported_count
        assert "human_label" in review_rows[0]
        assert review_rows[0]["human_label"] == ""  # Empty for human labeling

    # 6. Check judge_check.py evaluation on annotated CSV
    annotated_csv = out_dir / "annotated_review.csv"
    with open(annotated_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=review_rows[0].keys())
        writer.writeheader()
        for i, row in enumerate(review_rows):
            # Simulate human label agreeing with judge 80% of the time
            verdict = row["judge_verdict"]
            row["human_label"] = verdict if (i % 5 != 0) else (1 if verdict == "0" else 0)
            writer.writerow(row)

    agreement_res = evaluate_human_judge_agreement(annotated_csv)
    assert agreement_res["annotated_count"] == exported_count
    assert agreement_res["agreement_rate"] >= 0.7
    assert agreement_res["cohen_kappa"] is not None
