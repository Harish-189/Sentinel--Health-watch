"""Capacity forecast (SPEC 8): stochastic growth projection, Monte Carlo, P10/P50/P90 bands."""

from __future__ import annotations

import numpy as np

from app.analysis.confounders import completeness
from app.analysis.context import AnalysisContext
from app.analysis.models import Band, Forecast
from app.config import get_settings
from app.data.districts import index_of

HISTORY_DAYS = 30


def _last_finite(y: np.ndarray, upto: int) -> float:
    vals = y[: upto + 1][np.isfinite(y[: upto + 1])]
    return float(vals[-1]) if vals.size else 0.0


def smooth7(y: np.ndarray) -> np.ndarray:
    """Trailing 7-day mean (removes the day-of-week pattern), ignoring suppressed/missing days."""
    out = np.full(len(y), np.nan)
    for i in range(6, len(y)):
        w = y[i - 6 : i + 1]
        if np.isfinite(w).sum() >= 4:
            out[i] = np.nanmean(w)
    return out


def growth_fit(adm: np.ndarray) -> tuple[float, float, float]:
    """Log-linear fit of recent admissions -> (current level, daily growth rate, its std. error)."""
    t = np.arange(len(adm), dtype=float)
    ok = np.isfinite(adm)
    if ok.sum() < 4:
        level = float(np.nanmean(adm)) if ok.any() else 1.0
        return max(level, 1.0), 0.0, 0.05
    y = np.log(adm[ok] + 1.0)
    X = np.column_stack([np.ones(ok.sum()), t[ok]])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    dof = max(int(ok.sum()) - 2, 1)
    se = 2.0 * float(np.sqrt(resid @ resid / dof / np.sum((t[ok] - t[ok].mean()) ** 2)))  # x2: autocorrelation
    level = float(np.exp(beta[0] + beta[1] * t[-1]) - 1.0)
    return max(level, 1.0), float(beta[1]), se


def _band(sims: np.ndarray) -> Band:
    p10, p50, p90 = np.percentile(sims, [10, 50, 90], axis=0)
    return Band(p10=np.round(p10, 1).tolist(), p50=np.round(p50, 1).tolist(), p90=np.round(p90, 1).tolist())


def _first_breach(prob: np.ndarray, days: list[int]) -> int | None:
    hit = np.flatnonzero(prob >= 0.5)
    return days[int(hit[0])] if hit.size else None


def forecast_capacity(ctx: AnalysisContext, district: str, intervention: bool = False) -> Forecast:
    fc = get_settings().forecast
    as_of, H, n = ctx.as_of, fc.horizon_days, fc.n_sims
    adm = ctx.raw(district, "capacity", "admissions")[as_of - fc.fit_days - 5 : as_of + 1]
    level, r, se = growth_fit(smooth7(adm)[6:])
    comp = max(completeness(ctx, district), 0.5)
    se_eff = (se + 0.005) / comp**2  # low-reporting districts get wider bands, not exclusion

    rng = np.random.default_rng([ctx.seed, index_of(district), as_of])
    rates = np.clip(rng.normal(r, se_eff, n), *fc.growth_clip)
    beds_now = _last_finite(ctx.raw(district, "capacity", "beds_occupied"), as_of)
    icu_now = _last_finite(ctx.raw(district, "capacity", "icu_occupied"), as_of)
    beds_total = _last_finite(ctx.raw(district, "capacity", "beds_total"), as_of)
    icu_total = _last_finite(ctx.raw(district, "capacity", "icu_total"), as_of)

    beds = np.full(n, beds_now)
    icu = np.full(n, icu_now)
    growth = np.zeros(n)
    beds_out = np.empty((n, H))
    icu_out = np.empty((n, H))
    for h in range(H):
        cut = fc.intervention_growth_cut if intervention and h >= fc.intervention_delay_days else 0.0
        growth += rates - cut
        new = rng.poisson(level * np.exp(growth)).astype(float)
        new_icu = rng.binomial(new.astype(np.int64), fc.icu_share)
        beds = beds - rng.binomial(beds.astype(np.int64), 1 / fc.los_mean_days) + new
        icu = icu - rng.binomial(icu.astype(np.int64), 1 / fc.icu_los_mean_days) + new_icu
        beds_out[:, h], icu_out[:, h] = beds, icu

    days = [as_of + h + 1 for h in range(H)]
    p_beds = (beds_out > beds_total).mean(axis=0)
    p_icu = (icu_out > icu_total).mean(axis=0)
    hist = list(range(max(0, as_of - HISTORY_DAYS + 1), as_of + 1))
    bed_hist = ctx.raw(district, "capacity", "beds_occupied")
    icu_hist = ctx.raw(district, "capacity", "icu_occupied")
    start = ctx.dates[0]
    return Forecast(
        forecast_id=f"FC-{district}-capacity",
        district=district,
        as_of=as_of,
        intervention=intervention,
        days=days,
        dates=[(start + np.timedelta64(d, "D")).strftime("%Y-%m-%d") for d in days],
        beds=_band(beds_out),
        icu=_band(icu_out),
        beds_total=beds_total,
        icu_total=icu_total,
        history_days=hist,
        history_beds=[float(bed_hist[d]) if np.isfinite(bed_hist[d]) else None for d in hist],
        history_icu=[float(icu_hist[d]) if np.isfinite(icu_hist[d]) else None for d in hist],
        breach_prob_beds=np.round(p_beds, 3).tolist(),
        breach_prob_icu=np.round(p_icu, 3).tolist(),
        breach_day_beds=_first_breach(p_beds, days),
        breach_day_icu=_first_breach(p_icu, days),
        growth_rate=round(r, 4),
        growth_se=round(se_eff, 4),
    )
