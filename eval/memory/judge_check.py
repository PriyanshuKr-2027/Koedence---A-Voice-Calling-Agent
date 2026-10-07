"""LLM Judge Quality and Human Agreement Checker.

Samples 50 answers from ablation raw traces (raw.jsonl), exporting them to a CSV
with an empty 'human_label' column for manual grading.
Later computes Cohen's Kappa and percent agreement between judge verdicts and human labels.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import random
from typing import Any, Dict, List, Optional, Union

from eval.common.mode import get_eval_mode, stamp_csv_mock_data
from eval.common.stats import cohen_kappa


def export_judge_samples_for_review(
    raw_jsonl_path: Union[str, Path] = "results/ablation/raw.jsonl",
    out_csv_path: Union[str, Path] = "results/ablation/judge_review.csv",
    sample_size: int = 50,
    seed: int = 42,
    mode: Optional[str] = None,
) -> int:
    """Samples answers and writes them to CSV with empty human_label column."""
    raw_p = Path(raw_jsonl_path)
    if not raw_p.exists():
        raise FileNotFoundError(f"Raw trace file not found: {raw_p}")

    records: List[Dict[str, Any]] = []
    with open(raw_p, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line.strip()))

    if not records:
        raise ValueError("Raw trace file is empty")

    rng = random.Random(seed)
    sampled = rng.sample(records, min(sample_size, len(records)))

    out_p = Path(out_csv_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    fields = [
        "sample_id",
        "dataset",
        "config",
        "question",
        "gold_answer",
        "candidate_answer",
        "judge_verdict",
        "human_label",
    ]

    with open(out_p, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for r in sampled:
            writer.writerow({
                "sample_id": r.get("sample_id", ""),
                "dataset": r.get("dataset", ""),
                "config": r.get("config", ""),
                "question": r.get("question", ""),
                "gold_answer": r.get("gold_answer", ""),
                "candidate_answer": r.get("candidate_answer", ""),
                "judge_verdict": 1 if r.get("is_correct") else 0,
                "human_label": "",
            })

    # Check whether mock run
    active_mode = mode or get_eval_mode()
    if active_mode == "mock" or "MOCK_" in str(raw_p) or "MOCK_" in str(out_p):
        stamp_csv_mock_data(out_p, mode="mock")

    print(f"Exported {len(sampled)} items for human review to: {out_p}")
    return len(sampled)


def evaluate_human_judge_agreement(
    reviewed_csv_path: Union[str, Path],
) -> Dict[str, Any]:
    """Computes Cohen's Kappa and percent agreement between judge and human labels."""
    csv_p = Path(reviewed_csv_path)
    if not csv_p.exists():
        raise FileNotFoundError(f"Review CSV not found: {csv_p}")

    judge_labels = []
    human_labels = []

    with open(csv_p, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            h_raw = str(row.get("human_label", "")).strip().lower()
            if h_raw in ("1", "true", "correct", "yes"):
                h_val = 1
            elif h_raw in ("0", "false", "incorrect", "no"):
                h_val = 0
            else:
                continue  # skip unannotated rows

            j_raw = str(row.get("judge_verdict", "")).strip().lower()
            j_val = 1 if j_raw in ("1", "true", "correct", "yes") else 0

            judge_labels.append(j_val)
            human_labels.append(h_val)

    if not human_labels:
        print("No annotated rows found in CSV. Please fill the 'human_label' column first.")
        return {"annotated_count": 0, "cohen_kappa": None, "agreement_rate": None}

    n = len(human_labels)
    agreements = sum(1 for j, h in zip(judge_labels, human_labels) if j == h)
    agreement_rate = round(agreements / float(n), 4)
    kappa = round(cohen_kappa(judge_labels, human_labels), 4)

    print("=" * 60)
    print("LLM JUDGE VS HUMAN ANNOTATOR AGREEMENT")
    print("=" * 60)
    print(f"Annotated Samples: {n}")
    print(f"Agreements:        {agreements}/{n}")
    print(f"Agreement Rate:    {agreement_rate * 100:.1f}%")
    print(f"Cohen's Kappa:     {kappa:.4f}")
    print("=" * 60)

    return {
        "annotated_count": n,
        "agreements": agreements,
        "agreement_rate": agreement_rate,
        "cohen_kappa": kappa,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Judge Quality and Human Agreement Tool")
    parser.add_argument("--raw", default="results/ablation/raw.jsonl", help="Path to raw.jsonl from ablation run")
    parser.add_argument("--out", default="results/ablation/judge_review.csv", help="Output path for export CSV")
    parser.add_argument("--sample-size", type=int, default=50, help="Number of items to sample for human grading")
    parser.add_argument("--evaluate", help="Path to filled review CSV to compute agreement stats")
    parser.add_argument("--seed", type=int, default=42, help="Sampling seed")
    args = parser.parse_args()

    if args.evaluate:
        evaluate_human_judge_agreement(args.evaluate)
    else:
        export_judge_samples_for_review(
            raw_jsonl_path=args.raw,
            out_csv_path=args.out,
            sample_size=args.sample_size,
            seed=args.seed,
        )


if __name__ == "__main__":
    main()
