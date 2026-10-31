"""Verifier: rule check first (evidence IDs exist, numbers match, no tier claims, no individual-level
language), then an optional LLM critic. Ungrounded claims are dropped, never repaired."""

from __future__ import annotations

import json
import re
from typing import Any

from app.agents.llm import LLMSession, LLMUnavailable, text_of
from app.agents.schemas import Claim, DroppedClaim, Hypothesis, Recommendation, Verification
from app.analysis.models import EvidenceItem
from app.config import get_settings

TIER_RE = re.compile(r"\bE[0-3]\b|\b(intervention[- ]grade|tier)\b", re.IGNORECASE)
INDIVIDUAL_RE = re.compile(
    r"\b(diagnos\w*|patients?|individuals?|persons?|household|named|this person|quarantine (him|her|them)|"
    r"isolate (him|her|them)|will (develop|become ill))\b", re.IGNORECASE)

CRITIC_SYSTEM = (
    "You audit claims from a public-health surveillance system. For each claim you get the claim text and the "
    "summaries of the evidence it cites. Flag a claim only if its evidence does not support what it says. "
    "Return JSON only."
)
CRITIC_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"unsupported": {"type": "array", "items": {
        "type": "object",
        "properties": {"claim_id": {"type": "string"}, "reason": {"type": "string"}},
        "required": ["claim_id", "reason"], "additionalProperties": False}}},
    "required": ["unsupported"], "additionalProperties": False,
}


def _number_ok(claimed: float, actual: Any) -> bool:
    if isinstance(actual, bool) or not isinstance(actual, int | float):
        return False
    cfg = get_settings().llm
    tol = max(cfg.number_rel_tol * abs(actual), cfg.number_abs_tol)
    if abs(claimed - actual) <= tol:
        return True
    return 0 <= abs(actual) <= 1.5 and abs(claimed - 100 * actual) <= max(tol * 100, 1.1)  # 0.92 written as 92


def check_claim(claim: Claim, evidence: dict[str, EvidenceItem]) -> str | None:
    """Return a drop reason, or None if the claim is grounded."""
    if not claim.evidence_ids:
        return "no evidence ID cited"
    missing = [e for e in claim.evidence_ids if e not in evidence]
    if missing:
        return f"unknown evidence ID(s): {', '.join(missing[:3])}"
    if INDIVIDUAL_RE.search(claim.text):
        return "individual-level language (population signals only)"
    if TIER_RE.search(claim.text):
        return "asserts an evidence tier (tiers are set by the deterministic gate only)"
    for n in claim.numbers:
        item = evidence.get(n.evidence_id)
        if item is None:
            return f"number cites unknown evidence ID {n.evidence_id}"
        if n.field not in item.data:
            return f"field '{n.field}' not present in {n.evidence_id}"
        if not _number_ok(n.value, item.data[n.field]):
            return f"numeric mismatch: {n.field}={n.value} but {n.evidence_id} has {item.data[n.field]}"
    return None


def _critic(session: LLMSession, claims: list[tuple[str, Claim]], evidence: dict[str, EvidenceItem]) -> dict[str, str]:
    payload = [{"claim_id": cid, "text": c.text,
                "evidence": [evidence[e].summary for e in c.evidence_ids if e in evidence]} for cid, c in claims]
    msg = session.create(system=CRITIC_SYSTEM, fast=True, schema=CRITIC_SCHEMA,
                         effort=get_settings().llm.critic_effort, max_tokens=2000,
                         messages=[{"role": "user", "content": json.dumps(payload)}])
    data = json.loads(text_of(msg))
    return {u["claim_id"]: u["reason"] for u in data.get("unsupported", [])}


def verify(hypotheses: list[Hypothesis], evidence: dict[str, EvidenceItem],
           session: LLMSession | None = None) -> tuple[list[Hypothesis], Verification]:
    dropped: list[DroppedClaim] = []
    total = 0
    survivors: list[tuple[str, Claim]] = []
    for hi, h in enumerate(hypotheses, start=1):
        h.hypothesis_id = h.hypothesis_id or f"H{hi}"
        for ci, c in enumerate(h.claims, start=1):
            c.claim_id = c.claim_id or f"{h.hypothesis_id}.C{ci}"
            total += 1
            reason = check_claim(c, evidence)
            if reason:
                dropped.append(DroppedClaim(hypothesis_id=h.hypothesis_id, claim_id=c.claim_id, text=c.text,
                                            reason=reason))
            else:
                survivors.append((c.claim_id, c))

    critic = "rules_only"
    use_critic = session is not None and session.online and get_settings().llm.verifier_llm_critic and survivors
    if use_critic and session is not None:
        try:
            flagged = _critic(session, survivors, evidence)
            critic = "llm"
            for cid, c in survivors:
                if cid in flagged:
                    dropped.append(DroppedClaim(hypothesis_id=cid.split(".")[0], claim_id=cid, text=c.text,
                                                reason=f"critic: {flagged[cid]}"))
        except (LLMUnavailable, ValueError, KeyError):
            critic = "skipped"

    dropped_ids = {d.claim_id for d in dropped}
    kept: list[Hypothesis] = []
    dropped_h: list[str] = []
    for h in hypotheses:
        h.claims = [c for c in h.claims if c.claim_id not in dropped_ids]
        h.supporting_ids = [e for e in h.supporting_ids if e in evidence]
        h.contradicting_ids = [e for e in h.contradicting_ids if e in evidence]
        had_claims = any(d.hypothesis_id == h.hypothesis_id for d in dropped) or h.claims
        if had_claims and not h.claims:
            dropped_h.append(h.hypothesis_id)
        else:
            kept.append(h)
    _normalize(kept)
    grounded = total - len(dropped)
    return kept, Verification(
        total_claims=total, grounded_claims=grounded, groundedness=round(grounded / total, 3) if total else 1.0,
        hallucination_rate=round(len(dropped) / total, 3) if total else 0.0, dropped=dropped,
        dropped_hypotheses=dropped_h, critic=critic,  # type: ignore[arg-type]
    )


def _normalize(hypotheses: list[Hypothesis]) -> None:
    total = sum(max(h.probability, 0.0) for h in hypotheses)
    if total > 0:
        for h in hypotheses:
            h.probability = round(max(h.probability, 0.0) / total, 3)
    hypotheses.sort(key=lambda h: -h.probability)


def verify_recommendations(recs: list[Recommendation], evidence: dict[str, EvidenceItem]) -> list[Recommendation]:
    out = []
    for r in recs:
        r.evidence_ids = [e for e in r.evidence_ids if e in evidence]
        if r.evidence_ids and not INDIVIDUAL_RE.search(r.rationale):
            out.append(r)
    return out
