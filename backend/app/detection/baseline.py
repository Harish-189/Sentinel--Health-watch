"""Seasonal baseline: OLS on trend + annual Fourier + day-of-week + holiday terms, robust refit."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.detection.detectors import robust_scale

Array = np.ndarray


def design_matrix(dates: pd.DatetimeIndex, holidays: set[int], harmonics: int) -> Array:
    n = len(dates)
    t = np.arange(n, dtype=float) / 365.25
    doy = dates.day_of_year.to_numpy().astype(float)
    dow = dates.day_of_week.to_numpy()
    cols: list[Array] = [np.ones(n), t]
    for h in range(1, harmonics + 1):
        w = 2 * np.pi * h * doy / 365.25
        cols += [np.sin(w), np.cos(w)]
    cols += [(dow == d).astype(float) for d in range(1, 7)]
    hol = np.zeros(n)
    hol[[d for d in holidays if 0 <= d < n]] = 1.0
    pre = np.r_[hol[1:], 0.0] * (1 - hol)
    post = np.r_[0.0, hol[:-1]] * (1 - hol)
    cols += [hol, pre, post]
    return np.column_stack(cols)


@dataclass(frozen=True)
class BaselineFit:
    pred: Array  # fitted expected value (transformed scale) for every day
    sigma: float  # robust residual scale on the training window


def fit_baseline(
    y: Array, X: Array, train: Array, min_train: int, outlier_mad: float, min_sigma: float
) -> BaselineFit | None:
    mask = train & np.isfinite(y)
    if mask.sum() < min_train:
        return None
    beta, *_ = np.linalg.lstsq(X[mask], y[mask], rcond=None)
    resid = y[mask] - X[mask] @ beta
    s = robust_scale(resid)
    keep = np.abs(resid - np.median(resid)) <= outlier_mad * max(s, min_sigma)
    if keep.sum() >= min_train:
        beta, *_ = np.linalg.lstsq(X[mask][keep], y[mask][keep], rcond=None)
    pred = X @ beta
    sigma = max(robust_scale(y[mask] - pred[mask]), min_sigma)
    return BaselineFit(pred=pred, sigma=sigma)
