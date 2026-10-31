"""Scenario Lab: inject a scenario (or an uploaded CSV) and explain the Evidence Delta.

Everything here is deterministic: tiers come from the gate, hypotheses from the rule-based agent, and the
plain-language explanation is assembled from gate-criterion and confounder diffs (no LLM involved)."""

from __future__ import annotations

import time

from pydantic import BaseModel

from app.agents.offline import offline_hypotheses
from app.agents.orchestrator import run_analysis
from app.analysis.models import TIERS, AnalysisBundle, DistrictAssessment
from app.data.scenarios import OVERLAYS
from app.data.uploads import is_upload


class DistrictDelta(BaseModel):
    district: str
    name: str
    before: str
    after: str
    conf_before: float
    conf_after: float
    move: int  # tier steps (+ up / - down)


class SignalChange(BaseModel):
    district: str
    name: str
    change: str  # new | cleared | sources_changed | syndrome_changed
    before_sources: list[str]
    after_sources: list[str]
    signal_id: str | None


class HypothesisMove(BaseModel):
    category: str
    title: str
    kind: str
    before: float
    after: float


class EvidenceDelta(BaseModel):
    injected: str
    injected_label: str
    expected: str
    base: list[str]
    applied: list[str]  # the new scenario (base + injection), to apply to the whole console
    seed: int
    focus: str
    focus_name: str
    districts: list[DistrictDelta]
    signals: list[SignalChange]
    hypotheses: list[HypothesisMove]
    explanation: list[str]
    latency_ms: float


def _label(token: str) -> tuple[str, str]:
    if is_upload(token):
        return "Uploaded CSV", "Re-graded on the uploaded aggregates; the gate decides whether it escalates."
    o = OVERLAYS[token]
    expected = (
        "An infectious surge: the affected cluster should climb to E3."
        if o.is_epidemic
        else "A non-infectious explanation: the gate should NOT escalate it to E3."
    )
    return o.description, expected


def _hyps(a: DistrictAssessment) -> dict[str, tuple[str, str, float]]:
    hs = offline_hypotheses(a.name, a.signal, a.confounders, a.confidence)
    return {h.category: (h.title, h.kind, h.probability) for h in hs}


def _explain(token_label: str, moved: list[DistrictDelta], b: DistrictAssessment, a: DistrictAssessment) -> list[str]:
    lines = []
    if moved:
        parts = [f"{d.name} {d.before}→{d.after}" for d in moved[:4]]
        lines.append(f"Injecting “{token_label}” moved {len(moved)} district tier(s): {', '.join(parts)}.")
    else:
        lines.append(f"Injecting “{token_label}” changed no district tier: the evidence did not clear the next gate.")
    bc = {c.key: c for c in b.gate.criteria}
    flips = []
    for c in a.gate.criteria:
        prev = bc.get(c.key)
        was = prev.met if prev is not None else False
        if was != c.met:
            flips.append(
                f"{a.name}: “{c.label}” is {'now met' if c.met else 'no longer met'} ({c.detail.rstrip('.')})."
            )
    lines += flips[:4]
    new_down = [d for d in a.gate.downgrades if d not in b.gate.downgrades]
    for d in new_down:
        lines.append(f"{a.name}: downgraded: {d}.")
    bcf = {cf.name: cf for cf in b.confounders}
    for cf in a.confounders:
        if cf.status == "explains" and (cf.name not in bcf or bcf[cf.name].status != "explains"):
            lines.append(f"{a.name}: {cf.label.lower()} now explains about {cf.explained_share:.0%} of the excess.")
    if a.gate.tier != b.gate.tier:
        lines.append(f"Confidence for {a.name} moved {b.confidence.point:.0%} → {a.confidence.point:.0%}.")
    lines.append("Tiers come from the deterministic evidence gate; the LLM does not decide them.")
    return lines


def evidence_delta(
    base: tuple[str, ...], inject: str, seed: int, district: str | None = None, with_hypotheses: bool = True
) -> EvidenceDelta:
    before: AnalysisBundle = run_analysis(base, seed=seed)
    t0 = time.perf_counter()
    applied = (*base, inject)
    after: AnalysisBundle = run_analysis(applied, seed=seed)
    bmap = {a.district: a for a in before.assessments}
    amap = {a.district: a for a in after.assessments}

    deltas = [
        DistrictDelta(
            district=d,
            name=amap[d].name,
            before=bmap[d].gate.tier,
            after=amap[d].gate.tier,
            conf_before=round(bmap[d].confidence.point, 3),
            conf_after=round(amap[d].confidence.point, 3),
            move=TIERS.index(amap[d].gate.tier) - TIERS.index(bmap[d].gate.tier),
        )
        for d in amap
    ]
    moved = sorted([x for x in deltas if x.move], key=lambda x: (-abs(x.move), -TIERS.index(x.after), -x.conf_after))

    signals = []
    for d in amap:
        bs, as_ = bmap[d].signal, amap[d].signal
        if bs is None and as_ is None:
            continue
        change = (
            "new"
            if bs is None
            else "cleared"
            if as_ is None
            else "syndrome_changed"
            if bs.syndrome != as_.syndrome
            else "sources_changed"
            if set(bs.sources) != set(as_.sources)
            else ""
        )
        if change:
            signals.append(
                SignalChange(
                    district=d,
                    name=amap[d].name,
                    change=change,
                    before_sources=bs.sources if bs else [],
                    after_sources=as_.sources if as_ else [],
                    signal_id=(as_.signal_id if as_ else bs.signal_id if bs else None),
                )
            )

    focus = district or (
        moved[0].district if moved else max(deltas, key=lambda x: abs(x.conf_after - x.conf_before)).district
    )
    hyps: list[HypothesisMove] = []
    if with_hypotheses:
        hb, ha = _hyps(bmap[focus]), _hyps(amap[focus])
        for cat in sorted(set(hb) | set(ha), key=lambda c: -max(hb.get(c, ("", "", 0))[2], ha.get(c, ("", "", 0))[2])):
            title, kind, _ = ha.get(cat) or hb[cat]
            hyps.append(
                HypothesisMove(
                    category=cat,
                    title=title,
                    kind=kind,
                    before=hb.get(cat, ("", "", 0.0))[2],
                    after=ha.get(cat, ("", "", 0.0))[2],
                )
            )

    label, expected = _label(inject)
    return EvidenceDelta(
        injected=inject,
        injected_label=label,
        expected=expected,
        base=list(base),
        applied=list(applied),
        seed=seed,
        focus=focus,
        focus_name=amap[focus].name,
        districts=deltas,
        signals=signals,
        hypotheses=hyps[:6],
        explanation=_explain(label, moved, bmap[focus], amap[focus]),
        latency_ms=round((time.perf_counter() - t0) * 1000, 1),
    )
