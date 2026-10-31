"""Action catalog (SPEC 9) and simulated enterprise executors. Nothing here targets a person."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from app.analysis.models import TIERS, tier_at_least


@dataclass(frozen=True)
class ActionSpec:
    name: str
    title: str
    min_tier: str
    executes_as: str
    system: str
    target: Literal["system", "population"]
    description: str


CATALOG: dict[str, ActionSpec] = {
    a.name: a
    for a in (
        ActionSpec("request_data_validation", "Request data validation", "E1", "ticket", "Data Steward Desk",
                   "system", "Ask the data steward to verify feeds, site lists and recent schema changes."),
        ActionSpec("increase_monitoring", "Increase monitoring", "E1", "config", "Surveillance Watchlist",
                   "system", "Add the district and syndrome to the daily watchlist with tighter thresholds."),
        ActionSpec("request_lab_sampling", "Request lab sampling", "E2", "lab_request", "Public Health Lab",
                   "system", "Request targeted aggregate sampling on the relevant pathogen panel."),
        ActionSpec("draft_clinician_advisory", "Draft clinician advisory", "E2", "draft", "Clinical Comms",
                   "population", "Draft (not send) an advisory to clinicians; a human edits and publishes."),
        ActionSpec("prepose_capacity", "Pre-position capacity", "E3", "capacity_plan", "Hospital Capacity Office",
                   "system", "Simulated plan to pre-position staff and beds in the hospital zone."),
        ActionSpec("draft_public_advisory", "Draft public advisory", "E3", "draft", "Public Comms",
                   "population", "Draft (not publish) a population-level advisory; a human edits and publishes."),
    )
}


def allowed_actions(tier: str) -> list[ActionSpec]:
    return [a for a in CATALOG.values() if tier_at_least(tier, a.min_tier)]


def ticket_for(ref: str, action: str) -> str:
    return "TKT-" + hashlib.sha1(f"{ref}:{action}".encode()).hexdigest()[:6].upper()


def _draft(spec: ActionSpec, district: str, params: dict[str, Any]) -> str:
    text = params.get("text")
    if isinstance(text, str) and text.strip():
        return text
    audience = "clinicians" if spec.name == "draft_clinician_advisory" else "residents"
    return (f"DRAFT for {audience} in {district}: aggregate surveillance shows elevated "
            f"{params.get('syndrome', 'respiratory')} activity. Follow standard guidance. "
            "Population-level notice only; no individual is identified.")


def execute(spec: ActionSpec, ref: str, district: str, params: dict[str, Any]) -> dict[str, Any]:
    """Simulated execution. Returns a receipt; no external system is contacted."""
    assert spec.min_tier in TIERS
    receipt: dict[str, Any] = {
        "ticket": ticket_for(ref, spec.name),
        "system": spec.system,
        "executes_as": spec.executes_as,
        "district": district,
        "executed_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "simulated": True,
    }
    if spec.executes_as == "draft":
        receipt["draft"] = _draft(spec, district, params)
        receipt["summary"] = "Draft saved for human editing; nothing was published."
    elif spec.executes_as == "capacity_plan":
        beds = int(params.get("beds", 12))
        receipt["plan"] = {"beds": beds, "staff_shifts": int(params.get("staff_shifts", beds // 2))}
        receipt["summary"] = f"Capacity plan filed: +{beds} surge beds in {district} hospital zone."
    elif spec.executes_as == "lab_request":
        receipt["summary"] = f"Lab sampling request filed for {params.get('panel', 'panel_A')} in {district}."
    elif spec.executes_as == "config":
        receipt["summary"] = f"{district} added to the daily watchlist."
    else:
        receipt["summary"] = f"Validation ticket opened with {spec.system} for {district}."
    return receipt
