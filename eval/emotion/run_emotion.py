"""Multimodal Emotion Evaluation Experiment.

Evaluates text-only (Groq NLP), audio-only (Hume AI), and fused signals (fuse_emotion_signals)
against adjudicated gold labels on dataset D3.

Outputs:
  - config.json: Mode, services_used, hyperparameters, environment info
  - metrics.json: Macro-F1, Accuracy, Valence MAE, Pearson r with bootstrap 95% CIs, latency, n counts
  - table_vi.csv: TABLE VI ready CSV comparing text-only, audio-only, and fused
  - sweep.csv: Audio weight sweep (w in [0..1] step 0.1) for Fig. 5(b)
  - disagreements.csv: Top 20 clips with greatest text vs audio divergence
  - Tone adapter trigger precision and recall against gold angry/frustrated clips
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
import scipy.stats
from sklearn.metrics import f1_score
import yaml

from app.core.config import settings
from app.services.emotion.audio_signal import analyze_audio_emotion
from app.services.emotion.fusion import fuse_emotion_signals
from app.services.emotion.text_signal import analyze_text_emotion
from app.services.emotion.tone_adapter import get_tone_instruction
from eval.common.cache import DiskCache
from eval.common.mode import ServiceTracker, get_eval_mode, require_live_services, stamp_csv_mock_data
from eval.common.runlog import write_metrics
from eval.common.stats import bootstrap_ci
from eval.emotion.kappa import compute_inter_annotator_agreement, map_valence_5point_to_unit


# ---------------------------------------------------------------------------
# Offline Heuristic Estimators (Used ONLY in mock mode)
# ---------------------------------------------------------------------------

def _heuristic_text_emotion(transcript: str) -> Dict[str, Any]:
    """Deterministic offline text emotion extractor based on transcript lexicon."""
    t = transcript.lower()
    if any(w in t for w in ["fraud", "cancel", "useless", "hung up", "immediately", "stop lying"]):
        return {"valence": -0.85, "arousal": 0.85, "dominant": "angry", "confidence": 0.9}
    if any(w in t for w in ["drop", "slow", "roaming", "charge", "failed", "disconnect", "weak", "ticket"]):
        return {"valence": -0.65, "arousal": 0.65, "dominant": "frustrated", "confidence": 0.85}
    if any(w in t for w in ["pareshan", "disappointed", "downtime", "dusra provider", "risking"]):
        return {"valence": -0.55, "arousal": 0.35, "dominant": "sad", "confidence": 0.8}
    if any(w in t for w in ["thank you", "badhiya", "excellent", "credit", "resolved", "fast"]):
        return {"valence": 0.85, "arousal": 0.75, "dominant": "happy", "confidence": 0.9}
    if any(w in t for w in ["theek hai", "kal subah", "router restart", "koi jaldi nahi", "understood"]):
        return {"valence": 0.45, "arousal": 0.25, "dominant": "calm", "confidence": 0.85}
    return {"valence": 0.0, "arousal": 0.3, "dominant": "neutral", "confidence": 0.75}


def _heuristic_audio_emotion(transcript: str, clip_id: str) -> Dict[str, Any]:
    """Deterministic offline audio emotion extractor simulating Hume prosodic cues."""
    base = _heuristic_text_emotion(transcript)
    hash_val = hash(clip_id) % 10
    v_adj = (hash_val - 5) * 0.03
    val = round(max(-1.0, min(1.0, base["valence"] + v_adj)), 3)
    aro = round(max(0.0, min(1.0, base["arousal"] + 0.05)), 3)
    return {
        "valence": val,
        "arousal": aro,
        "dominant": base["dominant"],
        "confidence": 0.88,
    }


# ---------------------------------------------------------------------------
# Core Evaluation Engine
# ---------------------------------------------------------------------------

async def evaluate_clip(
    row: Dict[str, Any],
    cache: DiskCache,
    fusion_w: float = 0.6,
    mock_mode: bool = False,
    tracker: Optional[ServiceTracker] = None,
) -> Dict[str, Any]:
    """Computes text-only, audio-only, and fused estimates for a single clip.

    In live mode:
      - Real APIs are queried.
      - If audio emotion cannot be computed (missing key, file, or error),
        audio_missing is True and the clip is excluded from audio and fused metrics.
      - Never falls back to heuristic audio or copies text signal into audio slot.
    """
    transcript = row.get("transcript", "")
    audio_path = row.get("audio_path", "")
    clip_id = row.get("clip_id", "")

    # 1. Text-Only Signal
    t0 = time.perf_counter()
    text_sig = None
    if mock_mode:
        text_sig = _heuristic_text_emotion(transcript)
    else:
        if settings.GROQ_API_KEY:
            cache_key = {"task": "text_emotion", "transcript": transcript}
            cached_t = cache.get("groq", "llama-3.3-70b-versatile", cache_key)
            if cached_t:
                text_sig = cached_t
            else:
                if tracker:
                    tracker.record("groq")
                text_sig = await analyze_text_emotion(transcript)
                if text_sig:
                    cache.set("groq", "llama-3.3-70b-versatile", cache_key, text_sig)
    text_ms = (time.perf_counter() - t0) * 1000.0

    # 2. Audio-Only Signal
    t1 = time.perf_counter()
    audio_sig = None
    audio_missing = False

    if mock_mode:
        audio_sig = _heuristic_audio_emotion(transcript, clip_id)
    else:
        if settings.HUME_API_KEY and Path(audio_path).exists():
            try:
                audio_bytes = Path(audio_path).read_bytes()
                cache_key = {"task": "audio_emotion", "clip_id": clip_id, "audio_len": len(audio_bytes)}
                cached_a = cache.get("hume", "batch-evm", cache_key)
                if cached_a:
                    audio_sig = cached_a
                else:
                    if tracker:
                        tracker.record("hume")
                    audio_sig = await analyze_audio_emotion(audio_bytes, settings.HUME_API_KEY)
                    if audio_sig:
                        cache.set("hume", "batch-evm", cache_key, audio_sig)
            except Exception:
                audio_sig = None

        if not audio_sig:
            audio_missing = True
            # DO NOT fallback to heuristic audio in live mode.
            # Never copy text signal into audio slot.

    audio_ms = (time.perf_counter() - t1) * 1000.0

    # 3. Fused Signal
    t2 = time.perf_counter()
    fused_sig = None
    if mock_mode:
        fused_sig = fuse_emotion_signals(text_sig, audio_sig, audio_weight=fusion_w)
    else:
        if not audio_missing and audio_sig is not None and text_sig is not None:
            fused_sig = fuse_emotion_signals(text_sig, audio_sig, audio_weight=fusion_w)
    fused_ms = (time.perf_counter() - t2) * 1000.0

    return {
        "clip_id": clip_id,
        "transcript": transcript,
        "gold_label": row.get("gold_label", "neutral"),
        "gold_valence": float(row.get("gold_valence", 0.0)),
        "text": text_sig,
        "audio": audio_sig,
        "audio_missing": audio_missing,
        "fused": fused_sig,
        "latency_ms": {
            "text": round(text_ms, 2),
            "audio": round(audio_ms, 2),
            "fused": round(fused_ms, 2),
        },
    }


def compute_performance_metrics(
    y_true_labels: List[str],
    y_pred_labels: List[str],
    y_true_valences: List[float],
    y_pred_valences: List[float],
    seed: int = 42,
) -> Dict[str, Any]:
    """Computes Macro-F1, Accuracy, Valence MAE, and Pearson r with bootstrap 95% CIs."""
    n = len(y_true_labels)
    if n == 0:
        return {
            "macro_f1": 0.0,
            "accuracy": 0.0,
            "ci_accuracy": [0.0, 0.0],
            "valence_mae": 0.0,
            "ci_valence_mae": [0.0, 0.0],
            "pearson_r": 0.0,
            "n": 0,
        }

    arr_true = np.asarray(y_true_labels)
    arr_pred = np.asarray(y_pred_labels)
    val_true = np.asarray(y_true_valences, dtype=float)
    val_pred = np.asarray(y_pred_valences, dtype=float)

    # 1. Macro-F1 and Accuracy
    macro_f1 = float(f1_score(arr_true, arr_pred, average="macro", zero_division=0))
    accuracy = float(np.mean(arr_true == arr_pred))

    # 2. Valence MAE and Pearson r
    mae = float(np.mean(np.abs(val_pred - val_true)))
    if np.std(val_pred) > 1e-6 and np.std(val_true) > 1e-6:
        pearson_r = float(scipy.stats.pearsonr(val_pred, val_true)[0])
    else:
        pearson_r = 0.0

    # 3. Bootstrap 95% Confidence Intervals
    correctness = (arr_true == arr_pred).astype(float)
    ci_acc = bootstrap_ci(correctness, seed=seed)

    abs_errors = np.abs(val_pred - val_true)
    ci_mae = bootstrap_ci(abs_errors, seed=seed)

    return {
        "macro_f1": round(macro_f1, 4),
        "accuracy": round(accuracy, 4),
        "ci_accuracy": [round(ci_acc.low, 4), round(ci_acc.high, 4)],
        "valence_mae": round(mae, 4),
        "ci_valence_mae": [round(ci_mae.low, 4), round(ci_mae.high, 4)],
        "pearson_r": round(pearson_r, 4),
        "n": n,
    }


# ---------------------------------------------------------------------------
# Main Emotion Runner
# ---------------------------------------------------------------------------

async def run_emotion_experiment(
    config_path: str = "eval/config.yaml",
    out_dir: str = "results/emotion",
    labels_csv_path: Optional[str] = None,
    stub_mode: bool = False,
    mock: Optional[bool] = None,
) -> Dict[str, Any]:
    """Orchestrates full multimodal emotion evaluation and exports TABLE VI."""
    is_mock_run = (mock is True) or (stub_mode is True) or (get_eval_mode() == "mock")
    mode_str = "mock" if is_mock_run else "live"

    # In live mode, ensure required keys are present
    if not is_mock_run:
        require_live_services(
            {
                "GROQ_API_KEY": bool(settings.GROQ_API_KEY),
                "HUME_API_KEY": bool(settings.HUME_API_KEY),
            },
            experiment_name="emotion",
            cli_mock=False,
        )

    tracker = ServiceTracker()

    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    seed = int(cfg.get("seeds", [0])[0])
    fusion_w = float(cfg.get("emotion", {}).get("fusion_w", 0.6))
    tone_threshold = float(cfg.get("emotion", {}).get("tone_threshold", 0.6))
    alert_threshold = float(cfg.get("emotion", {}).get("alert_threshold", 0.7))

    cache = DiskCache(cfg.get("paths", {}).get("cache_dir", ".eval_cache"))

    # Determine output path: default results/emotion gets timestamp (with MOCK_ in mock mode)
    raw_out = Path(out_dir)
    if raw_out == Path("results/emotion") or raw_out == Path("results"):
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        sub = f"MOCK_{ts}" if is_mock_run else ts
        out_path = Path("results/emotion") / sub
    else:
        out_path = raw_out

    out_path.mkdir(parents=True, exist_ok=True)

    # 1. Resolve and adjudicate gold dataset
    gold_csv = Path(labels_csv_path) if labels_csv_path else Path("eval/data/d3/gold_labels.csv")
    if not gold_csv.exists():
        raw_labels = Path("eval/data/d3/labels.csv")
        if not raw_labels.exists():
            from eval.data.gen_d3 import create_d3_dataset
            create_d3_dataset(str(raw_labels))
        compute_inter_annotator_agreement(str(raw_labels), str(gold_csv), config_path)

    rows: List[Dict[str, Any]] = []
    with open(gold_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)

    # 2. Evaluate each clip across text-only, audio-only, and fused
    eval_clips = []
    for r in rows:
        clip_res = await evaluate_clip(
            r,
            cache,
            fusion_w=fusion_w,
            mock_mode=is_mock_run,
            tracker=tracker,
        )
        eval_clips.append(clip_res)

    # Filter valid clips per signal
    valid_text_clips = [c for c in eval_clips if c.get("text") is not None]
    valid_audio_clips = [c for c in eval_clips if not c.get("audio_missing") and c.get("audio") is not None]
    valid_fused_clips = [c for c in eval_clips if c.get("fused") is not None]

    # Metrics for Text-Only
    text_gold_labels = [c["gold_label"] for c in valid_text_clips]
    text_gold_valences = [c["gold_valence"] for c in valid_text_clips]
    text_labels = [c["text"]["dominant"] for c in valid_text_clips]
    text_valences = [c["text"]["valence"] for c in valid_text_clips]
    metrics_text = compute_performance_metrics(text_gold_labels, text_labels, text_gold_valences, text_valences, seed=seed)

    # Metrics for Audio-Only
    audio_gold_labels = [c["gold_label"] for c in valid_audio_clips]
    audio_gold_valences = [c["gold_valence"] for c in valid_audio_clips]
    audio_labels = [c["audio"]["dominant"] for c in valid_audio_clips]
    audio_valences = [c["audio"]["valence"] for c in valid_audio_clips]
    metrics_audio = compute_performance_metrics(audio_gold_labels, audio_labels, audio_gold_valences, audio_valences, seed=seed)

    # Metrics for Fused
    fused_gold_labels = [c["gold_label"] for c in valid_fused_clips]
    fused_gold_valences = [c["gold_valence"] for c in valid_fused_clips]
    fused_labels = [c["fused"]["dominant"] for c in valid_fused_clips]
    fused_valences = [c["fused"]["valence"] for c in valid_fused_clips]
    metrics_fused = compute_performance_metrics(fused_gold_labels, fused_labels, fused_gold_valences, fused_valences, seed=seed)

    mean_lat_text = round(float(np.mean([c["latency_ms"]["text"] for c in valid_text_clips])), 2) if valid_text_clips else 0.0
    mean_lat_audio = round(float(np.mean([c["latency_ms"]["audio"] for c in valid_audio_clips])), 2) if valid_audio_clips else 0.0
    mean_lat_fused = round(float(np.mean([c["latency_ms"]["fused"] for c in valid_fused_clips])), 2) if valid_fused_clips else 0.0

    # 3. Weight sweep w in [0..1] in steps of 0.1 for Fig. 5(b)
    sweep_weights = [round(w * 0.1, 1) for w in range(11)]
    sweep_rows = []
    sweep_clips = valid_fused_clips if valid_fused_clips else eval_clips
    for w in sweep_weights:
        w_labels = []
        w_valences = []
        w_g_labels = []
        w_g_valences = []
        for c in sweep_clips:
            if c.get("text") and c.get("audio"):
                sig = fuse_emotion_signals(c["text"], c["audio"], audio_weight=w)
                w_labels.append(sig["dominant"])
                w_valences.append(sig["valence"])
                w_g_labels.append(c["gold_label"])
                w_g_valences.append(c["gold_valence"])
        m = compute_performance_metrics(w_g_labels, w_labels, w_g_valences, w_valences, seed=seed)
        row_dict = {
            "audio_weight": w,
            "macro_f1": m["macro_f1"],
            "valence_mae": m["valence_mae"],
            "accuracy": m["accuracy"],
            "pearson_r": m["pearson_r"],
        }
        if is_mock_run:
            row_dict["MOCK DATA"] = "MOCK DATA"
        sweep_rows.append(row_dict)

    sweep_csv = out_path / "sweep.csv"
    with open(sweep_csv, "w", encoding="utf-8", newline="") as f:
        fields = ["audio_weight", "macro_f1", "valence_mae", "accuracy", "pearson_r"]
        if is_mock_run:
            fields.append("MOCK DATA")
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(sweep_rows)

    # 4. Error analysis: 20 clips with largest text vs audio disagreement
    disagreement_clips = [c for c in eval_clips if c.get("text") and c.get("audio")]
    for c in disagreement_clips:
        c["text_audio_valence_diff"] = round(abs(c["text"]["valence"] - c["audio"]["valence"]), 3)
    sorted_disagreements = sorted(disagreement_clips, key=lambda x: x["text_audio_valence_diff"], reverse=True)
    top_disagreements = sorted_disagreements[:20]

    disagreements_csv = out_path / "disagreements.csv"
    with open(disagreements_csv, "w", encoding="utf-8", newline="") as f:
        fields = [
            "clip_id",
            "transcript",
            "gold_label",
            "gold_valence",
            "text_dominant",
            "text_valence",
            "audio_dominant",
            "audio_valence",
            "valence_difference",
            "fused_dominant",
            "fused_valence",
        ]
        if is_mock_run:
            fields.append("MOCK DATA")
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for d in top_disagreements:
            row_d = {
                "clip_id": d["clip_id"],
                "transcript": d["transcript"],
                "gold_label": d["gold_label"],
                "gold_valence": d["gold_valence"],
                "text_dominant": d["text"]["dominant"],
                "text_valence": d["text"]["valence"],
                "audio_dominant": d["audio"]["dominant"],
                "audio_valence": d["audio"]["valence"],
                "valence_difference": d["text_audio_valence_diff"],
                "fused_dominant": d["fused"]["dominant"] if d.get("fused") else "n/a",
                "fused_valence": d["fused"]["valence"] if d.get("fused") else 0.0,
            }
            if is_mock_run:
                row_d["MOCK DATA"] = "MOCK DATA"
            writer.writerow(row_d)

    # 5. Tone Adapter & Frustration Alert Trigger Evaluation
    tone_clips = [c for c in valid_fused_clips] if valid_fused_clips else []
    gold_frustrated_angry = [1 if c["gold_label"].lower() in ("angry", "frustrated") else 0 for c in tone_clips]
    tone_triggers = []
    alert_triggers = []

    tone_cfg = {"tone_adaptation": True}
    for c in tone_clips:
        instr = get_tone_instruction(c["fused"], tone_cfg) if c.get("fused") else None
        tone_triggers.append(1 if instr is not None else 0)
        alert_fired = 1 if (c.get("fused") and c["fused"]["valence"] < -alert_threshold) else 0
        alert_triggers.append(alert_fired)

    def calc_pr(gold_arr: List[int], pred_arr: List[int]) -> Dict[str, float]:
        tp = sum(1 for g, p in zip(gold_arr, pred_arr) if g == 1 and p == 1)
        fp = sum(1 for g, p in zip(gold_arr, pred_arr) if g == 0 and p == 1)
        fn = sum(1 for g, p in zip(gold_arr, pred_arr) if g == 1 and p == 0)
        prec = tp / float(tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / float(tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * (prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0
        return {"precision": round(prec, 4), "recall": round(rec, 4), "f1": round(f1, 4), "tp": tp, "fp": fp, "fn": fn}

    tone_pr = calc_pr(gold_frustrated_angry, tone_triggers)
    alert_pr = calc_pr(gold_frustrated_angry, alert_triggers)

    # 6. TABLE VI CSV Generation (with MOCK DATA column if mock)
    table_vi_csv = out_path / "table_vi.csv"
    if is_mock_run:
        table_vi_lines = [
            "Signal,Macro-F1,Accuracy,Valence MAE,Pearson r,Added Latency ms,MOCK DATA",
            f"Text-Only,{metrics_text['macro_f1']:.4f},{metrics_text['accuracy']:.4f},{metrics_text['valence_mae']:.4f},{metrics_text['pearson_r']:.4f},{mean_lat_text:.2f},MOCK DATA",
            f"Audio-Only,{metrics_audio['macro_f1']:.4f},{metrics_audio['accuracy']:.4f},{metrics_audio['valence_mae']:.4f},{metrics_audio['pearson_r']:.4f},{mean_lat_audio:.2f},MOCK DATA",
            f"Fused (w={fusion_w}),{metrics_fused['macro_f1']:.4f},{metrics_fused['accuracy']:.4f},{metrics_fused['valence_mae']:.4f},{metrics_fused['pearson_r']:.4f},{mean_lat_fused:.2f},MOCK DATA",
        ]
    else:
        table_vi_lines = [
            "Signal,Macro-F1,Accuracy,Valence MAE,Pearson r,Added Latency ms",
            f"Text-Only,{metrics_text['macro_f1']:.4f},{metrics_text['accuracy']:.4f},{metrics_text['valence_mae']:.4f},{metrics_text['pearson_r']:.4f},{mean_lat_text:.2f}",
            f"Audio-Only,{metrics_audio['macro_f1']:.4f},{metrics_audio['accuracy']:.4f},{metrics_audio['valence_mae']:.4f},{metrics_audio['pearson_r']:.4f},{mean_lat_audio:.2f}",
            f"Fused (w={fusion_w}),{metrics_fused['macro_f1']:.4f},{metrics_fused['accuracy']:.4f},{metrics_fused['valence_mae']:.4f},{metrics_fused['pearson_r']:.4f},{mean_lat_fused:.2f}",
        ]
    with open(table_vi_csv, "w", encoding="utf-8") as f:
        f.write("\n".join(table_vi_lines) + "\n")

    # 7. Write config.json
    try:
        from app.services.voice_pipeline import get_active_pipeline_path
        pipeline_path = get_active_pipeline_path()
    except Exception:
        pipeline_path = "custom"

    config_manifest = {
        "experiment": "emotion",
        "mode": mode_str,
        "pipeline_path": pipeline_path,
        "services_used": tracker.get_counts(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "parameters": {
            "fusion_w": fusion_w,
            "tone_threshold": tone_threshold,
            "alert_threshold": alert_threshold,
            "seed": seed,
        },
    }
    with open(out_path / "config.json", "w", encoding="utf-8") as f:
        json.dump(config_manifest, f, indent=2, default=str)

    # 8. Metrics JSON summary
    summary = {
        "mode": mode_str,
        "services_used": tracker.get_counts(),
        "parameters": {
            "fusion_w": fusion_w,
            "tone_threshold": tone_threshold,
            "alert_threshold": alert_threshold,
            "seed": seed,
        },
        "total_clips": len(eval_clips),
        "n_valid_text": len(valid_text_clips),
        "n_valid_audio": len(valid_audio_clips),
        "n_valid_fused": len(valid_fused_clips),
        "text_only": {**metrics_text, "latency_ms": mean_lat_text},
        "audio_only": {**metrics_audio, "latency_ms": mean_lat_audio},
        "fused": {**metrics_fused, "latency_ms": mean_lat_fused},
        "tone_adapter_trigger": tone_pr,
        "frustration_alert_trigger": alert_pr,
        "weight_sweep_file": str(sweep_csv),
        "disagreements_file": str(disagreements_csv),
        "table_vi_file": str(table_vi_csv),
    }

    write_metrics(out_path / "metrics.json", summary)

    # Stamp CSVs with mock data column if in mock mode
    if is_mock_run:
        stamp_csv_mock_data(table_vi_csv, mode="mock")
        stamp_csv_mock_data(sweep_csv, mode="mock")
        stamp_csv_mock_data(disagreements_csv, mode="mock")

    print("=" * 70)
    print(f"EMOTION EVALUATION COMPLETE ({mode_str.upper()} MODE)")
    print("=" * 70)
    print(f"Total Clips:       {len(eval_clips)}")
    print(f"Text-Only (n={len(valid_text_clips)}) Macro-F1: {metrics_text['macro_f1']} | MAE: {metrics_text['valence_mae']}")
    print(f"Audio-Only (n={len(valid_audio_clips)}) Macro-F1: {metrics_audio['macro_f1']} | MAE: {metrics_audio['valence_mae']}")
    print(f"Fused (n={len(valid_fused_clips)}) Macro-F1:     {metrics_fused['macro_f1']} | MAE: {metrics_fused['valence_mae']}")
    print(f"TABLE VI:          {table_vi_csv}")
    print(f"Sweep CSV:         {sweep_csv}")
    print(f"Disagreements CSV: {disagreements_csv}")
    print("=" * 70)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Multimodal Emotion Evaluation Experiment")
    parser.add_argument("--config", default="eval/config.yaml", help="Path to config file")
    parser.add_argument("--out", default="results/emotion", help="Output directory")
    parser.add_argument("--input", default="eval/data/d3/gold_labels.csv", help="Path to gold labels CSV")
    parser.add_argument("--mock", action="store_true", default=False, help="Run in offline mock mode")
    parser.add_argument("--stub", action="store_true", default=False, help="Alias for --mock")
    args = parser.parse_args()

    import asyncio
    asyncio.run(
        run_emotion_experiment(
            config_path=args.config,
            out_dir=args.out,
            labels_csv_path=args.input,
            mock=args.mock or args.stub,
        )
    )


if __name__ == "__main__":
    main()
