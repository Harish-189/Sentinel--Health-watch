import { useMemo } from "react";
import { axis, EChart, tooltip, type Option } from "../components/EChart";
import { SyndromeRow } from "../components/SyndromeRow";
import { EmptyState, IdChip, Panel, Q, TierChip } from "../components/ui";
import { useAnalysis, useDistricts, useSeries } from "../lib/api";
import { metricLabel, shortDate, signed, sourceLabel } from "../lib/format";
import { useApp } from "../lib/state";
import type { Anomaly, SeriesDetection, Signal } from "../lib/types";
import { color, font, source as srcColor } from "../theme";

type Syndrome = "respiratory" | "gastrointestinal" | "febrile_rash" | "other";
const WINDOW = 45; // days shown as capsules (legible at 1080p)

// One representative series per source and syndrome, in expected lead order.
const PANELS: Record<Syndrome, [string, string][]> = {
  respiratory: [["pharmacy", "cough_cold"], ["absenteeism", "school_rate"], ["mobility", "mobility_index"], ["clinic", "respiratory"], ["lab", "panel_A_positivity"], ["capacity", "admissions"]],
  gastrointestinal: [["pharmacy", "ors_rehydration"], ["absenteeism", "school_rate"], ["mobility", "mobility_index"], ["clinic", "gastrointestinal"], ["lab", "panel_B_positivity"], ["capacity", "admissions"]],
  febrile_rash: [["pharmacy", "antipyretic"], ["absenteeism", "school_rate"], ["mobility", "mobility_index"], ["clinic", "febrile_rash"], ["lab", "panel_A_positivity"], ["capacity", "admissions"]],
  other: [["pharmacy", "antipyretic"], ["absenteeism", "workplace_rate"], ["mobility", "mobility_index"], ["clinic", "other"], ["lab", "panel_B_positivity"], ["capacity", "admissions"]],
};
const colorOf = (s: string) => srcColor[s === "capacity" ? "hospital" : s] ?? color.textSecondary;

export default function SignalExplorer() {
  const { district, setDistrict, syndrome, setSyndrome } = useApp();
  const districts = useDistricts();
  const analysis = useAnalysis();
  const a = analysis.data?.assessments.find((x) => x.district === district);
  // "All" follows the district's own corroborated signal.
  const syn: Syndrome = syndrome !== "all" ? syndrome : ((a?.signal?.syndrome as Syndrome) || "respiratory");
  const series = useSeries(district);

  return (
    <div className="flex flex-col gap-3">
      <Panel bodyClass="flex flex-wrap items-center gap-3 px-4 py-3">
        <span className="label-caps">District</span>
        <div className="flex flex-wrap gap-1.5">
          {(districts.data ?? []).map((d) => {
            const t = analysis.data?.assessments.find((x) => x.district === d.code)?.gate.tier ?? "E0";
            const on = d.code === district;
            return (
              <button key={d.code} onClick={() => setDistrict(d.code)} className={`inline-flex items-center gap-2 rounded-lg border px-2.5 py-1.5 text-xs transition-colors ${on ? "border-accent/60 bg-accent/10 text-ink" : "border-line/30 text-ink-2 hover:border-line/50"}`}>
                {d.name}
                <TierChip tier={t} size="sm" />
              </button>
            );
          })}
        </div>
      </Panel>
      <SyndromeRow value={syndrome} onChange={setSyndrome} />

      <Q q={series} label="Scoring series against seasonal baselines" rows={8}>
        {(data) => (
          <>
            <LeadLagPanel series={data.series} syndrome={syn} signal={a?.signal?.syndrome === syn ? a.signal : null} />
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2 2xl:grid-cols-3">
              {PANELS[syn].map(([src, metric], i) => {
                const s = data.series.find((x) => x.source === src && x.metric === metric);
                const anoms = data.anomalies.filter((x) => x.source === src && x.metric === metric);
                return s ? <SourcePanel key={`${src}.${metric}`} s={s} anomalies={anoms} delay={i * 0.05} /> : null;
              })}
            </div>
          </>
        )}
      </Q>
    </div>
  );
}

function SourcePanel({ s, anomalies, delay }: { s: SeriesDetection; anomalies: Anomaly[]; delay: number }) {
  const c = colorOf(s.source);
  const option = useMemo<Option>(() => {
    // Range capsules: one rounded bar per day spanning the expected range (soft grey), observed value as a dot.
    // Anomalous days (z >= 3) turn coral.
    const o = Math.max(0, s.days.length - WINDOW);
    const cut = <T,>(arr: T[]) => arr.slice(o);
    const x = cut(s.dates).map(shortDate);
    const z = cut(s.z);
    const lower = cut(s.lower);
    const upper = cut(s.upper);
    const obs = cut(s.observed);
    const hot = z.map((v) => v !== null && v >= 3);
    const lo = Math.min(...lower, ...obs.filter((v): v is number => v !== null));
    const hi = Math.max(...upper, ...obs.filter((v): v is number => v !== null));
    const pad = (hi - lo) * 0.08;
    return {
      grid: { left: 44, right: 12, top: 14, bottom: 24 },
      tooltip: {
        ...tooltip,
        trigger: "axis",
        axisPointer: { type: "shadow", shadowStyle: { color: "rgba(95,189,191,0.12)" } },
        formatter: (ps: { dataIndex: number }[]) => {
          const i = (ps[0]?.dataIndex ?? 0) + o;
          const z = s.z[i];
          return `<div style="font-family:${font.mono};font-size:11px"><b>${s.dates[i]}</b><br/>observed <b>${s.observed[i]?.toFixed(1) ?? "–"}</b><br/>expected ${s.expected[i].toFixed(1)} <span style="opacity:.6">[${s.lower[i].toFixed(1)}–${s.upper[i].toFixed(1)}]</span><br/>z <b style="color:${z !== null && z >= 3 ? "#E5535D" : "inherit"}">${z?.toFixed(2) ?? "–"}</b></div>`;
        },
      },
      xAxis: { type: "category", data: x, ...axis, axisLabel: { ...axis.axisLabel, interval: 9 }, splitLine: { show: false } },
      yAxis: { type: "value", min: lo - pad, max: hi + pad, ...axis, axisLabel: { ...axis.axisLabel, showMinLabel: false, showMaxLabel: false, formatter: (v: number) => (Math.abs(v) >= 1000 ? `${(v / 1000).toFixed(1)}k` : Math.abs(v) < 1 && v !== 0 ? v.toFixed(2) : String(Math.round(v))) } },
      series: [
        // Stacks start at value 0: an invisible base up to the lower bound (clipped below the axis), then the capsule.
        { name: "base", type: "bar", stack: "range", data: lower, itemStyle: { color: "transparent" }, silent: true, barWidth: "58%" },
        {
          name: "Expected range",
          type: "bar",
          stack: "range",
          data: upper.map((u, i) => ({ value: u - lower[i], itemStyle: { color: hot[i] ? "rgba(229,83,93,0.28)" : "rgba(23,54,58,0.10)", borderRadius: 99 } })),
          barWidth: "58%",
          silent: true,
        },
        {
          name: "Observed",
          type: "scatter",
          data: obs.map((v, i) => (v === null ? null : { value: v, symbolSize: hot[i] ? 8 : 5.5, itemStyle: { color: hot[i] ? "#E5535D" : c, borderColor: "#fff", borderWidth: hot[i] ? 1.5 : 1 } })),
          z: 5,
        },
      ],
    };
  }, [s, c]);
  const latestZ = [...s.z].reverse().find((z) => z !== null) ?? null;
  return (
    <Panel
      delay={delay}
      title={
        <span className="flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-sm" style={{ background: c }} />
          {sourceLabel(s.source === "capacity" ? "hospital" : s.source)} <span className="font-normal text-ink-3">· {metricLabel(s.metric)}</span>
        </span>
      }
      right={latestZ !== null && <span className={`num text-xs ${latestZ >= 3 ? "text-e3" : "text-ink-3"}`}>z {signed(latestZ, 1)}</span>}
      bodyClass="px-2 pb-3 pt-1"
    >
      <EChart option={option} height={190} />
      <div className="flex min-h-[22px] flex-wrap items-center gap-1 px-2">
        {anomalies.length ? (
          anomalies.map((a) => <IdChip key={a.evidence_id} id={a.evidence_id} />)
        ) : (
          <span className="text-[11px] text-ink-3">Within baseline band: no anomaly episodes</span>
        )}
      </div>
    </Panel>
  );
}

function LeadLagPanel({ series, syndrome, signal }: { series: SeriesDetection[]; syndrome: Syndrome; signal: Signal | null }) {
  const picks = PANELS[syndrome].filter(([src]) => src !== "capacity");
  const option = useMemo<Option>(() => {
    const lines = picks.map(([src, metric]) => series.find((s) => s.source === src && s.metric === metric)).filter((s): s is SeriesDetection => !!s);
    const start = Math.max(0, (lines[0]?.days.length ?? 0) - 40);
    const x = (lines[0]?.dates ?? []).slice(start).map(shortDate);
    // 3-day centred mean of z to make the onset order legible.
    const smooth = (z: (number | null)[]) => z.map((_, i) => {
      const w = z.slice(Math.max(0, i - 1), i + 2).filter((v): v is number => v !== null);
      return w.length ? +(w.reduce((a, b) => a + b, 0) / w.length).toFixed(2) : null;
    });
    return {
      grid: { left: 40, right: 136, top: 16, bottom: 26 },
      tooltip: { ...tooltip, valueFormatter: (v: number) => (v === null || v === undefined ? "–" : `z ${v.toFixed(1)}`) },
      xAxis: { type: "category", data: x, boundaryGap: false, ...axis, axisLabel: { ...axis.axisLabel, interval: 6 }, splitLine: { show: false } },
      yAxis: { type: "value", ...axis, name: "z", nameTextStyle: { color: color.textMuted, fontFamily: font.mono, fontSize: 10 } },
      series: [
        ...lines.map((s) => ({
          name: sourceLabel(s.source),
          type: "line",
          data: smooth(s.z).slice(start),
          symbol: "none",
          lineStyle: { color: colorOf(s.source), width: 2 },
          itemStyle: { color: colorOf(s.source) },
          endLabel: { show: true, formatter: "{a}", color: color.textSecondary, fontSize: 10.5, fontFamily: font.sans },
          emphasis: { focus: "series" },
        })),
        { name: "threshold", type: "line", data: [], markLine: { silent: true, symbol: "none", lineStyle: { color: "rgba(229,83,93,0.5)", type: "dashed" }, label: { formatter: "z = 3", color: "#E5535D", fontSize: 10 }, data: [{ yAxis: 3 }] } },
      ],
    };
  }, [series, picks]);
  const order = signal ? Object.entries(signal.onset_by_source).sort((a, b) => a[1] - b[1]) : [];
  return (
    <Panel title="Lead-lag overlay" subtitle="Robust z-score per source, last 40 days. Infectious surges typically move pharmacy/absenteeism → clinic → lab." right={signal && <IdChip id={signal.signal_id} />} bodyClass="grid grid-cols-1 gap-3 p-3 xl:grid-cols-[minmax(0,1fr)_260px]">
      <EChart option={option} height={240} />
      <div className="flex flex-col gap-2">
        <div className="label-caps">Onset order</div>
        {order.length === 0 ? (
          <EmptyState title="No corroborated signal" body={`No multi-source ${syndrome} signal in this district.`} />
        ) : (
          <>
            <ol className="flex flex-col gap-1.5">
              {order.map(([src, day], i) => (
                <li key={src} className="flex items-center gap-2 text-xs">
                  <span className="num w-4 text-ink-3">{i + 1}</span>
                  <span className="h-2 w-2 rounded-sm" style={{ background: colorOf(src) }} />
                  <span className="flex-1 text-ink-2">{sourceLabel(src)}</span>
                  <span className="num text-ink-3">day {day}</span>
                </li>
              ))}
            </ol>
            <div className="mt-1 rounded-lg border border-line/30 bg-white/50 p-2.5">
              <div className="label-caps">Lag consistency</div>
              <div className="num mt-1 text-xl font-semibold text-ink">{Math.round(signal!.lag_consistency * 100)}%</div>
              <div className="mt-1 flex flex-col gap-0.5">
                {signal!.lead_lag.map((l) => (
                  <div key={l.source} className="num text-[10.5px] text-ink-3">
                    {l.source.split(".")[0]} {l.best_lag >= 0 ? "leads" : "lags"} clinic by {Math.abs(l.best_lag)}d · r {l.corr.toFixed(2)}
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
      </div>
    </Panel>
  );
}
