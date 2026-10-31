"""Run every detector over every (district, source, metric) series as of a given day (causal)."""

from __future__ import annotations

import numpy as np
import pandas as pd
from pydantic import BaseModel

from app.config import DetectionCfg, get_settings
from app.data.schema import METRICS, MetricSpec
from app.detection.baseline import design_matrix, fit_baseline
from app.detection.detectors import (
    alarm_onset,
    consecutive_runs,
    cusum,
    ewma,
    ewma_limit,
    robust_z,
)
from app.detection.models import Anomaly, SeriesDetection, evidence_id, series_id

Array = np.ndarray
Key = tuple[str, str, str]  # (district, source, metric)


class DetectionReport(BaseModel):
    as_of: int
    as_of_date: str
    window_start: int
    series: list[SeriesDetection]
    anomalies: list[Anomaly]

    def series_for(self, district: str, source: str, metric: str) -> SeriesDetection:
        for s in self.series:
            if (s.district, s.source, s.metric) == (district, source, metric):
                return s
        raise KeyError((district, source, metric))

    def anomalies_for(self, district: str | None = None, source: str | None = None) -> list[Anomaly]:
        return [
            a
            for a in self.anomalies
            if (district is None or a.district == district) and (source is None or a.source == source)
        ]


def to_matrix(df: pd.DataFrame) -> tuple[dict[Key, Array], pd.DatetimeIndex]:
    """Long frame -> {(district, source, metric): values over all days}, plus derived lab positivity."""
    dates = pd.DatetimeIndex(pd.to_datetime(df.drop_duplicates("day").sort_values("day")["date"]))
    wide = df.set_index(["district", "source", "metric", "day"])["value"].unstack("day")
    wide = wide.reindex(columns=range(len(dates)))
    mats: dict[Key, Array] = {k: row.astype(float) for k, row in zip(wide.index, wide.values, strict=True)}
    for district in df["district"].unique():
        for panel in ("A", "B"):
            tests = mats.get((district, "lab", f"panel_{panel}_tests"))
            pos = mats.get((district, "lab", f"panel_{panel}_positives"))
            if tests is None or pos is None:
                continue
            with np.errstate(divide="ignore", invalid="ignore"):
                rate = np.where(tests > 0, pos / tests, np.nan)
            mats[(district, "lab", f"panel_{panel}_positivity")] = rate
    return mats, dates


def _forward(y: Array, log_scale: bool) -> Array:
    return np.log1p(np.clip(y, 0, None)) if log_scale else y


def _inverse(y: Array, log_scale: bool) -> Array:
    return np.expm1(y) if log_scale else y


def _round(x: Array, nd: int = 4) -> list[float]:
    return [round(float(v), nd) for v in x]


def _optional(x: Array, nd: int = 4) -> list[float | None]:
    return [round(float(v), nd) if np.isfinite(v) else None for v in x]


def _score_series(
    key: Key,
    spec: MetricSpec,
    y_raw: Array,
    X: Array,
    train: Array,
    window: Array,
    dates: pd.DatetimeIndex,
    cfg: DetectionCfg,
) -> tuple[SeriesDetection, list[Anomaly]] | None:
    district, source, metric = key
    y = _forward(y_raw, spec.log_scale)
    fit = fit_baseline(y, X, train, cfg.min_train_days, cfg.outlier_mad, cfg.min_sigma)
    if fit is None:
        return None
    sign = 1.0 if spec.direction == "up" else -1.0
    w = window
    z = sign * robust_z(y[w], fit.pred[w], fit.sigma)
    e = ewma(z, cfg.ewma_lambda)
    c = cusum(z, cfg.cusum_k)
    band = cfg.z_threshold * fit.sigma
    expected = _inverse(fit.pred[w], spec.log_scale)
    lower = _inverse(fit.pred[w] - band, spec.log_scale)
    upper = _inverse(fit.pred[w] + band, spec.log_scale)
    if spec.log_scale:
        lower = np.clip(lower, 0, None)
    days = np.flatnonzero(w)
    day_dates = dates[days].strftime("%Y-%m-%d")
    sid = series_id(district, source, metric)
    series = SeriesDetection(
        series_id=sid, district=district, source=source, metric=metric,
        log_scale=spec.log_scale, direction=spec.direction, sigma=round(fit.sigma, 5),
        days=days.tolist(), dates=list(day_dates), observed=_optional(y_raw[w]),
        expected=_round(expected), lower=_round(lower), upper=_round(upper),
        z=_optional(z, 3), ewma=_round(e, 3), cusum=_round(c, 3),
    )
    flags = np.nan_to_num(z, nan=-np.inf) >= cfg.z_threshold
    ewma_alarm = e >= ewma_limit(cfg.ewma_lambda, cfg.ewma_L)
    cusum_alarm = c >= cfg.cusum_h
    anomalies = []
    for s, t in consecutive_runs(flags, cfg.consecutive_days, cfg.merge_gap_days):
        seg = slice(s, t + 1)
        zs = z[seg][np.isfinite(z[seg])]
        obs, exp_ = y_raw[w][seg], expected[seg]
        ok = np.isfinite(obs) & (np.abs(exp_) > 1e-9)
        excess = float(np.mean((obs[ok] - exp_[ok]) / np.abs(exp_[ok]))) * sign if ok.any() else 0.0
        e_on = alarm_onset(ewma_alarm, s, lookback=7)
        c_on = alarm_onset(cusum_alarm, s, lookback=7)
        onsets = [s] + [o for o in (e_on, c_on) if o is not None and o <= t]
        anomalies.append(
            Anomaly(
                evidence_id=evidence_id(district, source, metric, int(days[s])),
                series_id=sid, district=district, source=source, metric=metric,
                start_day=int(days[s]), end_day=int(days[t]),
                start_date=day_dates[s], end_date=day_dates[t],
                peak_z=round(float(zs.max()), 2), mean_z=round(float(zs.mean()), 2),
                days_flagged=int(flags[seg].sum()), persistence_days=t - s + 1,
                excess_pct=round(excess, 3),
                ewma_alarm_day=int(days[e_on]) if e_on is not None else None,
                cusum_alarm_day=int(days[c_on]) if c_on is not None else None,
                first_signal_day=int(days[min(onsets)]),
            )
        )
    return series, anomalies


def detect_all(
    df: pd.DataFrame,
    holidays: set[int] | None = None,
    as_of: int | None = None,
    districts: list[str] | None = None,
) -> DetectionReport:
    cfg = get_settings().detection
    mats, dates = to_matrix(df)
    n = len(dates)
    as_of = n - 1 if as_of is None else min(as_of, n - 1)
    day = np.arange(n)
    train = day < as_of - cfg.train_guard_days
    window = (day > as_of - cfg.eval_window) & (day <= as_of)
    X = design_matrix(dates, holidays or set(), cfg.fourier_harmonics)

    series: list[SeriesDetection] = []
    anomalies: list[Anomaly] = []
    specs = [m for m in METRICS if m.detect]
    for key in sorted(mats):
        district, source, metric = key
        if districts is not None and district not in districts:
            continue
        spec = next((m for m in specs if (m.source, m.metric) == (source, metric)), None)
        if spec is None:
            continue
        y = mats[key].copy()
        y[day > as_of] = np.nan  # causal: nothing after as_of is visible
        scored = _score_series(key, spec, y, X, train, window, dates, cfg)
        if scored is None:
            continue
        series.append(scored[0])
        anomalies.extend(scored[1])
    anomalies.sort(key=lambda a: (a.start_day, a.district, a.source, a.metric))
    return DetectionReport(
        as_of=as_of,
        as_of_date=dates[as_of].strftime("%Y-%m-%d"),
        window_start=int(day[window][0]),
        series=series,
        anomalies=anomalies,
    )
