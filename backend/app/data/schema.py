"""Registry of aggregate metrics. Every series in the system is (district, source, metric) daily."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Kind = Literal["count", "rate", "measure"]
Direction = Literal["up", "down"]


@dataclass(frozen=True)
class MetricSpec:
    source: str
    metric: str
    kind: Kind  # only "count" is subject to small-cell suppression
    log_scale: bool  # baseline fitted on log1p(value)
    direction: Direction  # which deviation counts as anomalous
    detect: bool = True
    derived: bool = False  # computed in detection, not simulated


def _counts(source: str, metrics: tuple[str, ...]) -> list[MetricSpec]:
    return [MetricSpec(source, m, "count", True, "up") for m in metrics]


METRICS: tuple[MetricSpec, ...] = (
    *_counts("clinic", ("respiratory", "gastrointestinal", "febrile_rash", "other")),
    *_counts("lab", ("panel_A_tests", "panel_A_positives", "panel_B_tests", "panel_B_positives")),
    MetricSpec("lab", "panel_A_positivity", "rate", False, "up", derived=True),
    MetricSpec("lab", "panel_B_positivity", "rate", False, "up", derived=True),
    *_counts("pharmacy", ("antipyretic", "ors_rehydration", "antiviral", "cough_cold")),
    MetricSpec("absenteeism", "school_rate", "rate", False, "up"),
    MetricSpec("absenteeism", "workplace_rate", "rate", False, "up"),
    MetricSpec("environment", "temperature", "measure", False, "up"),
    MetricSpec("environment", "rainfall", "measure", False, "up", detect=False),
    MetricSpec("environment", "humidity", "measure", False, "up", detect=False),
    MetricSpec("environment", "aqi", "measure", False, "up"),
    MetricSpec("mobility", "mobility_index", "measure", False, "down"),
    MetricSpec("capacity", "admissions", "count", True, "up"),
    MetricSpec("capacity", "beds_occupied", "measure", False, "up", detect=False),
    MetricSpec("capacity", "beds_total", "measure", False, "up", detect=False),
    MetricSpec("capacity", "icu_occupied", "measure", False, "up", detect=False),
    MetricSpec("capacity", "icu_total", "measure", False, "up", detect=False),
    MetricSpec("meta", "sites_expected", "measure", False, "up", detect=False),
    MetricSpec("meta", "sites_received", "measure", False, "up", detect=False),
    MetricSpec("meta", "schema_version", "measure", False, "up", detect=False),
)

SPEC_BY_KEY: dict[tuple[str, str], MetricSpec] = {(m.source, m.metric): m for m in METRICS}

# Sources that count toward "independent sources agree" (environment is a confounder, capacity an outcome).
INDEPENDENT_SOURCES: tuple[str, ...] = ("clinic", "lab", "pharmacy", "absenteeism", "mobility")

LONG_COLUMNS: tuple[str, ...] = ("day", "date", "district", "source", "metric", "value")


def spec(source: str, metric: str) -> MetricSpec:
    return SPEC_BY_KEY[(source, metric)]
