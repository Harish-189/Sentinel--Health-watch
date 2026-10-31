"""Typed loader for backend/config.yaml. All thresholds come from here."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"


class SimulationCfg(BaseModel):
    days: int
    start_date: str
    onset_day: int
    seed: int
    default_primary: str


class PrivacyCfg(BaseModel):
    k_min: int
    laplace_enabled: bool
    laplace_epsilon: float
    pii_patterns: list[str]
    allowlist: list[str]


class DetectionCfg(BaseModel):
    train_guard_days: int
    min_train_days: int
    eval_window: int
    fourier_harmonics: int
    outlier_mad: float
    z_threshold: float
    consecutive_days: int
    merge_gap_days: int
    ewma_lambda: float
    ewma_L: float
    cusum_k: float
    cusum_h: float
    min_sigma: float


class GateCfg(BaseModel):
    e1_z: float
    e1_consecutive: int
    e2_min_sources: int
    lag_window_days: int
    completeness_min: float
    e3_persistence_days: int
    e3_min_adjacent: int
    e3_residual_excess: float
    holiday_explains_max: float
    backlog_tests_z_max: float


class Settings(BaseModel):
    simulation: SimulationCfg
    privacy: PrivacyCfg
    detection: DetectionCfg
    gate: GateCfg
    forecast: dict[str, Any]
    llm: dict[str, Any]


@lru_cache(maxsize=4)
def get_settings(path: str | None = None) -> Settings:
    cfg_path = Path(path or os.environ.get("SENTINEL_CONFIG") or CONFIG_PATH)
    with cfg_path.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return Settings.model_validate(raw)
