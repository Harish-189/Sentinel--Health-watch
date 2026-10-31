"""Compact evidence JSON for the LLM. Never raw series, never person-level fields, size-capped."""

from __future__ import annotations

import json
from typing import Any

from app.analysis.models import ConfounderResult, EvidenceItem, Signal

MAX_PACKET_CHARS = 14_000
MAX_ITEMS = 40


def build_packet(district: str, district_name: str, as_of_date: str, sig: Signal | None,
                 confounders: list[ConfounderResult], evidence: dict[str, EvidenceItem]) -> dict[str, Any]:
    items = [e for e in evidence.values() if e.district == district and e.kind in ("anomaly", "signal", "confounder")]
    if sig is not None:
        items += [evidence[i] for i in sig.adjacent_evidence if i in evidence]
        items += [e for e in evidence.values() if e.kind == "calendar"
                  and sig.first_day - 10 <= int(e.data.get("day", -999)) <= sig.last_day + 3]
    items = sorted({e.id: e for e in items}.values(), key=lambda e: e.id)[:MAX_ITEMS]
    packet: dict[str, Any] = {
        "district": district,
        "district_label": district_name,
        "as_of": as_of_date,
        "signal": None if sig is None else {
            "signal_ref": sig.signal_id, "syndrome": sig.syndrome, "sources": sig.sources,
            "independent_sources": sig.independent_sources, "onset_by_source_day": sig.onset_by_source,
            "lag_consistency": sig.lag_consistency, "mean_z": sig.mean_z, "peak_z": sig.peak_z,
            "mean_excess": sig.mean_excess, "persistence_days": sig.persistence_days,
            "adjacent_districts": sig.adjacent_districts,
            "lead_lag": [ll.model_dump() for ll in sig.lead_lag],
        },
        "alternative_explanation_checks": [
            {"evidence_id": c.confounder_id, "check": c.name, "status": c.status, "explained_share": c.explained_share,
             "summary": c.summary, "values": c.values}
            for c in confounders
        ],
        "evidence": [{"evidence_id": e.id, "kind": e.kind, "summary": e.summary} for e in items],
    }
    size = len(json.dumps(packet, default=str))
    while size > MAX_PACKET_CHARS and packet["evidence"]:
        packet["evidence"].pop()
        size = len(json.dumps(packet, default=str))
    return packet
