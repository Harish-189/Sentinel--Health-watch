"""Non-epidemic explanations, each tested with numbers: holiday, reporting change, lab backlog,
weather, seasonal expectation. Status semantics: `ruled_out` = the explanation fails (SPEC "fail"),
`explains` = it accounts for the signal, `inconclusive` = cannot tell."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.analysis.context import AnalysisContext
from app.analysis.correlate import panel_for
from app.analysis.models import ConfounderResult, Signal, Status
from app.config import get_settings
from app.detection.models import series_id


def _cf(sig: Signal, name: str, label: str, status: Status, summary: str, share: float,
        values: dict[str, float | int | str | bool | None], ids: list[str]) -> ConfounderResult:
    return ConfounderResult(
        confounder_id=f"CF-{sig.district}-{name}", name=name, label=label, status=status, summary=summary,
        explained_share=round(float(np.clip(share, 0, 1)), 3), values=values, evidence_ids=ids,
    )


def _excess_by_day(ctx: AnalysisContext, sig: Signal) -> dict[int, float]:
    """Relative excess (obs - expected)/expected summed per day over the signal's window anomalies."""
    out: dict[int, float] = {}
    anomalies = {a.evidence_id: a for a in ctx.report.anomalies}
    for eid in sig.window_ids:
        a = anomalies[eid]
        s = ctx.series(a.district, a.source, a.metric)
        if s is None:
            continue
        for d, obs, exp in zip(s.days, s.observed, s.expected, strict=True):
            if a.start_day <= d <= a.end_day and obs is not None and abs(exp) > 1e-9:
                excess = (obs - exp) / abs(exp) * (1 if s.direction == "up" else -1)
                out[d] = out.get(d, 0.0) + max(0.0, excess)
    return out


def holiday(ctx: AnalysisContext, sig: Signal) -> ConfounderResult:
    g = get_settings().gate
    excess = _excess_by_day(ctx, sig)
    total = sum(excess.values())
    near_days = {d for h in ctx.holidays for d in range(h - g.holiday_window_days, h + g.holiday_window_days + 1)}
    share = sum(v for d, v in excess.items() if d in near_days) / total if total > 0 else 0.0
    window = range(sig.first_day - g.holiday_window_days, sig.last_day + g.holiday_window_days + 1)
    hols = sorted(d for d in ctx.holidays if d in window)
    status: Status = (
        "explains" if share >= g.holiday_explains_max else "ruled_out" if share <= g.holiday_ruled_out_max
        else "inconclusive"
    )
    names = ", ".join(f"{ctx.holidays[d]} ({ctx.date(d)})" for d in hols) or "none"
    summary = f"{share:.0%} of excess falls within ±{g.holiday_window_days} days of a holiday (holidays: {names})."
    return _cf(sig, "holiday", "Holiday / calendar effect", status, summary, share,
               {"explained_share": round(share, 3), "holidays_in_window": len(hols),
                "holiday": ctx.holidays[hols[0]] if hols else None},
               [f"CAL-{d:04d}" for d in hols] + sig.window_ids)


def completeness(ctx: AnalysisContext, district: str) -> float:
    g = get_settings().gate
    lo = max(0, ctx.as_of - g.completeness_window + 1)
    exp = ctx.raw(district, "meta", "sites_expected")[lo : ctx.as_of + 1]
    rec = ctx.raw(district, "meta", "sites_received")[lo : ctx.as_of + 1]
    ok = np.isfinite(exp) & np.isfinite(rec) & (exp > 0)
    return float(np.mean(rec[ok] / exp[ok])) if ok.any() else 0.0


def _level_step(ctx: AnalysisContext, sig: Signal, t: int, span: int = 14) -> float:
    """Mean relative level change (after vs before day t) across the signal's anomalous series."""
    anomalies = {a.evidence_id: a for a in ctx.report.anomalies}
    steps = []
    for eid in sig.window_ids:
        a = anomalies[eid]
        y = ctx.raw(a.district, a.source, a.metric)
        before, after = y[max(0, t - span) : t], y[t : min(t + span, ctx.as_of + 1)]
        if np.isfinite(before).sum() >= 5 and np.isfinite(after).sum() >= 3 and np.nanmean(before) > 0:
            steps.append(np.nanmean(after) / np.nanmean(before) - 1)
    return float(np.mean(steps)) if steps else 0.0


def reporting(ctx: AnalysisContext, sig: Signal) -> ConfounderResult:
    g = get_settings().gate
    d = sig.district
    sites = ctx.raw(d, "meta", "sites_expected")
    schema = ctx.raw(d, "meta", "schema_version")
    lo = max(1, sig.first_day - 21)
    changes = [t for t in range(lo, ctx.as_of + 1) if sites[t] != sites[t - 1] or schema[t] != schema[t - 1]]
    anomalies = {a.evidence_id: a for a in ctx.report.anomalies}
    starts = [anomalies[e].start_day for e in sig.window_ids]
    # a step change is detected some days after it happens: accept changes up to 21 days before onset
    aligned = [t for t in changes if any(s - 21 <= t <= s + g.reporting_align_days for s in starts)]
    comp = completeness(ctx, d)
    ids = [series_id(d, "meta", "sites_expected"), series_id(d, "meta", "schema_version")]
    share = 0.0
    if aligned:
        t = aligned[0]
        step = _level_step(ctx, sig, t)
        share = min(1.0, step / sig.mean_excess) if sig.mean_excess > 0 else 1.0
        status: Status = "explains"
        summary = (f"Reporting network changed on {ctx.date(t)} (sites {sites[t - 1]:.0f}→{sites[t]:.0f}, "
                   f"schema v{schema[t]:.0f}), aligned with the signal onset.")
    elif changes or comp < g.completeness_min:
        status = "inconclusive"
        summary = f"Reporting completeness {comp:.0%}; {len(changes)} meta change(s) not aligned with onset."
    else:
        status = "ruled_out"
        summary = f"No site or schema change; completeness {comp:.0%} over {g.completeness_window} days."
    return _cf(sig, "reporting_change", "Reporting / site change", status, summary, share,
               {"completeness": round(comp, 3), "meta_changes": len(changes), "aligned": bool(aligned)}, ids)


@dataclass(frozen=True)
class LabEvidence:
    panel: str
    pos_rising: bool
    tests_stable: bool
    batch_pattern: bool
    tests_zmax: float
    positivity_ids: list[str]
    tests_id: str
    contradicted: bool  # positivity rose earlier but recent results are flat


def lab_evidence(ctx: AnalysisContext, sig: Signal) -> LabEvidence:
    g = get_settings().gate
    d, panel = sig.district, panel_for(sig.syndrome)
    tests = ctx.series(d, "lab", f"panel_{panel}_tests")
    pos_s = ctx.series(d, "lab", f"panel_{panel}_positivity")
    recent_from = ctx.as_of - 20
    n_low = n_high = run = longest = 0
    tests_zmax = 0.0
    if tests is not None:
        for day, obs, exp, z in zip(tests.days, tests.observed, tests.expected, tests.z, strict=True):
            if day < recent_from or obs is None:
                continue
            n_low += obs < 0.4 * exp
            n_high += obs > 2.0 * exp
            tests_zmax = max(tests_zmax, z or 0.0)
            run = run + 1 if (z or 0.0) >= g.backlog_tests_z_max else 0
            longest = max(longest, run)
    batch = n_low >= 3 and n_high >= 1
    pos_anoms = [
        a for a in ctx.report.anomalies_for(d, "lab")
        if a.metric == f"panel_{panel}_positivity" and a.end_day >= ctx.as_of - g.active_within_days
    ]
    recent_z: list[float] = []
    if pos_s is not None:
        recent_z = [z for day, z in zip(pos_s.days, pos_s.z, strict=True) if day > ctx.as_of - 7 and z is not None]
    recent_mean = float(np.mean(recent_z)) if recent_z else 0.0
    contradicted = bool(pos_anoms) and recent_mean < g.contradict_pos_z_max and sig.last_day >= ctx.as_of - 2
    return LabEvidence(
        panel=panel,
        pos_rising=bool(pos_anoms) and not contradicted,
        tests_stable=not batch and longest < 2,  # no sustained surge in test volume
        batch_pattern=batch,
        tests_zmax=round(tests_zmax, 2),
        positivity_ids=[a.evidence_id for a in pos_anoms],
        tests_id=series_id(d, "lab", f"panel_{panel}_tests"),
        contradicted=contradicted,
    )


def lab_backlog(ctx: AnalysisContext, sig: Signal, lab: LabEvidence) -> ConfounderResult:
    ids = [lab.tests_id, *lab.positivity_ids]
    values: dict[str, float | int | str | bool | None] = {
        "batch_pattern": lab.batch_pattern, "tests_zmax": lab.tests_zmax, "positivity_rising": lab.pos_rising}
    if lab.batch_pattern:
        share = 1.0 / max(sig.independent_sources, 1) if "lab" in sig.sources else 0.0
        return _cf(sig, "lab_backlog", "Lab batch / backlog", "explains",
                   f"Panel {lab.panel} shows trickle-then-dump reporting; positivity is flat, so the jump in "
                   "positives reflects batching.", share, values, ids)
    if lab.pos_rising:
        return _cf(sig, "lab_backlog", "Lab batch / backlog", "ruled_out",
                   f"Panel {lab.panel} positivity is rising while test volume is stable (max z {lab.tests_zmax}).",
                   0.0, values, ids)
    return _cf(sig, "lab_backlog", "Lab batch / backlog", "inconclusive",
               f"No batch pattern and no positivity rise on panel {lab.panel}.", 0.0, values, ids)


def weather(ctx: AnalysisContext, sig: Signal) -> ConfounderResult:
    g = get_settings().gate
    d = sig.district
    if sig.syndrome != "respiratory":
        return _cf(sig, "weather", "Weather / air quality", "ruled_out",
                   "Not plausible for a gastrointestinal signal.", 0.0, {}, sig.window_ids)
    env = [
        a for a in ctx.report.anomalies_for(d, "environment")
        if a.end_day >= sig.first_day - 3 and a.start_day <= sig.last_day
    ]
    clinic, aqi = ctx.series(d, "clinic", "respiratory"), ctx.series(d, "environment", "aqi")
    corr = 0.0
    if clinic is not None and aqi is not None:
        lo = sig.first_day - 14
        pairs = [(c, q) for day, c, q in zip(clinic.days, clinic.z, aqi.z, strict=True)
                 if day >= lo and c is not None and q is not None]
        if len(pairs) >= 8:
            arr = np.array(pairs)
            if arr[:, 0].std() > 0 and arr[:, 1].std() > 0:
                corr = float(np.corrcoef(arr[:, 0], arr[:, 1])[0, 1])
    ids = [a.evidence_id for a in env] + [series_id(d, "environment", "aqi")]
    values: dict[str, float | int | str | bool | None] = {"env_anomalies": len(env), "corr_aqi": round(corr, 3)}
    if env and corr >= g.weather_corr_min:
        return _cf(sig, "weather", "Weather / air quality", "explains",
                   f"AQI/heat anomaly in {d} with same-day correlation r={corr:.2f} to respiratory visits.",
                   corr, values, ids)  # attribute r (not r^2): conservative toward the confounder
    if not env:
        return _cf(sig, "weather", "Weather / air quality", "ruled_out",
                   f"No heat or AQI anomaly in {d} during the signal (r={corr:.2f}).", 0.0, values, ids)
    return _cf(sig, "weather", "Weather / air quality", "inconclusive",
               f"Environmental anomaly present but weak correlation (r={corr:.2f}).", corr**2 / 2, values, ids)


def seasonal(ctx: AnalysisContext, sig: Signal) -> ConfounderResult:
    g = get_settings().gate
    d = sig.district
    metric = "gastrointestinal" if sig.syndrome == "gastrointestinal" else "respiratory"
    y = ctx.raw(d, "clinic", metric)
    now = slice(sig.first_day, ctx.as_of + 1)
    last = slice(sig.first_day - 364, ctx.as_of + 1 - 364)  # 52 weeks back keeps weekdays aligned
    a, b = y[now], y[last]
    ok = np.isfinite(a) & np.isfinite(b)
    yoy = float(a[ok].sum() / b[ok].sum()) if ok.any() and b[ok].sum() > 0 else float("nan")
    ids = [series_id(d, "clinic", metric)]
    values: dict[str, float | int | str | bool | None] = {"yoy_ratio": round(yoy, 3) if np.isfinite(yoy) else None}
    if not np.isfinite(yoy):
        return _cf(sig, "seasonal", "Seasonal expectation", "inconclusive", "No prior-year data for comparison.",
                   0.0, values, ids)
    if yoy <= g.seasonal_yoy_explains:
        share = 1 - (yoy - 1) / sig.mean_excess if sig.mean_excess > 0 else 1.0
        return _cf(sig, "seasonal", "Seasonal expectation", "explains",
                   f"Clinic {metric} visits are {yoy:.2f}× the same weeks last year: consistent with the season.",
                   share, values, ids)
    status: Status = "ruled_out" if yoy >= g.seasonal_yoy_ruled_out else "inconclusive"
    return _cf(sig, "seasonal", "Seasonal expectation", status,
               f"Clinic {metric} visits are {yoy:.2f}× the same weeks last year.", 0.0, values, ids)


def check_all(ctx: AnalysisContext, sig: Signal) -> tuple[list[ConfounderResult], LabEvidence, float]:
    """Run all checks; return results, lab evidence, and residual excess after adjustment."""
    lab = lab_evidence(ctx, sig)
    results = [holiday(ctx, sig), reporting(ctx, sig), lab_backlog(ctx, sig, lab), weather(ctx, sig),
               seasonal(ctx, sig)]
    residual = sig.mean_excess * float(np.prod([1 - r.explained_share for r in results]))
    return results, lab, round(max(residual, 0.0), 3)
