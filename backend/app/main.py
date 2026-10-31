"""Sentinel API."""

from __future__ import annotations

import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.agents.llm import LLMSession, models, resolve_mode
from app.agents.orchestrator import run_analysis
from app.agents.pipeline import run_pipeline, run_to_casefile
from app.agents.schemas import CaseFile
from app.agents.timeline import Timeline, build_timeline
from app.agents.tools import CATALOG
from app.analysis.forecast import forecast_capacity
from app.analysis.models import AnalysisBundle, Forecast
from app.config import get_settings
from app.data.districts import DISTRICTS, neighbors
from app.data.privacy import apply_privacy
from app.data.scenarios import CORE_SCENARIOS, OVERLAYS, simulate
from app.detection.models import Anomaly, SeriesDetection
from app.detection.run import DetectionReport, detect_all
from app.governance.approvals import Governance, GovernanceError, KillSwitchEngaged, PendingAction
from app.governance.audit import AuditEntry
from app.governance.store import default_gov_engine

DEMO_SEED = get_settings().simulation.demo_seed
GOV = Governance(default_gov_engine())


def _warm() -> None:
    """Precompute the default demo so the first page load is instant."""
    scenario = ("true_outbreak",)
    run_analysis(scenario, seed=DEMO_SEED)
    _detection(scenario, DEMO_SEED, None)
    run_to_casefile(scenario, DEMO_SEED)
    build_timeline(scenario, DEMO_SEED)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    threading.Thread(target=_warm, daemon=True).start()
    yield


app = FastAPI(title="Sentinel", version="0.3.0", lifespan=lifespan)


def _scenario(name: str) -> tuple[str, ...]:
    parts = tuple(p for p in name.split("+") if p)
    if not parts or any(p not in OVERLAYS for p in parts):
        raise HTTPException(404, f"unknown scenario: {name}")
    return parts


@lru_cache(maxsize=16)
def _detection(scenario: tuple[str, ...], seed: int, as_of: int | None) -> DetectionReport:
    sim = simulate(list(scenario), seed=seed)
    return detect_all(apply_privacy(sim.df), holidays=sim.holidays, as_of=as_of)


# ------------------------------------------------------------------ read APIs


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "kill_switch": GOV.kill_switch_engaged()}


@app.get("/api/districts")
def districts() -> list[dict[str, object]]:
    return [
        {"code": d.code, "name": d.name, "population": d.population, "q": d.q, "r": d.r,
         "neighbors": sorted(neighbors(d.code))}
        for d in DISTRICTS
    ]


@app.get("/api/scenarios")
def scenarios() -> list[dict[str, object]]:
    return [
        {"name": o.name, "core": o.name in CORE_SCENARIOS, "is_epidemic": o.is_epidemic,
         "description": o.description}
        for o in OVERLAYS.values()
    ]


@app.get("/api/detect")
def detect(scenario: str = "true_outbreak", seed: int = DEMO_SEED, as_of: int | None = None) -> DetectionReport:
    return _detection(_scenario(scenario), seed, as_of)


class SeriesResponse(BaseModel):
    district: str
    as_of: int
    as_of_date: str
    series: list[SeriesDetection]
    anomalies: list[Anomaly]


@app.get("/api/series")
def series(district: str = "D3", scenario: str = "true_outbreak", seed: int = DEMO_SEED,
           as_of: int | None = None) -> SeriesResponse:
    rep = _detection(_scenario(scenario), seed, as_of)
    return SeriesResponse(district=district, as_of=rep.as_of, as_of_date=rep.as_of_date,
                          series=[s for s in rep.series if s.district == district],
                          anomalies=rep.anomalies_for(district))


@app.get("/api/timeline")
def timeline(scenario: str = "true_outbreak", seed: int = DEMO_SEED) -> Timeline:
    return build_timeline(_scenario(scenario), seed)


@app.get("/api/analysis")
def analysis(scenario: str = "true_outbreak", seed: int = DEMO_SEED, as_of: int | None = None) -> AnalysisBundle:
    return run_analysis(_scenario(scenario), seed=seed, as_of=as_of)


@app.get("/api/forecast")
def forecast(district: str = "D3", scenario: str = "true_outbreak", seed: int = DEMO_SEED, as_of: int | None = None,
             intervention: bool = False) -> Forecast:
    bundle = run_analysis(_scenario(scenario), seed=seed, as_of=as_of)
    if not intervention:
        return bundle.assessment(district).forecast
    return forecast_capacity(bundle.context, district, intervention=True)


@app.get("/api/system")
def system() -> dict[str, Any]:
    mode, reason = resolve_mode()
    model, fast = models()
    return {"llm_mode": mode, "degraded_reason": reason, "model": model, "fast_model": fast,
            "kill_switch": GOV.kill_switch_engaged()}


@app.get("/api/casefile")
def casefile(scenario: str = "true_outbreak", seed: int = DEMO_SEED, as_of: int | None = None,
             district: str | None = None) -> CaseFile:
    return run_to_casefile(_scenario(scenario), seed, as_of, district, gov=GOV)


@app.get("/api/analyze/stream")
def analyze_stream(scenario: str = "true_outbreak", seed: int = DEMO_SEED, as_of: int | None = None,
                   district: str | None = None, pace_ms: float = 350.0) -> StreamingResponse:
    names = _scenario(scenario)

    def events() -> Any:
        for item in run_pipeline(names, seed, as_of, district, gov=GOV, session=LLMSession(), pace_ms=pace_ms):
            kind = "casefile" if isinstance(item, CaseFile) else "step"
            yield f"event: {kind}\ndata: {item.model_dump_json()}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/catalog")
def catalog() -> list[dict[str, str]]:
    return [{"name": a.name, "title": a.title, "min_tier": a.min_tier, "system": a.system,
             "description": a.description} for a in CATALOG.values()]


# ------------------------------------------------------------------ governance


class ProposeBody(BaseModel):
    action: str
    district: str
    scenario: str = "true_outbreak"
    seed: int = DEMO_SEED
    as_of: int | None = None
    rationale: str = ""
    evidence_ids: list[str] = Field(default_factory=list)
    params: dict[str, Any] = Field(default_factory=dict)
    proposed_by: str = "officer"


class DecisionBody(BaseModel):
    actor: str = "officer"
    reason: str = ""
    params: dict[str, Any] | None = None
    rationale: str | None = None


class KillBody(BaseModel):
    engaged: bool
    actor: str = "officer"
    reason: str = ""


def _gov_call(fn: Any, *args: Any, **kwargs: Any) -> Any:
    try:
        return fn(*args, **kwargs)
    except KillSwitchEngaged as e:
        raise HTTPException(423, str(e)) from e
    except GovernanceError as e:
        raise HTTPException(400, str(e)) from e


@app.get("/api/actions")
def list_actions(status: str | None = None) -> list[PendingAction]:
    return GOV.list(status)


@app.post("/api/actions")
def propose_action(body: ProposeBody) -> PendingAction:
    # The tier is recomputed server-side; a client cannot claim a higher tier.
    bundle = run_analysis(_scenario(body.scenario), seed=body.seed, as_of=body.as_of)
    tier = bundle.assessment(body.district).gate.tier
    unknown = [e for e in body.evidence_ids if e not in bundle.evidence]
    if unknown:
        raise HTTPException(400, f"unknown evidence ids: {unknown}")
    return _gov_call(GOV.propose, body.action, body.district, tier, body.rationale, body.evidence_ids,
                     body.params, body.proposed_by)


@app.post("/api/actions/{ref}/approve")
def approve_action(ref: str, body: DecisionBody) -> PendingAction:
    return _gov_call(GOV.approve, ref, body.actor)


@app.post("/api/actions/{ref}/edit")
def edit_action(ref: str, body: DecisionBody) -> PendingAction:
    return _gov_call(GOV.edit, ref, body.actor, body.params, body.rationale)


@app.post("/api/actions/{ref}/reject")
def reject_action(ref: str, body: DecisionBody) -> PendingAction:
    return _gov_call(GOV.reject, ref, body.actor, body.reason)


@app.get("/api/audit")
def audit(limit: int | None = None) -> dict[str, Any]:
    entries: list[AuditEntry] = GOV.audit.list(limit)
    return {"verified": GOV.audit.verify_chain(), "entries": entries}


@app.get("/api/killswitch")
def get_kill_switch() -> dict[str, bool]:
    return {"engaged": GOV.kill_switch_engaged()}


@app.post("/api/killswitch")
def set_kill_switch(body: KillBody) -> dict[str, bool]:
    if not body.reason.strip():
        raise HTTPException(400, "a reason is required")
    GOV.set_kill_switch(body.engaged, body.actor, body.reason)
    return {"engaged": GOV.kill_switch_engaged()}
