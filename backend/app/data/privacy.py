"""Privacy-by-design: PII schema guard, small-cell suppression, optional Laplace noise."""

from __future__ import annotations

import re
from collections.abc import Iterable

import numpy as np
import pandas as pd

from app.config import get_settings
from app.data.schema import SPEC_BY_KEY


class PIIViolation(ValueError):
    """Raised when ingested data carries a person-level or PII-like field."""


def _patterns() -> list[re.Pattern[str]]:
    return [re.compile(p, re.IGNORECASE) for p in get_settings().privacy.pii_patterns]


def is_pii_name(name: str) -> bool:
    if name.lower() in get_settings().privacy.allowlist:
        return False
    return any(p.search(name) for p in _patterns())


def _offenders(names: Iterable[str]) -> list[str]:
    return sorted({n for n in names if is_pii_name(str(n))})


def guard_columns(df: pd.DataFrame) -> None:
    """Reject PII-like column names, and PII-like metric names in long-format data."""
    bad = _offenders(df.columns)
    if "metric" in df.columns:
        bad += _offenders(df["metric"].unique())
    if bad:
        raise PIIViolation(f"PII-like fields rejected at ingestion: {bad}")


def suppress_small_cells(df: pd.DataFrame, k_min: int | None = None) -> pd.DataFrame:
    """Counts below k_min become null and are flagged. Rates and measures are untouched."""
    k = get_settings().privacy.k_min if k_min is None else k_min
    out = df.copy()
    is_count = [
        SPEC_BY_KEY.get((s, m)) is not None and SPEC_BY_KEY[(s, m)].kind == "count"
        for s, m in zip(out["source"], out["metric"], strict=True)
    ]
    small = np.asarray(is_count) & (out["value"] < k).to_numpy()
    out["suppressed"] = small
    out.loc[small, "value"] = np.nan
    return out


def laplace_noise(values: np.ndarray, epsilon: float | None = None, seed: int = 0) -> np.ndarray:
    """Add Laplace(1/epsilon) noise to counts for display/export; clipped at zero."""
    eps = get_settings().privacy.laplace_epsilon if epsilon is None else epsilon
    rng = np.random.default_rng(seed)
    noisy = values + rng.laplace(0.0, 1.0 / eps, size=values.shape)
    return np.clip(np.round(noisy), 0, None)


def apply_privacy(df: pd.DataFrame) -> pd.DataFrame:
    """Full ingestion pipeline: guard, then suppress."""
    guard_columns(df)
    return suppress_small_cells(df)
