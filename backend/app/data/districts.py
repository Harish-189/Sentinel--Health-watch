"""Eight Tamil Nadu districts. Names and approximate coordinates are real; every number attached to them
(catchment population, reporting sites, all surveillance data) is simulated. No census figures, no facility names."""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache

from app.config import get_settings


@dataclass(frozen=True)
class District:
    code: str
    name: str
    population: int  # simulated catchment population (not a census figure)
    lat: float
    lon: float
    sites: int  # reporting sites expected
    completeness: float  # long-run probability that a site reports on a given day


DISTRICTS: tuple[District, ...] = (
    District("CHN", "Chennai", 520_000, 13.08, 80.27, 18, 0.99),
    District("VLR", "Vellore", 220_000, 12.92, 79.13, 9, 0.985),
    District("SLM", "Salem", 300_000, 11.66, 78.15, 12, 0.985),
    District("ERD", "Erode", 260_000, 11.34, 77.72, 11, 0.985),
    District("CBE", "Coimbatore", 420_000, 11.02, 76.96, 17, 0.99),
    District("TRY", "Tiruchirappalli", 310_000, 10.79, 78.70, 12, 0.985),
    District("MDU", "Madurai", 380_000, 9.92, 78.12, 14, 0.98),
    District("TNV", "Tirunelveli", 160_000, 8.73, 77.70, 6, 0.95),  # low-reporting district (fairness check)
)

CODES: tuple[str, ...] = tuple(d.code for d in DISTRICTS)


def by_code(code: str) -> District:
    for d in DISTRICTS:
        if d.code == code:
            return d
    raise KeyError(code)


@cache
def neighbors(code: str) -> frozenset[str]:
    """Adjacent districts, from `geography.adjacency` in config.yaml (undirected)."""
    by_code(code)
    pairs = get_settings().geography.adjacency
    return frozenset({b for a, b in pairs if a == code} | {a for a, b in pairs if b == code})


def index_of(code: str) -> int:
    return CODES.index(code)
