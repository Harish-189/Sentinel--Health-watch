"""Typed loader for backend/config.yaml. All thresholds come from here."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"


class SimulationCfg(BaseModel):
    days: int
    start_date: str
    onset_day: int
    seed: int
    demo_seed: int
    demo_scenario: list[str]
    timeline_start: int
    default_primary: str
    scenario_targets: dict[str, list[str]]


class GeographyCfg(BaseModel):
    adjacency: list[tuple[str, str]]


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
    active_within_days: int
    completeness_window: int
    feed_window: int
    holiday_window_days: int
    holiday_ruled_out_max: float
    reporting_align_days: int
    weather_corr_min: float
    seasonal_yoy_explains: float
    seasonal_yoy_ruled_out: float
    contradict_pos_z_max: float


class ConfidenceCfg(BaseModel):
    intercept: float
    weights: dict[str, float]
    platt_a: float
    platt_b: float
    bootstrap_n: int


class ForecastCfg(BaseModel):
    n_sims: int
    horizon_days: int
    los_mean_days: float
    icu_los_mean_days: float
    fit_days: int
    icu_share: float
    growth_clip: tuple[float, float]
    intervention_growth_cut: float
    intervention_delay_days: int


class LLMCfg(BaseModel):
    default_model: str
    default_fast_model: str
    max_calls_per_analysis: int
    max_tokens: int
    timeout_s: float
    effort: str
    critic_effort: str
    verifier_llm_critic: bool
    tool_rounds_max: int
    prompt_version: str
    number_rel_tol: float
    number_abs_tol: float
    pricing: dict[str, tuple[float, float, float]]


class Settings(BaseModel):
    simulation: SimulationCfg
    geography: GeographyCfg
    privacy: PrivacyCfg
    detection: DetectionCfg
    gate: GateCfg
    confidence: ConfidenceCfg
    forecast: ForecastCfg
    llm: LLMCfg


@lru_cache(maxsize=4)
def get_settings(path: str | None = None) -> Settings:
    cfg_path = Path(path or os.environ.get("SENTINEL_CONFIG") or CONFIG_PATH)
    with cfg_path.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return Settings.model_validate(raw)
