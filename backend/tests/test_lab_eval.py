import pytest
from fastapi.testclient import TestClient

from app.agents.lab import evidence_delta
from app.agents.orchestrator import run_analysis
from app.data.districts import CODES
from app.data.privacy import PIIViolation
from app.data.uploads import UploadError, parse_upload, register
from app.eval.harness import run_specs, summarize
from app.main import app

client = TestClient(app)
SEED = 8


# ---------------------------------------------------------------- eval harness


def test_run_specs_are_deterministic_and_rotate_primaries() -> None:
    a, b = run_specs(100), run_specs(100)
    assert a == b and len(a) == 100
    outbreak = [s for s in a if s["scenario"] == "true_outbreak"]
    assert {s["primary"] for s in outbreak} == set(CODES)  # fairness: every district hosts outbreaks
    assert {s["scenario"] for s in a} >= {"holiday_spike", "reporting_change", "lab_backlog", "noise_only"}


def _fake_run(scenario: str, primary: str, e3: set[str], base_eps: dict[str, list[int]]) -> dict[str, object]:
    affected = {primary} if scenario == "true_outbreak" else set()
    return {
        "i": 0,
        "scenario": scenario,
        "seed": 1,
        "primary": primary,
        "epidemic": bool(affected),
        "affected": sorted(affected),
        "onset": 700,
        "latency_ms": 100.0,
        "sentinel": {
            d: {
                "max_tier": "E3" if d in e3 else "E0",
                "final_tier": "E0",
                "first": {
                    "E1": 706 if d in e3 else None,
                    "E2": 709 if d in e3 else None,
                    "E3": 712 if d in e3 else None,
                },
                "detect_day": 704 if d in e3 else None,
                "confidence": 0.9 if d in e3 else 0.02,
                "affected": d in affected,
            }
            for d in CODES
        },
        "baseline": {
            d: {"episodes": base_eps.get(d, []), "first_alarm": (base_eps.get(d) or [None])[0]} for d in CODES
        },
        "forecast": {"coverage": 0.8, "mape": 0.1, "n": 14},
        "claims": {"total": 4, "grounded": 4},
    }


def test_summary_scores_false_interventions_against_truth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.eval.harness.adaptation", lambda: [])
    runs = [
        _fake_run("true_outbreak", "ERD", {"ERD"}, {"ERD": [707], "CHN": [710]}),  # 1 true E3; 1 baseline false alarm
        _fake_run("holiday_spike", "CHN", {"CHN"}, {"CHN": [706, 712]}),  # a false E3
    ]
    rep = summarize(runs, 1.0)
    iv = rep["intervention"]
    assert iv["e3_true"] == 1 and iv["e3_false"] == 1 and iv["false_intervention_rate"] == 0.5
    assert rep["detection"]["lead_time_days_median"] == 3.0  # baseline 707 - sentinel 704
    assert rep["false_alarms"]["baseline_per_90d"] > rep["false_alarms"]["sentinel_e2_per_90d"]


# ---------------------------------------------------------------- uploads (privacy guardrail)


def test_upload_rejects_person_level_columns() -> None:
    with pytest.raises(PIIViolation):
        parse_upload("day,district,source,metric,value,patient_name\n720,TRY,clinic,respiratory,50,Ravi\n")


def test_upload_rejects_unknown_metrics_and_districts() -> None:
    with pytest.raises(UploadError):
        parse_upload("day,district,source,metric,value\n720,TRY,clinic,made_up,5\n")
    with pytest.raises(UploadError):
        parse_upload("day,district,source,metric,value\n720,XYZ,clinic,respiratory,5\n")


def test_upload_overrides_values_in_analysis() -> None:
    rows = "\n".join(f"{d},TRY,clinic,gastrointestinal,{400 + 20 * (d - 714)}" for d in range(714, 730))
    token = "upload:" + register(parse_upload("day,district,source,metric,value\n" + rows))
    a = run_analysis(("noise_only", token), seed=SEED)
    assert any(e.startswith("EV-TRY-CLI-gastrointestinal") for e in a.evidence)


# ---------------------------------------------------------------- scenario lab


@pytest.mark.parametrize("decoy", ["holiday_spike", "reporting_change", "lab_backlog"])
def test_injected_decoys_never_reach_e3(decoy: str) -> None:
    d = evidence_delta(("noise_only",), decoy, SEED, with_hypotheses=False)
    assert all(x.after != "E3" for x in d.districts)
    assert d.explanation and "deterministic" in d.explanation[-1]


def test_injected_outbreak_escalates_with_hypothesis_movement() -> None:
    d = evidence_delta(("noise_only",), "true_outbreak", SEED)
    assert any(x.after == "E3" and x.move > 0 for x in d.districts)
    epi = next(h for h in d.hypotheses if h.kind == "epidemic")
    assert epi.after > epi.before
    assert any(s.change == "new" for s in d.signals)


def test_inject_and_upload_endpoints() -> None:
    assert (
        client.post("/api/scenario/inject", json={"inject": "true_outbreak", "base": "true_outbreak"}).status_code
        == 400
    )
    r = client.post("/api/data/upload", json={"csv": "day,district,source,metric,value,dob\n1,TRY,clinic,other,1,x\n"})
    assert r.status_code == 422 and "PII" in r.json()["detail"]
    sample = client.get("/api/data/sample").json()["csv"]
    up = client.post("/api/data/upload", json={"csv": sample, "base": "noise_only", "seed": SEED})
    assert up.status_code == 200 and up.json()["upload"].startswith("upload:")
    assert any(x["district"] == "TRY" and x["after"] != "E0" for x in up.json()["delta"]["districts"])


def test_demo_reset_clears_actions() -> None:
    client.get("/api/casefile", params={"scenario": "true_outbreak", "seed": SEED})
    assert client.post("/api/demo-reset", json={"actor": "test"}).json()["ok"]
    assert client.get("/api/actions", params={"status": "pending"}).json() == []
    assert client.get("/api/audit").json()["verified"]
