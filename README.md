# Sentinel: public-health early warning for Tamil Nadu (synthetic)

Fuses clinic visits, pharmacy sales, school absenteeism, mobility and lab data (aggregated by district) to catch
outbreaks early **without** escalating holidays, reporting changes or lab backlogs. A deterministic evidence gate
sets the tier (E0–E3); LLM agents only explain and propose; every claim cites evidence IDs; nothing executes
without human approval.

> **Synthetic data only.** City names are real; every number (including "simulated catchment population") is simulated.
> Population-level signals only. No individual diagnosis.

## Run (one command, works offline after first install)

Requirements: Python 3.11+, Node 20+.

```bash
./start.sh                 # macOS / Linux / Git Bash
.\start.ps1                # Windows PowerShell
```

Open **http://localhost:5173**. Ports: `API_PORT` / `WEB_PORT` env vars (bash) or `-ApiPort` / `-WebPort` (PowerShell).
First start creates the venv, installs deps, warms the demo and builds the evaluation report (~2 min, in the background).

- **LLM:** offline rule-based agents by default ("Degraded mode"). For live Claude: set `ANTHROPIC_API_KEY` (optionally `LLM_MODE=online`, `ANTHROPIC_MODEL`). Results are cached; per-analysis call budget in `backend/config.yaml`.
- **Tests:** `cd backend && .venv/Scripts/python -m pytest -q` (or `.venv/bin/python`), `ruff check .`, `mypy app`
- **Evaluation:** `cd backend && python -m app.eval.harness --runs 100` → `data/generated/eval/report.json`

## Demo script (≈5 minutes)

1. **Command Center.** The western cluster (Erode, Coimbatore, Salem) is **E3**; Chennai (festival) and Madurai (new reporting network) sit at **E1**: decoys the gate refuses to escalate. Point out the callouts (+% vs expected), State Pulse, and **▶ Replay**: watch E1 → E2 → E3 emerge over ~2 weeks.
2. **Click Erode → Investigation.** The live stepper streams Detect → … → Recommend. Show ranked hypotheses (epidemic and non-epidemic), **7/7 claims grounded**, click an evidence chip, the **Why E3?** criteria and the PASS/FAIL alternative-explanations checklist.
3. **Capacity Forecast.** P10–P90 bands; bed breach **≥99%**; toggle **Apply intervention** and watch the risk drop.
4. **Action Queue.** Approve "Pre-position capacity" → execution receipt (ticket ID); reject another with a reason; show the hash-chained audit log. Hit **KILL SWITCH** (reason required) → approvals blocked.
5. **Scenario Lab (jury surprise).** Inject **Lab backlog** → Erode drops **E3 → E2** in about a second, with a plain-language "why". Then **Use sample CSV** (GI cluster in Tiruchirappalli) → it lights up. Click **Try PII** → rejected at ingestion. **Apply to console** to propagate.
6. **Evaluation.** 100 seeded simulations vs a single-threshold baseline: false-intervention rate, false alarms/90 days, lead time, calibration curve, fairness by district (incl. low-reporting Tirunelveli), adaptation timings.
7. **Demo reset** (top bar) returns to a clean state; the audit log keeps the record.

## Layout

`backend/app/{data,detection,analysis,agents,governance,eval}` · `backend/tests` · `frontend/src` · thresholds in `backend/config.yaml` · see `SPEC.md`, `CLAUDE.md`.
