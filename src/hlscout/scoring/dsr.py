"""Sharpe significance: t-stat and Deflated Sharpe Ratio (Bailey & Lopez de Prado)."""

from __future__ import annotations

import math
from statistics import NormalDist

import numpy as np

N01 = NormalDist()
EULER = 0.5772156649015329


def tstat(r: np.ndarray) -> float:
    if len(r) < 3 or r.std(ddof=1) == 0:
        return 0.0
    return float(r.mean() / (r.std(ddof=1) / math.sqrt(len(r))))


def deflated_sharpe_prob(r: np.ndarray, n_trials: int) -> float:
    """P(true Sharpe > 0 after correcting for the best of `n_trials` wallets scanned)."""
    T = len(r)
    if T < 10 or r.std(ddof=1) == 0:
        return 0.0
    sr = r.mean() / r.std(ddof=1)  # per-period Sharpe
    z = (r - r.mean()) / r.std(ddof=1)
    skew, kurt = float((z**3).mean()), float((z**4).mean())
    n = max(n_trials, 2)
    # expected max Sharpe of n null trials; null Sharpe variance ~ 1/T
    sr0 = math.sqrt(1.0 / T) * ((1 - EULER) * N01.inv_cdf(1 - 1.0 / n)
                                + EULER * N01.inv_cdf(1 - 1.0 / (n * math.e)))
    denom = math.sqrt(max(1e-12, 1 - skew * sr + (kurt - 1) / 4 * sr**2))
    return float(N01.cdf((sr - sr0) * math.sqrt(T - 1) / denom))
