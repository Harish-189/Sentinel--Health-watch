import numpy as np

from app.agents.orchestrator import run_analysis
from app.analysis.forecast import forecast_capacity


def _fc(scenario: str, district: str = "D3", intervention: bool = False):  # type: ignore[no-untyped-def]
    bundle = run_analysis(scenario, seed=42)
    return forecast_capacity(bundle.context, district, intervention=intervention)


def test_bands_are_ordered_and_widen() -> None:
    fc = _fc("true_outbreak")
    for band in (fc.beds, fc.icu):
        p10, p50, p90 = map(np.array, (band.p10, band.p50, band.p90))
        assert (p10 <= p50).all() and (p50 <= p90).all()
        assert (p90 - p10)[-1] > (p90 - p10)[0]
    assert len(fc.beds.p50) == len(fc.days) == 14


def test_outbreak_raises_breach_probability() -> None:
    hot = _fc("true_outbreak")
    calm = _fc("noise_only")
    assert max(hot.breach_prob_beds) > max(calm.breach_prob_beds)


def test_intervention_lowers_projection() -> None:
    base = _fc("true_outbreak")
    cut = _fc("true_outbreak", intervention=True)
    assert cut.beds.p50[-1] < base.beds.p50[-1]
    assert max(cut.breach_prob_beds) <= max(base.breach_prob_beds)


def test_forecast_is_seeded() -> None:
    assert _fc("true_outbreak") == _fc("true_outbreak")
