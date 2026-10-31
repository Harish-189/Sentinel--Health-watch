"""Full agent pipeline, streamed step by step:
Detect → Correlate → Confounders → Hypothesize → Verify → Grade → Forecast → Recommend.

The LLM explains and proposes; the deterministic gate (Grade) decides the tier; actions only become
PendingActions for a human."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from typing import Any, Literal

from app.agents import orchestrator as orc
from app.agents.hypothesis import generate
from app.agents.llm import LLMSession
from app.agents.packet import build_packet
from app.agents.recommender import recommend
from app.agents.schemas import CaseFile, Recommendation, StepEvent
from app.agents.verifier import verify, verify_recommendations
from app.analysis.forecast import prob_label
from app.analysis.models import TIERS, AnalysisBundle, DistrictAssessment, Signal
from app.config import get_settings
from app.data.districts import by_code
from app.governance.approvals import Governance, GovernanceError

STEPS: tuple[str, ...] = ("Detect", "Correlate", "Confounders", "Hypothesize", "Verify", "Grade", "Forecast",
                          "Recommend")
_CACHE: dict[tuple[Any, ...], CaseFile] = {}


def _focus(signals: dict[str, Signal | None], district: str | None) -> str:
    if district:
        return district
    ranked = [s for s in signals.values() if s is not None]
    if not ranked:
        return get_settings().simulation.default_primary
    return max(ranked, key=lambda s: (s.independent_sources, len(s.adjacent_districts), s.peak_z)).district


def tier_explanation(a: DistrictAssessment) -> str:
    unmet = [c.label for c in a.gate.criteria if not c.met]
    head = f"{a.name} is graded {a.gate.tier} by the deterministic evidence gate."
    if a.gate.downgrades:
        head += " Downgraded: " + "; ".join(a.gate.downgrades) + "."
    if a.gate.tier == "E3":
        return head + " All intervention-grade criteria are met."
    nxt = TIERS[min(TIERS.index(a.gate.tier) + 1, 3)]
    missing = [c.label for c in a.gate.criteria if not c.met and c.tier == nxt] or unmet
    return head + (f" Missing for {nxt}: " + "; ".join(missing) + "." if missing else "")


def _submit(gov: Governance | None, recs: list[Recommendation], a: DistrictAssessment) -> str:
    if gov is None:
        return "not submitted"
    if gov.kill_switch_engaged():
        return "blocked by kill switch"
    pending = {(p.action, p.district): p.ref for p in gov.list("pending")}
    for r in recs:
        if (r.action, a.district) in pending:
            r.pending_ref = pending[(r.action, a.district)]
            continue
        try:
            p = gov.propose(r.action, a.district, a.gate.tier, r.rationale, r.evidence_ids, r.params,
                            proposed_by="recommender")
            r.pending_ref = p.ref
        except GovernanceError:
            r.pending_ref = None
    return f"{sum(r.pending_ref is not None for r in recs)} queued for human approval"


def run_pipeline(scenario: tuple[str, ...], seed: int, as_of: int | None = None, district: str | None = None,
                 gov: Governance | None = None, session: LLMSession | None = None,
                 pace_ms: float = 0.0) -> Iterator[StepEvent | CaseFile]:
    """Yields StepEvents (running/done) and finally the CaseFile."""
    session = session or LLMSession()
    key = (scenario, seed, as_of, district, session.mode)
    t_start = time.perf_counter()
    events: list[StepEvent] = []

    def step(name: str, fn: Callable[[], Any], detail: Callable[[Any], str]) -> Iterator[StepEvent]:
        yield StepEvent(step=name, status="running")
        t0 = time.perf_counter()
        result = fn()
        ms = (time.perf_counter() - t0) * 1000
        if pace_ms > ms:
            time.sleep((pace_ms - ms) / 1000)
        status: Literal["done", "degraded"] = (
            "degraded" if name in ("Hypothesize", "Recommend") and not session.online else "done")
        ev = StepEvent(step=name, status=status, ms=round(ms, 1), detail=detail(result))
        events.append(ev)
        box["last"] = result
        yield ev

    box: dict[str, Any] = {}
    cached = _CACHE.get(key)
    if cached is not None:  # replay a computed case file (still paced, so the UI stepper animates)
        for ev in cached.steps:
            yield StepEvent(step=ev.step, status="running")
            time.sleep(pace_ms / 1000 if pace_ms else 0)
            yield ev
        if gov is not None:
            _submit(gov, cached.recommendations, cached.assessment)
        yield cached
        return

    yield from step("Detect", lambda: orc.detect_step(scenario, seed, as_of),
                    lambda c: f"{len(c.report.anomalies)} anomalies across {len(c.report.series)} series")
    ctx = box["last"]
    yield from step("Correlate", lambda: orc.correlate_step(ctx),
                    lambda s: f"{sum(v is not None for v in s.values())} district signal(s)")
    signals = box["last"]
    focus = _focus(signals, district)
    yield from step("Confounders", lambda: orc.confounder_step(ctx, signals),
                    lambda c: ", ".join(f"{r.name}:{r.status}" for r in c[focus].results) or "no signal to test")
    cfs = box["last"]

    evidence = orc.base_evidence(ctx)
    for d, sig in signals.items():
        evidence.update(orc.signal_evidence(sig, cfs[d].results))
    # Offline reasoning ranks hypotheses with the deterministic confidence score; the tier itself is never
    # given to the Hypothesis agent (it is graded after verification).
    pre_grades = orc.grade_step(ctx, signals, cfs)
    name = by_code(focus).name
    packet = build_packet(focus, name, ctx.date(ctx.as_of), signals[focus], cfs[focus].results, evidence)
    yield from step("Hypothesize",
                    lambda: generate(session, packet, evidence, name, signals[focus], cfs[focus].results,
                                     pre_grades[focus][1]),
                    lambda r: f"{len(r[0])} hypotheses ({r[1]})")
    hypotheses, _source = box["last"]
    yield from step("Verify", lambda: verify(hypotheses, evidence, session),
                    lambda r: f"{r[1].grounded_claims}/{r[1].total_claims} claims grounded")
    hypotheses, verification = box["last"]
    yield from step("Grade", lambda: orc.grade_step(ctx, signals, cfs),
                    lambda g: f"{focus} {g[focus][0].tier} (confidence {g[focus][1].point:.2f})")
    grades = box["last"]
    yield from step("Forecast", lambda: orc.forecast_step(ctx),
                    lambda f: f"max P(bed breach) {prob_label(max(f[focus].breach_prob_beds))}")
    bundle: AnalysisBundle = orc.assemble(ctx, signals, cfs, grades, box["last"])
    evidence = bundle.evidence
    a = bundle.assessment(focus)
    hyp_brief = [{"title": h.title, "kind": h.kind, "probability": h.probability} for h in hypotheses]

    def _recommend() -> tuple[list[Recommendation], str]:
        recs = verify_recommendations(recommend(session, a, hyp_brief), evidence)
        return recs, _submit(gov, recs, a)

    yield from step("Recommend", _recommend, lambda r: f"{len(r[0])} action(s); {r[1]}")
    recs, submitted = box["last"]
    if submitted == "blocked by kill switch":
        events[-1].status = "blocked"

    cited = {e for h in hypotheses for c in h.claims for e in c.evidence_ids}
    cited |= {e for h in hypotheses for e in h.supporting_ids + h.contradicting_ids}
    cited |= {e for r in recs for e in r.evidence_ids}
    cited |= {e for c in a.gate.criteria for e in c.evidence_ids} | {cf.confounder_id for cf in a.confounders}
    case = CaseFile(
        scenario=list(scenario), seed=seed, as_of=ctx.as_of, as_of_date=ctx.date(ctx.as_of), district=focus,
        district_name=name, tiers={x.district: x.gate.tier for x in bundle.assessments}, assessment=a,
        hypotheses=hypotheses, verification=verification, recommendations=recs, usage=session.usage,
        latency_ms=round((time.perf_counter() - t_start) * 1000, 1), steps=events,
        evidence={e: evidence[e] for e in sorted(cited) if e in evidence}, tier_explanation=tier_explanation(a),
    )
    _CACHE[key] = case
    yield case


def run_to_casefile(scenario: tuple[str, ...], seed: int, as_of: int | None = None, district: str | None = None,
                    gov: Governance | None = None, session: LLMSession | None = None) -> CaseFile:
    for item in run_pipeline(scenario, seed, as_of, district, gov, session):
        if isinstance(item, CaseFile):
            return item
    raise RuntimeError("pipeline produced no case file")


def clear_cache() -> None:
    _CACHE.clear()
