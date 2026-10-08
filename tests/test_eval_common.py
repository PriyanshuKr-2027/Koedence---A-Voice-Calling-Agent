"""Tests for VoCall evaluation common statistics and utilities.

Validates bootstrap_ci, paired_bootstrap, mcnemar, and cohen_kappa using
small hand-computed analytical examples without any network calls.
"""

from __future__ import annotations

import math
from pathlib import Path
import sys
import tempfile

# Ensure repo root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pytest
import scipy.stats
import yaml

from eval.common.cache import DiskCache, compute_cache_key
from eval.common.cost import CostTracker, estimate_call_cost
from eval.common.runlog import append_jsonl, start_run, write_metrics
from eval.common.stats import bootstrap_ci, cohen_kappa, mcnemar, paired_bootstrap



# ---------------------------------------------------------------------------
# stats.py unit tests with hand-computed analytical checks
# ---------------------------------------------------------------------------

def test_bootstrap_ci_constant():
    """Constant array must produce identical lower, upper bounds and mean."""
    values = [4.5, 4.5, 4.5, 4.5]
    low, high = bootstrap_ci(values, n=100, seed=42)
    assert low == 4.5
    assert high == 4.5


def test_bootstrap_ci_hand_computed_bounds():
    """Bootstrap CI on [1, 2, 3, 4, 5] should center around 3.0 and stay bounded."""
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    ci = bootstrap_ci(values, n=1000, ci=0.95, seed=0)
    low, high = ci

    assert ci.mean == 3.0
    assert 1.0 <= low <= 3.0
    assert 3.0 <= high <= 5.0
    assert low < high


def test_paired_bootstrap_identical_pairs():
    """Identical pairs have mean difference of zero and p-value = 1.0."""
    a = [10.0, 20.0, 30.0, 40.0]
    b = [10.0, 20.0, 30.0, 40.0]
    low, high, p_val = paired_bootstrap(a, b, n=200, seed=0)

    assert low == 0.0
    assert high == 0.0
    assert p_val == 1.0


def test_paired_bootstrap_constant_shift():
    """Constant shift between pairs has exact mean difference and p-value = 0.0."""
    a = [15.0, 25.0, 35.0, 45.0]
    b = [10.0, 20.0, 30.0, 40.0]
    res = paired_bootstrap(a, b, n=500, seed=0)

    assert math.isclose(res.mean_diff, 5.0)
    assert math.isclose(res.low, 5.0)
    assert math.isclose(res.high, 5.0)
    assert res.p_value == 0.0


def test_mcnemar_exact_hand_computed():
    """
    Hand-computed McNemar exact test:
      b = 1 discordant (A=1, B=0)
      c = 10 discordant (A=0, B=1)
      Total discordant n = 11 (< 25, triggers exact binomial).
      Under H0, X ~ Binom(11, 0.5).
      k = min(1, 10) = 1.
      P(X <= 1) = [C(11,0) + C(11,1)] * 0.5^11 = (1 + 11) / 2048 = 12 / 2048.
      Two-sided p-value = 2 * (12 / 2048) = 24 / 2048 = 0.01171875.
    """
    # 2x2 contingency table: [[d, c], [b, a]]
    table = [[40, 10], [1, 50]]
    stat, p_val = mcnemar(table, exact=True)

    expected_p = 24.0 / 2048.0
    assert stat == 1.0
    assert math.isclose(p_val, expected_p, rel_tol=1e-7)


def test_mcnemar_1d_arrays_exact():
    """Same hand-computed scenario passed as 1D binary observation arrays."""
    # b_disc = 1 (a=1, b=0), c_disc = 10 (a=0, b=1)
    a = [1] * 1 + [0] * 10 + [1] * 5 + [0] * 5
    b = [0] * 1 + [1] * 10 + [1] * 5 + [0] * 5

    stat, p_val = mcnemar(a, b)
    expected_p = 24.0 / 2048.0
    assert stat == 1.0
    assert math.isclose(p_val, expected_p, rel_tol=1e-7)


def test_mcnemar_asymptotic_hand_computed():
    """
    Hand-computed McNemar Chi-Square test with continuity correction:
      b = 30, c = 10, total discordant n = 40 (>= 25).
      diff = |30 - 10| = 20.
      chi2 = (|20| - 1)^2 / 40 = 19^2 / 40 = 361 / 40 = 9.025.
      p_val = chi2.sf(9.025, df=1).
    """
    table = [[100, 10], [30, 100]]
    stat, p_val = mcnemar(table, exact=False, correction=True)

    expected_stat = 9.025
    expected_p = float(scipy.stats.chi2.sf(expected_stat, df=1))

    assert math.isclose(stat, expected_stat, rel_tol=1e-5)
    assert math.isclose(p_val, expected_p, rel_tol=1e-5)


def test_cohen_kappa_hand_computed():
    """
    Hand-computed Cohen's Kappa:
      Rater A: [1, 0, 1, 1, 0, 1]  (4 ones, 2 zeros) -> pA(1) = 4/6, pA(0) = 2/6
      Rater B: [1, 0, 1, 0, 0, 1]  (3 ones, 3 zeros) -> pB(1) = 3/6, pB(0) = 3/6
      N = 6. Agreements: indices 0, 1, 2, 4, 5 (5 out of 6).
      Po = 5/6.
      Pe = (4/6 * 3/6) + (2/6 * 3/6) = 12/36 + 6/36 = 18/36 = 1/2 = 0.5.
      kappa = (Po - Pe) / (1 - Pe) = (5/6 - 3/6) / (1 - 3/6) = (2/6) / (3/6) = 2/3.
    """
    rater_a = [1, 0, 1, 1, 0, 1]
    rater_b = [1, 0, 1, 0, 0, 1]

    kappa = cohen_kappa(rater_a, rater_b)
    assert math.isclose(kappa, 2.0 / 3.0, rel_tol=1e-5)


def test_cohen_kappa_perfect_agreement():
    """Identical raters yield kappa = 1.0."""
    rater = ["pos", "neg", "pos", "neutral", "pos"]
    assert cohen_kappa(rater, rater) == 1.0


# ---------------------------------------------------------------------------
# cache.py, runlog.py, cost.py offline tests
# ---------------------------------------------------------------------------

def test_cache_sha256_hit_and_miss():
    """Verifies disk cache hashing and retrieval without network."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = DiskCache(cache_dir=tmpdir)

        provider = "groq"
        model = "llama-3.3-70b-versatile"
        prompt = {"system": "prompt", "user": "test input"}

        assert not cache.has(provider, model, prompt)
        assert cache.get(provider, model, prompt) is None

        # Set cache
        key = cache.set(provider, model, prompt, {"answer": "hello world"})
        assert isinstance(key, str)
        assert len(key) == 64  # SHA-256 hex length

        # Get cache
        cached = cache.get(provider, model, prompt)
        assert cached == {"answer": "hello world"}

        # Function cached_call should not invoke fn on hit
        called = False
        def fn():
            nonlocal called
            called = True
            return {"answer": "fresh"}

        res = cache.cached_call(provider, model, prompt, fn)
        assert not called
        assert res == {"answer": "hello world"}


def test_runlog_start_run_manifest():
    """Verifies start_run writes config.json with seed, python version, and git commit."""
    with tempfile.TemporaryDirectory() as tmpdir:
        dummy_cfg = {
            "seeds": [42, 1],
            "models": {"embedding_model": "nomic-embed-text-v1_5"},
            "memory": {"k": 5, "tau": 0.75},
        }
        run = start_run("test_exp", config=dummy_cfg, base_dir=tmpdir)

        config_json = run.run_dir / "config.json"
        assert config_json.exists()

        with open(config_json, "r", encoding="utf-8") as f:
            manifest = yaml.safe_load(f)

        assert manifest["experiment"] == "test_exp"
        assert manifest["seed"] == 42
        assert "git_commit" in manifest
        assert "python_version" in manifest
        assert "settings_snapshot" in manifest
        assert manifest["settings_snapshot"]["RETRIEVAL_TOP_K"] == 5
        assert manifest["settings_snapshot"]["RETRIEVAL_TAU"] == 0.75
        assert manifest["model_names"]["embedding_model"] == "nomic-embed-text-v1_5"

        # Test append_jsonl and write_metrics
        run.append_jsonl("records.jsonl", {"item": 1, "score": 0.95})
        run.write_metrics("metrics.json", {"accuracy": 0.95})

        assert (run.run_dir / "records.jsonl").exists()
        assert (run.run_dir / "metrics.json").exists()


def test_cost_tracker_and_pricing():
    """Verifies token tracking and estimated USD costs offline."""
    tracker = CostTracker()
    cost = estimate_call_cost("llama-3.3-70b-versatile", prompt_tokens=1000, completion_tokens=500)
    assert cost > 0.0

    with tracker.track("groq", "llama-3.3-70b-versatile") as scope:
        scope.set_tokens(prompt_tokens=1000, completion_tokens=500)

    summary = tracker.summary()
    assert summary["total_calls"] == 1
    assert summary["total_tokens"] == 1500
    assert summary["total_cost_usd"] == cost
