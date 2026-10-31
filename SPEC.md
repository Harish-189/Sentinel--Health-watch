# SPEC.md: Sentinel, Public Health Early-Warning Intelligence

> TCS AI Hackathon, Challenge 14 (Theme 3: AI for Impact). Population-level signals only. No individual diagnosis.
> Read this file at the start of each feature. Build in the phase order in section 12. Do not skip ahead.

## 1. One-line pitch
A multi-agent system that watches aggregate health signals, detects anomalies, tests them against non-epidemic explanations, grades the evidence with a deterministic gate, forecasts hospital capacity impact, and recommends actions that a human must approve.

## 2. Core principle (the judging differentiator)
**Correlation is not intervention-grade evidence.** Every signal is graded on an evidence ladder by deterministic code. The LLM can explain and propose, but it can never raise an evidence tier.

| Tier | Name | Meaning | Allowed actions |
|---|---|---|---|
| E0 | Noise | Within expected seasonal range | None |
| E1 | Watch | Single-source anomaly or uncorrelated | Monitor, request data validation |
| E2 | Corroborated | At least 3 independent sources agree, confounders not ruled out or only partly | Targeted investigation, lab sampling request |
| E3 | Intervention-grade | E2 plus confounders rejected, lab confirmation, spatial coherence, persistence | Public advisories, capacity pre-positioning (human approval required) |

## 3. Stakeholders
District health officer (decider), hospital capacity planner, epidemiologist (reviewer), data steward (privacy), jury/mentors (evaluators).

## 4. Capability coverage (must show at least 5 of 7; target all 7)
1. Reason across sources: cross-source correlation and lead-lag analysis.
2. Plan multi-step: orchestrator pipeline (section 6).
3. Act through tools: tool-calling agents plus simulated enterprise actions (ticket, advisory draft, lab request).
4. Verify: Verifier agent checks every claim against evidence IDs and recomputed numbers.
5. Adapt: Scenario Lab injects surprises and the system re-evaluates and explains the delta.
6. Human control: approval queue, edit, reject, audit log, and a kill switch.
7. Evaluate: benchmark harness with ground-truth simulated outbreaks.

## 5. Data (synthetic, privacy-by-design)
No real data is used. The simulator generates 2 years of daily data, 8 districts.

**Sources (all aggregate counts, no person-level fields anywhere):**
- `clinic_visits`: by syndrome group (respiratory, gastrointestinal, febrile_rash, other)
- `lab`: tests_done, positives, by pathogen panel (generic names: panel_A, panel_B)
- `pharmacy`: units by class (antipyretic, ors_rehydration, antiviral, cough_cold)
- `absenteeism`: school and workplace absence rate
- `environment`: temperature, rainfall, humidity, AQI
- `mobility`: aggregate mobility index (relative to baseline)
- `capacity`: beds_total, beds_occupied, icu_total, icu_occupied per hospital zone
- `meta`: reporting_sites_expected, reporting_sites_received, schema_version (to detect reporting changes)

**Privacy rules (enforced in `data/privacy.py`, tested):**
- Small-cell suppression: any count below `K_MIN=5` is suppressed to null and flagged.
- Schema allowlist: ingestion rejects any column matching PII patterns (name, id, dob, address, phone).
- Optional Laplace noise on exported or displayed small counts (config flag).
- No individual-level tables exist. The LLM only ever receives aggregated evidence JSON.

**Simulator scenarios (`data/scenarios.py`, seeded, reproducible):**
- `true_outbreak`: respiratory or GI surge in a district cluster, with lead-lag across sources (pharmacy and absenteeism lead, clinic follows, lab confirms, admissions lag).
- `holiday_spike`: clinic or pharmacy surge with a calendar explanation.
- `reporting_change`: a site joins or leaves, producing a step change with no real change.
- `lab_backlog`: lab positives jump because of batch reporting.
- `weather_driven`: heat or AQI drives respiratory visits (non-infectious).
- `seasonal_peak`: expected annual rise.
- `noise_only`: control with no event.

## 6. Pipeline (orchestrator, `agents/orchestrator.py`)
`Ingest → Validate → Detect → Correlate → Confounder-check → Hypothesize → Verify → Grade → Forecast → Recommend → Human gate → Audit → (Adapt loop)`

| Step | Component | LLM? | Notes |
|---|---|---|---|
| Validate | data quality checks | no | completeness, schema, suppression |
| Detect | seasonal baseline (day-of-week + trend + holiday calendar) + robust z-score + EWMA/CUSUM | no | per source, per district |
| Correlate | cross-correlation with lag, cross-source agreement, spatial coherence | no | outputs independent-source count |
| Confounder-check | holiday calendar, reporting completeness, seasonal expectation, lab batch pattern, weather | no | each returns pass, fail, or inconclusive with evidence |
| Hypothesize | Hypothesis agent | yes | outputs ranked hypotheses INCLUDING non-epidemic ones; each cites evidence IDs |
| Verify | Verifier | rule check first, LLM critic second | rejects any claim lacking a valid evidence ID or with a numeric mismatch |
| Grade | evidence gate | no | deterministic tier E0-E3 plus confidence |
| Forecast | capacity forecaster | no | Monte Carlo growth model, 14-day horizon, with bands |
| Recommend | Recommender | yes (constrained) | picks from an action catalog gated by tier; cannot invent actions |
| Human gate | approvals | no | nothing executes without approval |
| Adapt | re-run on new evidence or scenario | mixed | emits an "evidence delta" explanation |

## 7. Evidence gate rules (`analysis/evidence.py`, thresholds in `config.yaml`)
- E1 if any source `robust_z >= 3` for at least 2 consecutive days.
- E2 if at least 3 independent sources are anomalous within a lead-lag-consistent window AND the data-quality check passes.
- E3 if E2 AND all of: lab positivity rising with tests_done stable (not a backlog), spatial coherence (at least 2 adjacent districts or a dose-response gradient), persistence of at least 3 days after the first detection, and all confounders `fail` (i.e., ruled out) or residual excess after confounder adjustment of at least 30 percent.
- Downgrade immediately if reporting completeness drops below 90 percent, a holiday explains at least 70 percent of excess, or contradicting evidence arrives.
- Confidence is a logistic score over: independent_sources, mean_z, lag_consistency, spatial_coherence, persistence_days, confounder_residual. It is Platt-calibrated on the eval harness output. Report it as a point estimate plus a bootstrap interval.

## 8. Capacity forecast (`analysis/forecast.py`)
- Input: recent admissions growth rate, district population scaling, length-of-stay distribution.
- Method: stochastic growth projection with Monte Carlo (n=1000), producing P10/P50/P90 bands for 14 days.
- Output: projected beds and ICU occupancy vs. capacity, and the day of expected breach with probability.
- Always show the uncertainty band. Never show a single line as truth.

## 9. Action catalog (`agents/tools.py`, simulated enterprise systems)
| Action | Min tier | Executes as |
|---|---|---|
| `request_data_validation` | E1 | simulated ticket to data steward |
| `increase_monitoring` | E1 | config change to watchlist |
| `request_lab_sampling` | E2 | simulated lab request |
| `draft_clinician_advisory` | E2 | draft only, human edits |
| `prepose_capacity` (staff/beds) | E3 | simulated capacity plan |
| `draft_public_advisory` | E3 | draft only, human edits |

All actions create a `PendingAction`. A human must Approve, Edit, or Reject with a reason. Everything is written to an append-only audit log. No action touches a person.

## 10. Frontend (React + Vite + TypeScript + Tailwind + ECharts)
Visual identity: dark "mission control" theme, a district heat map, tier-colored alert chips (E0-E3), evidence-delta animations. Not a generic admin template.

Pages:
1. **Command Center**: district map, active signals with tier chips, system status, kill switch.
2. **Signal Explorer**: multi-source small-multiples with baseline bands and anomaly markers; lead-lag view.
3. **Investigation**: the AI case file with ranked hypotheses (epidemic AND non-epidemic), evidence graph (claim → evidence IDs → raw series), alternative explanations with pass/fail, confidence plus interval, "why not E3?" panel.
4. **Capacity Forecast**: bands with breach probability, and a what-if (intervention on or off).
5. **Action Queue**: pending actions with approve, edit, reject, plus the audit log.
6. **Evaluation**: live metrics from the harness vs. the single-threshold baseline.
7. **Scenario Lab** (jury surprise): inject a scenario or upload a new CSV mid-demo; the system re-runs and shows the evidence delta (what changed, which tier moved, why).

## 11. API (FastAPI)
- `GET /signals`, `GET /series?source&district`
- `POST /analyze` (runs the pipeline, streams steps via SSE)
- `GET /cases/{id}` (hypotheses, evidence, tier, confidence)
- `GET /forecast/{district}`
- `GET /actions`, `POST /actions/{id}/decision`
- `GET /audit`
- `POST /scenario/inject`, `POST /data/upload`
- `GET /eval/report`, `POST /eval/run`
- `POST /killswitch`

## 12. Build phases (each ends with a commit and passing tests)
- **P0**: scaffold, config, CI, Dockerfile, CLAUDE.md in place.
- **P1**: simulator, all 7 scenarios, privacy module, tests.
- **P2**: baseline + anomaly detectors, with unit tests against injected scenarios.
- **P3**: correlation, confounder checks, evidence gate, with tests per scenario (the holiday, reporting_change, and lab_backlog scenarios must NOT reach E3).
- **P4**: forecaster, with tests.
- **P5**: LLM layer (hypothesis, verifier, recommender), offline fallback, token caps, response caching.
- **P6**: governance (approvals, audit, kill switch, guardrails).
- **P7**: eval harness, with 200 simulated runs and metrics report.
- **P8**: frontend pages 1-5.
- **P9**: Scenario Lab and Evaluation pages, plus the SSE live pipeline view.
- **P10**: polish, Docker compose, deployment, the 5-slide deck, and a demo script rehearsal.

## 13. Evaluation (`eval/harness.py`)
Run N=200 seeded simulations across all scenarios against ground truth. Compare to a baseline (a single-source z-score threshold).
Metrics:
- Detection lead time (days earlier than baseline), sensitivity on true outbreaks
- False alarms per 90 days, and E3 precision (the false-intervention rate is the headline)
- Confidence calibration (Brier score, reliability curve)
- Groundedness: percent of LLM claims that pass verification
- Hallucination rate: claims rejected by the Verifier
- Forecast error: MAPE/coverage of the P10-P90 band on admissions
- Latency per analysis, and tokens/cost per analysis
- Fairness: detection sensitivity and lead time by district (including low-reporting districts)
- Adaptation: time and correctness of tier change after the scenario injection

## 14. Responsible AI (map to NIST AI RMF GenAI Profile: Govern, Map, Measure, Manage)
- **Privacy**: aggregate-only, k-suppression, PII schema guard, no individual data to the LLM.
- **Security**: secrets in env, input validation, no code execution from LLM output, rate limits.
- **Hallucination control**: structured outputs, evidence-ID citation required, Verifier rejects ungrounded claims, deterministic tiering.
- **Human oversight**: approval queue, edit, reject with reason, kill switch, audit log.
- **Failure handling**: the LLM down or over budget triggers offline rule-based reasoning, a clearly labeled degraded mode, and a data-quality failure that blocks the tier upgrade.
- **Bias/fairness**: reporting-completeness bias between districts is measured and displayed; low-data districts get wider uncertainty, not silent exclusion.
- **Explicit limits**: no individual diagnosis, no personalized prediction, no autonomous intervention. A guardrail test asserts this.

## 15. Token and cost controls (in the design, not just in the workflow)
- The LLM receives compact evidence JSON (summary stats, IDs), never raw series.
- A max LLM calls per analysis (config), a structured output schema, and prompt caching for the static instructions.
- Cache the LLM result by the hash of the evidence bundle; only re-call when evidence changes.
- A smaller model for hypothesis drafting and the critic, a stronger model only for the final case summary (configurable).

## 16. Definition of done
- [ ] All 7 scenarios behave as expected; holiday, reporting_change, lab_backlog never reach E3.
- [ ] The Verifier blocks a deliberately injected ungrounded claim in a test.
- [ ] Nothing executes without human approval (test).
- [ ] The PII guard rejects a bad upload (test).
- [ ] The Scenario Lab produces a visible evidence delta in under 10 seconds.
- [ ] The eval report is generated and shown in the UI.
- [ ] Runs from `docker compose up`.
- [ ] A 5-slide deck: Problem, Architecture, Working prototype, Evidence and evaluation and Responsible AI, Dynamic adaptation.
