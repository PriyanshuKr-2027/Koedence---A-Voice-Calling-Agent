"""VoCall Statistical Analysis Utilities.

Provides bootstrap confidence intervals, paired bootstrap tests, McNemar tests,
and Cohen's Kappa inter-rater agreement for research evaluation.
"""

from __future__ import annotations

import math
from typing import Any, List, Optional, Sequence, Tuple, Union
import numpy as np
import scipy.stats


class BootstrapResult(tuple):
    """Result of bootstrap_ci, unpackable as (low, high) with named properties."""

    def __new__(cls, low: float, high: float, mean: float):
        return super().__new__(cls, (float(low), float(high)))

    def __init__(self, low: float, high: float, mean: float):
        self.low = float(low)
        self.high = float(high)
        self.mean = float(mean)

    def __repr__(self) -> str:
        return f"BootstrapResult(low={self.low:.4f}, high={self.high:.4f}, mean={self.mean:.4f})"


class PairedBootstrapResult(tuple):
    """Result of paired_bootstrap, unpackable as (low, high, p_value) with named properties."""

    def __new__(cls, low: float, high: float, p_value: float, mean_diff: float):
        return super().__new__(cls, (float(low), float(high), float(p_value)))

    def __init__(self, low: float, high: float, p_value: float, mean_diff: float):
        self.low = float(low)
        self.high = float(high)
        self.p_value = float(p_value)
        self.mean_diff = float(mean_diff)

    def __repr__(self) -> str:
        return (
            f"PairedBootstrapResult(low={self.low:.4f}, high={self.high:.4f}, "
            f"p_value={self.p_value:.4f}, mean_diff={self.mean_diff:.4f})"
        )


class McNemarResult(tuple):
    """Result of mcnemar, unpackable as (statistic, p_value) with contingency table."""

    def __new__(cls, statistic: float, p_value: float, contingency_table: Optional[List[List[int]]] = None):
        return super().__new__(cls, (float(statistic), float(p_value)))

    def __init__(self, statistic: float, p_value: float, contingency_table: Optional[List[List[int]]] = None):
        self.statistic = float(statistic)
        self.p_value = float(p_value)
        self.contingency_table = contingency_table or [[0, 0], [0, 0]]

    def __repr__(self) -> str:
        return f"McNemarResult(statistic={self.statistic:.4f}, p_value={self.p_value:.4e})"


def bootstrap_ci(
    values: Sequence[float],
    n: int = 1000,
    ci: float = 0.95,
    seed: Optional[int] = None,
) -> BootstrapResult:
    """
    Computes empirical bootstrap confidence interval for the mean.

    Args:
        values: Sequence of numeric observations.
        n: Number of bootstrap resamples (default 1000).
        ci: Confidence level between 0 and 1 (default 0.95).
        seed: Random seed for reproducibility.

    Returns:
        BootstrapResult(low, high, mean) unpackable as (low, high).
    """
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        raise ValueError("values cannot be empty")
    if arr.ndim != 1:
        arr = arr.flatten()

    orig_mean = float(np.mean(arr))
    if arr.size == 1 or np.all(arr == arr[0]):
        return BootstrapResult(orig_mean, orig_mean, orig_mean)

    rng = np.random.default_rng(seed)
    indices = rng.integers(0, arr.size, size=(n, arr.size))
    boot_means = np.mean(arr[indices], axis=1)

    alpha = (1.0 - ci) / 2.0
    low = float(np.percentile(boot_means, 100.0 * alpha))
    high = float(np.percentile(boot_means, 100.0 * (1.0 - alpha)))

    return BootstrapResult(low=low, high=high, mean=orig_mean)


def paired_bootstrap(
    a: Sequence[float],
    b: Sequence[float],
    n: int = 1000,
    ci: float = 0.95,
    seed: Optional[int] = None,
) -> PairedBootstrapResult:
    """
    Computes paired bootstrap confidence interval for mean difference (a - b)
    and empirical two-sided p-value testing H0: mean(a - b) == 0.

    Args:
        a: First sequence of paired observations.
        b: Second sequence of paired observations.
        n: Number of bootstrap iterations.
        ci: Confidence level (default 0.95).
        seed: Random seed for reproducibility.

    Returns:
        PairedBootstrapResult(low, high, p_value, mean_diff) unpackable as (low, high, p_value).
    """
    arr_a = np.asarray(a, dtype=float)
    arr_b = np.asarray(b, dtype=float)

    if arr_a.shape != arr_b.shape:
        raise ValueError(f"Shape mismatch: {arr_a.shape} vs {arr_b.shape}")
    if arr_a.size == 0:
        raise ValueError("Inputs cannot be empty")

    diffs = arr_a - arr_b
    mean_diff = float(np.mean(diffs))

    if diffs.size == 1 or np.all(diffs == diffs[0]):
        p_val = 1.0 if np.isclose(mean_diff, 0.0) else 0.0
        return PairedBootstrapResult(mean_diff, mean_diff, p_val, mean_diff)

    rng = np.random.default_rng(seed)
    indices = rng.integers(0, diffs.size, size=(n, diffs.size))
    boot_diffs = np.mean(diffs[indices], axis=1)

    alpha = (1.0 - ci) / 2.0
    low = float(np.percentile(boot_diffs, 100.0 * alpha))
    high = float(np.percentile(boot_diffs, 100.0 * (1.0 - alpha)))

    # Empirical two-sided p-value against zero difference
    prop_leq_zero = np.mean(boot_diffs <= 0.0)
    prop_geq_zero = np.mean(boot_diffs >= 0.0)
    p_value = float(min(1.0, 2.0 * min(prop_leq_zero, prop_geq_zero)))

    return PairedBootstrapResult(low=low, high=high, p_value=p_value, mean_diff=mean_diff)


def mcnemar(
    a: Union[Sequence[Any], Sequence[Sequence[int]]],
    b: Optional[Sequence[Any]] = None,
    exact: Optional[bool] = None,
    correction: bool = True,
) -> McNemarResult:
    """
    Performs McNemar's test for paired nominal / binary data.

    Accepts either:
      1. Two 1D binary arrays a and b (True/False or 1/0).
      2. A single 2x2 contingency matrix: [[n00, n01], [n10, n11]].

    Args:
        a: Array of outcomes or 2x2 table.
        b: Array of paired outcomes if a is 1D.
        exact: If True, uses exact binomial test. If None, auto-selects exact
               when discordant pairs (b + c) < 25.
        correction: Apply Edwards continuity correction for chi-square approximation.

    Returns:
        McNemarResult(statistic, p_value) with contingency_table.
    """
    if b is None:
        # a is expected to be a 2x2 table
        table = np.asarray(a, dtype=int)
        if table.shape != (2, 2):
            raise ValueError(f"Contingency table must be 2x2, got {table.shape}")
        b_disc = int(table[0, 1])
        c_disc = int(table[1, 0])
        matrix = table.tolist()
    else:
        arr_a = np.asarray(a)
        arr_b = np.asarray(b)
        if arr_a.shape != arr_b.shape:
            raise ValueError(f"Shape mismatch: {arr_a.shape} vs {arr_b.shape}")
        if arr_a.size == 0:
            raise ValueError("Inputs cannot be empty")

        # Discordant counts:
        # b_disc: A is positive, B is negative
        # c_disc: A is negative, B is positive
        b_disc = int(np.sum((arr_a.astype(bool)) & (~arr_b.astype(bool))))
        c_disc = int(np.sum((~arr_a.astype(bool)) & (arr_b.astype(bool))))
        a_concord = int(np.sum((arr_a.astype(bool)) & (arr_b.astype(bool))))
        d_concord = int(np.sum((~arr_a.astype(bool)) & (~arr_b.astype(bool))))
        matrix = [[d_concord, c_disc], [b_disc, a_concord]]

    n_disc = b_disc + c_disc

    if n_disc == 0:
        return McNemarResult(0.0, 1.0, matrix)

    use_exact = exact if exact is not None else (n_disc < 25)

    if use_exact:
        k = min(b_disc, c_disc)
        # Two-sided exact binomial test with p = 0.5
        # Under H0, X ~ Binomial(n_disc, 0.5)
        # Two-sided p-value: 2 * sum_{i=0..k} binom(n_disc, i) * 0.5^n_disc
        prob_sum = 0.0
        for i in range(k + 1):
            prob_sum += math.comb(n_disc, i) * (0.5 ** n_disc)
        p_val = float(min(1.0, 2.0 * prob_sum))
        statistic = float(k)
        return McNemarResult(statistic, p_val, matrix)
    else:
        # Asymptotic Chi-Square test with 1 degree of freedom
        diff = abs(b_disc - c_disc)
        if correction:
            stat = ((max(0.0, diff - 1.0)) ** 2) / float(n_disc)
        else:
            stat = (diff ** 2) / float(n_disc)
        p_val = float(scipy.stats.chi2.sf(stat, df=1))
        return McNemarResult(stat, p_val, matrix)


def cohen_kappa(
    rater_a: Sequence[Any],
    rater_b: Sequence[Any],
    weights: Optional[str] = None,
) -> float:
    """
    Computes Cohen's Kappa score for inter-rater reliability.

    Args:
        rater_a: Labels assigned by first rater/evaluator.
        rater_b: Labels assigned by second rater/evaluator.
        weights: Weighting scheme (e.g. None or 'linear', 'quadratic').

    Returns:
        float: Kappa score between -1.0 and 1.0.
    """
    try:
        from sklearn.metrics import cohen_kappa_score
        return float(cohen_kappa_score(rater_a, rater_b, weights=weights))
    except (ImportError, Exception):
        # Fallback pure-Python/numpy unweighted implementation
        arr_a = np.asarray(rater_a)
        arr_b = np.asarray(rater_b)
        if arr_a.shape != arr_b.shape:
            raise ValueError(f"Shape mismatch: {arr_a.shape} vs {arr_b.shape}")
        n = arr_a.size
        if n == 0:
            raise ValueError("Inputs cannot be empty")

        p_o = float(np.mean(arr_a == arr_b))
        categories = np.unique(np.concatenate([arr_a, arr_b]))

        p_e = 0.0
        for cat in categories:
            prop_a = float(np.mean(arr_a == cat))
            prop_b = float(np.mean(arr_b == cat))
            p_e += prop_a * prop_b

        if np.isclose(p_e, 1.0):
            return 1.0 if np.isclose(p_o, 1.0) else 0.0

        kappa = (p_o - p_e) / (1.0 - p_e)
        return float(kappa)
