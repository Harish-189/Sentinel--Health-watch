from fastapi.testclient import TestClient

from app.agents.orchestrator import run_analysis
from app.agents.timeline import _frame
from app.main import app

client = TestClient(app)


def test_series_endpoint_is_district_scoped() -> None:
    r = client.get("/api/series", params={"district": "ERD", "seed": 7})
    assert r.status_code == 200
    body = r.json()
    assert body["series"] and all(s["district"] == "ERD" for s in body["series"])
    assert all(a["district"] == "ERD" for a in body["anomalies"])


def test_timeline_frame_matches_gate_tiers() -> None:
    frame = _frame(("true_outbreak",), 7, 720)
    bundle = run_analysis(("true_outbreak",), seed=7, as_of=720)
    assert {d: f.tier for d, f in frame.districts.items()} == {a.district: a.gate.tier for a in bundle.assessments}


def test_unknown_scenario_is_404() -> None:
    assert client.get("/api/series", params={"scenario": "nope"}).status_code == 404
