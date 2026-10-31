"""Confidence: logistic score over gate features, Platt-calibrated, with a bootstrap interval."""

from __future__ import annotations

import math

import numpy as np

from app.analysis.context import AnalysisContext
from app.analysis.models import Confidence, Signal
from app.config import get_settings


def features(n_sources: int, mean_z: float, lag: float, n_adjacent: int, persistence: int,
             residual: float) -> dict[str, float]:
    return {
        "independent_sources": float(np.clip((n_sources - 1) / 4, 0, 1)),
        "mean_z": float(np.clip(mean_z / 6, 0, 1)),
        "lag_consistency": float(np.clip(lag, 0, 1)),
        "spatial_coherence": float(np.clip(n_adjacent / 2, 0, 1)),
        "persistence_days": float(np.clip(persistence / 7, 0, 1)),
        "confounder_residual": float(np.clip(residual / 0.6, 0, 1)),
    }


def score(feats: dict[str, float]) -> float:
    c = get_settings().confidence
    logit = c.intercept + sum(c.weights[k] * v for k, v in feats.items())
    return 1 / (1 + math.exp(-(c.platt_a * logit + c.platt_b)))


def estimate(ctx: AnalysisContext, sig: Signal | None, residual: float, seed: int) -> Confidence:
    if sig is None:
        f = features(0, 0.0, 0.0, 0, 0, 0.0)
        p = round(score(f), 3)
        return Confidence(point=p, low=p, high=p, features=f)
    f = features(sig.independent_sources, sig.mean_z, sig.lag_consistency, len(sig.adjacent_districts),
                 sig.persistence_days, residual)
    point = score(f)
    anomalies = {a.evidence_id: a for a in ctx.report.anomalies}
    window = [anomalies[e] for e in sig.window_ids]
    rng = np.random.default_rng([seed, sum(map(ord, sig.district))])
    resid_ratio = residual / sig.mean_excess if sig.mean_excess > 0 else 0.0
    draws = []
    for _ in range(get_settings().confidence.bootstrap_n):
        sample = [window[i] for i in rng.integers(0, len(window), len(window))]
        mean_excess = float(np.mean([a.excess_pct for a in sample]))
        persistence = max(a.end_day for a in sample) - min(a.start_day for a in sample)
        draws.append(score(features(
            len({a.source for a in sample}), float(np.mean([a.mean_z for a in sample])), sig.lag_consistency,
            len(sig.adjacent_districts), min(persistence, sig.persistence_days), mean_excess * resid_ratio,
        )))
    low, high = np.percentile(draws, [10, 90])
    return Confidence(point=round(point, 3), low=round(min(float(low), point), 3),
                      high=round(max(float(high), point), 3), features={k: round(v, 3) for k, v in f.items()})
