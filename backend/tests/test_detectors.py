import numpy as np
import pytest

from app.data.privacy import apply_privacy
from app.data.scenarios import simulate
from app.detection.detectors import consecutive_runs, cusum, ewma, robust_scale
from app.detection.run import DetectionReport, detect_all


def _report(scenario: str | list[str], seed: int = 42) -> tuple[DetectionReport, int]:
    sim = simulate(scenario, seed=seed)
    return detect_all(apply_privacy(sim.df), holidays=sim.holidays), sim.truth.onset_day


@pytest.fixture(scope="module")
def outbreak() -> tuple[DetectionReport, int]:
    return _report("true_outbreak")


@pytest.fixture(scope="module")
def noise() -> tuple[DetectionReport, int]:
    return _report("noise_only")


# ---------------------------------------------------------------- unit: primitives


def test_robust_z_ignores_outliers_in_scale() -> None:
    resid = np.r_[np.random.default_rng(0).normal(0, 1, 500), [50.0] * 5]
    sigma = robust_scale(resid)
    assert 0.85 < sigma < 1.15


def test_ewma_and_cusum_alarm_on_sustained_shift() -> None:
    z = np.r_[np.zeros(20), np.full(10, 2.0)]
    e = ewma(z, lam=0.3)
    c = cusum(z, k=0.5)
    assert e[:20].max() == 0 and e[-1] > 1.5
    assert c[:20].max() == 0 and c[-1] > 5


def test_nan_does_not_break_ewma_or_cusum() -> None:
    z = np.array([0.0, np.nan, 3.0, np.nan, 3.0])
    assert np.isfinite(ewma(z, 0.3)).all()
    assert np.isfinite(cusum(z, 0.5)).all()


def test_consecutive_runs_requires_min_length_and_merges_gaps() -> None:
    flags = np.array([0, 1, 0, 0, 1, 1, 0, 1, 1, 1, 0, 0, 0, 0, 1], dtype=bool)
    runs = consecutive_runs(flags, min_len=2, merge_gap=1)
    assert runs == [(4, 9)]


# ---------------------------------------------------------------- scenario behavior


def test_true_outbreak_detected_in_primary_across_sources(outbreak: tuple[DetectionReport, int]) -> None:
    report, onset = outbreak
    d3 = [a for a in report.anomalies if a.district == "D3"]
    sources = {a.source for a in d3}
    assert {"clinic", "pharmacy", "absenteeism", "lab"} <= sources
    first = {s: min(a.start_day for a in d3 if a.source == s) for s in sources}
    assert all(onset <= day <= onset + 18 for day in first.values()), first


def test_true_outbreak_lead_lag_order(outbreak: tuple[DetectionReport, int]) -> None:
    report, _ = outbreak
    d3 = [a for a in report.anomalies if a.district == "D3"]
    first = {s: min(a.start_day for a in d3 if a.source == s) for s in {a.source for a in d3}}
    assert min(first["pharmacy"], first["absenteeism"]) <= first["clinic"] <= first["lab"] + 2


def test_true_outbreak_reaches_neighbor(outbreak: tuple[DetectionReport, int]) -> None:
    report, _ = outbreak
    assert {a.district for a in report.anomalies} & {"D1", "D2"}


def test_noise_only_few_false_alarms(noise: tuple[DetectionReport, int]) -> None:
    report, _ = noise
    # 8 districts x ~20 detected series x 90 days; allow a handful of spurious episodes
    assert len(report.anomalies) <= 6, [a.evidence_id for a in report.anomalies]


def test_regular_holidays_do_not_fire(noise: tuple[DetectionReport, int]) -> None:
    report, _ = noise
    harvest = 679  # Harvest Festival (Sep 10) falls inside the scored window
    assert not [a for a in report.anomalies if a.start_day - 1 <= harvest <= a.end_day + 1]


def test_seasonal_peak_absorbed_by_baseline() -> None:
    report, _ = _report("seasonal_peak")
    clinic_resp = [a for a in report.anomalies if a.metric == "respiratory"]
    assert len(clinic_resp) <= 1


def test_evidence_ids_are_unique_and_deterministic(outbreak: tuple[DetectionReport, int]) -> None:
    report, _ = outbreak
    ids = [a.evidence_id for a in report.anomalies]
    assert len(ids) == len(set(ids))
    again, _ = _report("true_outbreak")
    assert ids == [a.evidence_id for a in again.anomalies]


def test_series_carry_expected_band(outbreak: tuple[DetectionReport, int]) -> None:
    report, _ = outbreak
    s = report.series_for("D3", "clinic", "respiratory")
    assert len(s.days) == len(s.expected) == len(s.lower) == len(s.upper) == len(s.z)
    assert all(lo <= ex <= up for lo, ex, up in zip(s.lower, s.expected, s.upper, strict=True))


def test_detection_is_causal() -> None:
    """Scoring as of an earlier day must not see later data."""
    sim = simulate("true_outbreak")
    df = apply_privacy(sim.df)
    early = detect_all(df, holidays=sim.holidays, as_of=705)
    assert all(a.end_day <= 705 for a in early.anomalies)
    assert max(early.series_for("D3", "clinic", "respiratory").days) == 705
