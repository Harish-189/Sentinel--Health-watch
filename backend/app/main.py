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

from app.agents.lab import EvidenceDelta, evidence_delta
from app.agents.llm import LLMSession, models, resolve_mode
from app.agents.orchestrator import detect_step, run_analysis
from app.agents.pipeline import clear_cache as clear_casefiles
from app.agents.pipeline import run_pipeline, run_to_casefile
from app.agents.schemas import CaseFile
from app.agents.timeline import Timeline, build_timeline
from app.agents.tools import CATALOG
from app.analysis.forecast import forecast_capacity
from app.analysis.models import AnalysisBundle, Forecast
from app.config import get_settings
from app.data.districts import DISTRICTS, neighbors
from app.data.privacy import PIIViolation
from app.data.scenarios import CORE_SCENARIOS, OVERLAYS, simulate
from app.data.uploads import PREFIX, UploadError, parse_upload, register
from app.data.uploads import known as known_upload
from app.detection.models import Anomaly, SeriesDetection
from app.detection.run import DetectionReport
from app.eval import harness
from app.governance.approvals import Governance, GovernanceError, KillSwitchEngaged, PendingAction
from app.governance.audit import AuditEntry
from app.governance.store import default_gov_engine

DEMO_SEED = get_settings().simulation.demo_seed
PRIMARY = get_settings().simulation.default_primary
DEMO_SCENARIO = "+".join(get_settings().simulation.demo_scenario)
GOV = Governance(default_gov_engine())


def _warm() -> None:
    """Precompute the default demo so the first page load is instant."""
    scenario = _scenario(DEMO_SCENARIO)
    run_analysis(scenario, seed=DEMO_SEED)
    _detection(scenario, DEMO_SEED, None)
    run_to_casefile(scenario, DEMO_SEED)
    build_timeline(scenario, DEMO_SEED)
    if harness.load_report() is None:  # precompute the evaluation report once (cached on disk afterwards)
        _start_eval(100)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    threading.Thread(target=_warm, daemon=True).start()
    yield


app = FastAPI(title="Sentinel", version="0.3.0", lifespan=lifespan)


def _scenario(name: str) -> tuple[str, ...]:
    parts = tuple(p for p in name.split("+") if p)
    if not parts or any(p not in OVERLAYS and not known_upload(p) for p in parts):
        raise HTTPException(404, f"unknown scenario: {name}")
    return parts


@lru_cache(maxsize=16)
def _detection(scenario: tuple[str, ...], seed: int, as_of: int | None) -> DetectionReport:
    return detect_step(scenario, seed, as_of).report


# ------------------------------------------------------------------ read APIs


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "kill_switch": GOV.kill_switch_engaged()}


@app.get("/api/districts")
def districts() -> list[dict[str, object]]:
    return [
        {"code": d.code, "name": d.name, "population": d.population, "lat": d.lat, "lon": d.lon,
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
def detect(scenario: str = DEMO_SCENARIO, seed: int = DEMO_SEED, as_of: int | None = None) -> DetectionReport:
    return _detection(_scenario(scenario), seed, as_of)


class SeriesResponse(BaseModel):
    district: str
    as_of: int
    as_of_date: str
    series: list[SeriesDetection]
    anomalies: list[Anomaly]


@app.get("/api/series")
def series(district: str = PRIMARY, scenario: str = DEMO_SCENARIO, seed: int = DEMO_SEED,
           as_of: int | None = None) -> SeriesResponse:
    rep = _detection(_scenario(scenario), seed, as_of)
    return SeriesResponse(district=district, as_of=rep.as_of, as_of_date=rep.as_of_date,
                          series=[s for s in rep.series if s.district == district],
                          anomalies=rep.anomalies_for(district))


@app.get("/api/timeline")
def timeline(scenario: str = DEMO_SCENARIO, seed: int = DEMO_SEED) -> Timeline:
    return build_timeline(_scenario(scenario), seed)


@app.get("/api/analysis")
def analysis(scenario: str = DEMO_SCENARIO, seed: int = DEMO_SEED, as_of: int | None = None) -> AnalysisBundle:
    return run_analysis(_scenario(scenario), seed=seed, as_of=as_of)


@app.get("/api/forecast")
def forecast(district: str = PRIMARY, scenario: str = DEMO_SCENARIO, seed: int = DEMO_SEED, as_of: int | None = None,
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
            "kill_switch": GOV.kill_switch_engaged(), "demo_scenario": DEMO_SCENARIO, "demo_seed": DEMO_SEED,
            "default_district": PRIMARY}


@app.get("/api/casefile")
def casefile(scenario: str = DEMO_SCENARIO, seed: int = DEMO_SEED, as_of: int | None = None,
             district: str | None = None) -> CaseFile:
    return run_to_casefile(_scenario(scenario), seed, as_of, district, gov=GOV)


@app.get("/api/analyze/stream")
def analyze_stream(scenario: str = DEMO_SCENARIO, seed: int = DEMO_SEED, as_of: int | None = None,
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
    scenario: str = DEMO_SCENARIO
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


# ------------------------------------------------------------------ scenario lab


class InjectBody(BaseModel):
    inject: str
    base: str = DEMO_SCENARIO
    seed: int = DEMO_SEED
    district: str | None = None


@app.post("/api/scenario/inject")
def scenario_inject(body: InjectBody) -> EvidenceDelta:
    base = _scenario(body.base)
    if body.inject not in OVERLAYS and not known_upload(body.inject):
        raise HTTPException(404, f"unknown scenario: {body.inject}")
    if body.inject in base:
        raise HTTPException(400, f"{body.inject} is already part of the base scenario")
    return evidence_delta(base, body.inject, body.seed, body.district)


class UploadBody(BaseModel):
    csv: str = Field(max_length=2_000_000)
    base: str = DEMO_SCENARIO
    seed: int = DEMO_SEED


@app.post("/api/data/upload")
def data_upload(body: UploadBody) -> dict[str, Any]:
    base = _scenario(body.base)
    try:
        df = parse_upload(body.csv)
    except PIIViolation as e:  # privacy-by-design: person-level fields never get in
        raise HTTPException(422, str(e)) from e
    except UploadError as e:
        raise HTTPException(400, str(e)) from e
    token = PREFIX + register(df)
    return {"upload": token, "rows": len(df), "delta": evidence_delta(base, token, body.seed)}


@app.get("/api/data/sample")
def data_sample(seed: int = DEMO_SEED) -> dict[str, str]:
    """An example upload: a gastrointestinal bump in Tiruchirappalli over the last 2 weeks (aggregates only)."""
    df = simulate(list(_scenario(DEMO_SCENARIO)), seed=seed).df
    rows = ["day,district,source,metric,value"]
    for (src, metric), factor in {("clinic", "gastrointestinal"): 2.4, ("pharmacy", "ors_rehydration"): 2.2,
                                  ("absenteeism", "school_rate"): 1.6}.items():
        sel = df[(df.district == "TRY") & (df.source == src) & (df.metric == metric) & (df.day >= 714)]
        for _, r in sel.iterrows():
            ramp = min(1.0, (r.day - 713) / 5)
            val = r.value * (1 + (factor - 1) * ramp)
            rows.append(f"{r.day},TRY,{src},{metric},{round(val, 2) if metric.endswith('rate') else round(val)}")
    return {"filename": "tiruchirappalli_gi_cluster.csv", "csv": "\n".join(rows) + "\n"}


# ------------------------------------------------------------------ evaluation

_EVAL: dict[str, Any] = {"running": False, "done": 0, "total": 0, "error": None}


@app.get("/api/eval/report")
def eval_report() -> dict[str, Any]:
    rep = harness.load_report()
    if rep is None:
        raise HTTPException(404, "no evaluation report yet: run the harness")
    return rep


@app.get("/api/eval/status")
def eval_status() -> dict[str, Any]:
    return dict(_EVAL)


class EvalBody(BaseModel):
    runs: int = Field(default=100, ge=8, le=400)


@app.post("/api/eval/run")
def eval_run(body: EvalBody) -> dict[str, Any]:
    if _EVAL["running"]:
        raise HTTPException(409, "an evaluation is already running")
    _start_eval(body.runs)
    return dict(_EVAL)


def _start_eval(runs: int) -> None:
    _EVAL.update(running=True, done=0, total=runs, error=None)

    def work() -> None:
        try:
            harness.evaluate(runs, progress=lambda k, n: _EVAL.update(done=k, total=n))
        except Exception as e:  # surface failures to the UI instead of dying silently
            _EVAL["error"] = f"{type(e).__name__}: {e}"
        finally:
            _EVAL["running"] = False

    threading.Thread(target=work, daemon=True).start()


# ------------------------------------------------------------------ demo reset


class ResetBody(BaseModel):
    actor: str = "officer"


@app.post("/api/demo-reset")
def demo_reset(body: ResetBody) -> dict[str, Any]:
    """Back to a clean demo: clears queued actions, releases the kill switch, drops cached case files.
    The audit log is append-only and keeps a record of the reset."""
    GOV.reset(body.actor)
    clear_casefiles()
    return {"ok": True, "scenario": DEMO_SCENARIO, "seed": DEMO_SEED}
