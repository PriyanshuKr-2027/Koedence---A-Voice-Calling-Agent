"""Realism Review and Question Distribution Checker for Dataset D1.

Samples up to 20 conversation transcripts from calls.jsonl and prints them
for manual realism inspection.
Tallies and displays question counts by question type from questions.jsonl.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import random
from typing import Any, Dict, List, Optional, Union
import yaml


def load_jsonl(file_path: Union[str, Path]) -> List[Dict[str, Any]]:
    """Loads all records from a JSONL file."""
    path = Path(file_path)
    if not path.exists():
        return []
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line_str = line.strip()
            if line_str:
                records.append(json.loads(line_str))
    return records


def run_check_d1(
    data_dir: Union[str, Path] = "eval/data/d1",
    config_path: Optional[Union[str, Path]] = "eval/config.yaml",
    sample_size: int = 20,
    out_dir: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Inspects dataset D1 conversations and tallies question distributions."""
    d_path = Path(data_dir)
    callers = load_jsonl(d_path / "callers.jsonl")
    calls = load_jsonl(d_path / "calls.jsonl")
    questions = load_jsonl(d_path / "questions.jsonl")

    if not callers or not calls or not questions:
        print(f"Error: Dataset files not found in {d_path}. Run gen_d1.py first.")
        return {"status": "missing_data"}

    caller_map = {c["caller_id"]: c for c in callers}

    # Load seed if config exists
    seed = 42
    if config_path and Path(config_path).exists():
        with open(config_path, "r", encoding="utf-8") as cf:
            loaded_cfg = yaml.safe_load(cf) or {}
            seeds = loaded_cfg.get("seeds")
            if seeds and isinstance(seeds, list):
                seed = int(seeds[0])

    rng = random.Random(seed)

    # Question distribution tally
    q_counts = Counter(q.get("type", "unknown") for q in questions)
    total_turns = sum(len(c.get("turns", [])) for c in calls)
    avg_turns = round(total_turns / max(1, len(calls)), 2)
    avg_calls = round(len(calls) / max(1, len(callers)), 2)

    print("=" * 80)
    print("DATASET D1: SUMMARY OVERVIEW")
    print("=" * 80)
    print(f"Total Callers:       {len(callers)}")
    print(f"Total Calls:         {len(calls)} (average {avg_calls} calls/caller)")
    print(f"Total Turns:         {total_turns} (average {avg_turns} turns/call)")
    print(f"Total Questions:     {len(questions)} ({len(questions) // max(1, len(callers))} per caller)")
    print("-" * 80)
    print("QUESTION DISTRIBUTION BY TYPE:")
    for q_type, count in sorted(q_counts.items()):
        pct = (count / len(questions)) * 100
        print(f"  - {q_type:<30}: {count:>5} ({pct:>5.1f}%)")
    print("=" * 80)
    print()

    # Sample conversations
    sampled_indices = rng.sample(range(len(calls)), min(sample_size, len(calls)))
    print("=" * 80)
    print(f"SAMPLING {len(sampled_indices)} CONVERSATIONS FOR REALISM REVIEW")
    print("=" * 80)

    for i, idx in enumerate(sampled_indices, 1):
        call = calls[idx]
        caller = caller_map.get(call["caller_id"], {})
        name = caller.get("name", "Unknown")
        style = caller.get("language_style", "Unknown")
        phone = caller.get("phone", "Unknown")
        turns = call.get("turns", [])

        print(f"\n--- [Sample {i}/{len(sampled_indices)}] Call ID: {call.get('call_id')} ---")
        print(f"Caller:       {name} ({call.get('caller_id')}) | Phone: {phone}")
        print(f"Style:        {style} | Emotion Arc: {call.get('emotion_arc')}")
        print(f"Topic:        {call.get('call_topic')}")
        print(f"Complaint:    {'YES' if call.get('complaint_present') else 'NO'}")
        print(f"Turn Count:   {len(turns)}")
        print("Transcript:")
        for t_idx, turn in enumerate(turns, 1):
            role_label = turn.get("role", "speaker").upper()
            content = turn.get("content", "").strip()
            print(f"  Turn {t_idx:02d} [{role_label}]: {content}")

    print("\n" + "=" * 80)
    print("REALISM REVIEW SAMPLING COMPLETED")
    print("=" * 80)

    summary_data = {
        "n_callers": len(callers),
        "total_calls": len(calls),
        "total_questions": len(questions),
        "avg_calls_per_caller": avg_calls,
        "avg_turns_per_call": avg_turns,
        "question_counts": dict(q_counts),
    }

    if out_dir:
        out_p = Path(out_dir)
        out_p.mkdir(parents=True, exist_ok=True)
        summary_file = out_p / "check_d1_summary.json"
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(summary_data, f, indent=2)

    return summary_data


def main() -> None:
    parser = argparse.ArgumentParser(description="Realism Review and Question Distribution Checker for Dataset D1")
    parser.add_argument("--config", default="eval/config.yaml", help="Path to config file")
    parser.add_argument("--in", dest="data_dir", default="eval/data/d1", help="Directory containing D1 dataset JSONL files")
    parser.add_argument("--out", default="results/check_d1", help="Output directory for inspection summary")
    parser.add_argument("--sample-size", type=int, default=20, help="Number of conversations to print for review")
    args = parser.parse_args()

    run_check_d1(
        data_dir=args.data_dir,
        config_path=args.config,
        sample_size=args.sample_size,
        out_dir=args.out,
    )


if __name__ == "__main__":
    main()
