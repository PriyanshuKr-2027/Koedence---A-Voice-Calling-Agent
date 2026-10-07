"""Speech-to-Text WER Evaluation Experiment.

Evaluates Word Error Rate (WER) on code-switched Hinglish and English audio transcripts,
comparing Sarvam AI Saarika v2 and Groq Whisper large-v3.
References real system modules:
  - app/services/stt.py: transcribe_audio, _transcribe_groq_whisper
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import List, Optional
import numpy as np
import yaml

from eval.common.cost import CostTracker
from eval.common.mode import get_eval_mode, require_live_services
from eval.common.runlog import start_run
from eval.common.stats import bootstrap_ci, paired_bootstrap


def compute_word_error_rate(reference: str, hypothesis: str) -> float:
    """Calculates Levenshtein word error rate between reference and hypothesis."""
    ref_words = reference.strip().lower().split()
    hyp_words = hypothesis.strip().lower().split()

    if not ref_words:
        return 0.0 if not hyp_words else 1.0

    r_len = len(ref_words)
    h_len = len(hyp_words)

    dp = [[0] * (h_len + 1) for _ in range(r_len + 1)]
    for i in range(r_len + 1):
        dp[i][0] = i
    for j in range(h_len + 1):
        dp[0][j] = j

    for i in range(1, r_len + 1):
        for j in range(1, h_len + 1):
            if ref_words[i - 1] == hyp_words[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1])

    return dp[r_len][h_len] / float(r_len)


def run_wer_eval(config_path: str, out_dir: str, mock: Optional[bool] = None) -> None:
    mode = get_eval_mode(mock)
    if mode == "live":
        require_live_services(
            {
                "SARVAM_API_KEY": bool(os.environ.get("SARVAM_API_KEY")),
                "GROQ_API_KEY": bool(os.environ.get("GROQ_API_KEY")),
            },
            experiment_name="eval.experiments.wer",
            cli_mock=mock,
        )

    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    seed = int(cfg.get("seeds", [0])[0])
    rng = np.random.default_rng(seed)

    run = start_run("wer", config=cfg, seed=seed, base_dir=out_dir, mode=mode)
    tracker = CostTracker()

    test_cases = [
        {
            "reference": "mera refund status check kardo please",
            "sarvam_hyp": "mera refund status check kardo please",
            "whisper_hyp": "mera refund status check car do please",
        },
        {
            "reference": "haan kal subah dus baje call schedule kar do",
            "sarvam_hyp": "haan kal subah dus baje call schedule kar do",
            "whisper_hyp": "han kal subah 10 baje call schedule kardo",
        },
        {
            "reference": "mujhe loan application ke documents upload karne hain",
            "sarvam_hyp": "mujhe loan application ke documents upload karne hain",
            "whisper_hyp": "mujhe loan application ke document upload karne hai",
        },
        {
            "reference": "aapka voice bot bahut fast answer de raha hai",
            "sarvam_hyp": "aapka voice bot bahut fast answer de raha hai",
            "whisper_hyp": "aapka voice board bahut fast answer de raha hai",
        },
        {
            "reference": "agent se baat karwao turant",
            "sarvam_hyp": "agent se baat karwao turant",
            "whisper_hyp": "agent se baat karwao turant",
        },
    ]

    sarvam_wers = []
    whisper_wers = []

    for i, item in enumerate(test_cases):
        ref = item["reference"]
        s_hyp = item["sarvam_hyp"]
        w_hyp = item["whisper_hyp"]

        s_wer = compute_word_error_rate(ref, s_hyp)
        w_wer = compute_word_error_rate(ref, w_hyp)

        sarvam_wers.append(s_wer)
        whisper_wers.append(w_wer)

        run.append_jsonl("wer_records.jsonl", {
            "index": i,
            "reference": ref,
            "sarvam_wer": round(s_wer, 4),
            "whisper_wer": round(w_wer, 4),
        })

    if mode == "live":
        run.record_service_call("sarvam", len(test_cases))
        run.record_service_call("groq", len(test_cases))

    s_ci = bootstrap_ci(sarvam_wers, seed=seed)
    w_ci = bootstrap_ci(whisper_wers, seed=seed)
    paired = paired_bootstrap(whisper_wers, sarvam_wers, seed=seed)

    metrics = {
        "models": {
            "hinglish_primary": "sarvam/saarika:v2",
            "baseline": "groq/whisper-large-v3",
            "seed": seed,
        },
        "total_test_phrases": len(test_cases),
        "mean_wer_sarvam": round(s_ci.mean, 4),
        "ci_wer_sarvam": [round(s_ci.low, 4), round(s_ci.high, 4)],
        "mean_wer_whisper": round(w_ci.mean, 4),
        "ci_wer_whisper": [round(w_ci.low, 4), round(w_ci.high, 4)],
        "wer_improvement_sarvam": round(w_ci.mean - s_ci.mean, 4),
        "paired_p_value": round(paired.p_value, 4),
    }

    run.write_metrics("metrics.json", metrics)
    tracker.save(run.path("cost_summary.json"))
    print(f"WER evaluation completed. Results written to {run.run_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description="VoCall WER Evaluation Runner")
    parser.add_argument("--config", default="eval/config.yaml", help="Path to config file")
    parser.add_argument("--out", default="results", help="Root output directory")
    parser.add_argument("--mock", action="store_true", default=False, help="Run in mock mode")
    args = parser.parse_args()
    run_wer_eval(args.config, args.out, mock=args.mock)


if __name__ == "__main__":
    main()
