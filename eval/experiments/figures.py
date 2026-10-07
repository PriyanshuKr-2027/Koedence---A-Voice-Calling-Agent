"""Figure and Table Generation Script.

Aggregates metrics from results/ directories and compiles summary tables
and plot manifests for documentation and research paper sections.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional
import yaml

from eval.common.mode import get_eval_mode
from eval.common.runlog import start_run


def generate_figures(config_path: str, out_dir: str, mock: Optional[bool] = None) -> None:
    mode = get_eval_mode(mock)
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    seed = int(cfg.get("seeds", [0])[0])
    run = start_run("figures", config=cfg, seed=seed, base_dir=out_dir, mode=mode)

    results_root = Path(cfg.get("paths", {}).get("results_dir", "results"))

    summary_tables = {}
    experiments = ["memory", "emotion", "wer", "latency", "erasure"]

    for exp in experiments:
        exp_dir = results_root / exp
        if exp_dir.exists():
            # Find latest run
            runs = sorted(exp_dir.glob("*_*"))
            if runs:
                latest_metrics = runs[-1] / "metrics.json"
                if latest_metrics.exists():
                    try:
                        with open(latest_metrics, "r", encoding="utf-8") as mf:
                            summary_tables[exp] = json.load(mf)
                    except Exception:
                        summary_tables[exp] = {"status": "read_error"}
                else:
                    summary_tables[exp] = {"status": "no_metrics_file"}
        else:
            summary_tables[exp] = {"status": "not_run_yet"}

    run.write_metrics("aggregated_experiment_summary.json", summary_tables)
    print(f"Figures and summary tables compiled. Output saved to {run.run_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description="VoCall Figure and Table Generator")
    parser.add_argument("--config", default="eval/config.yaml", help="Path to config file")
    parser.add_argument("--out", default="results", help="Root output directory")
    parser.add_argument("--mock", action="store_true", default=False, help="Run in mock mode")
    args = parser.parse_args()
    generate_figures(args.config, args.out, mock=args.mock)


if __name__ == "__main__":
    main()
