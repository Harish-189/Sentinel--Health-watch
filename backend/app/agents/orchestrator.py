"""Pipeline orchestrator (SPEC 6). Stage 2: deterministic steps. LLM steps plug in at Stage 3.

Ingest → Validate → Detect → Correlate → Confounder-check → Grade → Forecast
"""

from __future__ import annotations

from functools import lru_cache

from app.analysis import confidence as conf
from app.analysis.confounders import check_all
from app.analysis.context import AnalysisContext
from app.analysis.correlate import build_signal, link_spatial
from app.analysis.evidence import grade
from app.analysis.forecast import forecast_capacity
from app.analysis.models import TIERS, AnalysisBundle, DistrictAssessment, EvidenceItem, Signal
from app.config import get_settings
from app.data.districts import CODES, by_code
from app.data.privacy import apply_privacy
from app.data.scenarios import simulate
from app.detection.models import series_id
from app.detection.run import detect_all, to_matrix


def build_context(scenario: tuple[str, ...], seed: int, as_of: int | None) -> AnalysisContext:
    sim = simulate(list(scenario), seed=seed)
    df = apply_privacy(sim.df)  # Ingest + Validate (PII guard, k-suppression)
    report = detect_all(df, holidays=sim.holidays, as_of=as_of)  # Detect
    mats, dates = to_matrix(df)
    return AnalysisContext(scenario=scenario, seed=seed, as_of=report.as_of, df=df, mats=mats, dates=dates,
                           holidays=dict(sim.calendar.holidays), report=report, truth=sim.truth)


def assess(ctx: AnalysisContext) -> list[DistrictAssessment]:
    signals: dict[str, Signal | None] = {d: build_signal(ctx, d) for d in CODES}  # Correlate
    link_spatial(signals)
    out = []
    for d in CODES:
        sig = signals[d]
        if sig is not None:
            confounders, lab, residual = check_all(ctx, sig)  # Confounder-check
        else:
            confounders, lab, residual = [], None, 0.0
        gate = grade(ctx, d, sig, confounders, lab, residual)  # Grade
        out.append(DistrictAssessment(
            district=d, name=by_code(d).name, signal=sig, confounders=confounders, gate=gate,
            confidence=conf.estimate(ctx, sig, residual, ctx.seed),
            forecast=forecast_capacity(ctx, d),  # Forecast
        ))
    return out


def evidence_index(ctx: AnalysisContext, assessments: list[DistrictAssessment]) -> dict[str, EvidenceItem]:
    """Every ID the LLM may cite, with a compact summary and the numbers behind it."""
    items: dict[str, EvidenceItem] = {}

    def add(item: EvidenceItem) -> None:
        items[item.id] = item

    for an in ctx.report.anomalies:
        add(EvidenceItem(id=an.evidence_id, kind="anomaly", district=an.district,
                         summary=f"{an.source}.{an.metric} anomalous {an.start_date}→{an.end_date}, "
                                 f"peak z {an.peak_z}, "
                                 f"excess {an.excess_pct:+.0%}",
                         data=an.model_dump(include={"source", "metric", "start_day", "end_day", "peak_z", "mean_z",
                                                    "excess_pct", "first_signal_day", "series_id"})))
    for s in ctx.report.series:
        add(EvidenceItem(id=s.series_id, kind="series", district=s.district,
                         summary=f"{s.source}.{s.metric} daily series with expected band",
                         data={"source": s.source, "metric": s.metric}))
    for d in CODES:
        for m in ("sites_expected", "sites_received", "schema_version"):
            add(EvidenceItem(id=series_id(d, "meta", m), kind="series", district=d,
                             summary=f"reporting metadata: {m}", data={"source": "meta", "metric": m}))
        add(EvidenceItem(id=series_id(d, "environment", "aqi"), kind="series", district=d,
                         summary="environment.aqi daily series", data={"source": "environment", "metric": "aqi"}))
    for day, name in ctx.holidays.items():
        add(EvidenceItem(id=f"CAL-{day:04d}", kind="calendar", district=None, summary=f"{name} on {ctx.date(day)}",
                         data={"day": day, "name": name}))
    for a in assessments:
        if a.signal is not None:
            sg = a.signal
            add(EvidenceItem(id=sg.signal_id, kind="signal", district=a.district,
                             summary=f"{sg.syndrome} signal: {sg.independent_sources} sources "
                                     f"({', '.join(sg.sources)})",
                             data=sg.model_dump(include={"sources", "independent_sources", "mean_z", "peak_z",
                                                         "lag_consistency", "persistence_days", "onset_by_source",
                                                         "adjacent_districts"})))
        for c in a.confounders:
            add(EvidenceItem(id=c.confounder_id, kind="confounder", district=a.district,
                             summary=f"{c.label}: {c.status}. {c.summary}", data={"status": c.status, **c.values}))
        for k in a.gate.criteria:
            add(EvidenceItem(id=k.criterion_id, kind="criterion", district=a.district,
                             summary=f"{k.label}: {'met' if k.met else 'not met'} ({k.value} vs {k.threshold})",
                             data={"met": k.met, "value": k.value, "tier": k.tier}))
        f = a.forecast
        add(EvidenceItem(id=f.forecast_id, kind="forecast", district=a.district,
                         summary=f"14-day bed P50 {f.beds.p50[-1]:.0f}/{f.beds_total:.0f}, max P(breach) "
                                 f"{max(f.breach_prob_beds):.0%}",
                         data={"breach_day_beds": f.breach_day_beds, "max_breach_prob": max(f.breach_prob_beds)}))
    return items


@lru_cache(maxsize=32)
def run_analysis(scenario: str | tuple[str, ...] = "true_outbreak", seed: int | None = None,
                 as_of: int | None = None) -> AnalysisBundle:
    names = (scenario,) if isinstance(scenario, str) else tuple(scenario)
    seed = get_settings().simulation.seed if seed is None else seed
    ctx = build_context(names, seed, as_of)
    assessments = assess(ctx)
    primary = max(assessments, key=lambda a: (TIERS.index(a.gate.tier), a.confidence.point)).district
    return AnalysisBundle(
        scenario=list(names), seed=seed, as_of=ctx.as_of, as_of_date=ctx.date(ctx.as_of), primary=primary,
        assessments=assessments, evidence=evidence_index(ctx, assessments), context=ctx,
    )
