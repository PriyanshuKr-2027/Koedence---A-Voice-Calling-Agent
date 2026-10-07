"""Inter-Annotator Agreement and Gold Label Adjudication Tool.

Computes unweighted Cohen's Kappa for categorical emotion labels
and quadratic-weighted Cohen's Kappa for valence scores on dataset D3.
Writes adjudicated gold label file, flagging disagreements for manual resolution.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Any, Dict, List, Tuple, Union
import yaml

from eval.common.stats import cohen_kappa


def map_valence_5point_to_unit(v: Union[int, float, str]) -> float:
    """
    Maps 5-point discrete valence scale [1, 2, 3, 4, 5] to continuous interval [-1.0, 1.0].
      1 -> -1.0 (strongly negative / angry / frustrated)
      2 -> -0.5 (mildly negative / irritated)
      3 ->  0.0 (neutral)
      4 ->  0.5 (mildly positive / pleased)
      5 ->  1.0 (strongly positive / delighted)
    If value is already float within [-1.0, 1.0], returns clamped value.
    """
    f_val = float(v)
    if -1.0 <= f_val <= 1.0 and not (1.0 <= f_val <= 5.0 and f_val.is_integer()):
        return max(-1.0, min(1.0, f_val))
    # Map 1..5 to -1.0..1.0
    mapped = (f_val - 3.0) / 2.0
    return max(-1.0, min(1.0, round(mapped, 3)))


def map_unit_to_5point(v: float) -> int:
    """Inversely maps continuous valence [-1.0, 1.0] to discrete 5-point integer scale [1..5]."""
    discrete = round(v * 2.0 + 3.0)
    return int(max(1, min(5, discrete)))


def compute_inter_annotator_agreement(
    labels_csv_path: Union[str, Path] = "eval/data/d3/labels.csv",
    out_adjudicated_path: Union[str, Path] = "eval/data/d3/gold_labels.csv",
    config_path: Union[str, Path] = "eval/config.yaml",
) -> Dict[str, Any]:
    """
    Loads labels.csv, computes unweighted and quadratic-weighted Cohen's Kappa,
    and writes adjudicated gold label file with disagreement flags.
    """
    in_p = Path(labels_csv_path)
    if not in_p.exists():
        raise FileNotFoundError(f"Input labels file not found: {in_p}")

    rows: List[Dict[str, Any]] = []
    with open(in_p, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)

    if not rows:
        raise ValueError("Input labels file contains no records")

    ann1_cats: List[str] = []
    ann2_cats: List[str] = []
    ann1_val_discrete: List[int] = []
    ann2_val_discrete: List[int] = []

    adjudicated_rows: List[Dict[str, Any]] = []
    disagreement_count = 0

    for r in rows:
        cat1 = str(r["annotator_1_label"]).strip().lower()
        cat2 = str(r["annotator_2_label"]).strip().lower()

        # Parse valences
        v1_raw = float(r["annotator_1_valence"])
        v2_raw = float(r["annotator_2_valence"])

        v1_discrete = int(round(v1_raw)) if 1.0 <= v1_raw <= 5.0 else map_unit_to_5point(v1_raw)
        v2_discrete = int(round(v2_raw)) if 1.0 <= v2_raw <= 5.0 else map_unit_to_5point(v2_raw)

        v1_mapped = map_valence_5point_to_unit(v1_raw)
        v2_mapped = map_valence_5point_to_unit(v2_raw)

        ann1_cats.append(cat1)
        ann2_cats.append(cat2)
        ann1_val_discrete.append(v1_discrete)
        ann2_val_discrete.append(v2_discrete)

        is_agreed = (cat1 == cat2)
        if not is_agreed:
            disagreement_count += 1

        # Gold label: consensus if agreed, otherwise annotator 1 with flag for manual check
        gold_label = cat1 if is_agreed else (r.get("adjudicated_label") or cat1)
        gold_valence = round((v1_mapped + v2_mapped) / 2.0, 3)

        adjudicated_rows.append({
            "clip_id": r.get("clip_id", ""),
            "audio_path": r.get("audio_path", ""),
            "transcript": r.get("transcript", ""),
            "gold_label": gold_label,
            "gold_valence": gold_valence,
            "annotator_1_label": cat1,
            "annotator_1_valence": v1_mapped,
            "annotator_2_label": cat2,
            "annotator_2_valence": v2_mapped,
            "agreement": is_agreed,
            "needs_adjudication": not is_agreed,
        })

    # 1. Unweighted Cohen's Kappa for categorical emotion labels
    kappa_categorical = cohen_kappa(ann1_cats, ann2_cats)

    # 2. Quadratic-weighted Cohen's Kappa for ordinal valence ratings
    kappa_valence = cohen_kappa(ann1_val_discrete, ann2_val_discrete, weights="quadratic")

    # Write adjudicated gold file
    out_p = Path(out_adjudicated_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "clip_id",
        "audio_path",
        "transcript",
        "gold_label",
        "gold_valence",
        "annotator_1_label",
        "annotator_1_valence",
        "annotator_2_label",
        "annotator_2_valence",
        "agreement",
        "needs_adjudication",
    ]

    with open(out_p, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(adjudicated_rows)

    print("=" * 65)
    print("DATASET D3: INTER-ANNOTATOR RELIABILITY")
    print("=" * 65)
    print(f"Total Evaluated Clips:             {len(rows)}")
    print(f"Categorical Disagreements:         {disagreement_count} ({(disagreement_count / len(rows)) * 100:.1f}%)")
    print(f"Cohen's Kappa (Categorical):       {kappa_categorical:.4f}")
    print(f"Cohen's Kappa (Valence Quadratic): {kappa_valence:.4f}")
    print(f"Adjudicated Gold File Written to:  {out_p}")
    print("=" * 65)

    return {
        "total_clips": len(rows),
        "disagreements": disagreement_count,
        "cohen_kappa_categorical": round(kappa_categorical, 4),
        "cohen_kappa_valence_quadratic": round(kappa_valence, 4),
        "out_file": str(out_p),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute Cohen's Kappa and Adjudicate Gold Emotion Labels")
    parser.add_argument("--input", default="eval/data/d3/labels.csv", help="Path to input labels.csv")
    parser.add_argument("--out", default="eval/data/d3/gold_labels.csv", help="Path to write adjudicated gold file")
    parser.add_argument("--config", default="eval/config.yaml", help="Path to config file")
    args = parser.parse_args()

    compute_inter_annotator_agreement(
        labels_csv_path=args.input,
        out_adjudicated_path=args.out,
        config_path=args.config,
    )


if __name__ == "__main__":
    main()
