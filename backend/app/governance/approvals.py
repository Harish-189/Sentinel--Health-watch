"""Human gate: every action is a PendingAction until a human approves, edits or rejects it."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.agents.tools import CATALOG, execute
from app.analysis.models import TIERS, tier_at_least
from app.data.privacy import is_pii_name
from app.governance.audit import AuditLog
from app.governance.store import ActionRow, ControlRow, GovBase

KILL_KEY = "kill_switch"


class GovernanceError(ValueError):
    pass


class KillSwitchEngaged(GovernanceError):
    pass


class PendingAction(BaseModel):
    ref: str
    action: str
    title: str
    district: str
    signal_tier: str
    min_tier: str
    status: str  # pending | executed | rejected
    params: dict[str, Any]
    rationale: str
    evidence_ids: list[str]
    proposed_by: str
    decided_by: str | None
    decision_reason: str | None
    receipt: dict[str, Any] | None
    created_at: str
    updated_at: str


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _out(r: ActionRow) -> PendingAction:
    return PendingAction(
        ref=r.ref, action=r.action, title=CATALOG[r.action].title, district=r.district, signal_tier=r.signal_tier,
        min_tier=r.min_tier, status=r.status, params=json.loads(r.params_json), rationale=r.rationale,
        evidence_ids=json.loads(r.evidence_json), proposed_by=r.proposed_by, decided_by=r.decided_by,
        decision_reason=r.decision_reason, receipt=json.loads(r.receipt_json) if r.receipt_json else None,
        created_at=r.created_at, updated_at=r.updated_at,
    )


def _check_params(params: dict[str, Any]) -> None:
    bad = [k for k in params if is_pii_name(k)]
    if bad:
        raise GovernanceError(f"person-level parameters are not allowed: {bad}")


class Governance:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        GovBase.metadata.create_all(engine)
        self.audit = AuditLog(engine)

    # ------------------------------------------------------------- kill switch
    def kill_switch_engaged(self) -> bool:
        with Session(self.engine) as s:
            row = s.get(ControlRow, KILL_KEY)
            return row is not None and row.value == "on"

    def set_kill_switch(self, engaged: bool, actor: str, reason: str) -> None:
        with Session(self.engine) as s:
            row = s.get(ControlRow, KILL_KEY) or ControlRow(key=KILL_KEY, value="off")
            row.value = "on" if engaged else "off"
            s.merge(row)
            self.audit.append(actor, "kill_switch_engaged" if engaged else "kill_switch_released", KILL_KEY,
                              {"reason": reason}, session=s)
            s.commit()

    def _guard(self) -> None:
        if self.kill_switch_engaged():
            raise KillSwitchEngaged("kill switch engaged: no actions may be proposed or executed")

    # ------------------------------------------------------------- lifecycle
    def propose(self, action: str, district: str, signal_tier: str, rationale: str, evidence_ids: list[str],
                params: dict[str, Any] | None = None, proposed_by: str = "recommender") -> PendingAction:
        self._guard()
        spec = CATALOG.get(action)
        if spec is None:
            raise GovernanceError(f"unknown action '{action}': only catalog actions are allowed")
        if signal_tier not in TIERS or not tier_at_least(signal_tier, spec.min_tier):
            raise GovernanceError(f"{action} requires tier {spec.min_tier}; signal is {signal_tier}")
        params = params or {}
        _check_params(params)
        with Session(self.engine) as s:
            n = s.scalar(select(func.count()).select_from(ActionRow)) or 0
            now = _now()
            row = ActionRow(ref=f"ACT-{n + 1:04d}", action=action, district=district, signal_tier=signal_tier,
                            min_tier=spec.min_tier, status="pending", params_json=json.dumps(params),
                            rationale=rationale, evidence_json=json.dumps(evidence_ids), proposed_by=proposed_by,
                            created_at=now, updated_at=now)
            s.add(row)
            self.audit.append(proposed_by, "action_proposed", row.ref,
                              {"action": action, "district": district, "tier": signal_tier,
                               "evidence_ids": evidence_ids}, session=s)
            s.commit()
            return _out(row)

    def get(self, ref: str) -> PendingAction:
        with Session(self.engine) as s:
            return _out(self._row(s, ref))

    def list(self, status: str | None = None) -> list[PendingAction]:
        with Session(self.engine) as s:
            stmt = select(ActionRow).order_by(ActionRow.ref)
            if status:
                stmt = stmt.where(ActionRow.status == status)
            return [_out(r) for r in s.scalars(stmt)]

    @staticmethod
    def _row(s: Session, ref: str, pending: bool = False) -> ActionRow:
        row = s.get(ActionRow, ref)
        if row is None:
            raise GovernanceError(f"no such action: {ref}")
        if pending and row.status != "pending":
            raise GovernanceError(f"{ref} is already {row.status}")
        return row

    def approve(self, ref: str, actor: str) -> PendingAction:
        self._guard()
        with Session(self.engine) as s:
            row = self._row(s, ref, pending=True)
            self.audit.append(actor, "action_approved", ref, {"action": row.action}, session=s)
            receipt = execute(CATALOG[row.action], ref, row.district, json.loads(row.params_json))
            row.status, row.decided_by, row.receipt_json = "executed", actor, json.dumps(receipt)
            row.updated_at = _now()
            self.audit.append("system", "action_executed", ref, {"ticket": receipt["ticket"]}, session=s)
            s.commit()
            return _out(row)

    def edit(self, ref: str, actor: str, params: dict[str, Any] | None = None,
             rationale: str | None = None) -> PendingAction:
        with Session(self.engine) as s:
            row = self._row(s, ref, pending=True)
            if params:
                _check_params(params)
                row.params_json = json.dumps({**json.loads(row.params_json), **params})
            if rationale is not None:
                row.rationale = rationale
            row.updated_at = _now()
            self.audit.append(actor, "action_edited", ref, {"params": params or {}, "rationale": rationale},
                              session=s)
            s.commit()
            return _out(row)

    def reject(self, ref: str, actor: str, reason: str) -> PendingAction:
        if not reason or not reason.strip():
            raise GovernanceError("a reason is required to reject an action")
        with Session(self.engine) as s:
            row = self._row(s, ref, pending=True)
            row.status, row.decided_by, row.decision_reason, row.updated_at = "rejected", actor, reason.strip(), _now()
            self.audit.append(actor, "action_rejected", ref, {"reason": reason.strip()}, session=s)
            s.commit()
            return _out(row)

    def reset(self, actor: str) -> None:
        """Demo reset: clears actions and releases the kill switch. The audit log is kept (append-only)."""
        with Session(self.engine) as s:
            s.query(ActionRow).delete()
            s.query(ControlRow).delete()
            self.audit.append(actor, "demo_reset", "system", {}, session=s)
            s.commit()
