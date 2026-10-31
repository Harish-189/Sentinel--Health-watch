"""Append-only, hash-chained audit log. There is deliberately no update or delete API."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.governance.store import AuditRow

GENESIS = "0" * 64


class AuditEntry(BaseModel):
    seq: int
    ts: str
    actor: str
    event: str
    subject: str
    payload: dict[str, Any]
    prev_hash: str
    hash: str


def _digest(prev: str, ts: str, actor: str, event: str, subject: str, payload_json: str) -> str:
    return hashlib.sha256("|".join((prev, ts, actor, event, subject, payload_json)).encode()).hexdigest()


class AuditLog:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def append(self, actor: str, event: str, subject: str, payload: dict[str, Any] | None = None,
               session: Session | None = None) -> None:
        own = session is None
        s = session or Session(self.engine)
        try:
            last = s.scalars(select(AuditRow).order_by(AuditRow.seq.desc()).limit(1)).first()
            prev = last.hash if last else GENESIS
            ts = datetime.now(UTC).isoformat(timespec="milliseconds")
            body = json.dumps(payload or {}, sort_keys=True, default=str)
            s.add(AuditRow(ts=ts, actor=actor, event=event, subject=subject, payload_json=body, prev_hash=prev,
                           hash=_digest(prev, ts, actor, event, subject, body)))
            if own:
                s.commit()
            else:
                s.flush()
        finally:
            if own:
                s.close()

    def list(self, limit: int | None = None) -> list[AuditEntry]:
        with Session(self.engine) as s:
            stmt = select(AuditRow).order_by(AuditRow.seq)
            rows = s.scalars(stmt).all()
        entries = [AuditEntry(seq=r.seq, ts=r.ts, actor=r.actor, event=r.event, subject=r.subject,
                              payload=json.loads(r.payload_json), prev_hash=r.prev_hash, hash=r.hash) for r in rows]
        return entries[-limit:] if limit else entries

    def verify_chain(self) -> bool:
        prev = GENESIS
        with Session(self.engine) as s:
            for r in s.scalars(select(AuditRow).order_by(AuditRow.seq)):
                if r.prev_hash != prev or r.hash != _digest(prev, r.ts, r.actor, r.event, r.subject, r.payload_json):
                    return False
                prev = r.hash
        return True
