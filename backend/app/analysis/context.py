"""Shared inputs for one analysis run (not serialized)."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from app.data.scenarios import GroundTruth
from app.detection.models import SeriesDetection
from app.detection.run import DetectionReport

Array = np.ndarray


@dataclass
class AnalysisContext:
    scenario: tuple[str, ...]
    seed: int
    as_of: int
    df: pd.DataFrame  # privacy-processed long frame (has `suppressed`)
    mats: dict[tuple[str, str, str], Array]
    dates: pd.DatetimeIndex
    holidays: dict[int, str]
    report: DetectionReport
    truth: GroundTruth
    _series: dict[tuple[str, str, str], SeriesDetection] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._series = {(s.district, s.source, s.metric): s for s in self.report.series}

    def series(self, district: str, source: str, metric: str) -> SeriesDetection | None:
        return self._series.get((district, source, metric))

    def raw(self, district: str, source: str, metric: str) -> Array:
        """Observed values for all days up to as_of (later days are NaN)."""
        y = self.mats.get((district, source, metric))
        if y is None:
            return np.full(len(self.dates), np.nan)
        out = y.copy()
        out[self.as_of + 1 :] = np.nan
        return out

    def date(self, day: int) -> str:
        return str(self.dates[day].strftime("%Y-%m-%d"))
