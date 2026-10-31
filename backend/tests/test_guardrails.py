"""Explicit limits (SPEC 14): no individual diagnosis, no personalized prediction, no autonomous action,
the LLM never decides tiers, and only compact aggregate evidence reaches the LLM."""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.agents import pipeline
from app.agents.llm import LLMSession
from app.agents.orchestrator import run_analysis
from app.agents.packet import MAX_PACKET_CHARS, build_packet
from app.agents.pipeline import run_to_casefile
from app.agents.verifier import INDIVIDUAL_RE
from app.data.privacy import is_pii_name

SCENARIOS = ["true_outbreak", "holiday_spike", "reporting_change", "lab_backlog", "weather_driven", "noise_only"]


def _keys(obj: Any) -> list[str]:
    if isinstance(obj, dict):
        return [k for k, v in obj.items() for k in [k, *_keys(v)]]
    if isinstance(obj, list):
        return [k for v in obj for k in _keys(v)]
    return []


def _numeric_lists(obj: Any) -> list[int]:
    if isinstance(obj, dict):
        return [n for v in obj.values() for n in _numeric_lists(v)]
    if isinstance(obj, list):
        own = [len(obj)] if obj and all(isinstance(x, int | float) for x in obj) else []
        return own + [n for v in obj for n in _numeric_lists(v)]
    return []


@pytest.fixture(autouse=True)
def _fresh() -> None:
    pipeline.clear_cache()


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_packet_is_compact_aggregate_and_pii_free(scenario: str) -> None:
    bundle = run_analysis(scenario, seed=42)
    a = bundle.assessment(bundle.primary)
    packet = build_packet(a.district, a.name, bundle.as_of_date, a.signal, a.confounders, bundle.evidence)
    assert not [k for k in _keys(packet) if is_pii_name(k)]
    assert max(_numeric_lists(packet), default=0) < 30  # no raw time series
    assert len(json.dumps(packet, default=str)) <= MAX_PACKET_CHARS
    assert "tier" not in packet and "criteria" not in packet  # the Hypothesis agent never sees the tier


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_outputs_are_population_level_and_tiers_are_deterministic(scenario: str) -> None:
    case = run_to_casefile((scenario,), 42, session=LLMSession(mode="degraded", cache_dir=None))
    text = " ".join([h.title + " " + h.summary + " " + " ".join(c.text for c in h.claims) for h in case.hypotheses]
                    + [r.rationale + " " + json.dumps(r.params) for r in case.recommendations])
    assert not INDIVIDUAL_RE.search(text)
    bundle = run_analysis(scenario, seed=42)
    assert case.tiers == {a.district: a.gate.tier for a in bundle.assessments}


def test_no_action_executes_from_the_pipeline() -> None:
    case = run_to_casefile(("true_outbreak",), 42, session=LLMSession(mode="degraded", cache_dir=None))
    assert all(r.pending_ref is None for r in case.recommendations)  # no governance passed: nothing queued


def test_api_refuses_individual_level_action_params() -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    r = TestClient(app).post("/api/actions", json={"action": "increase_monitoring", "district": "D3",
                                                   "params": {"patient_name": "x"}, "evidence_ids": []})
    assert r.status_code == 400
