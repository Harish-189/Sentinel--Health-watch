"""Agent outputs: hypotheses, verification, recommendations, the case file."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.analysis.models import DistrictAssessment, EvidenceItem

HypothesisKind = Literal["epidemic", "non_epidemic"]
CATEGORIES: tuple[str, ...] = (
    "infectious_respiratory", "infectious_gastrointestinal", "holiday", "reporting_change", "lab_backlog",
    "weather", "seasonal", "data_quality", "noise",
)


class NumberRef(BaseModel):
    evidence_id: str
    field: str
    value: float


class Claim(BaseModel):
    claim_id: str = ""
    text: str
    evidence_ids: list[str]
    numbers: list[NumberRef] = Field(default_factory=list)


class Hypothesis(BaseModel):
    hypothesis_id: str = ""
    title: str
    kind: HypothesisKind
    category: str
    probability: float
    summary: str
    claims: list[Claim]
    supporting_ids: list[str] = Field(default_factory=list)
    contradicting_ids: list[str] = Field(default_factory=list)


class DroppedClaim(BaseModel):
    hypothesis_id: str
    claim_id: str
    text: str
    reason: str


class Verification(BaseModel):
    total_claims: int
    grounded_claims: int
    groundedness: float
    hallucination_rate: float
    dropped: list[DroppedClaim]
    dropped_hypotheses: list[str]
    critic: Literal["llm", "skipped", "rules_only"]


class Recommendation(BaseModel):
    action: str
    title: str
    min_tier: str
    rationale: str
    evidence_ids: list[str]
    params: dict[str, Any] = Field(default_factory=dict)
    pending_ref: str | None = None
    source: Literal["llm", "rules"] = "rules"


class LLMUsage(BaseModel):
    mode: Literal["online", "degraded"] = "degraded"
    degraded_reason: str | None = None
    model: str = ""
    fast_model: str = ""
    calls: int = 0
    cache_hits: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float = 0.0


class StepEvent(BaseModel):
    step: str
    status: Literal["running", "done", "skipped", "blocked", "degraded"]
    ms: float = 0.0
    detail: str = ""


class CaseFile(BaseModel):
    scenario: list[str]
    seed: int
    as_of: int
    as_of_date: str
    district: str
    district_name: str
    tiers: dict[str, str]
    assessment: DistrictAssessment
    hypotheses: list[Hypothesis]
    verification: Verification
    recommendations: list[Recommendation]
    usage: LLMUsage
    latency_ms: float
    steps: list[StepEvent]
    evidence: dict[str, EvidenceItem]
    tier_explanation: str
