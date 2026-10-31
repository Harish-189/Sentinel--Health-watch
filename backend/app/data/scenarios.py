"""Scenario overlays (seeded, reproducible) and the `simulate` entry point.

Core scenarios (SPEC 5): true_outbreak, holiday_spike, reporting_change, lab_backlog,
weather_driven, seasonal_peak, noise_only. Two extra overlays power the Scenario Lab and
compose on top of a core one: contradicting_lab, source_outage.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd
from pydantic import BaseModel

from app.config import get_settings
from app.data.calendar import Calendar
from app.data.districts import CODES, index_of, neighbors
from app.data.simulator import (
    Array,
    Drivers,
    SimContext,
    apply_completeness,
    generate,
    make_context,
    to_long,
)

Series = dict[tuple[str, str], Array]


def hump(rel: Array, peak: float = 22.0, k: float = 2.0) -> Array:
    """Epidemic-curve shape: 0 before onset, rises to 1 at `peak` days, then decays."""
    x = np.clip(rel, 0, None) / peak
    return np.where(rel > 0, x**k * np.exp(k * (1 - x)), 0.0)


def plateau(rel: Array, ramp: float = 2.0, hold: float = 12.0, down: float = 3.0) -> Array:
    up = np.clip(rel / ramp, 0, 1)
    fall = np.clip(1 - (rel - ramp - hold) / down, 0, 1)
    return np.where(rel >= 0, np.minimum(up, fall), 0.0)


def cluster(primary: str, size: int = 3) -> list[str]:
    """Primary district plus adjacent districts that also touch each other where possible."""
    nb = sorted(neighbors(primary))
    picked = [primary, *nb[:1]]
    touching = [c for c in nb[1:] if any(c in neighbors(p) for p in picked[1:])]
    rest = [c for c in nb[1:] if c not in touching]
    return (picked + touching + rest)[:size]


# --------------------------------------------------------------------------- overlays

DriverFn = Callable[[Drivers, SimContext], list[str]]
PostFn = Callable[[Series, SimContext], None]


@dataclass(frozen=True)
class Overlay:
    name: str
    is_epidemic: bool
    description: str
    drivers: DriverFn
    post: PostFn | None = None


def _t(ctx: SimContext) -> Array:
    return np.arange(ctx.days, dtype=float)


def _true_outbreak(drv: Drivers, ctx: SimContext) -> list[str]:
    t = _t(ctx)
    amp = float(ctx.rng.uniform(0.85, 1.15))
    members = cluster(ctx.primary)
    spread = list(zip(members, (1.0, 0.6, 0.5), (0, 4, 5), strict=False))
    m, a = drv.mult, drv.add
    for code, intensity, extra in spread:
        i = index_of(code)

        def f(lag: float, _extra: float = extra, _k: float = intensity) -> Array:
            return _k * amp * hump(t - ctx.onset_day - _extra - lag)

        # Lead-lag: pharmacy + absenteeism lead, clinic follows (+2), lab confirms (+4), admissions lag clinic.
        if ctx.syndrome == "gastrointestinal":
            m["ors"][i] *= 1 + 1.6 * f(0)
            m["antipyretic"][i] *= 1 + 0.3 * f(0)
            a["school"][i] += 3.0 * f(0)
            a["work"][i] += 1.5 * f(1)
            m["gi"][i] *= 1 + 1.8 * f(2)
            a["pos_B"][i] += 0.20 * f(4)
            m["tests_B"][i] *= 1 + 0.15 * f(4)
            a["mobility"][i] -= 4.0 * f(3)
        else:
            m["antipyretic"][i] *= 1 + 1.3 * f(0)
            m["cough_cold"][i] *= 1 + 1.0 * f(0)
            m["antiviral"][i] *= 1 + 1.5 * f(1)
            a["school"][i] += 5.0 * f(0)
            a["work"][i] += 2.5 * f(1)
            m["resp"][i] *= 1 + 1.6 * f(2)
            m["febrile"][i] *= 1 + 0.4 * f(2)
            a["pos_A"][i] += 0.22 * f(4)
            m["tests_A"][i] *= 1 + 0.15 * f(4)
            a["mobility"][i] -= 6.0 * f(3)
    return members


FESTIVAL = "Lantern Night Festival"


def _holiday_spike(drv: Drivers, ctx: SimContext) -> list[str]:
    o = ctx.onset_day
    cal: Calendar = ctx.calendar
    cal.add(o + 6, FESTIVAL)
    cal.add(o + 7, FESTIVAL)
    m, a = drv.mult, drv.add
    stock = slice(o + 3, o + 6)  # pre-festival stocking up at pharmacies
    rush = slice(o + 8, o + 11)  # post-festival clinic rush (deferred visits, minor injuries)
    for ch in ("antipyretic", "cough_cold", "ors"):
        m[ch][:, stock] *= 1.6
    for ch in ("resp", "gi", "other"):
        m[ch][:, rush] *= 1.5
    a["mobility"][:, o + 6 : o + 8] += 30.0  # crowds offset the usual holiday dip
    a["school"][:, rush] += 1.5
    return list(CODES)


def _reporting_change(drv: Drivers, ctx: SimContext) -> list[str]:
    i, o = index_of(ctx.primary), ctx.onset_day
    for ch in ("resp", "gi", "febrile", "other"):
        drv.mult[ch][i, o:] *= 1.3
    for ch in ("antipyretic", "cough_cold", "antiviral", "ors"):
        drv.mult[ch][i, o:] *= 1.25
    return [ctx.primary]


def _reporting_change_post(out: Series, ctx: SimContext) -> None:
    i, o = index_of(ctx.primary), ctx.onset_day
    out[("meta", "sites_expected")][i, o:] += 4
    out[("meta", "sites_received")][i, o:] += ctx.rng.binomial(4, 0.98, size=ctx.days - o)
    out[("meta", "schema_version")][i, o:] = 2


def _lab_backlog(drv: Drivers, ctx: SimContext) -> list[str]:
    return [ctx.primary]


def _lab_backlog_post(out: Series, ctx: SimContext) -> None:
    """Batch reporting: ~10% of results trickle in for 4 days, then the backlog is dumped over 2 days."""
    i, rng = index_of(ctx.primary), ctx.rng
    cycle, trickle = 6, 4
    for panel in ("A", "B"):
        tests = out[("lab", f"panel_{panel}_tests")][i]
        pos = out[("lab", f"panel_{panel}_positives")][i]
        for start in range(ctx.onset_day, ctx.days - cycle + 1, cycle):
            held_t = held_p = 0.0
            for d in range(start, start + trickle):
                kt = float(rng.binomial(int(tests[d]), 0.1))
                kp = float(rng.hypergeometric(int(pos[d]), int(tests[d] - pos[d]), int(kt)))
                held_t += tests[d] - kt
                held_p += pos[d] - kp
                tests[d], pos[d] = kt, kp
            for j, d in enumerate(range(start + trickle, start + cycle)):
                share_t = held_t // 2 if j == 0 else held_t  # second day gets the remainder
                share_p = float(rng.hypergeometric(int(held_p), int(held_t - held_p), int(share_t)))
                tests[d] += share_t
                pos[d] += share_p
                held_t -= share_t
                held_p -= share_p


def _weather_driven(drv: Drivers, ctx: SimContext) -> list[str]:
    t = _t(ctx)
    members = cluster(ctx.primary)
    w = plateau(t - ctx.onset_day)
    m, a = drv.mult, drv.add
    for code in members:
        i = index_of(code)
        m["aqi"][i] *= 1 + 1.8 * w
        a["temp"][i] += 5.0 * w
        m["resp"][i] *= 1 + 0.7 * w  # same-day response to heat/pollution, not infectious
        m["cough_cold"][i] *= 1 + 0.5 * w
        m["antipyretic"][i] *= 1 + 0.1 * w
        m["tests_A"][i] *= 1 + 0.3 * w  # more testing, positivity unchanged
        a["school"][i] += 1.2 * w
        a["mobility"][i] -= 5.0 * w
    return members


def _seasonal_peak(drv: Drivers, ctx: SimContext) -> list[str]:
    peak_day = min(ctx.onset_day + 15, ctx.days - 1)
    ctx.resp_peak_doy = float(ctx.dates[peak_day].day_of_year)
    ctx.resp_amp = 0.5
    return list(CODES)


def _noise_only(drv: Drivers, ctx: SimContext) -> list[str]:
    return []


def _contradicting_lab(drv: Drivers, ctx: SimContext) -> list[str]:
    """New lab results in the last 10 days show flat positivity (contradicts an infectious cause)."""
    start = max(ctx.days - 10, ctx.onset_day)
    for code in cluster(ctx.primary):
        drv.add["pos_A"][index_of(code), start:] = 0.0
        drv.add["pos_B"][index_of(code), start:] = 0.0
    return [ctx.primary]


def _source_outage(drv: Drivers, ctx: SimContext) -> list[str]:
    return list(CODES)


def _source_outage_post(out: Series, ctx: SimContext) -> None:
    """Pharmacy feed goes dark for the last 5 days (all districts)."""
    for key in out:
        if key[0] == "pharmacy":
            out[key][:, ctx.days - 5 :] = np.nan


OVERLAYS: dict[str, Overlay] = {
    o.name: o
    for o in (
        Overlay("true_outbreak", True, "Infectious surge in a district cluster with cross-source lead-lag.",
                _true_outbreak),
        Overlay("holiday_spike", False, "Pharmacy and clinic surge around a newly declared festival.",
                _holiday_spike),
        Overlay("reporting_change", False, "A reporting network joins one district: step change, no real change.",
                _reporting_change, _reporting_change_post),
        Overlay("lab_backlog", False, "Lab results batch-reported: positives jump while positivity is flat.",
                _lab_backlog, _lab_backlog_post),
        Overlay("weather_driven", False, "Heat and poor air quality drive non-infectious respiratory visits.",
                _weather_driven),
        Overlay("seasonal_peak", False, "Expected annual respiratory rise, present in every year of history.",
                _seasonal_peak),
        Overlay("noise_only", False, "Control: no event.", _noise_only),
        Overlay("contradicting_lab", False, "New lab results show flat positivity in the affected cluster.",
                _contradicting_lab),
        Overlay("source_outage", False, "Pharmacy data feed outage for the last 5 days.",
                _source_outage, _source_outage_post),
    )
}
CORE_SCENARIOS: tuple[str, ...] = (
    "true_outbreak", "holiday_spike", "reporting_change", "lab_backlog",
    "weather_driven", "seasonal_peak", "noise_only",
)


class GroundTruth(BaseModel):
    scenarios: list[str]
    seed: int
    is_epidemic: bool
    onset_day: int
    primary: str
    syndrome: str
    affected: dict[str, list[str]]
    description: str


@dataclass
class SimResult:
    df: pd.DataFrame
    truth: GroundTruth
    calendar: Calendar
    ctx: SimContext

    @property
    def holidays(self) -> set[int]:
        return set(self.calendar.holidays)


def simulate(
    scenario: str | Sequence[str] = "noise_only",
    seed: int | None = None,
    onset_day: int | None = None,
    primary: str | None = None,
    syndrome: str = "respiratory",
) -> SimResult:
    names = [scenario] if isinstance(scenario, str) else list(scenario)
    unknown = [n for n in names if n not in OVERLAYS]
    if unknown:
        raise ValueError(f"unknown scenario(s): {unknown}")
    seed = get_settings().simulation.seed if seed is None else seed
    ctx = make_context(seed, onset_day, primary, syndrome)
    drv = Drivers.neutral(len(CODES), ctx.days)
    affected = {n: OVERLAYS[n].drivers(drv, ctx) for n in names}
    out = generate(drv, ctx)
    apply_completeness(np.random.default_rng([seed, 31]), out)
    for n in names:
        post = OVERLAYS[n].post
        if post is not None:
            post(out, ctx)
    truth = GroundTruth(
        scenarios=names,
        seed=seed,
        is_epidemic=any(OVERLAYS[n].is_epidemic for n in names),
        onset_day=ctx.onset_day,
        primary=ctx.primary,
        syndrome=syndrome,
        affected=affected,
        description=" + ".join(OVERLAYS[n].description for n in names),
    )
    return SimResult(df=to_long(out, ctx.dates), truth=truth, calendar=ctx.calendar, ctx=ctx)
