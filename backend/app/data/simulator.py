"""Seeded synthetic generator of aggregate health signals (no real data, no person-level rows).

Generation is two-phase: scenario overlays first edit latent *drivers* (multipliers / additive
shifts per district-day), then counts are sampled. Base noise is seeded by `seed`; scenario jitter
uses a separate stream, so every (scenario, seed) pair is exactly reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from app.config import get_settings
from app.data.calendar import Calendar, build_calendar
from app.data.districts import DISTRICTS

Array = np.ndarray

# Multiplicative drivers (default 1) and additive drivers (default 0), each shaped (districts, days).
MULT_CHANNELS = (
    "resp", "gi", "febrile", "other",
    "antipyretic", "ors", "antiviral", "cough_cold",
    "tests_A", "tests_B", "aqi",
)
ADD_CHANNELS = ("school", "work", "pos_A", "pos_B", "temp", "mobility")

CLINIC_DOW = np.array([1.25, 1.10, 1.05, 1.00, 1.00, 0.80, 0.55])  # Mon..Sun
PHARM_DOW = np.array([1.05, 1.00, 1.00, 1.00, 1.05, 1.10, 0.80])
NB_SHAPE = 80.0  # gamma-Poisson overdispersion


@dataclass
class SimContext:
    seed: int
    days: int
    dates: pd.DatetimeIndex
    calendar: Calendar
    onset_day: int
    primary: str
    syndrome: str
    rng: np.random.Generator  # scenario-only RNG (jitter), separate from base noise
    resp_peak_doy: float = 15.0  # mid-January respiratory peak
    resp_amp: float = 0.35
    notes: list[str] = field(default_factory=list)


@dataclass
class Drivers:
    mult: dict[str, Array]
    add: dict[str, Array]

    @classmethod
    def neutral(cls, n_districts: int, days: int) -> Drivers:
        return cls(
            mult={c: np.ones((n_districts, days)) for c in MULT_CHANNELS},
            add={c: np.zeros((n_districts, days)) for c in ADD_CHANNELS},
        )


def _season(doy: Array, peak: float, amp: float) -> Array:
    return 1.0 + amp * np.cos(2 * np.pi * (doy - peak) / 365.25)


def _nb(rng: np.random.Generator, lam: Array) -> Array:
    """Negative-binomial counts via gamma-Poisson mixture."""
    lam = np.clip(lam, 0, None)
    return rng.poisson(lam * rng.gamma(NB_SHAPE, 1.0 / NB_SHAPE, size=lam.shape)).astype(float)


def _thin(rng: np.random.Generator, counts: Array, frac: Array) -> Array:
    """Reporting completeness: only reports from received sites arrive."""
    return rng.binomial(counts.astype(np.int64), np.clip(frac, 0, 1)).astype(float)


def generate(drv: Drivers, ctx: SimContext) -> dict[tuple[str, str], Array]:
    """Sample every (source, metric) series as a (districts, days) array."""
    rng = np.random.default_rng(ctx.seed)
    n_d, n_t = len(DISTRICTS), ctx.days
    t = np.arange(n_t)
    doy = ctx.dates.day_of_year.to_numpy().astype(float)
    dow = ctx.dates.day_of_week.to_numpy()
    hol, pre, post = ctx.calendar.flags()
    pop = np.array([d.population for d in DISTRICTS], dtype=float)[:, None] / 1e5
    trend = 1.0 + 0.03 * t / 365.0

    s_resp = _season(doy, ctx.resp_peak_doy, ctx.resp_amp)
    s_gi = _season(doy, 200.0, 0.25)
    s_feb = _season(doy, 240.0, 0.30)
    clinic_cal = CLINIC_DOW[dow] * (1 - 0.5 * hol) * (1 + 0.25 * post) * trend
    pharm_cal = PHARM_DOW[dow] * (1 - 0.3 * hol) * (1 + 0.2 * pre) * trend

    m, a = drv.mult, drv.add
    out: dict[tuple[str, str], Array] = {}

    # Clinic visits by syndrome group
    resp_base = pop * 40 * s_resp * clinic_cal
    out[("clinic", "respiratory")] = _nb(rng, resp_base * m["resp"])
    out[("clinic", "gastrointestinal")] = _nb(rng, pop * 18 * s_gi * clinic_cal * m["gi"])
    out[("clinic", "febrile_rash")] = _nb(rng, pop * 8 * s_feb * clinic_cal * m["febrile"])
    out[("clinic", "other")] = _nb(rng, pop * 80 * clinic_cal * m["other"])

    # Lab panels: tests track baseline demand (not the outbreak), positivity carries the signal
    for panel, base, season in (("A", resp_base, s_resp), ("B", pop * 18 * s_gi * clinic_cal, s_gi)):
        tests = _nb(rng, 0.9 * base * m[f"tests_{panel}"])
        pos_rate = np.clip(0.08 + 0.03 * (season - 1) / 0.3 + a[f"pos_{panel}"], 0.01, 0.9)
        out[("lab", f"panel_{panel}_tests")] = tests
        out[("lab", f"panel_{panel}_positives")] = rng.binomial(tests.astype(np.int64), pos_rate).astype(float)

    # Pharmacy units by class
    out[("pharmacy", "antipyretic")] = _nb(rng, pop * 60 * s_resp**0.7 * pharm_cal * m["antipyretic"])
    out[("pharmacy", "cough_cold")] = _nb(rng, pop * 45 * s_resp * pharm_cal * m["cough_cold"])
    out[("pharmacy", "antiviral")] = _nb(rng, pop * 8 * s_resp * pharm_cal * m["antiviral"])
    out[("pharmacy", "ors_rehydration")] = _nb(rng, pop * 30 * s_gi * pharm_cal * m["ors"])

    # Absenteeism (percent of enrolled / employed absent)
    mon = (dow == 0).astype(float)
    shape = (n_d, n_t)
    school = 4.0 + 1.5 * (s_resp - 1) / ctx.resp_amp * 0.5 + 0.4 * mon + a["school"]
    work = 3.0 + 0.6 * (s_resp - 1) / ctx.resp_amp * 0.5 + 0.2 * mon + a["work"]
    out[("absenteeism", "school_rate")] = np.round(np.clip(school + rng.normal(0, 0.3, shape), 0, None), 2)
    out[("absenteeism", "workplace_rate")] = np.round(np.clip(work + rng.normal(0, 0.2, shape), 0, None), 2)

    # Environment (regional climate + district offsets)
    offset = rng.normal(0, 1.0, (n_d, 1))
    temp = 26 + 6 * np.cos(2 * np.pi * (doy - 130) / 365.25) + offset + a["temp"]
    monsoon = np.clip(np.cos(2 * np.pi * (doy - 215) / 365.25), 0, None)
    out[("environment", "temperature")] = np.round(temp + rng.normal(0, 1.2, shape), 1)
    rain = rng.gamma(0.6, 4 + 30 * monsoon, shape) * (rng.random(shape) < 0.2 + 0.6 * monsoon)
    out[("environment", "rainfall")] = np.round(rain, 1)
    out[("environment", "humidity")] = np.round(np.clip(55 + 25 * monsoon + rng.normal(0, 5, shape), 10, 100), 1)
    aqi = (70 + 45 * _season(doy, 0.0, 1.0) / 2) * np.exp(rng.normal(0, 0.12, shape)) * m["aqi"]
    out[("environment", "aqi")] = np.round(aqi)

    # Mobility index (100 = baseline)
    weekend = (dow >= 5).astype(float)
    mob = 100 - 12 * weekend - 25 * hol + a["mobility"] + rng.normal(0, 2.5, shape)
    out[("mobility", "mobility_index")] = np.round(mob, 1)

    _capacity(rng, out, ctx)
    _reporting(rng, out, ctx)
    return out


def _capacity(rng: np.random.Generator, out: dict[tuple[str, str], Array], ctx: SimContext) -> None:
    """Admissions lag clinic visits by 2 days; occupancy evolves with stochastic length of stay."""
    fc = get_settings().forecast
    los, icu_los = fc.los_mean_days, fc.icu_los_mean_days
    c = out
    lam = (
        0.03 * c[("clinic", "respiratory")]
        + 0.04 * c[("clinic", "gastrointestinal")]
        + 0.03 * c[("clinic", "febrile_rash")]
        + 0.03 * c[("clinic", "other")]
    )
    lam = np.concatenate([lam[:, :1].repeat(2, axis=1), lam[:, :-2]], axis=1)
    adm = rng.poisson(lam).astype(float)
    icu_adm = rng.binomial(adm.astype(np.int64), 0.10).astype(float)

    n_d, n_t = adm.shape
    mean_adm = adm[:, :365].mean(axis=1)
    beds = np.empty((n_d, n_t))
    icu = np.empty((n_d, n_t))
    beds[:, 0] = np.round(mean_adm * los)
    icu[:, 0] = np.round(mean_adm * 0.10 * icu_los)
    beds_total = np.round(mean_adm * los / 0.70)
    icu_total = np.round(mean_adm * 0.10 * icu_los / 0.66)
    for i in range(1, n_t):
        beds[:, i] = beds[:, i - 1] - rng.binomial(beds[:, i - 1].astype(np.int64), 1 / los) + adm[:, i]
        icu[:, i] = icu[:, i - 1] - rng.binomial(icu[:, i - 1].astype(np.int64), 1 / icu_los) + icu_adm[:, i]
    out[("capacity", "admissions")] = adm
    out[("capacity", "beds_occupied")] = np.minimum(beds, np.round(beds_total[:, None] * 1.2))
    out[("capacity", "icu_occupied")] = np.minimum(icu, np.round(icu_total[:, None] * 1.2))
    out[("capacity", "beds_total")] = np.repeat(beds_total[:, None], n_t, axis=1)
    out[("capacity", "icu_total")] = np.repeat(icu_total[:, None], n_t, axis=1)


def _reporting(rng: np.random.Generator, out: dict[tuple[str, str], Array], ctx: SimContext) -> None:
    n_t = ctx.days
    expected = np.array([[d.sites] * n_t for d in DISTRICTS], dtype=float)
    p = np.array([d.completeness for d in DISTRICTS])[:, None]
    received = rng.binomial(expected.astype(np.int64), np.broadcast_to(p, expected.shape)).astype(float)
    out[("meta", "sites_expected")] = expected
    out[("meta", "sites_received")] = received
    out[("meta", "schema_version")] = np.ones_like(expected)


def apply_completeness(rng: np.random.Generator, out: dict[tuple[str, str], Array]) -> None:
    """Thin site-reported counts by the fraction of sites that reported that day."""
    frac = out[("meta", "sites_received")] / out[("meta", "sites_expected")]
    for key in list(out):
        if key[0] in ("clinic", "pharmacy"):
            out[key] = _thin(rng, out[key], frac)
    for panel in ("A", "B"):
        tk, pk = ("lab", f"panel_{panel}_tests"), ("lab", f"panel_{panel}_positives")
        tests, pos = out[tk].astype(np.int64), out[pk].astype(np.int64)
        kept = _thin(rng, out[tk], frac).astype(np.int64)
        out[pk] = rng.hypergeometric(pos, tests - pos, kept).astype(float)
        out[tk] = kept.astype(float)


def to_long(out: dict[tuple[str, str], Array], dates: pd.DatetimeIndex) -> pd.DataFrame:
    n_t = len(dates)
    codes = np.array([d.code for d in DISTRICTS])
    day_idx = np.arange(n_t)
    date_str = dates.strftime("%Y-%m-%d").to_numpy()
    frames = []
    for (source, metric), arr in out.items():
        frames.append(
            pd.DataFrame(
                {
                    "day": np.tile(day_idx, len(codes)),
                    "date": np.tile(date_str, len(codes)),
                    "district": np.repeat(codes, n_t),
                    "source": source,
                    "metric": metric,
                    "value": arr.reshape(-1).astype(float),
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


def make_context(
    seed: int, onset_day: int | None, primary: str | None, syndrome: str
) -> SimContext:
    sim = get_settings().simulation
    dates = pd.date_range(sim.start_date, periods=sim.days, freq="D")
    return SimContext(
        seed=seed,
        days=sim.days,
        dates=dates,
        calendar=build_calendar(dates),
        onset_day=sim.onset_day if onset_day is None else onset_day,
        primary=primary or sim.default_primary,
        syndrome=syndrome,
        rng=np.random.default_rng([seed, 7919]),
    )
