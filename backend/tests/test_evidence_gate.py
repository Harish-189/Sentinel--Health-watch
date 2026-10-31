"""The evidence gate is the safety core: confounder scenarios must never reach E3."""

import pytest

from app.agents.orchestrator import run_analysis
from app.analysis.models import TIERS

SEEDS = range(5)


def _max_tier(scenario: str | tuple[str, ...], seed: int) -> str:
    bundle = run_analysis(scenario, seed=seed)
    return max((a.gate.tier for a in bundle.assessments), key=TIERS.index)


@pytest.mark.parametrize("seed", SEEDS)
def test_true_outbreak_reaches_e3_in_primary(seed: int) -> None:
    bundle = run_analysis("true_outbreak", seed=seed)
    assert bundle.assessment("ERD").gate.tier == "E3"
    assert bundle.primary == "ERD" or bundle.assessment(bundle.primary).gate.tier == "E3"


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize(
    "scenario", ["holiday_spike", "reporting_change", "lab_backlog", "weather_driven", "seasonal_peak"]
)
def test_confounder_scenarios_never_reach_e3(scenario: str, seed: int) -> None:
    assert _max_tier(scenario, seed) != "E3"


@pytest.mark.parametrize("seed", SEEDS)
def test_noise_only_stays_quiet(seed: int) -> None:
    assert TIERS.index(_max_tier("noise_only", seed)) <= TIERS.index("E1")


@pytest.mark.parametrize("seed", SEEDS)
def test_contradicting_lab_downgrades_outbreak(seed: int) -> None:
    bundle = run_analysis(("true_outbreak", "contradicting_lab"), seed=seed)
    gate = bundle.assessment("ERD").gate
    assert gate.tier != "E3"
    assert gate.downgrades or not next(c for c in gate.criteria if c.key == "e3_lab").met


def test_holiday_is_named_as_downgrade() -> None:
    bundle = run_analysis("holiday_spike", seed=42)
    gated = [a for a in bundle.assessments if a.signal is not None]
    assert gated and all(a.gate.tier in ("E0", "E1") for a in gated)
    assert any("holiday" in d for a in gated for d in a.gate.downgrades)


def test_gate_is_deterministic() -> None:
    a = run_analysis("true_outbreak", seed=3).assessment("ERD").gate
    run_analysis.cache_clear()
    b = run_analysis("true_outbreak", seed=3).assessment("ERD").gate
    assert a == b


def test_every_criterion_has_threshold_and_evidence() -> None:
    gate = run_analysis("true_outbreak", seed=42).assessment("ERD").gate
    keys = {c.key for c in gate.criteria}
    assert {"e1_anomaly", "e2_sources", "e2_quality", "e3_lab", "e3_spatial", "e3_persistence",
            "e3_confounders"} <= keys
    for c in gate.criteria:
        assert c.criterion_id.startswith("GT-ERD-")
        assert c.threshold is not None
    assert all(c.evidence_ids for c in gate.criteria if c.met)


def test_confidence_interval_brackets_point() -> None:
    conf = run_analysis("true_outbreak", seed=42).assessment("ERD").confidence
    assert conf.low <= conf.point <= conf.high
    assert 0 <= conf.low and conf.high <= 1
    quiet = run_analysis("noise_only", seed=42).assessment("ERD").confidence
    assert conf.point > quiet.point


def test_evidence_index_resolves_every_cited_id() -> None:
    bundle = run_analysis("true_outbreak", seed=42)
    for a in bundle.assessments:
        cited = {e for c in a.gate.criteria for e in c.evidence_ids}
        cited |= {e for cf in a.confounders for e in cf.evidence_ids}
        assert cited <= set(bundle.evidence), cited - set(bundle.evidence)
