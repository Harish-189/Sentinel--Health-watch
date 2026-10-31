"""Cross-source correlation: group anomalies into district signals, lead-lag, spatial coherence."""

from __future__ import annotations

import numpy as np

from app.analysis.context import AnalysisContext
from app.analysis.models import LeadLag, Signal
from app.config import get_settings
from app.data.districts import neighbors
from app.data.schema import INDEPENDENT_SOURCES
from app.detection.models import Anomaly

SYNDROMES: tuple[str, ...] = ("respiratory", "gastrointestinal")
_BOTH = frozenset(SYNDROMES)
SYNDROME_OF: dict[tuple[str, str], frozenset[str]] = {
    ("clinic", "respiratory"): frozenset({"respiratory"}),
    ("clinic", "febrile_rash"): frozenset({"respiratory"}),
    ("clinic", "gastrointestinal"): frozenset({"gastrointestinal"}),
    ("clinic", "other"): _BOTH,
    ("pharmacy", "antipyretic"): _BOTH,
    ("pharmacy", "cough_cold"): frozenset({"respiratory"}),
    ("pharmacy", "antiviral"): frozenset({"respiratory"}),
    ("pharmacy", "ors_rehydration"): frozenset({"gastrointestinal"}),
    ("absenteeism", "school_rate"): _BOTH,
    ("absenteeism", "workplace_rate"): _BOTH,
    ("mobility", "mobility_index"): _BOTH,
    **{("lab", f"panel_A_{m}"): frozenset({"respiratory"}) for m in ("tests", "positives", "positivity")},
    **{("lab", f"panel_B_{m}"): frozenset({"gastrointestinal"}) for m in ("tests", "positives", "positivity")},
}
# Expected order of an infectious surge: early-warning sources, then clinic, then lab.
EXPECTED_RANK: dict[str, int] = {"pharmacy": 0, "absenteeism": 0, "mobility": 1, "clinic": 1, "lab": 2}
MAX_LAG = 7


def panel_for(syndrome: str) -> str:
    return "B" if syndrome == "gastrointestinal" else "A"


def _candidates(ctx: AnalysisContext, district: str, syndrome: str) -> list[Anomaly]:
    recent = ctx.as_of - get_settings().gate.active_within_days
    return [
        a
        for a in ctx.report.anomalies_for(district)
        if a.source in INDEPENDENT_SOURCES
        and syndrome in SYNDROME_OF.get((a.source, a.metric), frozenset())
        and a.end_day >= recent
    ]


def _best_window(cands: list[Anomaly], width: int) -> list[Anomaly]:
    """Lag-consistent window (first_signal_day within `width`) covering the most sources."""
    best: list[Anomaly] = []
    best_key = (-1, -1.0)
    for anchor in sorted(cands, key=lambda a: a.first_signal_day):
        f0 = anchor.first_signal_day
        members = [a for a in cands if f0 <= a.first_signal_day <= f0 + width]
        key = (len({a.source for a in members}), sum(a.peak_z for a in members))
        if key > best_key:
            best, best_key = members, key
    return best


def lag_consistency(onsets: dict[str, int]) -> float:
    pairs = agree = 0
    srcs = sorted(onsets)
    for i, a in enumerate(srcs):
        for b in srcs[i + 1 :]:
            ra, rb = EXPECTED_RANK[a], EXPECTED_RANK[b]
            if ra == rb:
                continue
            pairs += 1
            early, late = (a, b) if ra < rb else (b, a)
            agree += onsets[early] <= onsets[late]
    return round(agree / pairs, 3) if pairs else 0.5


def _xcorr(x: np.ndarray, ref: np.ndarray) -> tuple[int, float]:
    """Lag in [-MAX_LAG, MAX_LAG] maximizing corr(x[t], ref[t + lag]); positive = x leads."""
    best = (0, -1.0)
    n = len(x)
    for lag in range(-MAX_LAG, MAX_LAG + 1):
        a = x[: n - lag] if lag >= 0 else x[-lag:]
        b = ref[lag:] if lag >= 0 else ref[: n + lag]
        ok = np.isfinite(a) & np.isfinite(b)
        if ok.sum() < 10 or np.std(a[ok]) == 0 or np.std(b[ok]) == 0:
            continue
        c = float(np.corrcoef(a[ok], b[ok])[0, 1])
        if c > best[1]:
            best = (lag, c)
    return best[0], round(best[1], 3)


def _lead_lag(ctx: AnalysisContext, window: list[Anomaly]) -> list[LeadLag]:
    rep: dict[str, Anomaly] = {}
    for a in window:
        if a.source not in rep or a.peak_z > rep[a.source].peak_z:
            rep[a.source] = a
    ref_src = "clinic" if "clinic" in rep else min(rep, key=lambda s: rep[s].first_signal_day)
    ref = rep[ref_src]
    ref_s = ctx.series(ref.district, ref.source, ref.metric)
    out: list[LeadLag] = []
    if ref_s is None:
        return out
    ref_z = np.array([np.nan if v is None else v for v in ref_s.z])[-45:]
    for src, a in sorted(rep.items()):
        if src == ref_src:
            continue
        s = ctx.series(a.district, a.source, a.metric)
        if s is None:
            continue
        z = np.array([np.nan if v is None else v for v in s.z])[-45:]
        lag, corr = _xcorr(z, ref_z)
        out.append(LeadLag(source=f"{src}.{a.metric}", reference=f"{ref_src}.{ref.metric}", best_lag=lag, corr=corr))
    return out


def build_signal(ctx: AnalysisContext, district: str) -> Signal | None:
    gate = get_settings().gate
    best: tuple[tuple[int, float], str, list[Anomaly], list[Anomaly]] | None = None
    for syndrome in SYNDROMES:
        cands = _candidates(ctx, district, syndrome)
        if not cands:
            continue
        window = _best_window(cands, gate.lag_window_days)
        key = (len({a.source for a in window}), sum(a.peak_z for a in window))
        if best is None or key > best[0]:
            best = (key, syndrome, cands, window)
    if best is None:
        return None
    _, syndrome, cands, window = best
    onsets: dict[str, int] = {}
    for a in window:
        onsets[a.source] = min(onsets.get(a.source, a.first_signal_day), a.first_signal_day)
    first_det = min(a.start_day for a in cands) + gate.e1_consecutive - 1
    last_day = max(a.end_day for a in cands)
    return Signal(
        signal_id=f"SG-{district}-{syndrome[:4]}",
        district=district,
        syndrome=syndrome,
        sources=sorted(onsets),
        independent_sources=len(onsets),
        window_ids=[a.evidence_id for a in window],
        evidence_ids=[a.evidence_id for a in cands],
        first_day=min(a.start_day for a in window),
        last_day=last_day,
        first_detection_day=first_det,
        persistence_days=max(0, last_day - first_det),
        mean_z=round(float(np.mean([a.mean_z for a in window])), 2),
        peak_z=round(max(a.peak_z for a in window), 2),
        mean_excess=round(float(np.mean([a.excess_pct for a in window])), 3),
        onset_by_source=onsets,
        lag_consistency=lag_consistency(onsets),
        lead_lag=_lead_lag(ctx, window),
    )


def link_spatial(signals: dict[str, Signal | None]) -> None:
    """Mark adjacent districts with an overlapping same-syndrome multi-source signal."""
    for code, sig in signals.items():
        if sig is None:
            continue
        adj = []
        for n in sorted(neighbors(code)):
            other = signals.get(n)
            if (
                other is not None
                and other.syndrome == sig.syndrome
                and other.independent_sources >= 2
                and other.first_day <= sig.last_day + 7
                and other.last_day >= sig.first_day - 7
            ):
                adj.append(other)
        sig.adjacent_districts = [o.district for o in adj]
        sig.adjacent_evidence = [o.signal_id for o in adj]
