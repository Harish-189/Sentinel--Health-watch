"""Sentinel API. Stage 1 exposes health, districts, scenarios and detection; later stages extend it."""

from __future__ import annotations

from functools import lru_cache

from fastapi import FastAPI, HTTPException

from app.data.districts import DISTRICTS, neighbors
from app.data.privacy import apply_privacy
from app.data.scenarios import CORE_SCENARIOS, OVERLAYS, simulate
from app.detection.run import DetectionReport, detect_all

app = FastAPI(title="Sentinel", version="0.1.0")


@lru_cache(maxsize=16)
def _detection(scenario: str, seed: int, as_of: int | None) -> DetectionReport:
    sim = simulate(scenario.split("+"), seed=seed)
    return detect_all(apply_privacy(sim.df), holidays=sim.holidays, as_of=as_of)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


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
def detect(scenario: str = "true_outbreak", seed: int = 42, as_of: int | None = None) -> DetectionReport:
    if any(part not in OVERLAYS for part in scenario.split("+")):
        raise HTTPException(404, f"unknown scenario: {scenario}")
    return _detection(scenario, seed, as_of)
