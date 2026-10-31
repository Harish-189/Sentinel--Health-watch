"""Governance tables: pending actions, append-only audit log, controls (kill switch)."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

GOV_DB = Path(__file__).resolve().parents[2] / "data" / "generated" / "governance.db"


class GovBase(DeclarativeBase):
    pass


class ActionRow(GovBase):
    __tablename__ = "pending_actions"

    ref: Mapped[str] = mapped_column(String(16), primary_key=True)
    action: Mapped[str] = mapped_column(String(48))
    district: Mapped[str] = mapped_column(String(8))
    signal_tier: Mapped[str] = mapped_column(String(2))
    min_tier: Mapped[str] = mapped_column(String(2))
    status: Mapped[str] = mapped_column(String(16))
    params_json: Mapped[str] = mapped_column(Text, default="{}")
    rationale: Mapped[str] = mapped_column(Text, default="")
    evidence_json: Mapped[str] = mapped_column(Text, default="[]")
    proposed_by: Mapped[str] = mapped_column(String(32))
    decided_by: Mapped[str | None] = mapped_column(String(32), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    receipt_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String(32))
    updated_at: Mapped[str] = mapped_column(String(32))


class AuditRow(GovBase):
    __tablename__ = "audit_log"

    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[str] = mapped_column(String(32))
    actor: Mapped[str] = mapped_column(String(32))
    event: Mapped[str] = mapped_column(String(48))
    subject: Mapped[str] = mapped_column(String(32))
    payload_json: Mapped[str] = mapped_column(Text)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))


class ControlRow(GovBase):
    __tablename__ = "controls"

    key: Mapped[str] = mapped_column(String(32), primary_key=True)
    value: Mapped[str] = mapped_column(String(64))


def default_gov_engine() -> Engine:
    GOV_DB.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite:///{GOV_DB}", connect_args={"check_same_thread": False})
