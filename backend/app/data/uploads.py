"""Uploaded aggregate CSVs (Scenario Lab). An upload is a set of long-format aggregate rows
(day, district, source, metric, value) that override the simulated values; it is referenced in a scenario
as the token `upload:<id>`, so every endpoint (analysis, case file, timeline) works on it unchanged.

The PII guard runs first: person-level or PII-like columns/metrics are rejected at ingestion."""

from __future__ import annotations

import hashlib
import io

import pandas as pd

from app.data.districts import CODES
from app.data.privacy import guard_columns
from app.data.schema import METRICS

PREFIX = "upload:"
MAX_ROWS = 5000
REQUIRED = ("day", "district", "source", "metric", "value")
_UPLOADS: dict[str, pd.DataFrame] = {}
_KNOWN = {(m.source, m.metric) for m in METRICS if not m.derived}


class UploadError(ValueError):
    pass


def parse_upload(csv_text: str) -> pd.DataFrame:
    try:
        df = pd.read_csv(io.StringIO(csv_text))
    except Exception as e:  # malformed CSV
        raise UploadError(f"could not parse CSV: {type(e).__name__}") from e
    df.columns = [str(c).strip() for c in df.columns]
    guard_columns(df)  # raises PIIViolation before anything else is inspected
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise UploadError(f"missing columns: {missing} (expected {list(REQUIRED)})")
    extra = [c for c in df.columns if c not in REQUIRED]
    if extra:
        raise UploadError(f"unexpected columns: {extra}: aggregates only")
    if len(df) == 0 or len(df) > MAX_ROWS:
        raise UploadError(f"expected 1..{MAX_ROWS} rows, got {len(df)}")
    bad_d = sorted(set(df["district"]) - set(CODES))
    if bad_d:
        raise UploadError(f"unknown districts: {bad_d[:5]}")
    keys = set(zip(df["source"], df["metric"], strict=True))
    bad_m = sorted(f"{s}.{m}" for s, m in keys - _KNOWN)
    if bad_m:
        raise UploadError(f"unknown source.metric: {bad_m[:5]}")
    df["day"] = pd.to_numeric(df["day"], errors="coerce")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    if df["day"].isna().any() or df["value"].isna().any() or (df["value"] < 0).any():
        raise UploadError("day and value must be numbers; values must be >= 0")
    df["day"] = df["day"].astype(int)
    return df[list(REQUIRED)].drop_duplicates(["day", "district", "source", "metric"], keep="last")


def register(df: pd.DataFrame) -> str:
    uid = hashlib.sha256(df.to_csv(index=False).encode()).hexdigest()[:10]
    _UPLOADS[uid] = df
    return uid


def is_upload(token: str) -> bool:
    return token.startswith(PREFIX)


def known(token: str) -> bool:
    return is_upload(token) and token[len(PREFIX):] in _UPLOADS


def apply_uploads(df: pd.DataFrame, tokens: list[str]) -> pd.DataFrame:
    """Override simulated rows with uploaded values (days outside the simulated range are ignored)."""
    if not tokens:
        return df
    out = df.copy()
    key = ["day", "district", "source", "metric"]
    for t in tokens:
        up = _UPLOADS[t[len(PREFIX):]]
        merged = out.merge(up, on=key, how="left", suffixes=("", "_up"))
        has = merged["value_up"].notna().to_numpy()
        out.loc[has, "value"] = merged.loc[has, "value_up"].to_numpy()
    return out
