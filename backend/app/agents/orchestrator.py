"""Pipeline orchestrator (SPEC 6), deterministic steps.

Ingest → Validate → Detect → Correlate → Confounder-check → Grade → Forecast. The LLM steps
(Hypothesize, Verify, Recommend) live in `pipeline.py` and reuse these step functions.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from app.analysis import confidence as conf
from app.analysis.confounders import LabEvidence, check_all
from app.analysis.context import AnalysisContext
from app.analysis.correlate import build_signal, link_spatial
from app.analysis.evidence import grade
from app.analysis.forecast import forecast_capacity, prob_label
from app.analysis.models import (
    TIERS,
    AnalysisBundle,
    Confidence,
    ConfounderResult,
    DistrictAssessment,
    EvidenceItem,
    Forecast,
    GateResult,
    Signal,
)
from app.config import get_settings
from app.data.districts import CODES, by_code
from app.data.privacy import apply_privacy
from app.data.scenarios import simulate
from app.detection.models import series_id
from app.detection.run import detect_all, to_matrix


@dataclass
class ConfounderSet:
    results: list[ConfounderResult]
    lab: LabEvidence | None
    residual: float


# ------------------------------------------------------------------ steps


def detect_step(scenario: tuple[str, ...], seed: int, as_of: int | None) -> AnalysisContext:
    sim = simulate(list(scenario), seed=seed)
    df = apply_privacy(sim.df)  # Ingest + Validate (PII guard, k-suppression)
    report = detect_all(df, holidays=sim.holidays, as_of=as_of)
    mats, dates = to_matrix(df)
    return AnalysisContext(scenario=scenario, seed=seed, as_of=report.as_of, df=df, mats=mats, dates=dates,
                           holidays=dict(sim.calendar.holidays), report=report, truth=sim.truth)


def correlate_step(ctx: AnalysisContext) -> dict[str, Signal | None]:
    signals = {d: build_signal(ctx, d) for d in CODES}
    link_spatial(signals)
    return signals


def confounder_step(ctx: AnalysisContext, signals: dict[str, Signal | None]) -> dict[str, ConfounderSet]:
    out = {}
    for d, sig in signals.items():
        if sig is None:
            out[d] = ConfounderSet([], None, 0.0)
        else:
            results, lab, residual = check_all(ctx, sig)
            out[d] = ConfounderSet(results, lab, residual)
    return out


def grade_step(ctx: AnalysisContext, signals: dict[str, Signal | None],
               cfs: dict[str, ConfounderSet]) -> dict[str, tuple[GateResult, Confidence]]:
    return {
        d: (grade(ctx, d, signals[d], cfs[d].results, cfs[d].lab, cfs[d].residual),
            conf.estimate(ctx, signals[d], cfs[d].residual, ctx.seed))
        for d in CODES
    }


def forecast_step(ctx: AnalysisContext) -> dict[str, Forecast]:
    return {d: forecast_capacity(ctx, d) for d in CODES}


def assemble(ctx: AnalysisContext, signals: dict[str, Signal | None], cfs: dict[str, ConfounderSet],
             grades: dict[str, tuple[GateResult, Confidence]], forecasts: dict[str, Forecast]) -> AnalysisBundle:
    assessments = [
        DistrictAssessment(district=d, name=by_code(d).name, signal=signals[d], confounders=cfs[d].results,
                           gate=grades[d][0], confidence=grades[d][1], forecast=forecasts[d])
        for d in CODES
    ]
    primary = max(assessments, key=lambda a: (TIERS.index(a.gate.tier), a.confidence.point)).district
    evidence = base_evidence(ctx)
    for a in assessments:
        evidence.update(signal_evidence(a.signal, a.confounders))
        evidence.update(assessment_evidence(a))
    return AnalysisBundle(scenario=list(ctx.scenario), seed=ctx.seed, as_of=ctx.as_of, as_of_date=ctx.date(ctx.as_of),
                          primary=primary, assessments=assessments, evidence=evidence, context=ctx)


# ------------------------------------------------------------------ evidence index


def base_evidence(ctx: AnalysisContext) -> dict[str, EvidenceItem]:
    """Detection-level IDs: anomalies, series, reporting metadata, calendar."""
    items: dict[str, EvidenceItem] = {}
    for an in ctx.report.anomalies:
        items[an.evidence_id] = EvidenceItem(
            id=an.evidence_id, kind="anomaly", district=an.district,
            summary=f"{an.source}.{an.metric} anomalous {an.start_date}→{an.end_date}, "
                    f"peak z {an.peak_z}, excess {an.excess_pct:+.0%}",
            data=an.model_dump(include={"source", "metric", "start_day", "end_day", "peak_z", "mean_z",
                                        "excess_pct", "first_signal_day", "persistence_days", "series_id"}))
    for s in ctx.report.series:
        items[s.series_id] = EvidenceItem(id=s.series_id, kind="series", district=s.district,
                                          summary=f"{s.source}.{s.metric} daily series with expected band",
                                          data={"source": s.source, "metric": s.metric})
    for d in CODES:
        for m in ("sites_expected", "sites_received", "schema_version"):
            sid = series_id(d, "meta", m)
            items[sid] = EvidenceItem(id=sid, kind="series", district=d, summary=f"reporting metadata: {m}",
                                      data={"source": "meta", "metric": m})
    for day, name in ctx.holidays.items():
        cid = f"CAL-{day:04d}"
        items[cid] = EvidenceItem(id=cid, kind="calendar", district=None, summary=f"{name} on {ctx.date(day)}",
                                  data={"day": day, "name": name})
    return items


def signal_evidence(sig: Signal | None, confounders: list[ConfounderResult]) -> dict[str, EvidenceItem]:
    items: dict[str, EvidenceItem] = {}
    if sig is not None:
        items[sig.signal_id] = EvidenceItem(
            id=sig.signal_id, kind="signal", district=sig.district,
            summary=f"{sig.syndrome} signal: {sig.independent_sources} sources ({', '.join(sig.sources)})",
            data=sig.model_dump(include={"sources", "independent_sources", "mean_z", "peak_z", "mean_excess",
                                         "lag_consistency", "persistence_days", "onset_by_source",
                                         "adjacent_districts", "first_day", "last_day"}))
    for c in confounders:
        items[c.confounder_id] = EvidenceItem(
            id=c.confounder_id, kind="confounder", district=sig.district if sig else None,
            summary=f"{c.label}: {c.status}. {c.summary}",
            data={"status": c.status, "explained_share": c.explained_share, **c.values})
    return items


def assessment_evidence(a: DistrictAssessment) -> dict[str, EvidenceItem]:
    items: dict[str, EvidenceItem] = {}
    for k in a.gate.criteria:
        items[k.criterion_id] = EvidenceItem(
            id=k.criterion_id, kind="criterion", district=a.district,
            summary=f"{k.label}: {'met' if k.met else 'not met'} ({k.value} vs {k.threshold})",
            data={"met": k.met, "value": k.value, "tier": k.tier})
    f = a.forecast
    items[f.forecast_id] = EvidenceItem(
        id=f.forecast_id, kind="forecast", district=a.district,
        summary=f"14-day bed P50 {f.beds.p50[-1]:.0f}/{f.beds_total:.0f}, "
                f"max P(breach) {prob_label(max(f.breach_prob_beds))}",
        data={"breach_day_beds": f.breach_day_beds, "max_breach_prob": max(f.breach_prob_beds),
              "beds_total": f.beds_total, "p50_end": f.beds.p50[-1], "p90_end": f.beds.p90[-1]})
    return items


# ------------------------------------------------------------------ full deterministic run


@lru_cache(maxsize=32)
def run_analysis(scenario: str | tuple[str, ...] = "true_outbreak", seed: int | None = None,
                 as_of: int | None = None) -> AnalysisBundle:
    names = (scenario,) if isinstance(scenario, str) else tuple(scenario)
    seed = get_settings().simulation.seed if seed is None else seed
    ctx = detect_step(names, seed, as_of)
    signals = correlate_step(ctx)
    cfs = confounder_step(ctx, signals)
    grades = grade_step(ctx, signals, cfs)
    return assemble(ctx, signals, cfs, grades, forecast_step(ctx))
