"""Detector primitives: robust z-score, EWMA, CUSUM, consecutive-run extraction."""

from __future__ import annotations

import numpy as np

Array = np.ndarray
MAD_TO_SIGMA = 1.4826
Z_CLIP = (-4.0, 6.0)  # bound single-day influence on EWMA/CUSUM


def robust_scale(x: Array) -> float:
    """MAD-based scale estimate (equals the std. dev. for Gaussian data), ignoring NaNs."""
    x = x[np.isfinite(x)]
    if x.size == 0:
        return float("nan")
    med = np.median(x)
    return float(MAD_TO_SIGMA * np.median(np.abs(x - med)))


def robust_z(y: Array, expected: Array, sigma: float) -> Array:
    return (y - expected) / sigma


def ewma(z: Array, lam: float) -> Array:
    out = np.zeros_like(z, dtype=float)
    prev = 0.0
    for i, v in enumerate(np.clip(z, *Z_CLIP)):
        if np.isfinite(v):
            prev = lam * v + (1 - lam) * prev
        out[i] = prev
    return out


def ewma_limit(lam: float, L: float) -> float:
    return float(L * np.sqrt(lam / (2 - lam)))


def cusum(z: Array, k: float) -> Array:
    """One-sided upper CUSUM on standardized residuals."""
    out = np.zeros_like(z, dtype=float)
    s = 0.0
    for i, v in enumerate(np.clip(z, *Z_CLIP)):
        if np.isfinite(v):
            s = max(0.0, s + v - k)
        out[i] = s
    return out


def consecutive_runs(flags: Array, min_len: int, merge_gap: int) -> list[tuple[int, int]]:
    """Index ranges (inclusive) of streaks of True with length >= min_len; nearby streaks merge."""
    streaks: list[tuple[int, int]] = []
    start: int | None = None
    for i, f in enumerate(np.r_[flags.astype(bool), False]):
        if f and start is None:
            start = i
        elif not f and start is not None:
            if i - start >= min_len:
                streaks.append((start, i - 1))
            start = None
    merged: list[tuple[int, int]] = []
    for s, e in streaks:
        if merged and s - merged[-1][1] - 1 <= merge_gap:
            merged[-1] = (merged[-1][0], e)
        else:
            merged.append((s, e))
    return merged


def alarm_onset(alarm: Array, anchor: int, lookback: int) -> int | None:
    """Earliest index of the alarm streak that contains `anchor` (searching back up to `lookback`),
    else the first alarm after `anchor`."""
    if alarm[anchor]:
        i = anchor
        while i > 0 and anchor - i < lookback and alarm[i - 1]:
            i -= 1
        return i
    after = np.flatnonzero(alarm[anchor:])
    return int(anchor + after[0]) if after.size else None
