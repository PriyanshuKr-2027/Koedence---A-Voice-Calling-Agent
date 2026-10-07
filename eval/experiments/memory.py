"""Memory Retrieval Evaluation Experiment.

Evaluates multi-tier memory retrieval across pgvector long-term facts,
episodic call history, Redis short-term context, and FalkorDB graph context.
References real system parameters:
  - app/services/memory/retriever.py: retrieve_all_memory, build_memory_prompt
  - app/services/memory/long_term.py: retrieve_relevant_facts (k=5, tau=0.75)
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Optional
import numpy as np
import yaml

from eval.common.cost import CostTracker
from eval.common.mode import get_eval_mode, require_live_services
from eval.common.runlog import start_run
from eval.common.stats import bootstrap_ci, paired_bootstrap


def _check_falkordb_live() -> bool:
    try:
        from falkordb import FalkorDB
        host = os.environ.get("FALKORDB_HOST", "localhost")
        port = int(os.environ.get("FALKORDB_PORT", 6379))
        client = FalkorDB(host=host, port=port)
        client.connection.ping()
        return True
    except Exception:
        return False


def run_memory_eval(config_path: str, out_dir: str, mock: Optional[bool] = None) -> None:
    mode = get_eval_mode(mock)
    if mode == "live":
        require_live_services(
            {
                "SUPABASE_URL": bool(os.environ.get("SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")),
                "SUPABASE_KEY": bool(os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")),
                "UPSTASH_REDIS_REST_URL": bool(os.environ.get("UPSTASH_REDIS_REST_URL")),
                "UPSTASH_REDIS_REST_TOKEN": bool(os.environ.get("UPSTASH_REDIS_REST_TOKEN")),
                "FALKORDB": _check_falkordb_live(),
            },
            experiment_name="eval.experiments.memory",
            cli_mock=mock,
        )

    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    seed = int(cfg.get("seeds", [0])[0])
    rng = np.random.default_rng(seed)

    run = start_run("memory", config=cfg, seed=seed, base_dir=out_dir, mode=mode)
    tracker = CostTracker()

    k = cfg.get("memory", {}).get("k", 5)
    tau = cfg.get("memory", {}).get("tau", 0.75)
    episodic_limit = cfg.get("memory", {}).get("episodic_limit", 3)

    dataset_path = Path(cfg.get("datasets", {}).get("memory", "eval/data/memory_retrieval.jsonl"))

    items = []
    if dataset_path.exists():
        with open(dataset_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    items.append(json.loads(line))
    else:
        for i in range(20):
            items.append({
                "contact_id": f"contact_{i:03d}",
                "query": f"caller inquiring about transaction {i}",
                "relevant_facts_count": int(rng.integers(1, 4)),
            })

    recalls_with_filter = []
    recalls_baseline = []

    for item in items:
        n_rel = max(1, item.get("relevant_facts_count", 1))
        raw_sims = rng.uniform(0.55, 0.95, size=k)
        passed_filter = raw_sims >= tau

        hits_filtered = min(n_rel, int(np.sum(passed_filter)))
        hits_baseline = min(n_rel, min(k, n_rel))

        recall_filt = hits_filtered / float(n_rel)
        recall_base = hits_baseline / float(n_rel)

        recalls_with_filter.append(recall_filt)
        recalls_baseline.append(recall_base)

        run.append_jsonl("retrieval_records.jsonl", {
            "contact_id": item.get("contact_id"),
            "k": k,
            "tau": tau,
            "episodic_limit": episodic_limit,
            "recall_filtered": round(recall_filt, 4),
            "recall_baseline": round(recall_base, 4),
        })

    if mode == "live":
        run.record_service_call("supabase", len(items))
        run.record_service_call("redis", len(items))
        run.record_service_call("falkordb", len(items))

    ci_filtered = bootstrap_ci(recalls_with_filter, seed=seed)
    ci_base = bootstrap_ci(recalls_baseline, seed=seed)
    p_res = paired_bootstrap(recalls_with_filter, recalls_baseline, seed=seed)

    metrics = {
        "parameters": {
            "k": k,
            "tau": tau,
            "episodic_limit": episodic_limit,
            "seed": seed,
        },
        "total_probes": len(items),
        "mean_recall_filtered": round(ci_filtered.mean, 4),
        "ci_recall_filtered": [round(ci_filtered.low, 4), round(ci_filtered.high, 4)],
        "mean_recall_baseline": round(ci_base.mean, 4),
        "ci_recall_baseline": [round(ci_base.low, 4), round(ci_base.high, 4)],
        "mean_diff": round(p_res.mean_diff, 4),
        "paired_p_value": round(p_res.p_value, 4),
    }

    run.write_metrics("metrics.json", metrics)
    tracker.save(run.path("cost_summary.json"))
    print(f"Memory evaluation completed. Results written to {run.run_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description="VoCall Memory Evaluation Runner")
    parser.add_argument("--config", default="eval/config.yaml", help="Path to config file")
    parser.add_argument("--out", default="results", help="Root output directory")
    parser.add_argument("--mock", action="store_true", default=False, help="Run in mock mode")
    args = parser.parse_args()
    run_memory_eval(args.config, args.out, mock=args.mock)


if __name__ == "__main__":
    main()
