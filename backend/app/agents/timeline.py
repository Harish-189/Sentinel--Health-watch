"""Replay frames for the Command Center scrubber: per-day tiers and confidence for every district,
computed causally (each frame only sees data up to its as_of day). Cached on disk."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from app.agents.orchestrator import run_analysis
from app.config import get_settings

CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "generated" / "timeline"


class DistrictFrame(BaseModel):
    tier: str
    confidence: float
    sources: int
    syndrome: str | None
    peak_z: float | None


class Frame(BaseModel):
    as_of: int
    date: str
    districts: dict[str, DistrictFrame]


class Timeline(BaseModel):
    scenario: list[str]
    seed: int
    onset_day: int
    frames: list[Frame]


def _frame(scenario: tuple[str, ...], seed: int, as_of: int) -> Frame:
    # Bypass the in-memory LRU so replay frames do not evict the live analysis.
    bundle = run_analysis.__wrapped__(scenario, seed=seed, as_of=as_of)
    return Frame(as_of=bundle.as_of, date=bundle.as_of_date, districts={
        a.district: DistrictFrame(
            tier=a.gate.tier, confidence=round(a.confidence.point, 3),
            sources=a.signal.independent_sources if a.signal else 0,
            syndrome=a.signal.syndrome if a.signal else None,
            peak_z=a.signal.peak_z if a.signal else None)
        for a in bundle.assessments})


def build_timeline(scenario: tuple[str, ...], seed: int, cache_dir: Path | None = CACHE_DIR) -> Timeline:
    sim = get_settings().simulation
    path = cache_dir / f"{'+'.join(scenario)}_{seed}.json" if cache_dir else None
    if path is not None and path.exists():
        return Timeline.model_validate(json.loads(path.read_text(encoding="utf-8")))
    frames = [_frame(scenario, seed, d) for d in range(sim.timeline_start, sim.days)]
    tl = Timeline(scenario=list(scenario), seed=seed, onset_day=sim.onset_day, frames=frames)
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(tl.model_dump_json(), encoding="utf-8")
    return tl
