import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from app.agents.tools import CATALOG
from app.data.privacy import is_pii_name
from app.governance.approvals import Governance, GovernanceError, KillSwitchEngaged
from app.governance.store import GovBase


@pytest.fixture()
def gov() -> Governance:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    return Governance(engine)


def _propose(gov: Governance, action: str = "request_lab_sampling", tier: str = "E2") -> str:
    p = gov.propose(action, district="ERD", signal_tier=tier, rationale="test", evidence_ids=["EV-x"],
                    params={"panel": "panel_A"}, proposed_by="recommender")
    return p.ref


def test_nothing_executes_without_approval(gov: Governance) -> None:
    ref = _propose(gov)
    pending = gov.get(ref)
    assert pending.status == "pending" and pending.receipt is None
    done = gov.approve(ref, actor="officer")
    assert done.status == "executed" and done.receipt is not None
    assert done.receipt["ticket"].startswith("TKT-")


def test_tier_gating(gov: Governance) -> None:
    with pytest.raises(GovernanceError):
        _propose(gov, "draft_public_advisory", tier="E2")
    with pytest.raises(GovernanceError):
        _propose(gov, "request_lab_sampling", tier="E1")
    _propose(gov, "increase_monitoring", tier="E1")


def test_unknown_action_rejected(gov: Governance) -> None:
    with pytest.raises(GovernanceError):
        _propose(gov, "quarantine_household", tier="E3")


def test_reject_requires_reason(gov: Governance) -> None:
    ref = _propose(gov)
    with pytest.raises(GovernanceError):
        gov.reject(ref, actor="officer", reason=" ")
    assert gov.reject(ref, actor="officer", reason="lab already sampling").status == "rejected"
    with pytest.raises(GovernanceError):
        gov.approve(ref, actor="officer")


def test_edit_then_approve(gov: Governance) -> None:
    ref = _propose(gov, "draft_clinician_advisory")
    edited = gov.edit(ref, actor="officer", params={"text": "Reviewed wording"})
    assert edited.params["text"] == "Reviewed wording" and edited.status == "pending"
    assert gov.approve(ref, actor="officer").status == "executed"


def test_person_level_params_rejected(gov: Governance) -> None:
    with pytest.raises(GovernanceError):
        gov.propose("increase_monitoring", district="ERD", signal_tier="E1", rationale="x", evidence_ids=[],
                    params={"patient_name": "x"}, proposed_by="recommender")


def test_audit_chain_and_tamper_detection(gov: Governance) -> None:
    ref = _propose(gov)
    gov.approve(ref, actor="officer")
    events = [e.event for e in gov.audit.list()]
    assert events == ["action_proposed", "action_approved", "action_executed"]
    assert gov.audit.verify_chain()
    with gov.engine.begin() as conn:
        conn.execute(text("UPDATE audit_log SET actor = 'mallory' WHERE seq = 1"))
    assert not gov.audit.verify_chain()


def test_kill_switch_blocks_and_is_audited(gov: Governance) -> None:
    ref = _propose(gov)
    gov.set_kill_switch(True, actor="officer", reason="drill")
    assert gov.kill_switch_engaged()
    with pytest.raises(KillSwitchEngaged):
        gov.approve(ref, actor="officer")
    with pytest.raises(KillSwitchEngaged):
        _propose(gov)
    gov.set_kill_switch(False, actor="officer", reason="drill over")
    assert gov.approve(ref, actor="officer").status == "executed"
    assert "kill_switch_engaged" in [e.event for e in gov.audit.list()]


def test_catalog_matches_spec_and_targets_no_person() -> None:
    assert {a.name: a.min_tier for a in CATALOG.values()} == {
        "request_data_validation": "E1",
        "increase_monitoring": "E1",
        "request_lab_sampling": "E2",
        "draft_clinician_advisory": "E2",
        "prepose_capacity": "E3",
        "draft_public_advisory": "E3",
    }
    assert all(a.target in ("system", "population") for a in CATALOG.values())


def test_governance_schema_has_no_pii_columns() -> None:
    for table in GovBase.metadata.tables.values():
        for column in table.columns:
            assert not is_pii_name(column.name), f"{table.name}.{column.name}"
