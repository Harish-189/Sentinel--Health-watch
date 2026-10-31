"""Offline rule-based reasoning (degraded mode). Same output shape as the LLM agents, and every
claim is built from evidence items so it passes the same Verifier."""

from __future__ import annotations

import math

from app.agents.schemas import Claim, Hypothesis, NumberRef, Recommendation
from app.agents.tools import CATALOG, allowed_actions
from app.analysis.models import Confidence, ConfounderResult, DistrictAssessment, Forecast, Signal

NON_EPIDEMIC_TITLES: dict[str, tuple[str, str]] = {
    "holiday": ("holiday", "Holiday-driven care-seeking and purchasing"),
    "reporting_change": ("reporting_change", "Reporting artifact: change in reporting sites"),
    "lab_backlog": ("lab_backlog", "Lab batch reporting (backlog), not true positivity"),
    "weather": ("weather", "Heat / air-quality driven respiratory visits (non-infectious)"),
    "seasonal": ("seasonal", "Expected seasonal rise"),
}


def _signal_claims(sig: Signal) -> list[Claim]:
    first = min(sig.onset_by_source, key=lambda s: sig.onset_by_source[s])
    claims = [
        Claim(text=f"{sig.independent_sources} independent sources ({', '.join(sig.sources)}) became anomalous "
                   f"within the lag window; peak z {sig.peak_z}.",
              evidence_ids=[sig.signal_id, *sig.window_ids[:4]],
              numbers=[NumberRef(evidence_id=sig.signal_id, field="independent_sources",
                                 value=sig.independent_sources),
                       NumberRef(evidence_id=sig.signal_id, field="peak_z", value=sig.peak_z)]),
        Claim(text=f"{first.capitalize()} moved first; the onset order matches an infectious surge "
                   f"(lag consistency {sig.lag_consistency:.0%}).",
              evidence_ids=[sig.signal_id],
              numbers=[NumberRef(evidence_id=sig.signal_id, field="lag_consistency", value=sig.lag_consistency)]),
    ]
    if sig.adjacent_districts:
        claims.append(Claim(text=f"Adjacent districts {', '.join(sig.adjacent_districts)} show a matching "
                                 f"{sig.syndrome} signal (spatial coherence).",
                            evidence_ids=[sig.signal_id, *sig.adjacent_evidence]))
    return claims


def _lab_claim(confounders: list[ConfounderResult]) -> Claim | None:
    lab = next((c for c in confounders if c.name == "lab_backlog"), None)
    if lab is None or lab.status != "ruled_out":
        return None
    return Claim(text="Lab positivity is rising while test volume is stable, which a reporting backlog would not "
                      "produce.", evidence_ids=[lab.confounder_id, *lab.evidence_ids[:2]])


def _weight(c: ConfounderResult) -> float:
    if c.status == "explains":
        return max(c.explained_share, 0.35)
    if c.status == "inconclusive":
        return 0.4 * c.explained_share
    return 0.0


def offline_hypotheses(district_name: str, sig: Signal | None, confounders: list[ConfounderResult],
                       conf: Confidence) -> list[Hypothesis]:
    if sig is None:
        return [Hypothesis(title="Background variation within the expected range", kind="non_epidemic",
                           category="noise", probability=0.97,
                           summary=f"No sustained multi-day anomaly in {district_name}.",
                           claims=[], supporting_ids=[])]
    syndrome = "gastrointestinal" if sig.syndrome == "gastrointestinal" else "respiratory"
    epi_claims = _signal_claims(sig)
    lab = _lab_claim(confounders)
    if lab:
        epi_claims.append(lab)
    explaining = [c for c in confounders if _weight(c) > 0]
    weights: list[tuple[Hypothesis, float]] = [(
        Hypothesis(
            title=f"Infectious {syndrome} transmission in {district_name}", kind="epidemic",
            category=f"infectious_{syndrome}", probability=0.0,
            summary=f"Multi-source {syndrome} rise with an infectious lead-lag pattern.",
            claims=epi_claims, supporting_ids=[sig.signal_id, *sig.window_ids],
            contradicting_ids=[c.confounder_id for c in explaining]),
        conf.point,
    )]
    for c in explaining:
        category, title = NON_EPIDEMIC_TITLES.get(c.name, (c.name, c.label))
        claim = Claim(text=c.summary, evidence_ids=[c.confounder_id, *c.evidence_ids[:3]],
                      numbers=[NumberRef(evidence_id=c.confounder_id, field="explained_share",
                                         value=c.explained_share)])
        weights.append((Hypothesis(title=title, kind="non_epidemic", category=category, probability=0.0,
                                   summary=f"{c.label} accounts for about {c.explained_share:.0%} of the excess.",
                                   claims=[claim], supporting_ids=[c.confounder_id],
                                   contradicting_ids=[sig.signal_id]), _weight(c)))
    order = ("weather", "holiday", "reporting_change", "seasonal", "lab_backlog")
    rejected = sorted((c for c in confounders if c.status == "ruled_out"), key=lambda c: order.index(c.name))
    for c in rejected[: max(0, 2 - len(explaining))]:  # keep visible alternatives even when all are ruled out
        category, title = NON_EPIDEMIC_TITLES.get(c.name, (c.name, c.label))
        weights.append((Hypothesis(title=title, kind="non_epidemic", category=category, probability=0.0,
                                   summary=f"Considered and ruled out by the {c.label.lower()} check.",
                                   claims=[Claim(text=c.summary, evidence_ids=[c.confounder_id, *c.evidence_ids[:2]])],
                                   supporting_ids=[], contradicting_ids=[c.confounder_id]), 0.015))
    ruled_out = [c.confounder_id for c in confounders if c.status == "ruled_out"]
    weights.append((Hypothesis(
        title="Unexplained non-infectious fluctuation", kind="non_epidemic", category="noise", probability=0.0,
        summary="Residual chance the rise is coincidental; alternative checks: "
                f"{len(ruled_out)} of {len(confounders)} ruled out.",
        claims=[Claim(text=f"{len(ruled_out)} of {len(confounders)} alternative explanations were ruled out by "
                           "deterministic checks.", evidence_ids=ruled_out or [sig.signal_id])],
        supporting_ids=[], contradicting_ids=[sig.signal_id]), 0.05 + 0.1 * (1 - conf.point)))
    total = sum(w for _, w in weights) or 1.0
    out = []
    for h, w in weights:
        h.probability = round(w / total, 3)
        out.append(h)
    return sorted(out, key=lambda h: -h.probability)


def offline_recommendations(a: DistrictAssessment, forecast: Forecast) -> list[Recommendation]:
    tier = a.gate.tier
    allowed = {s.name for s in allowed_actions(tier)}
    sig = a.signal
    if sig is None or not allowed:
        return []
    cf = {c.name: c for c in a.confounders}
    crit = {c.key: c for c in a.gate.criteria}
    recs: list[Recommendation] = []

    def add(action: str, rationale: str, ids: list[str], **params: object) -> None:
        if action in allowed and action not in {r.action for r in recs}:
            spec = CATALOG[action]
            recs.append(Recommendation(action=action, title=spec.title, min_tier=spec.min_tier, rationale=rationale,
                                       evidence_ids=ids, params=dict(params), source="rules"))

    artifacts = [c for n, c in cf.items() if n in ("reporting_change", "lab_backlog") and c.status == "explains"]
    if artifacts or not crit["e2_quality"].met:
        ids = [c.confounder_id for c in artifacts] or [crit["e2_quality"].criterion_id]
        add("request_data_validation", "Verify feeds and site lists: a data artifact may explain part of the signal.",
            ids)
    add("increase_monitoring", f"Keep {a.name} on the daily watchlist while the {sig.syndrome} signal persists.",
        [sig.signal_id], syndrome=sig.syndrome)
    if not crit["e3_lab"].met:
        add("request_lab_sampling", "Lab confirmation is the missing criterion for intervention-grade evidence.",
            [crit["e3_lab"].criterion_id, sig.signal_id], panel="panel_B" if sig.syndrome == "gastrointestinal"
            else "panel_A")
    add("draft_clinician_advisory", f"Corroborated {sig.syndrome} signal across "
        f"{sig.independent_sources} sources; alert clinicians (draft only).", [sig.signal_id, *sig.window_ids[:2]],
        syndrome=sig.syndrome)
    peak_p90 = max(forecast.beds.p90)
    if max(forecast.breach_prob_beds) >= 0.5:
        beds = max(int(math.ceil(peak_p90 - forecast.beds_total)), 5)
        add("prepose_capacity", f"Bed occupancy is projected to exceed capacity (P(breach) "
            f"{max(forecast.breach_prob_beds):.0%}); pre-position {beds} surge beds.", [forecast.forecast_id],
            beds=beds)
    add("draft_public_advisory", "Intervention-grade evidence: prepare a population-level advisory (draft only).",
        [sig.signal_id, crit["e3_confounders"].criterion_id], syndrome=sig.syndrome)
    return recs
