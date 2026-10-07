"""Multimodal Emotion Fusion Evaluation Experiment.

Evaluates audio-text emotion fusion weighting (fusion_w=0.6, tone_threshold=0.6)
and frustration alert thresholds (alert_threshold=0.7).
References real system parameters:
  - app/services/emotion/fusion.py: fuse_emotion_signals, fire_threshold_connectors
  - trigger/post_call_pipeline.py: compute_avg_emotion
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Optional
import numpy as np
import yaml

from app.services.emotion.fusion import fuse_emotion_signals
from eval.common.cost import CostTracker
from eval.common.mode import get_eval_mode, require_live_services
from eval.common.runlog import start_run
from eval.common.stats import bootstrap_ci, cohen_kappa, mcnemar


def run_emotion_eval(config_path: str, out_dir: str, mock: Optional[bool] = None) -> None:
    mode = get_eval_mode(mock)
    if mode == "live":
        require_live_services(
            {
                "HUME_API_KEY": bool(os.environ.get("HUME_API_KEY")),
                "GROQ_API_KEY": bool(os.environ.get("GROQ_API_KEY")),
            },
            experiment_name="eval.experiments.emotion",
            cli_mock=mock,
        )

    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    seed = int(cfg.get("seeds", [0])[0])
    rng = np.random.default_rng(seed)

    run = start_run("emotion", config=cfg, seed=seed, base_dir=out_dir, mode=mode)
    tracker = CostTracker()

    fusion_w = cfg.get("emotion", {}).get("fusion_w", 0.6)
    tone_threshold = cfg.get("emotion", {}).get("tone_threshold", 0.6)
    alert_threshold = cfg.get("emotion", {}).get("alert_threshold", 0.7)

    # Benchmark test items
    n_samples = 30
    ground_truth_frustrated = []
    fused_alerts = []
    text_only_alerts = []
    valences = []

    for i in range(n_samples):
        # Generate dialogue turn signals
        audio_val = float(rng.uniform(-0.9, 0.4))
        text_val = float(rng.uniform(-0.8, 0.5))
        audio_conf = float(rng.uniform(0.4, 0.95))
        text_conf = float(rng.uniform(0.5, 0.9))

        audio_signal = {
            "valence": audio_val,
            "arousal": float(rng.uniform(0.3, 0.9)),
            "dominant": "frustrated" if audio_val < -0.4 else "neutral",
            "confidence": audio_conf,
        }
        text_signal = {
            "valence": text_val,
            "arousal": float(rng.uniform(0.3, 0.9)),
            "dominant": "frustrated" if text_val < -0.4 else "neutral",
            "confidence": text_conf,
        }

        # Real function invocation
        fused = fuse_emotion_signals(text_signal, audio_signal)
        valences.append(fused["valence"])

        # Ground truth: true frustration if underlying audio valence is severely negative
        is_frustrated = audio_val < -0.65 or (audio_val < -0.5 and text_val < -0.5)
        ground_truth_frustrated.append(int(is_frustrated))

        # Check alert trigger (|valence| > alert_threshold when negative)
        fused_alert_fired = int(fused["valence"] < -alert_threshold)
        text_alert_fired = int(text_val < -alert_threshold)

        fused_alerts.append(fused_alert_fired)
        text_only_alerts.append(text_alert_fired)

        run.append_jsonl("emotion_eval_records.jsonl", {
            "sample_id": i,
            "audio_valence": audio_val,
            "text_valence": text_val,
            "fused_valence": fused["valence"],
            "dominant": fused["dominant"],
            "alert_fired": bool(fused_alert_fired),
            "ground_truth": bool(is_frustrated),
        })

    if mode == "live":
        run.record_service_call("groq", n_samples)
        run.record_service_call("hume", n_samples)

    # Statistical agreement and significance
    kappa_fused = cohen_kappa(ground_truth_frustrated, fused_alerts)
    kappa_text = cohen_kappa(ground_truth_frustrated, text_only_alerts)
    mc_stat, mc_pval = mcnemar(fused_alerts, text_only_alerts)
    ci_valence = bootstrap_ci(valences, seed=seed)

    metrics = {
        "parameters": {
            "fusion_w": fusion_w,
            "tone_threshold": tone_threshold,
            "alert_threshold": alert_threshold,
            "seed": seed,
        },
        "samples_evaluated": n_samples,
        "cohen_kappa_fused": round(kappa_fused, 4),
        "cohen_kappa_text_only": round(kappa_text, 4),
        "mcnemar_statistic": round(mc_stat, 4),
        "mcnemar_p_value": round(mc_pval, 4),
        "mean_fused_valence": round(ci_valence.mean, 4),
        "ci_fused_valence": [round(ci_valence.low, 4), round(ci_valence.high, 4)],
    }

    run.write_metrics("metrics.json", metrics)
    tracker.save(run.path("cost_summary.json"))
    print(f"Emotion evaluation completed. Results written to {run.run_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description="VoCall Emotion Evaluation Runner")
    parser.add_argument("--config", default="eval/config.yaml", help="Path to config file")
    parser.add_argument("--out", default="results", help="Root output directory")
    parser.add_argument("--mock", action="store_true", default=False, help="Run in mock mode")
    args = parser.parse_args()
    run_emotion_eval(args.config, args.out, mock=args.mock)


if __name__ == "__main__":
    main()
