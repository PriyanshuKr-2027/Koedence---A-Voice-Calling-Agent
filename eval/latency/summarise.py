"""VoCall Pipeline Latency Summariser and Critical Path Evaluator.

Computes p50, p95, and p99 distributions per stage and for turn_total.
Evaluates Equation 1:
  turn_total vs stt + max(emotion, memory, intent) + llm_ttft + tts_ttfab + network_out
Computes and reports the overhead gap, fraction of turns under 800 ms,
and exports stacked-bar data for Fig. 5(a).
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


STAGES_ORDERED = [
    "stt",
    "emotion",
    "memory",
    "intent",
    "llm_ttft",
    "tts_ttfab",
    "network_out",
    "turn_total",
]


def load_latency_records(
    log_path: str | Path,
    warmup_turns: int = 3,
) -> Tuple[List[Dict[str, Any]], Dict[Tuple[str, int], Dict[str, float]], Dict[str, Any]]:
    """Loads and filters raw per-stage latency records from JSONL log.

    Discards the first `warmup_turns` of each call as warm-up.
    Groups records both as a flat list and as complete per-turn dictionaries.
    """
    path = Path(log_path)
    if not path.exists():
        raise FileNotFoundError(f"Latency log file not found at: {path}")

    raw_records: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line_str = line.strip()
            if line_str:
                try:
                    raw_records.append(json.loads(line_str))
                except Exception:
                    continue

    # Group records by (call_id, turn_idx)
    all_turns: Dict[Tuple[str, int], Dict[str, float]] = {}
    warmup_discarded_count = 0

    for rec in raw_records:
        call_id = str(rec.get("call_id", ""))
        turn_idx = int(rec.get("turn_idx", 0))
        stage_name = str(rec.get("stage", ""))
        ms_val = float(rec.get("ms", 0.0))

        if turn_idx <= warmup_turns:
            warmup_discarded_count += 1
            continue

        key = (call_id, turn_idx)
        if key not in all_turns:
            all_turns[key] = {}
        all_turns[key][stage_name] = ms_val

    # Filter flat records for stage-level distribution analysis
    measured_records = [
        r for r in raw_records if int(r.get("turn_idx", 0)) > warmup_turns
    ]

    metadata = {
        "total_raw_records": len(raw_records),
        "warmup_records_discarded": warmup_discarded_count,
        "measured_records": len(measured_records),
        "total_measured_turns": len(all_turns),
    }

    return measured_records, all_turns, metadata


def compute_percentiles(values: List[float]) -> Dict[str, float]:
    """Computes count, mean, min, p50, p95, p99, and max for numeric observations."""
    if not values:
        return {"count": 0, "mean": 0.0, "min": 0.0, "p50": 0.0, "p95": 0.0, "p99": 0.0, "max": 0.0}

    arr = np.asarray(values, dtype=float)
    return {
        "count": len(arr),
        "mean": round(float(np.mean(arr)), 2),
        "min": round(float(np.min(arr)), 2),
        "p50": round(float(np.percentile(arr, 50)), 2),
        "p95": round(float(np.percentile(arr, 95)), 2),
        "p99": round(float(np.percentile(arr, 99)), 2),
        "max": round(float(np.max(arr)), 2),
    }


def evaluate_equation_1(
    turns: Dict[Tuple[str, int], Dict[str, float]],
) -> Dict[str, Any]:
    """Checks Equation 1 on each measured turn:

    turn_total vs stt + max(emotion, memory, intent) + llm_ttft + tts_ttfab + network_out
    Computes critical path predictions, residual overhead gaps, and under-800ms compliance.
    """
    predicted_totals: List[float] = []
    observed_totals: List[float] = []
    overhead_gaps: List[float] = []
    fanout_critical_paths: List[float] = []

    under_800ms_count = 0
    total_turns_count = len(turns)

    for (call_id, turn_idx), stage_map in turns.items():
        stt_ms = stage_map.get("stt", 0.0)
        emo_ms = stage_map.get("emotion", 0.0)
        mem_ms = stage_map.get("memory", 0.0)
        int_ms = stage_map.get("intent", 0.0)
        llm_ms = stage_map.get("llm_ttft", 0.0)
        tts_ms = stage_map.get("tts_ttfab", 0.0)
        net_ms = stage_map.get("network_out", 0.0)
        observed_turn_total = stage_map.get("turn_total", 0.0)

        # In VoCall's parallel fanout, emotion, memory, and intent run concurrently
        fanout_max = max(emo_ms, mem_ms, int_ms)
        predicted_turn_total = stt_ms + fanout_max + llm_ms + tts_ms + net_ms
        gap = observed_turn_total - predicted_turn_total

        predicted_totals.append(predicted_turn_total)
        observed_totals.append(observed_turn_total)
        overhead_gaps.append(gap)
        fanout_critical_paths.append(fanout_max)

        if observed_turn_total < 800.0:
            under_800ms_count += 1

    fraction_under_800ms = (
        round(under_800ms_count / float(total_turns_count), 4) if total_turns_count > 0 else 0.0
    )
    pct_under_800ms = round(fraction_under_800ms * 100.0, 2)

    return {
        "total_measured_turns": total_turns_count,
        "turns_under_800ms": under_800ms_count,
        "fraction_under_800ms": fraction_under_800ms,
        "percentage_under_800ms": pct_under_800ms,
        "observed_total": compute_percentiles(observed_totals),
        "predicted_total": compute_percentiles(predicted_totals),
        "fanout_critical_path": compute_percentiles(fanout_critical_paths),
        "overhead_gap": compute_percentiles(overhead_gaps),
    }


def compile_fig5a_stacked_bar_data(
    turns: Dict[Tuple[str, int], Dict[str, float]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Compiles stacked-bar components for Fig. 5(a) across language slices.

    Stacked components:
      - STT
      - Cognitive Fanout: max(emotion, memory, intent)
      - LLM TTFT
      - TTS TTFAB
      - Network Out
      - Overhead Gap
    """
    # Separate turns by language code (derived from call_id prefix)
    en_turns = {k: v for k, v in turns.items() if "en" in k[0]}
    hing_turns = {k: v for k, v in turns.items() if "hing" in k[0]}

    subsets = [
        ("English", en_turns if en_turns else turns),
        ("Hinglish", hing_turns if hing_turns else turns),
        ("Overall", turns),
    ]

    table_rows: List[Dict[str, Any]] = []
    json_payload: Dict[str, Any] = {}

    for label, subset in subsets:
        if not subset:
            continue

        eq_eval = evaluate_equation_1(subset)

        # Collect stage values for percentile extraction
        stt_vals = [m.get("stt", 0.0) for m in subset.values()]
        fanout_vals = [max(m.get("emotion", 0.0), m.get("memory", 0.0), m.get("intent", 0.0)) for m in subset.values()]
        llm_vals = [m.get("llm_ttft", 0.0) for m in subset.values()]
        tts_vals = [m.get("tts_ttfab", 0.0) for m in subset.values()]
        net_vals = [m.get("network_out", 0.0) for m in subset.values()]
        obs_vals = [m.get("turn_total", 0.0) for m in subset.values()]

        p50_stt = float(np.percentile(stt_vals, 50))
        p50_fanout = float(np.percentile(fanout_vals, 50))
        p50_llm = float(np.percentile(llm_vals, 50))
        p50_tts = float(np.percentile(tts_vals, 50))
        p50_net = float(np.percentile(net_vals, 50))
        p50_obs = float(np.percentile(obs_vals, 50))
        p50_gap = max(0.0, p50_obs - (p50_stt + p50_fanout + p50_llm + p50_tts + p50_net))

        p95_stt = float(np.percentile(stt_vals, 95))
        p95_fanout = float(np.percentile(fanout_vals, 95))
        p95_llm = float(np.percentile(llm_vals, 95))
        p95_tts = float(np.percentile(tts_vals, 95))
        p95_net = float(np.percentile(net_vals, 95))
        p95_obs = float(np.percentile(obs_vals, 95))
        p95_gap = max(0.0, p95_obs - (p95_stt + p95_fanout + p95_llm + p95_tts + p95_net))

        pct_800 = eq_eval["percentage_under_800ms"]

        # p50 Row
        table_rows.append({
            "language": label,
            "metric": "p50",
            "stt_ms": round(p50_stt, 1),
            "cognitive_fanout_ms": round(p50_fanout, 1),
            "llm_ttft_ms": round(p50_llm, 1),
            "tts_ttfab_ms": round(p50_tts, 1),
            "network_out_ms": round(p50_net, 1),
            "overhead_gap_ms": round(p50_gap, 1),
            "total_turnaround_ms": round(p50_obs, 1),
            "pct_under_800ms": pct_800,
        })

        # p95 Row
        table_rows.append({
            "language": label,
            "metric": "p95",
            "stt_ms": round(p95_stt, 1),
            "cognitive_fanout_ms": round(p95_fanout, 1),
            "llm_ttft_ms": round(p95_llm, 1),
            "tts_ttfab_ms": round(p95_tts, 1),
            "network_out_ms": round(p95_net, 1),
            "overhead_gap_ms": round(p95_gap, 1),
            "total_turnaround_ms": round(p95_obs, 1),
            "pct_under_800ms": pct_800,
        })

        json_payload[label.lower()] = {
            "p50": table_rows[-2],
            "p95": table_rows[-1],
            "under_800ms_compliance_rate": eq_eval["fraction_under_800ms"],
        }

    return table_rows, json_payload


def summarise_latency(
    log_path: str | Path,
    out_dir: Optional[str | Path] = None,
    warmup_turns: int = 3,
) -> Dict[str, Any]:
    """Runs complete latency telemetry summarisation, checking Equation 1 and exporting Fig 5(a) data."""
    log_p = Path(log_path)
    measured_records, turns, meta = load_latency_records(log_p, warmup_turns=warmup_turns)

    if not turns:
        raise ValueError(f"No valid measured turns found in {log_path} after discarding {warmup_turns} warm-up turns.")

    target_out = Path(out_dir) if out_dir else log_p.parent

    # Per-stage distributions
    per_stage_metrics: Dict[str, Any] = {}
    for stg in STAGES_ORDERED:
        stage_vals = [r["ms"] for r in measured_records if r.get("stage") == stg]
        per_stage_metrics[stg] = compute_percentiles(stage_vals)

    # Equation 1 Check
    equation_result = evaluate_equation_1(turns)

    # Compile Fig. 5(a) stacked-bar data
    fig5a_rows, fig5a_json = compile_fig5a_stacked_bar_data(turns)

    # Write Fig 5(a) CSV
    fig5a_csv_path = target_out / "fig5a_stacked_bar.csv"
    with open(fig5a_csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(fig5a_rows[0].keys()))
        writer.writeheader()
        writer.writerows(fig5a_rows)

    # Write Fig 5(a) JSON
    fig5a_json_path = target_out / "fig5a_stacked_bar.json"
    with open(fig5a_json_path, "w", encoding="utf-8") as f:
        json.dump(fig5a_json, f, indent=2)

    # Write Complete Latency Summary JSON
    summary_metrics = {
        "metadata": meta,
        "warmup_turns_discarded": warmup_turns,
        "per_stage_percentiles": per_stage_metrics,
        "equation_1": equation_result,
        "fig5a_stacked_bar": fig5a_json,
    }

    metrics_out_path = target_out / "latency_summary.json"
    with open(metrics_out_path, "w", encoding="utf-8") as f:
        json.dump(summary_metrics, f, indent=2)

    # Print summary to console
    print("\n" + "=" * 80)
    print("VoCall Voice Pipeline Latency Profile & Equation 1 Critical Path Evaluation")
    print("=" * 80)
    print(f"Log Path: {log_p}")
    print(f"Total Raw Records: {meta['total_raw_records']} | Warmup Discarded: {meta['warmup_records_discarded']} turns")
    print(f"Measured Turns: {meta['total_measured_turns']}")
    print("-" * 80)
    print(f"{'Stage':<16} {'Count':<8} {'Mean (ms)':<12} {'p50 (ms)':<12} {'p95 (ms)':<12} {'p99 (ms)':<12}")
    print("-" * 80)
    for stg in STAGES_ORDERED:
        stats = per_stage_metrics.get(stg, {})
        print(f"{stg:<16} {stats.get('count', 0):<8} {stats.get('mean', 0.0):<12.2f} {stats.get('p50', 0.0):<12.2f} {stats.get('p95', 0.0):<12.2f} {stats.get('p99', 0.0):<12.2f}")

    print("-" * 80)
    eq_obs = equation_result["observed_total"]
    eq_pred = equation_result["predicted_total"]
    eq_gap = equation_result["overhead_gap"]
    pct_under_800 = equation_result["percentage_under_800ms"]

    print("Equation 1 Evaluation:")
    print("  turn_total vs stt + max(emotion, memory, intent) + llm_ttft + tts_ttfab + network_out")
    print(f"  Observed Turn Total (Mean / p50 / p95): {eq_obs['mean']:.2f} ms / {eq_obs['p50']:.2f} ms / {eq_obs['p95']:.2f} ms")
    print(f"  Predicted Critical Path (Mean / p50):   {eq_pred['mean']:.2f} ms / {eq_pred['p50']:.2f} ms")
    print(f"  Residual Overhead Gap (Mean / p50):     {eq_gap['mean']:.2f} ms / {eq_gap['p50']:.2f} ms")
    print(f"  Fraction of Turns Under 800 ms:         {equation_result['fraction_under_800ms']:.4f} ({pct_under_800:.1f}%)")
    print(f"  Fig 5(a) Stacked-Bar Data Exported:     {fig5a_csv_path}")
    print(f"  Summary Metrics JSON:                   {metrics_out_path}")
    print("=" * 80 + "\n")

    return summary_metrics


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="VoCall Latency Stage Telemetry Summariser")
    parser.add_argument("--log", default=None, help="Path to latency_stages.jsonl log file")
    parser.add_argument("--out", default=None, help="Output directory for summary metrics and Fig 5(a) CSV")
    parser.add_argument("--warmup", type=int, default=3, help="Number of initial turns per call to discard as warm-up")
    return parser.parse_args()


def find_latest_latency_log() -> Path:
    """Finds the most recent latency_stages.jsonl in results/latency/."""
    candidates = sorted(Path("results/latency").glob("*/latency_stages.jsonl"))
    if not candidates:
        raise FileNotFoundError("No latency_stages.jsonl found under results/latency/. Run eval.latency.replay first.")
    return candidates[-1]


def main() -> None:
    args = parse_args()
    log_target = Path(args.log) if args.log else find_latest_latency_log()
    summarise_latency(log_path=log_target, out_dir=args.out, warmup_turns=args.warmup)


if __name__ == "__main__":
    main()
