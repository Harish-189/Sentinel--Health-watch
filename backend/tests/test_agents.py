"""LLM layer, fully offline: a fake Anthropic client stands in for the API."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import anthropic
import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.agents import pipeline
from app.agents.llm import LLMSession
from app.agents.pipeline import STEPS, run_pipeline, run_to_casefile
from app.agents.schemas import CaseFile, Claim, Hypothesis, NumberRef, StepEvent
from app.agents.verifier import verify
from app.analysis.models import EvidenceItem
from app.governance.approvals import Governance

# ---------------------------------------------------------------- fakes


def _usage() -> SimpleNamespace:
    return SimpleNamespace(input_tokens=1200, output_tokens=300, cache_read_input_tokens=900,
                           cache_creation_input_tokens=0)


def text_msg(payload: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=json.dumps(payload))], stop_reason="end_turn",
                           usage=_usage())


def tool_msg(*calls: tuple[str, dict[str, Any]]) -> SimpleNamespace:
    blocks = [SimpleNamespace(type="tool_use", id=f"tu_{i}", name=n, input=inp) for i, (n, inp) in enumerate(calls)]
    return SimpleNamespace(content=blocks, stop_reason="tool_use", usage=_usage())


class FakeClient:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, Any]] = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs: Any) -> Any:
        self.requests.append(kwargs)
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def _gov() -> Governance:
    return Governance(create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool))


def _offline() -> LLMSession:
    return LLMSession(mode="degraded", cache_dir=None)


@pytest.fixture(autouse=True)
def _fresh() -> None:
    pipeline.clear_cache()


def _n_sources() -> int:
    from app.agents.orchestrator import run_analysis

    sig = run_analysis("true_outbreak", seed=42).assessment("D3").signal
    assert sig is not None
    return sig.independent_sources


def _llm_hypotheses() -> dict[str, Any]:
    n = _n_sources()
    return {"hypotheses": [
        {"title": "Respiratory outbreak", "kind": "epidemic", "category": "infectious_respiratory",
         "probability": 0.8, "summary": "Multi-source rise.",
         "claims": [
             {"text": f"{n} sources agree.", "evidence_ids": ["SG-D3-resp"],
              "numbers": [{"evidence_id": "SG-D3-resp", "field": "independent_sources", "value": n}]},
             {"text": "A made-up lab report confirms it.", "evidence_ids": ["EV-FAKE-001"], "numbers": []},
             {"text": "Peak z is huge.", "evidence_ids": ["SG-D3-resp"],
              "numbers": [{"evidence_id": "SG-D3-resp", "field": "peak_z", "value": 99.0}]},
             {"text": "This warrants E3.", "evidence_ids": ["SG-D3-resp"], "numbers": []},
         ],
         "supporting_ids": ["SG-D3-resp", "EV-NOPE"], "contradicting_ids": []},
        {"title": "Holiday effect", "kind": "non_epidemic", "category": "holiday", "probability": 0.1,
         "summary": "Calendar.", "claims": [{"text": "Holiday check ruled out.", "evidence_ids": ["CF-D3-holiday"],
                                             "numbers": []}], "supporting_ids": [], "contradicting_ids": []},
        {"title": "Reporting artifact", "kind": "non_epidemic", "category": "reporting_change", "probability": 0.1,
         "summary": "Sites.", "claims": [{"text": "Invented.", "evidence_ids": ["CF-D9-x"], "numbers": []}],
         "supporting_ids": [], "contradicting_ids": []},
    ]}


def _online_responses() -> list[Any]:
    return [
        tool_msg(("lookup_evidence", {"ids": ["SG-D3-resp"]})),  # hypothesis: tool round
        text_msg(_llm_hypotheses()),  # hypothesis: final JSON
        text_msg({"unsupported": []}),  # verifier critic (fast model)
        tool_msg(("propose_action", {"action": "draft_public_advisory", "rationale": "E3 signal",
                                     "evidence_ids": ["SG-D3-resp"]}),
                 ("propose_action", {"action": "quarantine_households", "rationale": "x", "evidence_ids": []})),
    ]


# ---------------------------------------------------------------- verifier


def _evidence() -> dict[str, EvidenceItem]:
    return {"SG-D3-resp": EvidenceItem(id="SG-D3-resp", kind="signal", district="D3", summary="s",
                                       data={"independent_sources": 5, "explained_share": 0.92})}


@pytest.mark.parametrize("claim,ok", [
    (Claim(text="Five sources agree.", evidence_ids=["SG-D3-resp"],
           numbers=[NumberRef(evidence_id="SG-D3-resp", field="independent_sources", value=5)]), True),
    (Claim(text="92% explained.", evidence_ids=["SG-D3-resp"],
           numbers=[NumberRef(evidence_id="SG-D3-resp", field="explained_share", value=92)]), True),
    (Claim(text="No citation.", evidence_ids=[]), False),
    (Claim(text="Fake.", evidence_ids=["EV-FAKE"]), False),
    (Claim(text="Six sources.", evidence_ids=["SG-D3-resp"],
           numbers=[NumberRef(evidence_id="SG-D3-resp", field="independent_sources", value=6)]), False),
    (Claim(text="Unknown field.", evidence_ids=["SG-D3-resp"],
           numbers=[NumberRef(evidence_id="SG-D3-resp", field="r0", value=2.5)]), False),
    (Claim(text="Signal is E3.", evidence_ids=["SG-D3-resp"]), False),
    (Claim(text="Patient X has the infection.", evidence_ids=["SG-D3-resp"]), False),
])
def test_verifier_rules(claim: Claim, ok: bool) -> None:
    h = Hypothesis(title="t", kind="epidemic", category="noise", probability=1.0, summary="s", claims=[claim])
    _, report = verify([h], _evidence())
    assert (report.grounded_claims == 1) is ok


def test_hypothesis_with_no_grounded_claims_is_dropped() -> None:
    bad = Hypothesis(title="t", kind="epidemic", category="noise", probability=0.5, summary="s",
                     claims=[Claim(text="x", evidence_ids=["EV-FAKE"])])
    good = Hypothesis(title="g", kind="non_epidemic", category="noise", probability=0.5, summary="s",
                      claims=[Claim(text="ok", evidence_ids=["SG-D3-resp"])])
    kept, report = verify([bad, good], _evidence())
    assert [h.title for h in kept] == ["g"] and report.dropped_hypotheses == ["H1"]
    assert kept[0].probability == 1.0


# ---------------------------------------------------------------- offline (degraded) reasoning


def test_offline_holiday_ranks_non_epidemic_first() -> None:
    case = run_to_casefile(("holiday_spike",), 42, district="D3", session=_offline())
    assert case.usage.mode == "degraded"
    assert case.hypotheses[0].kind == "non_epidemic" and case.hypotheses[0].category == "holiday"
    assert case.verification.groundedness == 1.0


def test_offline_outbreak_keeps_alternatives() -> None:
    case = run_to_casefile(("true_outbreak",), 42, session=_offline())
    assert case.district == "D3"
    assert case.hypotheses[0].kind == "epidemic"
    assert any(h.kind == "non_epidemic" for h in case.hypotheses)
    assert case.verification.groundedness == 1.0
    assert {r.action for r in case.recommendations} >= {"increase_monitoring", "draft_public_advisory"}


def test_offline_recommendations_respect_tier() -> None:
    case = run_to_casefile(("lab_backlog",), 42, district="D3", session=_offline())
    assert case.assessment.gate.tier == "E1"
    assert {r.min_tier for r in case.recommendations} <= {"E1"}
    assert "request_data_validation" in {r.action for r in case.recommendations}


# ---------------------------------------------------------------- online path (fake client)


def test_online_path_verifies_and_constrains(tmp_path: Path) -> None:
    fake = FakeClient(_online_responses())
    session = LLMSession(client=fake, mode="online", cache_dir=tmp_path)
    case = run_to_casefile(("true_outbreak",), 42, session=session)
    assert case.usage.mode == "online" and case.usage.calls == 4
    v = case.verification
    assert v.total_claims == 6 and v.grounded_claims == 2
    reasons = " ".join(d.reason for d in v.dropped)
    assert "unknown evidence" in reasons and "numeric mismatch" in reasons and "tier" in reasons
    assert "H3" in v.dropped_hypotheses
    assert all("EV-NOPE" not in h.supporting_ids for h in case.hypotheses)
    assert [r.action for r in case.recommendations] == ["draft_public_advisory"]
    assert case.usage.cost_usd > 0 and case.usage.cache_read_tokens > 0
    first = fake.requests[0]
    assert first["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert first["tool_choice"] == {"type": "auto"} and first["tools"][0]["strict"] is True
    assert first["output_config"]["format"]["type"] == "json_schema"
    packet_text = first["messages"][0]["content"]
    assert "\"tier\"" not in packet_text and "criteria" not in packet_text  # LLM never sees the tier


def test_result_cache_avoids_repeat_calls(tmp_path: Path) -> None:
    run_to_casefile(("true_outbreak",), 42, session=LLMSession(client=FakeClient(_online_responses()), mode="online",
                                                               cache_dir=tmp_path))
    pipeline.clear_cache()
    fake = FakeClient([text_msg({"unsupported": []})])  # only the critic is not cached
    case = run_to_casefile(("true_outbreak",), 42, session=LLMSession(client=fake, mode="online", cache_dir=tmp_path))
    assert case.usage.cache_hits == 2 and case.usage.calls == 1
    assert case.verification.grounded_claims == 2


def test_connection_error_falls_back_to_degraded(tmp_path: Path) -> None:
    err = anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))
    session = LLMSession(client=FakeClient([err]), mode="online", cache_dir=tmp_path)
    case = run_to_casefile(("true_outbreak",), 42, session=session)
    assert case.usage.mode == "degraded" and case.usage.degraded_reason == "network unavailable"
    assert case.hypotheses and case.verification.groundedness == 1.0
    assert case.recommendations  # rule-based recommender still works


def test_unexpected_client_error_falls_back(tmp_path: Path) -> None:
    """The SDK raises TypeError (not an API error) when no credentials resolve."""
    session = LLMSession(client=FakeClient([TypeError("Could not resolve authentication method")]), mode="online",
                         cache_dir=tmp_path)
    case = run_to_casefile(("true_outbreak",), 42, session=session)
    assert case.usage.mode == "degraded" and case.usage.degraded_reason == "no API credentials (set ANTHROPIC_API_KEY)"
    assert case.hypotheses and case.recommendations


def test_call_budget_is_enforced(tmp_path: Path) -> None:
    session = LLMSession(client=FakeClient(_online_responses()), mode="online", cache_dir=tmp_path)
    session.budget = 1
    case = run_to_casefile(("true_outbreak",), 42, session=session)
    assert case.usage.calls == 1
    assert "budget" in (case.usage.degraded_reason or "")


def test_missing_key_means_degraded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("LLM_MODE", "auto")
    s = LLMSession(cache_dir=None)
    assert not s.online and s.usage.degraded_reason == "no ANTHROPIC_API_KEY configured"


# ---------------------------------------------------------------- pipeline + governance


def test_pipeline_streams_steps_in_order_and_queues_actions() -> None:
    gov = _gov()
    items = list(run_pipeline(("true_outbreak",), 42, gov=gov, session=_offline()))
    done = [i.step for i in items if isinstance(i, StepEvent) and i.status != "running"]
    assert tuple(done) == STEPS
    case = items[-1]
    assert isinstance(case, CaseFile)
    assert all(r.pending_ref for r in case.recommendations)
    assert {p.status for p in gov.list()} == {"pending"}  # nothing executed
    run_to_casefile(("true_outbreak",), 42, gov=gov, session=_offline())
    assert len(gov.list()) == len(case.recommendations)  # idempotent


def test_kill_switch_blocks_recommend_step() -> None:
    gov = _gov()
    gov.set_kill_switch(True, actor="officer", reason="drill")
    case = run_to_casefile(("true_outbreak",), 42, gov=gov, session=_offline())
    assert case.steps[-1].step == "Recommend" and case.steps[-1].status == "blocked"
    assert gov.list() == []
