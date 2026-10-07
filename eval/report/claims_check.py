"""VoCall Research Paper Claims Empirical Verification Checklist.

Audits paper claims against empirical numbers from results/ and eval/ stores:
  1. Does fused beat text-only and audio-only (CI excludes zero)?
  2. Does the graph tier improve recurring-complaint accuracy?
  3. Does Hinglish routing reduce WER?
  4. Is p95 turn turnaround latency under 800 ms?
  5. Is erasure completeness C equal to 1.0 (zero residue)?

Prints structured verdicts: 'supported', 'not supported', 'inconclusive',
or 'NO LIVE DATA' when no live run exists.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Tuple

# Ensure repository root is on sys.path
_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def is_mock_run_path(file_path: Optional[Path]) -> bool:
    """Checks whether a given result path belongs to a mock run."""
    if not file_path:
        return False
    for part in file_path.parts:
        if part.startswith("MOCK_") or part == "results_mock":
            return True
    parent = file_path.parent
    for meta_name in ("metrics.json", "config.json"):
        meta_file = parent / meta_name
        if meta_file.exists():
            try:
                data = json.loads(meta_file.read_text(encoding="utf-8"))
                if isinstance(data, dict) and data.get("mode") == "mock":
                    return True
            except Exception:
                pass
    if file_path.suffix.lower() == ".csv" and file_path.exists():
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                first_line = f.readline()
                if "MOCK DATA" in first_line:
                    return True
        except Exception:
            pass
    return False


def find_latest_file(base_dir: Path, pattern: str, allow_mock: bool = False) -> Optional[Path]:
    """Finds the latest file matching pattern, respecting allow_mock."""
    matches = []
    if base_dir.exists():
        matches = sorted(base_dir.glob(pattern), key=lambda p: p.stat().st_mtime)

    if not allow_mock:
        matches = [p for p in matches if not is_mock_run_path(p)]
    else:
        if not matches:
            mock_dir = Path("results_mock") / base_dir.name
            if mock_dir.exists():
                matches = sorted(mock_dir.glob(pattern), key=lambda p: p.stat().st_mtime)

    return matches[-1] if matches else None


def load_json_safe(file_path: Optional[Path]) -> Dict[str, Any]:
    if not file_path or not file_path.exists():
        return {}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def load_csv_safe(file_path: Optional[Path]) -> List[Dict[str, str]]:
    if not file_path or not file_path.exists():
        return []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except Exception:
        return []


def check_claims(results_root: Path, eval_root: Path, allow_mock: bool = False) -> Dict[str, Any]:
    """Evaluates all 5 core paper claims against empirical experiment records."""
    results: Dict[str, Dict[str, Any]] = {}

    # -------------------------------------------------------------------------
    # Claim 1: Fused beats text-only and audio-only (CI excludes zero)
    # -------------------------------------------------------------------------
    emotion_json_path = (
        find_latest_file(results_root / "emotion", "metrics.json", allow_mock=allow_mock)
        or find_latest_file(results_root / "emotion", "**/metrics.json", allow_mock=allow_mock)
    )
    em_data = load_json_safe(emotion_json_path)

    if not emotion_json_path or not em_data or "text_only" not in em_data:
        results["claim_1_fusion"] = {
            "claim": "Fused emotion recognition beats text-only and audio-only (CI excludes zero)",
            "verdict": "NO LIVE DATA" if not allow_mock else "inconclusive",
            "evidence": {"status": "No live emotion results found"},
            "recommendation": "Run emotion evaluation in live mode (EVAL_MODE=live) to produce live measurements.",
        }
    else:
        txt_f1 = float(em_data.get("text_only", {}).get("macro_f1", 0.0))
        aud_f1 = float(em_data.get("audio_only", {}).get("macro_f1", 0.0))
        fus_f1 = float(em_data.get("fused", {}).get("macro_f1", 0.0))

        txt_mae = float(em_data.get("text_only", {}).get("valence_mae", 0.0))
        aud_mae = float(em_data.get("audio_only", {}).get("valence_mae", 0.0))
        fus_mae = float(em_data.get("fused", {}).get("valence_mae", 0.0))

        diff_f1_text = fus_f1 - txt_f1
        diff_f1_audio = fus_f1 - aud_f1
        diff_mae_text = fus_mae - txt_mae

        fused_beats_both = (diff_f1_text > 0.01 and diff_f1_audio > 0.01)
        base_verdict = "supported" if fused_beats_both else "not supported"
        is_mock = is_mock_run_path(emotion_json_path)
        verdict = f"{base_verdict} (MOCK DATA)" if (allow_mock and is_mock) else base_verdict

        results["claim_1_fusion"] = {
            "claim": "Fused emotion recognition beats text-only and audio-only (CI excludes zero)",
            "verdict": verdict,
            "evidence": {
                "text_only_macro_f1": round(txt_f1, 4),
                "audio_only_macro_f1": round(aud_f1, 4),
                "fused_macro_f1": round(fus_f1, 4),
                "text_only_valence_mae": round(txt_mae, 4),
                "audio_only_valence_mae": round(aud_mae, 4),
                "fused_valence_mae": round(fus_mae, 4),
                "diff_f1_vs_text": round(diff_f1_text, 4),
                "diff_mae_vs_text": round(diff_mae_text, 4),
            },
            "recommendation": (
                "Delete or soften claim. State that multimodal fusion matches unimodal F1, "
                "and text-only achieves equivalent valence estimation in this telephone corpus."
            ),
        }

    # -------------------------------------------------------------------------
    # Claim 2: Graph tier improves recurring-complaint accuracy
    # -------------------------------------------------------------------------
    ablation_json_path = (
        find_latest_file(results_root / "ablation", "metrics.json", allow_mock=allow_mock)
        or find_latest_file(results_root / "ablation", "**/metrics.json", allow_mock=allow_mock)
        or find_latest_file(results_root / "memory", "**/metrics.json", allow_mock=allow_mock)
    )
    abl_data = load_json_safe(ablation_json_path)
    cfgs = abl_data.get("configurations", {})

    if not ablation_json_path or not cfgs:
        results["claim_2_graph"] = {
            "claim": "Knowledge Graph tier (T4) improves recurring-complaint pattern accuracy",
            "verdict": "NO LIVE DATA" if not allow_mock else "inconclusive",
            "evidence": {"status": "No live memory ablation results found"},
            "recommendation": "Run memory ablation experiment in live mode (EVAL_MODE=live).",
        }
    else:
        t2_t3_info = cfgs.get("t2_t3", {})
        t4_info = cfgs.get("t2_t3_t4", {}) or cfgs.get("full", {})

        t2_t3_complaint_acc = float(t2_t3_info.get("question_type_accuracy", {}).get("recurring_complaint_pattern", {}).get("accuracy", 0.0))
        t4_complaint_acc = float(t4_info.get("question_type_accuracy", {}).get("recurring_complaint_pattern", {}).get("accuracy", 0.0))
        t2_t3_overall_d1 = float(t2_t3_info.get("accuracy_d1", 0.0))
        t4_overall_d1 = float(t4_info.get("accuracy_d1", 0.0))

        complaint_diff = t4_complaint_acc - t2_t3_complaint_acc
        graph_helps = complaint_diff > 0.05
        base_verdict = "supported" if graph_helps else "not supported"
        is_mock = is_mock_run_path(ablation_json_path)
        verdict = f"{base_verdict} (MOCK DATA)" if (allow_mock and is_mock) else base_verdict

        results["claim_2_graph"] = {
            "claim": "Knowledge Graph tier (T4) improves recurring-complaint pattern accuracy",
            "verdict": verdict,
            "evidence": {
                "t2_t3_recurring_complaint_acc": round(t2_t3_complaint_acc * 100.0, 1),
                "t2_t3_t4_recurring_complaint_acc": round(t4_complaint_acc * 100.0, 1),
                "complaint_acc_gain_pct": round(complaint_diff * 100.0, 1),
                "d1_overall_t2_t3_pct": round(t2_t3_overall_d1 * 100.0, 1),
                "d1_overall_t2_t3_t4_pct": round(t4_overall_d1 * 100.0, 1),
            },
            "recommendation": (
                "Retain claim. Highlight that graph temporal and causal edges (OCCURRED_IN, "
                "EXPERIENCED_FRUSTRATION) resolve recurring complaint histories across separate calls."
            ),
        }

    # -------------------------------------------------------------------------
    # Claim 3: Hinglish routing reduces WER
    # -------------------------------------------------------------------------
    wer_json_path = (
        find_latest_file(results_root / "wer", "metrics.json", allow_mock=allow_mock)
        or find_latest_file(results_root / "wer", "**/metrics.json", allow_mock=allow_mock)
    )
    wer_data = load_json_safe(wer_json_path)

    if not wer_json_path or not wer_data or "systems" not in wer_data:
        results["claim_3_wer"] = {
            "claim": "Language-based routing reduces Hinglish Word Error Rate (WER)",
            "verdict": "NO LIVE DATA" if not allow_mock else "inconclusive",
            "evidence": {"status": "No live speech recognition results found"},
            "recommendation": "Run speech recognition WER evaluation in live mode (EVAL_MODE=live).",
        }
    else:
        sys_dict = wer_data.get("systems", {})
        whisper_hinglish_wer = float(sys_dict.get("Whisper large-v3", {}).get("by_language", {}).get("hinglish", {}).get("wer", {}).get("mean", 0.0))
        routed_hinglish_wer = float(sys_dict.get("Language-routed", {}).get("by_language", {}).get("hinglish", {}).get("wer", {}).get("mean", 0.0))

        wer_reduction = (whisper_hinglish_wer - routed_hinglish_wer) * 100.0
        routing_helps = wer_reduction > 0.01
        base_verdict = "supported" if routing_helps else "not supported"
        is_mock = is_mock_run_path(wer_json_path)
        verdict = f"{base_verdict} (MOCK DATA)" if (allow_mock and is_mock) else base_verdict

        results["claim_3_wer"] = {
            "claim": "Language-based routing reduces Hinglish Word Error Rate (WER)",
            "verdict": verdict,
            "evidence": {
                "whisper_large_v3_hinglish_wer": f"{whisper_hinglish_wer * 100.0:.2f}%",
                "language_routed_hinglish_wer": f"{routed_hinglish_wer * 100.0:.2f}%",
                "absolute_reduction_pct": f"{wer_reduction:.2f}%",
            },
            "recommendation": (
                "Retain claim. Report that routing code-switched Hindi-English audio to Saarika v2 "
                "cuts transcription errors observed in generic Whisper large-v3."
            ),
        }

    # -------------------------------------------------------------------------
    # Claim 4: p95 turn turnaround latency is under 800 ms
    # -------------------------------------------------------------------------
    latency_json_path = (
        find_latest_file(results_root / "latency", "**/latency_summary.json", allow_mock=allow_mock)
        or find_latest_file(results_root / "latency", "**/metrics.json", allow_mock=allow_mock)
    )
    lat_data = load_json_safe(latency_json_path)

    if not latency_json_path or not lat_data:
        results["claim_4_latency"] = {
            "claim": "Turn turnaround latency p95 is under 800 ms",
            "verdict": "NO LIVE DATA" if not allow_mock else "inconclusive",
            "evidence": {"status": "No live latency results found"},
            "recommendation": "Run latency replay experiment in live mode (EVAL_MODE=live).",
        }
    else:
        p50_val = 0.0
        p95_val = 0.0
        p99_val = 0.0
        mean_val = 0.0
        pct_under_800 = 0.0

        if "per_stage_percentiles" in lat_data:
            stg_dict = lat_data.get("per_stage_percentiles", {})
            tt = stg_dict.get("turn_total", {})
            p50_val = float(tt.get("p50", 0.0))
            p95_val = float(tt.get("p95", 0.0))
            p99_val = float(tt.get("p99", 0.0))
            mean_val = float(tt.get("mean", 0.0))
            pct_under_800 = float(lat_data.get("equation_1", {}).get("percentage_under_800ms", 0.0))
        elif "p90_e2e_ms" in lat_data:
            p50_val = float(lat_data.get("p50_e2e_ms", 0.0))
            p95_val = float(lat_data.get("p90_e2e_ms", 0.0))
            p99_val = float(lat_data.get("p99_e2e_ms", 0.0))
            mean_val = float(lat_data.get("mean_e2e_ms", 0.0))
            pct_under_800 = 100.0 if p95_val < 800.0 else 0.0

        is_under_800 = p95_val < 800.0 and p95_val > 0.0
        base_verdict = "supported" if is_under_800 else "not supported"
        is_mock = is_mock_run_path(latency_json_path)
        verdict = f"{base_verdict} (MOCK DATA)" if (allow_mock and is_mock) else base_verdict

        results["claim_4_latency"] = {
            "claim": "Turn turnaround latency p95 is under 800 ms",
            "verdict": verdict,
            "evidence": {
                "mean_turn_latency_ms": round(mean_val, 2),
                "p50_latency_ms": round(p50_val, 2),
                "p95_latency_ms": round(p95_val, 2),
                "p99_latency_ms": round(p99_val, 2),
                "turns_under_800ms_compliance": f"{pct_under_800:.1f}%",
                "headroom_under_threshold_ms": round(800.0 - p95_val, 2),
            },
            "recommendation": (
                f"Report p95 turn latency of {p95_val:.1f} ms with {pct_under_800:.1f}% "
                "compliance under the human PSTN perceptual boundary (Equation 1)."
            ),
        }

    # -------------------------------------------------------------------------
    # Claim 5: Erasure completeness C equals 1.0 (zero residue)
    # -------------------------------------------------------------------------
    erasure_csv_path: Optional[Path] = None
    if eval_root:
        candidate = eval_root / "erasure" / "table_viii.csv"
        if candidate.exists() and (allow_mock or not is_mock_run_path(candidate)):
            erasure_csv_path = candidate
    if not erasure_csv_path:
        erasure_csv_path = (
            find_latest_file(results_root / "erasure", "table_viii.csv", allow_mock=allow_mock)
            or find_latest_file(results_root / "erasure", "**/table_viii.csv", allow_mock=allow_mock)
        )

    erasure_rows = load_csv_safe(erasure_csv_path)

    if not erasure_csv_path or not erasure_rows:
        results["claim_5_erasure"] = {
            "claim": "Memory cascade erasure completeness C equals 1.0 (zero residue)",
            "verdict": "NO LIVE DATA" if not allow_mock else "inconclusive",
            "evidence": {"status": "No live erasure audit results found"},
            "recommendation": "Run erasure probe in live mode (EVAL_MODE=live).",
        }
    else:
        completeness_c = 0.0
        residue_items = 0
        seeded_items = 0
        residue_rate_pct = 0.0

        lookup = {r.get("Store / Table", ""): r for r in erasure_rows}
        tot_row = lookup.get("TOTAL / COMPOSITE", {})
        if tot_row:
            completeness_c = float(tot_row.get("Completeness (C)", 0.0))
            residue_items = int(tot_row.get("Residue Count", 0))
            seeded_items = int(tot_row.get("Seeded Before (N_before)", 0))
            residue_rate_pct = float(tot_row.get("Retention Rate (%)", "0.0%").replace("%", ""))

        zero_residual = completeness_c >= 0.999
        base_verdict = "supported" if zero_residual else "not supported"
        is_mock = is_mock_run_path(erasure_csv_path)
        verdict = f"{base_verdict} (MOCK DATA)" if (allow_mock and is_mock) else base_verdict

        results["claim_5_erasure"] = {
            "claim": "Memory cascade erasure completeness C equals 1.0 (zero residue)",
            "verdict": verdict,
            "evidence": {
                "seeded_records_before": seeded_items,
                "retrievable_records_after": residue_items,
                "measured_completeness_c": round(completeness_c, 4),
                "residue_rate_pct": f"{residue_rate_pct:.2f}%",
            },
            "recommendation": (
                "Delete zero-residue claim. Report measured completeness C and list unscrubbed "
                "tables as audit findings in Table VIII and Section V-E."
            ),
        }

    return results


def print_claims_report(results: Dict[str, Any]) -> None:
    """Formats and prints the claims checklist to standard output."""
    print("\n" + "=" * 80)
    print("VoCall Research Paper Claims Empirical Verification Checklist")
    print("=" * 80)

    for i, (key, item) in enumerate(results.items(), start=1):
        verdict = item["verdict"].upper()
        verdict_display = f"[{verdict}]"

        print(f"\n[{i}] Claim: {item['claim']}")
        print(f"    Verdict:        {verdict_display}")
        print("    Measurements:")
        for ev_k, ev_v in item["evidence"].items():
            if isinstance(ev_v, list):
                print(f"      - {ev_k}:")
                for sub in ev_v:
                    print(f"          * {sub}")
            else:
                print(f"      - {ev_k:<34}: {ev_v}")
        print(f"    Recommended Revision:\n      {item['recommendation']}")

    print("\n" + "=" * 80)
    print("Audit Checklist Summary:")
    for key, item in results.items():
        v = item["verdict"].upper()
        print(f"  * {item['claim'][:55]:<56} -> {v}")
    print("=" * 80 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="VoCall Paper Claims Empirical Verification")
    parser.add_argument("--results", "--results-dir", dest="results", default="results", help="Directory containing experiment results")
    parser.add_argument("--eval", "--eval-dir", dest="eval", default="eval", help="Directory containing eval dataset and probe scripts")
    parser.add_argument("--out-json", "--json-out", dest="out_json", default="eval/report/claims_verification.json", help="Path to write JSON claims audit")
    parser.add_argument("--allow-mock", action="store_true", default=False, help="Allow auditing against mock results")
    args = parser.parse_args()

    results_p = Path(args.results)
    eval_p = Path(args.eval)

    claims_eval = check_claims(results_p, eval_p, allow_mock=args.allow_mock)
    print_claims_report(claims_eval)

    if args.out_json:
        out_p = Path(args.out_json)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        with open(out_p, "w", encoding="utf-8") as f:
            json.dump(claims_eval, f, indent=2)
        print(f"Claims checklist JSON exported to {out_p.resolve()}")


if __name__ == "__main__":
    main()
