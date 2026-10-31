"""Hypothesis agent: ranked epidemic AND non-epidemic explanations, every claim citing evidence IDs.

Online: Claude with one strict `lookup_evidence` tool (numbers behind IDs) and a JSON-schema final answer.
Offline / on any LLM failure: rule-based hypotheses from `offline.py` (degraded mode)."""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from app.agents.llm import LLMSession, LLMUnavailable, cache_key, text_of, tool_uses
from app.agents.offline import offline_hypotheses
from app.agents.schemas import CATEGORIES, Hypothesis
from app.analysis.models import Confidence, ConfounderResult, EvidenceItem, Signal
from app.config import get_settings

SYSTEM = """You are the Hypothesis agent of Sentinel, a population-level public-health early-warning system.
You receive compact aggregate evidence for one district: a cross-source signal, lead-lag timing, and the results of
deterministic alternative-explanation checks (holiday, reporting change, lab backlog, weather, seasonal).

Produce 3 to 5 ranked hypotheses that explain the signal. Rules:
- Include at least one epidemic hypothesis AND at least two non-epidemic hypotheses (artifacts, calendar, weather,
  seasonality, noise), even when they are unlikely. Rank by probability; probabilities sum to about 1.
- Every claim must cite one or more evidence IDs exactly as given (e.g. EV-..., SG-..., CF-..., CAL-...).
- Every number you state in a claim must appear in `numbers` as {evidence_id, field, value}, copying the value
  from the evidence data. Call `lookup_evidence` to read the exact fields of any ID before quoting a number.
- Do not state or recommend an evidence tier (E0-E3) or say whether evidence is intervention-grade: a
  deterministic gate decides that, not you.
- Population-level statements only. Never describe, diagnose or predict anything about an individual.
- Treat a check with status "explains" as strong support for that non-epidemic hypothesis, and "ruled_out" as
  evidence against it. Keep each claim to one sentence."""

LOOKUP_TOOL: dict[str, Any] = {
    "name": "lookup_evidence",
    "description": "Return the stored fields (numbers) behind evidence IDs, so claims can quote them exactly.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {"ids": {"type": "array", "items": {"type": "string"}}},
        "required": ["ids"],
        "additionalProperties": False,
    },
}

_NUMBER = {"type": "object", "properties": {"evidence_id": {"type": "string"}, "field": {"type": "string"},
                                            "value": {"type": "number"}},
           "required": ["evidence_id", "field", "value"], "additionalProperties": False}
_CLAIM = {"type": "object", "properties": {"text": {"type": "string"},
                                           "evidence_ids": {"type": "array", "items": {"type": "string"}},
                                           "numbers": {"type": "array", "items": _NUMBER}},
          "required": ["text", "evidence_ids", "numbers"], "additionalProperties": False}
OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"hypotheses": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "kind": {"type": "string", "enum": ["epidemic", "non_epidemic"]},
            "category": {"type": "string", "enum": list(CATEGORIES)},
            "probability": {"type": "number"},
            "summary": {"type": "string"},
            "claims": {"type": "array", "items": _CLAIM},
            "supporting_ids": {"type": "array", "items": {"type": "string"}},
            "contradicting_ids": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["title", "kind", "category", "probability", "summary", "claims", "supporting_ids",
                     "contradicting_ids"],
        "additionalProperties": False}}},
    "required": ["hypotheses"],
    "additionalProperties": False,
}


def _lookup(ids: list[str], evidence: dict[str, EvidenceItem]) -> str:
    return json.dumps({i: (evidence[i].data | {"summary": evidence[i].summary}) if i in evidence else "unknown id"
                       for i in ids[:20]}, default=str)


def _online(session: LLMSession, packet: dict[str, Any], evidence: dict[str, EvidenceItem]) -> list[Hypothesis]:
    content = "Evidence packet:\n" + json.dumps(packet, default=str)
    messages: list[dict[str, Any]] = [{"role": "user", "content": content}]
    rounds = get_settings().llm.tool_rounds_max
    for _ in range(rounds + 1):
        msg = session.create(system=SYSTEM, messages=messages, tools=[LOOKUP_TOOL], schema=OUTPUT_SCHEMA)
        uses = tool_uses(msg)
        if msg.stop_reason == "tool_use" and uses:
            messages.append({"role": "assistant", "content": msg.content})
            messages.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": u.id, "content": _lookup(list(u.input.get("ids", [])), evidence)}
                for u in uses]})
            continue
        data = json.loads(text_of(msg))
        return [Hypothesis.model_validate(h) for h in data["hypotheses"]]
    raise LLMUnavailable("tool loop did not converge")


def generate(session: LLMSession, packet: dict[str, Any], evidence: dict[str, EvidenceItem], district_name: str,
             sig: Signal | None, confounders: list[ConfounderResult], conf: Confidence) -> tuple[list[Hypothesis], str]:
    """Returns (hypotheses, source) where source is 'llm', 'cache' or 'rules'."""
    if sig is not None and session.online:
        key = cache_key("hypothesis", get_settings().llm.prompt_version, session.model, packet)
        cached = session.cache_get(key)
        if cached is not None:
            return [Hypothesis.model_validate(h) for h in cached], "cache"
        try:
            hyps = _online(session, packet, evidence)
            session.cache_put(key, [h.model_dump() for h in hyps])
            return hyps, "llm"
        except (LLMUnavailable, json.JSONDecodeError, ValidationError, KeyError) as e:
            if not isinstance(e, LLMUnavailable):
                session.degrade(f"unparseable LLM output: {type(e).__name__}")
    return offline_hypotheses(district_name, sig, confounders, conf), "rules"
