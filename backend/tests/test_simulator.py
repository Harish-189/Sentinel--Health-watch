import numpy as np
import pandas as pd
import pytest

from app.data.districts import CODES, neighbors
from app.data.scenarios import CORE_SCENARIOS, FESTIVAL, OVERLAYS, simulate
from app.data.schema import METRICS


def _series(df: pd.DataFrame, district: str, source: str, metric: str) -> np.ndarray:
    sub = df[(df.district == district) & (df.source == source) & (df.metric == metric)]
    return sub.sort_values("day")["value"].to_numpy()


def test_seeded_and_reproducible() -> None:
    a = simulate("true_outbreak", seed=7).df
    b = simulate("true_outbreak", seed=7).df
    c = simulate("true_outbreak", seed=8).df
    pd.testing.assert_frame_equal(a, b)
    assert not a["value"].equals(c["value"])


@pytest.mark.parametrize("name", CORE_SCENARIOS)
def test_every_scenario_produces_all_series(name: str) -> None:
    sim = simulate(name)
    df = sim.df
    expected = {(m.source, m.metric) for m in METRICS if not m.derived}
    assert set(zip(df.source, df.metric, strict=True)) == expected
    assert set(df.district) == set(CODES)
    assert list(df.columns) == ["day", "date", "district", "source", "metric", "value"]
    assert sim.truth.is_epidemic == (name == "true_outbreak")


def test_districts_have_adjacency() -> None:
    assert all(neighbors(c) for c in CODES)
    assert "D3" in neighbors("D1") and "D1" in neighbors("D3")


def test_outbreak_lab_positivity_rises_tests_stable() -> None:
    df = simulate("true_outbreak").df
    tests = _series(df, "D3", "lab", "panel_A_tests")
    pos = _series(df, "D3", "lab", "panel_A_positives")
    before, after = slice(660, 700), slice(720, 730)
    assert pos[after].sum() / tests[after].sum() > 2 * pos[before].sum() / tests[before].sum()
    assert tests[after].mean() < 1.6 * tests[before].mean()


def test_lab_backlog_batches_with_flat_positivity() -> None:
    df = simulate("lab_backlog").df
    tests = _series(df, "D3", "lab", "panel_A_tests")
    pos = _series(df, "D3", "lab", "panel_A_positives")
    tail = tests[700:]
    assert tail.max() > 3 * np.median(tests[600:700])  # dump days
    assert np.median(tail) < 0.3 * np.median(tests[600:700])  # trickle days
    ctrl = simulate("noise_only").df  # same season, no batching
    c_tests = _series(ctrl, "D3", "lab", "panel_A_tests")
    c_pos = _series(ctrl, "D3", "lab", "panel_A_positives")
    rate = pos[700:].sum() / tests[700:].sum()
    assert abs(rate - c_pos[700:].sum() / c_tests[700:].sum()) < 0.015


def test_reporting_change_updates_meta() -> None:
    df = simulate("reporting_change").df
    sites = _series(df, "D3", "meta", "sites_expected")
    schema = _series(df, "D3", "meta", "schema_version")
    assert sites[700] == sites[699] + 6
    assert schema[699] == 1 and schema[700] == 2


def test_holiday_spike_declares_festival() -> None:
    sim = simulate("holiday_spike")
    assert FESTIVAL in sim.calendar.holidays.values()


def test_weather_driven_raises_aqi_not_positivity() -> None:
    df = simulate("weather_driven").df
    aqi = _series(df, "D3", "environment", "aqi")
    assert aqi[703:712].mean() > 1.8 * aqi[660:700].mean()
    tests = _series(df, "D3", "lab", "panel_A_tests")
    pos = _series(df, "D3", "lab", "panel_A_positives")
    assert pos[703:712].sum() / tests[703:712].sum() < 0.12


def test_composed_overlays() -> None:
    sim = simulate(["true_outbreak", "source_outage"])
    pharm = sim.df[(sim.df.source == "pharmacy") & (sim.df.day >= 725)]
    assert pharm["value"].isna().all()
    assert set(OVERLAYS) >= {"contradicting_lab", "source_outage"}


def test_no_person_level_columns() -> None:
    df = simulate("noise_only").df
    assert len(df) == len(CODES) * 730 * len([m for m in METRICS if not m.derived])
