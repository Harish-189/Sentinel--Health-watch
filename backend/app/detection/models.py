"""Detection outputs. Every anomaly carries a deterministic evidence ID that later stages cite."""

from __future__ import annotations

from pydantic import BaseModel


def evidence_id(district: str, source: str, metric: str, start_day: int) -> str:
    return f"EV-{district}-{source[:3].upper()}-{metric}-{start_day:04d}"


def series_id(district: str, source: str, metric: str) -> str:
    return f"SR-{district}-{source[:3].upper()}-{metric}"


class SeriesDetection(BaseModel):
    series_id: str
    district: str
    source: str
    metric: str
    log_scale: bool
    direction: str
    sigma: float
    days: list[int]
    dates: list[str]
    observed: list[float | None]
    expected: list[float]
    lower: list[float]
    upper: list[float]
    z: list[float | None]  # direction-adjusted: positive = anomalous direction
    ewma: list[float]
    cusum: list[float]


class Anomaly(BaseModel):
    evidence_id: str
    series_id: str
    district: str
    source: str
    metric: str
    start_day: int
    end_day: int
    start_date: str
    end_date: str
    peak_z: float
    mean_z: float
    days_flagged: int
    persistence_days: int
    excess_pct: float  # mean (observed - expected) / expected over the episode
    ewma_alarm_day: int | None
    cusum_alarm_day: int | None
    first_signal_day: int  # earliest of z-rule, EWMA and CUSUM onsets
