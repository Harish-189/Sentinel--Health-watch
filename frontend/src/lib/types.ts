// Mirrors the backend pydantic models (app/analysis/models.py, app/agents/schemas.py, app/detection/models.py).
import type { Tier } from "../theme";

export interface District {
  code: string;
  name: string;
  population: number; // simulated catchment population
  lat: number;
  lon: number;
  neighbors: string[];
}

export interface Scenario {
  name: string;
  core: boolean;
  is_epidemic: boolean;
  description: string;
}

export interface LeadLag {
  source: string;
  reference: string;
  best_lag: number;
  corr: number;
}

export interface Signal {
  signal_id: string;
  district: string;
  syndrome: string;
  sources: string[];
  independent_sources: number;
  window_ids: string[];
  evidence_ids: string[];
  first_day: number;
  last_day: number;
  first_detection_day: number;
  persistence_days: number;
  mean_z: number;
  peak_z: number;
  mean_excess: number;
  onset_by_source: Record<string, number>;
  lag_consistency: number;
  lead_lag: LeadLag[];
  adjacent_districts: string[];
  adjacent_evidence: string[];
}

export type ConfounderStatus = "ruled_out" | "explains" | "inconclusive";

export interface ConfounderResult {
  confounder_id: string;
  name: string;
  label: string;
  status: ConfounderStatus;
  summary: string;
  explained_share: number;
  values: Record<string, number | string | boolean | null>;
  evidence_ids: string[];
}

export interface Criterion {
  criterion_id: string;
  key: string;
  tier: Tier;
  label: string;
  met: boolean;
  value: number | string | null;
  threshold: string;
  detail: string;
  evidence_ids: string[];
}

export interface GateResult {
  tier: Tier;
  raw_tier: Tier;
  criteria: Criterion[];
  downgrades: string[];
  residual_excess: number;
  data_quality: Record<string, number>;
}

export interface Confidence {
  point: number;
  low: number;
  high: number;
  features: Record<string, number>;
}

export interface Band {
  p10: number[];
  p50: number[];
  p90: number[];
}

export interface Forecast {
  forecast_id: string;
  district: string;
  as_of: number;
  intervention: boolean;
  days: number[];
  dates: string[];
  beds: Band;
  icu: Band;
  beds_total: number;
  icu_total: number;
  history_days: number[];
  history_beds: (number | null)[];
  history_icu: (number | null)[];
  breach_prob_beds: number[];
  breach_prob_icu: number[];
  breach_day_beds: number | null;
  breach_day_icu: number | null;
  growth_rate: number;
  growth_se: number;
}

export interface Assessment {
  district: string;
  name: string;
  signal: Signal | null;
  confounders: ConfounderResult[];
  gate: GateResult;
  confidence: Confidence;
  forecast: Forecast;
}

export interface EvidenceItem {
  id: string;
  kind: string;
  district: string | null;
  summary: string;
  data: Record<string, unknown>;
}

export interface AnalysisBundle {
  scenario: string[];
  seed: number;
  as_of: number;
  as_of_date: string;
  primary: string;
  assessments: Assessment[];
  evidence: Record<string, EvidenceItem>;
}

export interface SeriesDetection {
  series_id: string;
  district: string;
  source: string;
  metric: string;
  log_scale: boolean;
  direction: string;
  sigma: number;
  days: number[];
  dates: string[];
  observed: (number | null)[];
  expected: number[];
  lower: number[];
  upper: number[];
  z: (number | null)[];
  ewma: number[];
  cusum: number[];
}

export interface Anomaly {
  evidence_id: string;
  series_id: string;
  district: string;
  source: string;
  metric: string;
  start_day: number;
  end_day: number;
  start_date: string;
  end_date: string;
  peak_z: number;
  mean_z: number;
  days_flagged: number;
  persistence_days: number;
  excess_pct: number;
  first_signal_day: number;
}

export interface SeriesResponse {
  district: string;
  as_of: number;
  as_of_date: string;
  series: SeriesDetection[];
  anomalies: Anomaly[];
}

export interface DistrictFrame {
  tier: Tier;
  confidence: number;
  sources: number;
  syndrome: string | null;
  peak_z: number | null;
}

export interface Timeline {
  scenario: string[];
  seed: number;
  onset_day: number;
  frames: { as_of: number; date: string; districts: Record<string, DistrictFrame> }[];
}

export interface NumberRef {
  evidence_id: string;
  field: string;
  value: number;
}

export interface Claim {
  claim_id: string;
  text: string;
  evidence_ids: string[];
  numbers: NumberRef[];
}

export interface Hypothesis {
  hypothesis_id: string;
  title: string;
  kind: "epidemic" | "non_epidemic";
  category: string;
  probability: number;
  summary: string;
  claims: Claim[];
  supporting_ids: string[];
  contradicting_ids: string[];
}

export interface Verification {
  total_claims: number;
  grounded_claims: number;
  groundedness: number;
  hallucination_rate: number;
  dropped: { hypothesis_id: string; claim_id: string; text: string; reason: string }[];
  dropped_hypotheses: string[];
  critic: "llm" | "skipped" | "rules_only";
}

export interface Recommendation {
  action: string;
  title: string;
  min_tier: string;
  rationale: string;
  evidence_ids: string[];
  params: Record<string, unknown>;
  pending_ref: string | null;
  source: "llm" | "rules";
}

export interface LLMUsage {
  mode: "online" | "degraded";
  degraded_reason: string | null;
  model: string;
  fast_model: string;
  calls: number;
  cache_hits: number;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_write_tokens: number;
  cost_usd: number;
}

export type StepStatus = "running" | "done" | "skipped" | "blocked" | "degraded";

export interface StepEvent {
  step: string;
  status: StepStatus;
  ms: number;
  detail: string;
}

export interface CaseFile {
  scenario: string[];
  seed: number;
  as_of: number;
  as_of_date: string;
  district: string;
  district_name: string;
  tiers: Record<string, Tier>;
  assessment: Assessment;
  hypotheses: Hypothesis[];
  verification: Verification;
  recommendations: Recommendation[];
  usage: LLMUsage;
  latency_ms: number;
  steps: StepEvent[];
  evidence: Record<string, EvidenceItem>;
  tier_explanation: string;
}

export interface PendingAction {
  ref: string;
  action: string;
  title: string;
  district: string;
  signal_tier: Tier;
  min_tier: Tier;
  status: "pending" | "executed" | "rejected";
  params: Record<string, unknown>;
  rationale: string;
  evidence_ids: string[];
  proposed_by: string;
  decided_by: string | null;
  decision_reason: string | null;
  receipt: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface AuditEntry {
  seq: number;
  ts: string;
  actor: string;
  event: string;
  subject: string;
  payload: Record<string, unknown>;
  prev_hash: string;
  hash: string;
}

export interface SystemStatus {
  llm_mode: "online" | "degraded";
  degraded_reason: string | null;
  model: string;
  fast_model: string;
  kill_switch: boolean;
  demo_scenario: string;
  demo_seed: number;
  default_district: string;
}

// ---------------------------------------------------------------- Stage 5: Scenario Lab + Evaluation

export interface DistrictDelta {
  district: string;
  name: string;
  before: Tier;
  after: Tier;
  conf_before: number;
  conf_after: number;
  move: number;
}

export interface EvidenceDelta {
  injected: string;
  injected_label: string;
  expected: string;
  base: string[];
  applied: string[];
  seed: number;
  focus: string;
  focus_name: string;
  districts: DistrictDelta[];
  signals: { district: string; name: string; change: string; before_sources: string[]; after_sources: string[]; signal_id: string | null }[];
  hypotheses: { category: string; title: string; kind: string; before: number; after: number }[];
  explanation: string[];
  latency_ms: number;
}

export interface EvalReport {
  generated_at: string;
  runs: number;
  elapsed_s: number;
  window_days: number;
  llm_mode: string;
  baseline: { rule: string };
  detection: {
    outbreak_runs: number;
    sensitivity_e2: number | null;
    sensitivity_e3: number | null;
    sensitivity_baseline: number | null;
    lead_time_days_median: number | null;
    lead_time_days_mean: number | null;
    detect_delay_days_median: number | null;
    baseline_delay_days_median: number | null;
    e3_delay_days_median: number | null;
  };
  false_alarms: { sentinel_e2_per_90d: number; sentinel_e1_per_90d: number; baseline_per_90d: number; note: string };
  intervention: { e3_events: number; e3_true: number; e3_false: number; e3_precision: number | null; false_intervention_rate: number; baseline_precision: number | null; baseline_false_rate: number | null };
  calibration: { brier: number; brier_baseline: number; pairs: number; bins: { lo: number; hi: number; n: number; predicted: number; observed: number }[] };
  agents: { claims: number; grounded: number; groundedness: number | null; hallucination_rate: number | null; tokens_per_analysis: number; cost_per_analysis_usd: number };
  forecast: { target: string; made_on_day: number; p10_p90_coverage: number | null; mape_p50: number | null };
  latency: { mean_ms: number | null; p95_ms: number | null };
  fairness: { district: string; name: string; runs: number; low_reporting: boolean; sensitivity_e2: number | null; sensitivity_e3: number | null; sensitivity_baseline: number | null; detect_delay_days: number | null }[];
  outcomes: Record<string, { runs: number; E0: number; E1: number; E2: number; E3: number; baseline_alarm: number }>;
  adaptation: { scenario: string; seconds: number; max_tier_after: Tier; correct: boolean }[];
}

export interface EvalStatus {
  running: boolean;
  done: number;
  total: number;
  error: string | null;
}
