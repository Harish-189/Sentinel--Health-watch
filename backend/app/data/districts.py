"""Eight fictional districts on an axial hex grid. No real place names."""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache


@dataclass(frozen=True)
class District:
    code: str
    name: str
    population: int
    q: int  # axial hex coordinates (map layout and adjacency)
    r: int
    sites: int  # reporting sites expected
    completeness: float  # long-run probability that a site reports on a given day


DISTRICTS: tuple[District, ...] = (
    District("D1", "Northvale", 280_000, 0, -1, 11, 0.985),
    District("D2", "Kestrel Bay", 190_000, 1, -1, 8, 0.985),
    District("D3", "Amberfield", 420_000, 0, 0, 17, 0.99),
    District("D4", "Lowmoor", 260_000, 1, 0, 10, 0.985),
    District("D5", "Cindral", 310_000, 0, 1, 12, 0.985),
    District("D6", "Velmora", 230_000, -1, 0, 9, 0.98),
    District("D7", "Quillan Ridge", 150_000, -1, 1, 6, 0.95),  # low-reporting district (fairness check)
    District("D8", "Sunhollow", 200_000, 2, -1, 8, 0.97),
)

CODES: tuple[str, ...] = tuple(d.code for d in DISTRICTS)
_AXIAL_DIRS = ((1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1))


def by_code(code: str) -> District:
    for d in DISTRICTS:
        if d.code == code:
            return d
    raise KeyError(code)


@cache
def neighbors(code: str) -> frozenset[str]:
    d = by_code(code)
    cells = {(d.q + dq, d.r + dr) for dq, dr in _AXIAL_DIRS}
    return frozenset(o.code for o in DISTRICTS if (o.q, o.r) in cells)


def index_of(code: str) -> int:
    return CODES.index(code)
