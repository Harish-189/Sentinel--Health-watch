"""Deterministic evidence gate (SPEC 7). The LLM never touches this: tiers come from code only."""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.analysis.confounders import LabEvidence, completeness
from app.analysis.context import AnalysisContext
from app.analysis.models import TIERS, ConfounderResult, Criterion, GateResult, Signal, Tier
from app.config import get_settings
from app.data.schema import INDEPENDENT_SOURCES
from app.detection.models import series_id


def data_quality(ctx: AnalysisContext, district: str) -> dict[str, float]:
    """Meta completeness plus feed completeness (missing, not suppressed) per independent source."""
    g = get_settings().gate
    lo = ctx.as_of - g.feed_window
    df = ctx.df
    sub = df[(df["district"] == district) & (df["day"] > lo) & (df["day"] <= ctx.as_of)
             & df["source"].isin(INDEPENDENT_SOURCES)]
    present = sub["value"].notna() | sub["suppressed"]
    by_day: pd.Series = present.groupby([sub["source"], sub["day"]]).any()
    feed = {f"feed_{s}": float(by_day.loc[s].mean()) if s in by_day.index.get_level_values(0) else 0.0
            for s in INDEPENDENT_SOURCES}
    meta = completeness(ctx, district)
    feed_mean = float(np.mean(list(feed.values())))
    return {"meta_completeness": round(meta, 3), "feed_completeness": round(feed_mean, 3),
            "completeness": round(min(meta, feed_mean), 3), **{k: round(v, 3) for k, v in feed.items()}}


def _lower(a: Tier, b: Tier) -> Tier:
    return a if TIERS.index(a) <= TIERS.index(b) else b


def _crit(district: str, key: str, tier: Tier, label: str, met: bool, value: float | int | str | None,
          threshold: str, detail: str, ids: list[str]) -> Criterion:
    return Criterion(criterion_id=f"GT-{district}-{key}", key=key, tier=tier, label=label, met=met, value=value,
                     threshold=threshold, detail=detail, evidence_ids=ids)


def grade(
    ctx: AnalysisContext,
    district: str,
    sig: Signal | None,
    confounders: list[ConfounderResult],
    lab: LabEvidence | None,
    residual: float,
) -> GateResult:
    g = get_settings().gate
    dq = data_quality(ctx, district)
    meta_ids = [series_id(district, "meta", "sites_received"), series_id(district, "meta", "sites_expected")]
    if sig is None:
        criteria = [
            _crit(district, "e1_anomaly", "E1", "Sustained single-source anomaly", False, 0,
                  f"z ≥ {g.e1_z} for ≥ {g.e1_consecutive} days", "No sustained anomaly in the last "
                  f"{g.active_within_days} days.", []),
        ]
        return GateResult(tier="E0", raw_tier="E0", criteria=criteria, downgrades=[], residual_excess=0.0,
                          data_quality=dq)

    cf_by = {c.name: c for c in confounders}
    all_ruled_out = all(c.status == "ruled_out" for c in confounders)
    comp_ok = dq["completeness"] >= g.completeness_min
    assert lab is not None
    criteria = [
        _crit(district, "e1_anomaly", "E1", "Sustained single-source anomaly", True, sig.peak_z,
              f"z ≥ {g.e1_z} for ≥ {g.e1_consecutive} days", f"Peak z {sig.peak_z} across "
              f"{len(sig.evidence_ids)} anomaly episode(s).", sig.evidence_ids),
        _crit(district, "e2_sources", "E2", "Independent sources agree", sig.independent_sources >= g.e2_min_sources,
              sig.independent_sources, f"≥ {g.e2_min_sources} sources within {g.lag_window_days} days",
              f"Sources: {', '.join(sig.sources)}.", sig.window_ids),
        _crit(district, "e2_quality", "E2", "Data quality passes", comp_ok, dq["completeness"],
              f"completeness ≥ {g.completeness_min:.0%}",
              f"Site reporting {dq['meta_completeness']:.0%}, feed availability {dq['feed_completeness']:.0%}.",
              meta_ids),
        _crit(district, "e3_lab", "E3", "Lab positivity rising, test volume stable",
              lab.pos_rising and lab.tests_stable, lab.tests_zmax,
              f"positivity anomaly AND no sustained tests z ≥ {g.backlog_tests_z_max}, no batch pattern",
              ("Positivity rising; " if lab.pos_rising else "No positivity rise; ")
              + ("tests stable." if lab.tests_stable else "test volume unstable / batched.")
              + (" Recent results contradict the earlier rise." if lab.contradicted else ""),
              [*lab.positivity_ids, lab.tests_id]),
        _crit(district, "e3_spatial", "E3", "Spatial coherence", len(sig.adjacent_districts) >= g.e3_min_adjacent,
              len(sig.adjacent_districts), f"≥ {g.e3_min_adjacent} adjacent district(s) with a matching signal",
              f"Adjacent: {', '.join(sig.adjacent_districts) or 'none'}.", sig.adjacent_evidence),
        _crit(district, "e3_persistence", "E3", "Persistence after first detection",
              sig.persistence_days >= g.e3_persistence_days, sig.persistence_days,
              f"≥ {g.e3_persistence_days} days", f"Active {sig.persistence_days} day(s) after first detection.",
              sig.evidence_ids),
        _crit(district, "e3_confounders", "E3", "Confounders ruled out (or residual excess large)",
              all_ruled_out or residual >= g.e3_residual_excess, residual,
              f"all ruled out OR residual ≥ {g.e3_residual_excess:.0%}",
              "Not ruled out: " + (", ".join(c.name for c in confounders if c.status != "ruled_out") or "none")
              + f"; residual excess {residual:.0%}.", [c.confounder_id for c in confounders]),
    ]
    met = {c.key: c.met for c in criteria}
    raw: Tier = "E1"
    if met["e2_sources"] and met["e2_quality"]:
        raw = "E2"
        if all(met[k] for k in ("e3_lab", "e3_spatial", "e3_persistence", "e3_confounders")):
            raw = "E3"

    cap: Tier = "E3"
    downgrades: list[str] = []
    if not comp_ok:
        cap = "E1"
        downgrades.append(f"reporting completeness {dq['completeness']:.0%} < {g.completeness_min:.0%}")
    hol = cf_by.get("holiday")
    if hol is not None and hol.explained_share >= g.holiday_explains_max:
        cap = "E1"
        downgrades.append(f"holiday explains {hol.explained_share:.0%} of excess")
    if lab.contradicted:
        cap = _lower(cap, "E2")
        downgrades.append("new lab results contradict the earlier positivity rise")
    return GateResult(tier=_lower(raw, cap), raw_tier=raw, criteria=criteria, downgrades=downgrades,
                      residual_excess=residual, data_quality=dq)
