"""Evaluation harness (SPEC 13): seeded simulations vs a single-threshold baseline.

    python -m app.eval.harness --runs 100

Every run simulates one scenario (outbreak runs rotate the primary district across all 8 districts) and is analysed
causally at checkpoints (as_of = 703 ... 729), so alert *timing* can be compared, not just the final state.

Baseline: a single-source threshold (clinic respiratory visits, robust z >= 3 on any day), the classic syndromic rule.
Ground truth: districts in the true_outbreak cluster are positives; every other district-run is a negative.
The report is cached at data/generated/eval/report.json and served by GET /api/eval/report."""

from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from collections import Counter, defaultdict
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import numpy as np

from app.analysis.models import TIERS

REPORT_PATH = Path(__file__).resolve().parents[2] / "data" / "generated" / "eval" / "report.json"
CHECKPOINTS = (703, 706, 709, 712, 715, 718, 721, 724, 727, 729)
WINDOW = (CHECKPOINTS[0], CHECKPOINTS[-1])  # alert-counting window (days, inclusive)
FORECAST_FROM = 715  # backtest: forecast made on this day, scored on the following 14 days
BASELINE_SERIES = ("clinic", "respiratory")
BASELINE_Z = 3.0
MIX = (  # scenario weights for a 100-run evaluation
    ("true_outbreak", 32),
    ("holiday_spike", 12),
    ("reporting_change", 12),
    ("lab_backlog", 12),
    ("weather_driven", 11),
    ("seasonal_peak", 11),
    ("noise_only", 10),
)


def run_specs(n: int, seed0: int = 1000) -> list[dict[str, Any]]:
    """Deterministic run list: scenario mix scaled to n, primary district rotated for fairness."""
    from app.data.districts import CODES

    total = sum(w for _, w in MIX)
    names: list[str] = []
    for name, w in MIX:
        names += [name] * max(1, round(w * n / total))
    names = (names * (n // len(names) + 1))[:n]
    counters: Counter[str] = Counter()
    specs = []
    for i, name in enumerate(names):
        k = counters[name]
        counters[name] += 1
        specs.append({"i": i, "scenario": name, "seed": seed0 + i, "primary": CODES[k % len(CODES)]})
    return specs


# ------------------------------------------------------------------ one run (executed in a worker process)


def _episodes(flags: np.ndarray, days: list[int]) -> list[int]:
    """Start days of consecutive runs of True."""
    starts, prev = [], False
    for f, d in zip(flags, days, strict=True):
        if f and not prev:
            starts.append(d)
        prev = bool(f)
    return starts


def run_one(spec: dict[str, Any]) -> dict[str, Any]:
    from app.agents.offline import offline_hypotheses
    from app.agents.orchestrator import analyze_sim
    from app.agents.verifier import verify
    from app.data.districts import CODES, by_code
    from app.data.scenarios import simulate

    sim = simulate([spec["scenario"]], seed=spec["seed"], primary=spec["primary"])
    affected = set(sim.truth.affected.get("true_outbreak", []))
    tiers: dict[str, list[str]] = {d: [] for d in CODES}
    lat: list[float] = []
    bundle = None
    forecast_bundle = None
    for cp in CHECKPOINTS:
        t0 = time.perf_counter()
        bundle = analyze_sim(sim, as_of=cp)
        lat.append((time.perf_counter() - t0) * 1000)
        for a in bundle.assessments:
            tiers[a.district].append(a.gate.tier)
        if cp == FORECAST_FROM:
            forecast_bundle = bundle
    assert bundle is not None and forecast_bundle is not None
    final = {a.district: a for a in bundle.assessments}

    # Baseline: single-source threshold on the final (causal) detection report.
    base: dict[str, dict[str, Any]] = {}
    for d in CODES:
        s = bundle.context.series(d, *BASELINE_SERIES)
        days = s.days if s else []
        z = np.array([(-np.inf if v is None else v) for v in (s.z if s else [])], dtype=float)
        in_w = np.array([WINDOW[0] <= day <= WINDOW[1] for day in days], dtype=bool)
        flags = (z >= BASELINE_Z) & in_w
        eps = _episodes(flags, days)
        onset = [day for day, f in zip(days, z >= BASELINE_Z, strict=True) if f and day >= sim.truth.onset_day]
        base[d] = {"episodes": eps, "first_alarm": onset[0] if onset else None}

    # Sentinel per district: max tier, first checkpoint reaching E2 / E3, detection day, confidence.
    sent: dict[str, dict[str, Any]] = {}
    for d in CODES:
        idx = [TIERS.index(t) for t in tiers[d]]
        first = {
            t: next((cp for cp, v in zip(CHECKPOINTS, idx, strict=True) if v >= TIERS.index(t)), None)
            for t in ("E1", "E2", "E3")
        }
        sig = final[d].signal
        sent[d] = {
            "max_tier": TIERS[max(idx)],
            "final_tier": final[d].gate.tier,
            "first": first,
            "detect_day": sig.first_detection_day if sig else None,
            "confidence": final[d].confidence.point,
            "affected": d in affected,
        }

    # Forecast backtest for the primary district: made on day 715, scored on days 716-729 (bed occupancy).
    p = spec["primary"]
    f = forecast_bundle.assessment(p).forecast
    occ = bundle.context.raw(p, "capacity", "beds_occupied")
    hits, ape = [], []
    for k, day in enumerate(f.days):
        if day > CHECKPOINTS[-1] or day >= len(occ) or not np.isfinite(occ[day]):
            continue
        y = float(occ[day])
        hits.append(f.beds.p10[k] <= y <= f.beds.p90[k])
        if y > 0:
            ape.append(abs(f.beds.p50[k] - y) / y)

    # Groundedness (offline/rule-based agents; deterministic and free): verify the primary's hypotheses.
    a = final[p]
    hyps = offline_hypotheses(by_code(p).name, a.signal, a.confounders, a.confidence)
    _, ver = verify(hyps, bundle.evidence, None)

    return {
        **spec,
        "epidemic": sim.truth.is_epidemic,
        "affected": sorted(affected),
        "onset": sim.truth.onset_day,
        "sentinel": sent,
        "baseline": base,
        "latency_ms": statistics.fmean(lat),
        "forecast": {
            "coverage": statistics.fmean(hits) if hits else None,
            "mape": statistics.fmean(ape) if ape else None,
            "n": len(hits),
        },
        "claims": {"total": ver.total_claims, "grounded": ver.grounded_claims},
    }


# ------------------------------------------------------------------ metrics


def _median(xs: list[float]) -> float | None:
    return float(statistics.median(xs)) if xs else None


def _mean(xs: list[float]) -> float | None:
    return float(statistics.fmean(xs)) if xs else None


def summarize(runs: list[dict[str, Any]], elapsed_s: float) -> dict[str, Any]:
    from app.data.districts import CODES, by_code

    window_days = WINDOW[1] - WINDOW[0] + 1
    per90 = 90 / window_days
    ob = [r for r in runs if r["scenario"] == "true_outbreak"]

    # --- sensitivity + lead time on the primary district of outbreak runs
    def prim(r: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        return r["sentinel"][r["primary"]], r["baseline"][r["primary"]]

    sens_e2 = [TIERS.index(prim(r)[0]["max_tier"]) >= 2 for r in ob]
    sens_e3 = [prim(r)[0]["max_tier"] == "E3" for r in ob]
    sens_base = [prim(r)[1]["first_alarm"] is not None for r in ob]
    lead = [
        prim(r)[1]["first_alarm"] - prim(r)[0]["detect_day"]
        for r in ob
        if prim(r)[1]["first_alarm"] is not None and prim(r)[0]["detect_day"] is not None
    ]
    det_delay = [prim(r)[0]["detect_day"] - r["onset"] for r in ob if prim(r)[0]["detect_day"] is not None]
    base_delay = [prim(r)[1]["first_alarm"] - r["onset"] for r in ob if prim(r)[1]["first_alarm"] is not None]
    e3_delay = [prim(r)[0]["first"]["E3"] - r["onset"] for r in ob if prim(r)[0]["first"]["E3"] is not None]

    # --- false alarms (unaffected districts) and intervention precision
    fa_sent_e2 = fa_sent_e1 = fa_base = 0
    tp_e3 = fp_e3 = 0
    tp_base = fp_base = 0
    for r in runs:
        for d in CODES:
            s, b = r["sentinel"][d], r["baseline"][d]
            pos = s["affected"]
            lvl = TIERS.index(s["max_tier"])
            if not pos:
                fa_sent_e2 += lvl >= 2
                fa_sent_e1 += lvl >= 1
                fa_base += len(b["episodes"])
            if s["max_tier"] == "E3":
                tp_e3 += pos
                fp_e3 += not pos
            tp_base += len(b["episodes"]) if pos else 0
            fp_base += 0 if pos else len(b["episodes"])
    n = len(runs)

    # --- calibration: final confidence vs ground truth, all district-runs
    pairs = [(r["sentinel"][d]["confidence"], float(r["sentinel"][d]["affected"])) for r in runs for d in CODES]
    brier = _mean([(p - y) ** 2 for p, y in pairs])
    base_pairs = [
        (1.0 if r["baseline"][d]["episodes"] else 0.0, float(r["sentinel"][d]["affected"])) for r in runs for d in CODES
    ]
    brier_base = _mean([(p - y) ** 2 for p, y in base_pairs])
    bins = []
    for k in range(10):
        lo, hi = k / 10, (k + 1) / 10
        sel = [(p, y) for p, y in pairs if lo <= p < hi or (k == 9 and p == 1.0)]
        if sel:
            bins.append(
                {
                    "lo": lo,
                    "hi": hi,
                    "n": len(sel),
                    "predicted": _mean([p for p, _ in sel]),
                    "observed": _mean([y for _, y in sel]),
                }
            )

    # --- groundedness, forecast, latency
    total = sum(r["claims"]["total"] for r in runs)
    grounded = sum(r["claims"]["grounded"] for r in runs)
    cov = [r["forecast"]["coverage"] for r in runs if r["forecast"]["coverage"] is not None]
    mape = [r["forecast"]["mape"] for r in runs if r["forecast"]["mape"] is not None]
    lat = sorted(r["latency_ms"] for r in runs)

    # --- fairness: outbreak runs grouped by primary district
    fair = []
    by_d: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in ob:
        by_d[r["primary"]].append(r)
    for d in CODES:
        rs = by_d.get(d, [])
        fair.append(
            {
                "district": d,
                "name": by_code(d).name,
                "runs": len(rs),
                "low_reporting": by_code(d).completeness < 0.96,
                "sensitivity_e2": _mean([float(TIERS.index(prim(r)[0]["max_tier"]) >= 2) for r in rs]),
                "sensitivity_e3": _mean([float(prim(r)[0]["max_tier"] == "E3") for r in rs]),
                "sensitivity_baseline": _mean([float(prim(r)[1]["first_alarm"] is not None) for r in rs]),
                "detect_delay_days": _median(
                    [float(prim(r)[0]["detect_day"] - r["onset"]) for r in rs if prim(r)[0]["detect_day"] is not None]
                ),
            }
        )

    # --- outcome table: highest tier reached anywhere, per scenario
    outcomes: dict[str, dict[str, int]] = {}
    for r in runs:
        t = max((r["sentinel"][d]["max_tier"] for d in CODES), key=TIERS.index)
        row = outcomes.setdefault(r["scenario"], {"runs": 0, **{x: 0 for x in TIERS}, "baseline_alarm": 0})
        row["runs"] += 1
        row[t] += 1
        row["baseline_alarm"] += any(r["baseline"][d]["episodes"] for d in CODES)

    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "runs": n,
        "elapsed_s": round(elapsed_s, 1),
        "checkpoints": list(CHECKPOINTS),
        "window_days": window_days,
        "llm_mode": "offline (rule-based agents)",
        "baseline": {"rule": f"{'.'.join(BASELINE_SERIES)} robust z >= {BASELINE_Z:g} (single source, single day)"},
        "detection": {
            "outbreak_runs": len(ob),
            "sensitivity_e2": _mean([float(x) for x in sens_e2]),
            "sensitivity_e3": _mean([float(x) for x in sens_e3]),
            "sensitivity_baseline": _mean([float(x) for x in sens_base]),
            "lead_time_days_median": _median([float(x) for x in lead]),
            "lead_time_days_mean": _mean([float(x) for x in lead]),
            "detect_delay_days_median": _median([float(x) for x in det_delay]),
            "baseline_delay_days_median": _median([float(x) for x in base_delay]),
            "e3_delay_days_median": _median([float(x) for x in e3_delay]),
        },
        "false_alarms": {
            "sentinel_e2_per_90d": fa_sent_e2 / n * per90,
            "sentinel_e1_per_90d": fa_sent_e1 / n * per90,
            "baseline_per_90d": fa_base / n * per90,
            "note": f"statewide (8 districts), unaffected districts only, counted over days {WINDOW[0]}-{WINDOW[1]} "
            "and scaled to 90 days",
        },
        "intervention": {
            "e3_events": tp_e3 + fp_e3,
            "e3_true": tp_e3,
            "e3_false": fp_e3,
            "e3_precision": tp_e3 / (tp_e3 + fp_e3) if tp_e3 + fp_e3 else None,
            "false_intervention_rate": fp_e3 / (tp_e3 + fp_e3) if tp_e3 + fp_e3 else 0.0,
            "baseline_precision": tp_base / (tp_base + fp_base) if tp_base + fp_base else None,
            "baseline_false_rate": fp_base / (tp_base + fp_base) if tp_base + fp_base else None,
        },
        "calibration": {"brier": brier, "brier_baseline": brier_base, "bins": bins, "pairs": len(pairs)},
        "agents": {
            "claims": total,
            "grounded": grounded,
            "groundedness": grounded / total if total else None,
            "hallucination_rate": (total - grounded) / total if total else None,
            "tokens_per_analysis": 0,
            "cost_per_analysis_usd": 0.0,
        },
        "forecast": {
            "target": "bed occupancy, primary district",
            "made_on_day": FORECAST_FROM,
            "p10_p90_coverage": _mean(cov),
            "mape_p50": _mean(mape),
        },
        "latency": {"mean_ms": _mean(lat), "p95_ms": lat[int(0.95 * (len(lat) - 1))] if lat else None},
        "fairness": fair,
        "outcomes": outcomes,
        "adaptation": adaptation(),
        "runs_detail": [
            {
                "scenario": r["scenario"],
                "seed": r["seed"],
                "primary": r["primary"],
                "max_tier": max((r["sentinel"][d]["max_tier"] for d in CODES), key=TIERS.index),
                "baseline_alarms": sum(len(r["baseline"][d]["episodes"]) for d in CODES),
            }
            for r in runs
        ],
    }


def adaptation() -> list[dict[str, Any]]:
    """Scenario-injection check: inject each overlay onto a quiet world; time the re-analysis and check the tier
    moved correctly (outbreak -> E3 in the cluster; decoys never reach E3)."""
    from app.agents.lab import evidence_delta
    from app.config import get_settings

    seed = get_settings().simulation.demo_seed
    out = []
    for name in ("true_outbreak", "holiday_spike", "reporting_change", "lab_backlog", "weather_driven"):
        d = evidence_delta(("noise_only",), name, seed, with_hypotheses=False)
        max_after = max((x.after for x in d.districts), key=TIERS.index)
        ok = max_after == "E3" if name == "true_outbreak" else max_after != "E3"
        out.append(
            {"scenario": name, "seconds": round(d.latency_ms / 1000, 2), "max_tier_after": max_after, "correct": ok}
        )
    return out


# ------------------------------------------------------------------ driver


def evaluate(
    n: int = 100,
    workers: int | None = None,
    progress: Callable[[int, int], None] | None = None,
    path: Path | None = REPORT_PATH,
) -> dict[str, Any]:
    specs = run_specs(n)
    workers = workers or max(1, min(12, (os.cpu_count() or 2) - 2))
    t0 = time.perf_counter()
    runs: list[dict[str, Any]] = []
    if workers == 1:
        for k, s in enumerate(specs):
            runs.append(run_one(s))
            if progress:
                progress(k + 1, n)
    else:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            futs = [ex.submit(run_one, s) for s in specs]
            for k, fut in enumerate(as_completed(futs)):
                runs.append(fut.result())
                if progress:
                    progress(k + 1, n)
    runs.sort(key=lambda r: r["i"])
    report = summarize(runs, time.perf_counter() - t0)
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=1, default=float), encoding="utf-8")
    return report


def load_report(path: Path = REPORT_PATH) -> dict[str, Any] | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def main() -> None:
    ap = argparse.ArgumentParser(description="Sentinel evaluation harness")
    ap.add_argument("--runs", type=int, default=100)
    ap.add_argument("--workers", type=int, default=None)
    args = ap.parse_args()
    rep = evaluate(args.runs, args.workers, progress=lambda k, n: print(f"\r{k}/{n} runs", end="", flush=True))
    print()
    d, fa, iv = rep["detection"], rep["false_alarms"], rep["intervention"]
    print(f"runs={rep['runs']} in {rep['elapsed_s']}s")
    print(
        f"sensitivity E2={d['sensitivity_e2']:.2f} E3={d['sensitivity_e3']:.2f} "
        f"baseline={d['sensitivity_baseline']:.2f}"
    )
    print(f"lead time vs baseline (median days)={d['lead_time_days_median']}")
    print(f"false alarms /90d: sentinel E2={fa['sentinel_e2_per_90d']:.2f} baseline={fa['baseline_per_90d']:.2f}")
    print(f"E3 precision={iv['e3_precision']} false-intervention rate={iv['false_intervention_rate']:.3f}")
    print(f"brier={rep['calibration']['brier']:.3f} (baseline {rep['calibration']['brier_baseline']:.3f})")
    print(f"report -> {REPORT_PATH}")


if __name__ == "__main__":
    main()
