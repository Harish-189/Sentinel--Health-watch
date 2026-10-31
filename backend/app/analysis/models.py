"""Analysis outputs. Every claim-bearing object has an ID that the LLM layer must cite."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Tier = Literal["E0", "E1", "E2", "E3"]
TIERS: tuple[str, ...] = ("E0", "E1", "E2", "E3")
Status = Literal["ruled_out", "explains", "inconclusive"]


def tier_at_least(tier: str, minimum: str) -> bool:
    return TIERS.index(tier) >= TIERS.index(minimum)


class LeadLag(BaseModel):
    source: str
    reference: str
    best_lag: int  # days `source` leads `reference` (negative = lags)
    corr: float


class Signal(BaseModel):
    signal_id: str
    district: str
    syndrome: str
    sources: list[str]  # independent sources anomalous within the lag window
    independent_sources: int
    window_ids: list[str]  # anomalies inside the lag-consistent window
    evidence_ids: list[str]  # every recent anomaly in the signal
    first_day: int
    last_day: int
    first_detection_day: int
    persistence_days: int
    mean_z: float
    peak_z: float
    mean_excess: float
    onset_by_source: dict[str, int]
    lag_consistency: float
    lead_lag: list[LeadLag]
    adjacent_districts: list[str] = Field(default_factory=list)
    adjacent_evidence: list[str] = Field(default_factory=list)


class ConfounderResult(BaseModel):
    confounder_id: str
    name: str
    label: str
    status: Status  # ruled_out = this explanation fails; explains = it accounts for the signal
    summary: str
    explained_share: float
    values: dict[str, float | int | str | bool | None]
    evidence_ids: list[str]


class Criterion(BaseModel):
    criterion_id: str
    key: str
    tier: Tier
    label: str
    met: bool
    value: float | int | str | None
    threshold: str
    detail: str
    evidence_ids: list[str]


class GateResult(BaseModel):
    tier: Tier
    raw_tier: Tier
    criteria: list[Criterion]
    downgrades: list[str]
    residual_excess: float
    data_quality: dict[str, float]


class Confidence(BaseModel):
    point: float
    low: float
    high: float
    features: dict[str, float]


class Band(BaseModel):
    p10: list[float]
    p50: list[float]
    p90: list[float]


class Forecast(BaseModel):
    forecast_id: str
    district: str
    as_of: int
    intervention: bool
    days: list[int]
    dates: list[str]
    beds: Band
    icu: Band
    beds_total: float
    icu_total: float
    history_days: list[int]
    history_beds: list[float | None]
    history_icu: list[float | None]
    breach_prob_beds: list[float]
    breach_prob_icu: list[float]
    breach_day_beds: int | None  # first projected day with P(breach) >= 0.5
    breach_day_icu: int | None
    growth_rate: float
    growth_se: float


class DistrictAssessment(BaseModel):
    district: str
    name: str
    signal: Signal | None
    confounders: list[ConfounderResult]
    gate: GateResult
    confidence: Confidence
    forecast: Forecast


class EvidenceItem(BaseModel):
    id: str
    kind: str
    district: str | None
    summary: str
    data: dict[str, Any] = Field(default_factory=dict)


class AnalysisBundle(BaseModel):
    scenario: list[str]
    seed: int
    as_of: int
    as_of_date: str
    primary: str
    assessments: list[DistrictAssessment]
    evidence: dict[str, EvidenceItem]
    context: Any = Field(default=None, exclude=True, repr=False)

    def assessment(self, district: str) -> DistrictAssessment:
        for a in self.assessments:
            if a.district == district:
                return a
        raise KeyError(district)
