"""Recommender: constrained to the action catalog and gated by the deterministic tier.

Online: Claude calls a strict `propose_action` tool whose `action` enum contains ONLY the actions the tier
allows, so it cannot invent actions. Governance re-checks the tier on proposal. Offline: rule table."""

from __future__ import annotations

import json
from typing import Any

from app.agents.llm import LLMSession, LLMUnavailable, cache_key, tool_uses
from app.agents.offline import offline_recommendations
from app.agents.schemas import Recommendation
from app.agents.tools import CATALOG, allowed_actions
from app.analysis.models import DistrictAssessment
from app.config import get_settings

SYSTEM = """You are the Recommender of Sentinel, a population-level public-health early-warning system.
Given the deterministic evidence tier, the gate criteria, the capacity forecast and verified hypotheses for one
district, propose the most useful next actions by calling `propose_action` once per action (at most 4).
Only the actions offered in the tool are allowed. Every proposal must cite evidence IDs from the input and give a
one-sentence rationale. Nothing executes automatically: a human approves, edits or rejects every action.
Never target or mention an individual."""


def _tool(allowed: list[str]) -> dict[str, Any]:
    return {
        "name": "propose_action",
        "description": "Queue one catalog action for human approval.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": allowed},
                "rationale": {"type": "string"},
                "evidence_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["action", "rationale", "evidence_ids"],
            "additionalProperties": False,
        },
    }


def _packet(a: DistrictAssessment, hypotheses: list[dict[str, Any]]) -> dict[str, Any]:
    f = a.forecast
    return {
        "district": a.district, "tier": a.gate.tier, "confidence": a.confidence.point,
        "criteria": [{"id": c.criterion_id, "label": c.label, "met": c.met} for c in a.gate.criteria],
        "downgrades": a.gate.downgrades,
        "forecast": {"id": f.forecast_id, "max_breach_prob_beds": max(f.breach_prob_beds),
                     "breach_day_beds": f.breach_day_beds, "beds_total": f.beds_total},
        "signal_id": a.signal.signal_id if a.signal else None,
        "hypotheses": hypotheses,
    }


def _online(session: LLMSession, a: DistrictAssessment, hypotheses: list[dict[str, Any]],
            allowed: list[str]) -> list[Recommendation]:
    msg = session.create(system=SYSTEM, tools=[_tool(allowed)], max_tokens=4000,
                         messages=[{"role": "user", "content": json.dumps(_packet(a, hypotheses), default=str)}])
    recs: list[Recommendation] = []
    for u in tool_uses(msg):
        action = u.input.get("action")
        if action not in allowed or action in {r.action for r in recs}:
            continue  # out of catalog / above tier / duplicate: dropped
        spec = CATALOG[action]
        recs.append(Recommendation(action=action, title=spec.title, min_tier=spec.min_tier,
                                   rationale=str(u.input.get("rationale", ""))[:400],
                                   evidence_ids=[str(e) for e in u.input.get("evidence_ids", [])], source="llm"))
    if not recs:
        raise LLMUnavailable("no valid proposals")
    return recs


def recommend(session: LLMSession, a: DistrictAssessment, hypotheses: list[dict[str, Any]]) -> list[Recommendation]:
    allowed = [s.name for s in allowed_actions(a.gate.tier)]
    if not allowed or a.signal is None:
        return []
    rules = offline_recommendations(a, a.forecast)
    if session.online:
        key = cache_key("recommend", get_settings().llm.prompt_version, session.model, _packet(a, hypotheses))
        cached = session.cache_get(key)
        if cached is not None:
            return [Recommendation.model_validate(r) for r in cached]
        try:
            recs = _online(session, a, hypotheses, allowed)
            # keep rule-derived parameters (e.g. bed counts) where the model picked the same action
            params = {r.action: r.params for r in rules}
            for r in recs:
                r.params = params.get(r.action, {})
            session.cache_put(key, [r.model_dump() for r in recs])
            return recs
        except LLMUnavailable:
            pass
    return rules
