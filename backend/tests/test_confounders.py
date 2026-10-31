from app.agents.orchestrator import run_analysis


def _cf(scenario: str | tuple[str, ...], district: str = "D3", seed: int = 42) -> dict[str, str]:
    a = run_analysis(scenario, seed=seed).assessment(district)
    return {c.name: c.status for c in a.confounders}


def test_outbreak_rules_out_confounders() -> None:
    cf = _cf("true_outbreak")
    assert cf["holiday"] == "ruled_out"
    assert cf["reporting_change"] == "ruled_out"
    assert cf["lab_backlog"] == "ruled_out"
    assert cf["seasonal"] == "ruled_out"


def test_each_confounder_scenario_triggers_its_check() -> None:
    assert _cf("holiday_spike")["holiday"] == "explains"
    assert _cf("reporting_change")["reporting_change"] == "explains"
    assert _cf("lab_backlog")["lab_backlog"] == "explains"
    assert _cf("weather_driven")["weather"] == "explains"


def test_confounders_carry_numbers_and_ids() -> None:
    a = run_analysis("holiday_spike", seed=42).assessment("D3")
    hol = next(c for c in a.confounders if c.name == "holiday")
    assert hol.confounder_id == "CF-D3-holiday"
    assert "explained_share" in hol.values
    assert hol.summary
