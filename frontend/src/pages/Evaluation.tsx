import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Gauge, Play, XCircle } from "lucide-react";
import { useEffect, useMemo } from "react";
import { axis, EChart, tooltip, type Option } from "../components/EChart";
import { Badge, EmptyState, Panel, Q, TierChip } from "../components/ui";
import { post, useEvalReport, useEvalStatus } from "../lib/api";
import { titleCase } from "../lib/format";
import type { EvalReport } from "../lib/types";
import { color, font, TIERS, tier as tierTok } from "../theme";

const SENT = "#2E9EA3";
const BASE = "#9AA5A8";
const f1 = (x: number | null | undefined, d = 1) => (x === null || x === undefined ? "–" : x.toFixed(d));
const p0 = (x: number | null | undefined) => (x === null || x === undefined ? "–" : `${Math.round(x * 100)}%`);

export default function Evaluation() {
  const report = useEvalReport();
  const qc = useQueryClient();
  const status = useEvalStatus(true);
  const running = status.data?.running ?? false;
  const run = useMutation({ mutationFn: () => post("/api/eval/run", { runs: 100 }), onSuccess: () => qc.invalidateQueries({ queryKey: ["eval-status"] }) });

  useEffect(() => {
    if (status.data && !status.data.running && status.data.done > 0) qc.invalidateQueries({ queryKey: ["eval-report"] });
  }, [status.data?.running]); // eslint-disable-line react-hooks/exhaustive-deps

  const runBtn = (
    <button onClick={() => run.mutate()} disabled={running} className="inline-flex items-center gap-1.5 rounded-full bg-sidebar px-4 py-2 text-xs font-semibold text-cream disabled:opacity-50">
      <Play size={13} /> {running ? `Running ${status.data?.done}/${status.data?.total}…` : "Re-run 100 simulations"}
    </button>
  );

  return (
    <Q q={report} label="Loading evaluation report" rows={8}>
      {(r) =>
        !r ? (
          <Panel title="Evaluation" right={runBtn}>
            <EmptyState icon={<Gauge size={18} />} title="No evaluation report yet" body="Run 100 seeded simulations (about 1–2 minutes) to compare Sentinel against the single-threshold baseline." />
          </Panel>
        ) : (
          <Report r={r} runBtn={runBtn} error={status.data?.error ?? null} />
        )
      }
    </Q>
  );
}

function Metric({ label, sent, base, better, hint }: { label: string; sent: string; base?: string; better?: boolean; hint: string }) {
  return (
    <div className="rounded-xl border border-line/30 bg-white/55 p-3.5">
      <div className="label-caps">{label}</div>
      <div className="mt-1.5 flex items-baseline gap-2">
        <span className="num text-[26px] font-semibold leading-none" style={{ color: "#1B6E72" }}>
          {sent}
        </span>
        {base !== undefined && <span className="num text-[12px] text-ink-3">vs {base} baseline</span>}
      </div>
      <div className="mt-1 flex items-center gap-1.5 text-[11px] text-ink-3">
        {better !== undefined && (better ? <CheckCircle2 size={12} className="text-good" /> : <XCircle size={12} className="text-e3" />)}
        {hint}
      </div>
    </div>
  );
}

function Report({ r, runBtn, error }: { r: EvalReport; runBtn: React.ReactNode; error: string | null }) {
  const d = r.detection;
  const fa = r.false_alarms;
  const iv = r.intervention;

  const calib = useMemo<Option>(
    () => ({
      grid: { left: 44, right: 16, top: 16, bottom: 36 },
      tooltip: { ...tooltip, trigger: "item", formatter: (p: { data: number[] }) => `predicted ${p.data[0].toFixed(2)}<br/>observed ${p.data[1].toFixed(2)}<br/>n=${p.data[2]}` },
      xAxis: { type: "value", min: 0, max: 1, name: "predicted confidence", nameLocation: "middle", nameGap: 24, nameTextStyle: { color: color.textMuted, fontSize: 11 }, ...axis },
      yAxis: { type: "value", min: 0, max: 1, name: "observed rate", nameTextStyle: { color: color.textMuted, fontSize: 11 }, ...axis },
      series: [
        { type: "line", data: [[0, 0], [1, 1]], symbol: "none", lineStyle: { color: "rgba(23,54,58,0.3)", type: "dashed", width: 1 }, silent: true },
        { type: "line", data: r.calibration.bins.map((b) => [b.predicted, b.observed, b.n]), lineStyle: { color: SENT, width: 2 }, itemStyle: { color: SENT }, symbolSize: (v: number[]) => Math.min(18, 6 + Math.log2(v[2] + 1) * 1.5) },
      ],
    }),
    [r],
  );

  const fair = useMemo<Option>(
    () => ({
      grid: { left: 40, right: 12, top: 30, bottom: 28 },
      legend: { top: 0, right: 0, textStyle: { color: color.textSecondary, fontSize: 11 }, itemWidth: 10, itemHeight: 10 },
      tooltip: { ...tooltip, valueFormatter: (v: number) => `${Math.round(v * 100)}%` },
      xAxis: { type: "category", data: r.fairness.map((f) => f.name + (f.low_reporting ? " *" : "")), ...axis, axisLabel: { ...axis.axisLabel, fontFamily: font.sans, interval: 0, fontSize: 10 } },
      yAxis: { type: "value", min: 0, max: 1, ...axis, axisLabel: { ...axis.axisLabel, formatter: (v: number) => `${v * 100}%` } },
      series: [
        { name: "Sentinel E3", type: "bar", data: r.fairness.map((f) => f.sensitivity_e3 ?? 0), itemStyle: { color: SENT, borderRadius: [4, 4, 0, 0] }, barGap: "15%" },
        { name: "Baseline alarm", type: "bar", data: r.fairness.map((f) => f.sensitivity_baseline ?? 0), itemStyle: { color: BASE, borderRadius: [4, 4, 0, 0] } },
      ],
    }),
    [r],
  );

  return (
    <div className="flex flex-col gap-3">
      <Panel
        title={`${r.runs} seeded simulations · ${d.outbreak_runs} true outbreaks`}
        subtitle={`Baseline: ${r.baseline.rule}. Agents: ${r.llm_mode}. Generated ${r.generated_at.replace("T", " ")} in ${r.elapsed_s}s.`}
        right={runBtn}
        bodyClass="grid grid-cols-2 gap-3 p-3 lg:grid-cols-4"
      >
        {error && <div className="col-span-full text-xs text-e3">Last run failed: {error}</div>}
        <Metric label="False-intervention rate (E3)" sent={p0(iv.false_intervention_rate)} base={p0(iv.baseline_false_rate)} better={iv.false_intervention_rate <= (iv.baseline_false_rate ?? 1)} hint={`${iv.e3_false} false of ${iv.e3_events} E3 events · headline metric`} />
        <Metric label="False alarms / 90 days" sent={f1(fa.sentinel_e2_per_90d)} base={f1(fa.baseline_per_90d)} better={fa.sentinel_e2_per_90d <= fa.baseline_per_90d} hint="E2+ in unaffected districts, statewide" />
        <Metric label="Lead time vs baseline" sent={`${d.lead_time_days_median !== null && d.lead_time_days_median >= 0 ? "+" : ""}${f1(d.lead_time_days_median, 0)} d`} better={(d.lead_time_days_median ?? 0) >= 0} hint={`median; detection ${f1(d.detect_delay_days_median, 0)} d vs ${f1(d.baseline_delay_days_median, 0)} d after onset`} />
        <Metric label="Sensitivity (true outbreaks)" sent={p0(d.sensitivity_e2)} base={p0(d.sensitivity_baseline)} better={(d.sensitivity_e2 ?? 0) >= (d.sensitivity_baseline ?? 0)} hint={`E2+ on primary district · E3 ${p0(d.sensitivity_e3)} (median ${f1(d.e3_delay_days_median, 0)} d)`} />
        <Metric label="Brier score (lower is better)" sent={r.calibration.brier.toFixed(3)} base={r.calibration.brier_baseline.toFixed(3)} better={r.calibration.brier <= r.calibration.brier_baseline} hint={`${r.calibration.pairs} district-runs`} />
        <Metric label="Groundedness" sent={p0(r.agents.groundedness)} hint={`${r.agents.grounded}/${r.agents.claims} claims verified · hallucination ${p0(r.agents.hallucination_rate)}`} />
        <Metric label="Forecast P10–P90 coverage" sent={p0(r.forecast.p10_p90_coverage)} better={(r.forecast.p10_p90_coverage ?? 0) >= 0.7} hint={`nominal 80% · MAPE ${p0(r.forecast.mape_p50)} · ${r.forecast.target}`} />
        <Metric label="Latency / cost per analysis" sent={`${f1((r.latency.mean_ms ?? 0) / 1000, 2)} s`} hint={`p95 ${f1((r.latency.p95_ms ?? 0) / 1000, 2)} s · ${r.agents.tokens_per_analysis} tokens · $${r.agents.cost_per_analysis_usd.toFixed(2)}`} />
      </Panel>

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
        <Panel title="Confidence calibration" subtitle="Reliability curve: closer to the diagonal is better calibrated. Dot size = number of district-runs." bodyClass="p-2">
          <EChart option={calib} height={280} />
        </Panel>
        <Panel title="Fairness by district" subtitle="Outbreak sensitivity when each district hosts the outbreak · * low-reporting district" bodyClass="p-2">
          <EChart option={fair} height={280} />
        </Panel>
      </div>

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <Panel title="Highest tier reached, per scenario" subtitle="Decoys (holiday, reporting, lab backlog, weather) must never reach E3" bodyClass="overflow-x-auto p-0">
          <table className="w-full text-[12px]">
            <thead>
              <tr className="label-caps text-left">
                <th className="px-3 py-2">Scenario</th>
                <th className="px-2 py-2">Runs</th>
                {TIERS.map((t) => (
                  <th key={t} className="px-2 py-2">
                    {t}
                  </th>
                ))}
                <th className="px-3 py-2">Baseline alarmed</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(r.outcomes).map(([name, o]) => (
                <tr key={name} className="border-t border-line/20">
                  <td className="px-3 py-1.5 text-ink">{titleCase(name)}</td>
                  <td className="num px-2 text-ink-2">{o.runs}</td>
                  {TIERS.map((t) => (
                    <td key={t} className="num px-2" style={{ color: o[t] ? tierTok[t].ink : color.textMuted, fontWeight: o[t] ? 600 : 400 }}>
                      {o[t] || "·"}
                    </td>
                  ))}
                  <td className="num px-3 text-ink-2">
                    {o.baseline_alarm}/{o.runs}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
        <Panel title="Adaptation after injection" subtitle="Inject each scenario onto a quiet world: re-graded in seconds, tier moves checked" bodyClass="flex flex-col gap-1.5 p-3">
          {r.adaptation.map((a) => (
            <div key={a.scenario} className="flex items-center gap-2 rounded-lg bg-white/55 px-3 py-2 text-[12.5px]">
              {a.correct ? <CheckCircle2 size={14} className="text-good" /> : <XCircle size={14} className="text-e3" />}
              <span className="flex-1 text-ink">{titleCase(a.scenario)}</span>
              <TierChip tier={a.max_tier_after} size="sm" />
              <Badge color="#1B6E72">{a.seconds.toFixed(2)} s</Badge>
            </div>
          ))}
        </Panel>
      </div>
    </div>
  );
}
