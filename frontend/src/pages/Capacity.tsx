import { motion } from "framer-motion";
import { AlertTriangle, BedDouble, HeartPulse } from "lucide-react";
import { useMemo, useState } from "react";
import { axis, EChart, tooltip, type Option } from "../components/EChart";
import { CountUp, ErrorState, IdChip, LoadingBlock, Panel, TierChip, Toggle } from "../components/ui";
import { useAnalysis, useDistricts, useForecast } from "../lib/api";
import { probLabel, shortDate } from "../lib/format";
import { useApp } from "../lib/state";
import type { Forecast } from "../lib/types";
import { color, font, tier as tierTok } from "../theme";

const BAND = "#2E9EA3";

export default function Capacity() {
  const { district, setDistrict } = useApp();
  const [intervention, setIntervention] = useState(false);
  const districts = useDistricts();
  const analysis = useAnalysis();
  const base = useForecast(district, false);
  const withInt = useForecast(district, true);
  const f = intervention ? withInt.data : base.data;
  const q = intervention ? withInt : base;

  return (
    <div className="flex flex-col gap-3">
      <Panel bodyClass="flex flex-wrap items-center gap-3 px-4 py-3">
        <span className="label-caps">District</span>
        <div className="flex flex-wrap gap-1.5">
          {(districts.data ?? []).map((d) => {
            const a = analysis.data?.assessments.find((x) => x.district === d.code);
            const pb = a ? Math.max(...a.forecast.breach_prob_beds) : 0;
            return (
              <button key={d.code} onClick={() => setDistrict(d.code)} className={`inline-flex items-center gap-2 rounded-lg border px-2.5 py-1.5 text-xs ${d.code === district ? "border-accent/60 bg-accent/10 text-ink" : "border-line/30 text-ink-2 hover:border-line/50"}`}>
                {d.name}
                {pb >= 0.2 && <span className="num text-[10.5px]" style={{ color: pb >= 0.5 ? tierTok.E3.ink : tierTok.E2.ink }}>{probLabel(pb)}</span>}
              </button>
            );
          })}
        </div>
        <div className="ml-auto flex items-center gap-3 rounded-lg border border-line/30 bg-white/50 px-3 py-1.5">
          <Toggle on={intervention} onChange={setIntervention} label="Apply intervention" />
          <span className="hidden text-[11px] text-ink-3 md:inline">(slows growth after a 2-day delay)</span>
        </div>
      </Panel>

      {q.error && !f ? (
        <Panel>
          <ErrorState error={q.error} retry={() => q.refetch()} />
        </Panel>
      ) : !f ? (
        <Panel>
          <LoadingBlock label="Running 1,000 Monte Carlo trajectories" rows={8} />
        </Panel>
      ) : (
        <>
          <Callout f={f} base={base.data} withInt={withInt.data} intervention={intervention} tierOf={analysis.data?.assessments.find((x) => x.district === district)?.gate.tier} />
          <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
            <FanPanel f={f} kind="beds" />
            <FanPanel f={f} kind="icu" />
          </div>
        </>
      )}
    </div>
  );
}

function Callout({ f, base, withInt, intervention, tierOf }: { f: Forecast; base?: Forecast; withInt?: Forecast; intervention: boolean; tierOf?: keyof typeof tierTok }) {
  const pb = Math.max(...f.breach_prob_beds);
  const pi = Math.max(...f.breach_prob_icu);
  const sev = pb >= 0.5 ? tierTok.E3.ink : pb >= 0.2 ? tierTok.E2.ink : color.good;
  const peak = Math.max(...f.beds.p50);
  const delta = base && withInt ? Math.max(...base.breach_prob_beds) - Math.max(...withInt.breach_prob_beds) : null;
  const dayLabel = (d: number | null) => (d === null ? "not within 14 days" : shortDate(f.dates[f.days.indexOf(d)] ?? f.dates[0]));
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="glass grid grid-cols-2 gap-4 p-4 md:grid-cols-5" style={{ borderColor: `${sev}55`, boxShadow: `0 0 0 1px ${sev}22 inset` }}>
      <div className="col-span-2 flex items-start gap-3">
        <div className="grid h-11 w-11 shrink-0 place-items-center rounded-xl" style={{ background: `${sev}1f`, color: sev }}>
          <AlertTriangle size={20} />
        </div>
        <div>
          <div className="label-caps">Bed breach probability · 14 days</div>
          <div className="mt-1 text-4xl font-semibold leading-none" style={{ color: sev }}>
            <span className="num">{probLabel(pb)}</span>
          </div>
          <div className="mt-1.5 text-[12px] text-ink-2">
            {pb >= 0.5 ? (
              <>
                Occupancy is projected to exceed <span className="num">{f.beds_total.toFixed(0)}</span> beds from <b className="text-ink">{dayLabel(f.breach_day_beds)}</b>; P10–P90 peak <span className="num">{Math.max(...f.beds.p10).toFixed(0)}–{Math.max(...f.beds.p90).toFixed(0)}</span>.
              </>
            ) : (
              <>Capacity holds in most trajectories{pb > 0 ? `; ${probLabel(pb)} of runs breach.` : "."}</>
            )}
          </div>
          <div className="mt-2 flex items-center gap-2">
            <IdChip id={f.forecast_id} />
            {tierOf && <TierChip tier={tierOf} size="sm" />}
          </div>
        </div>
      </div>
      <Mini label="ICU breach probability" value={<span className="num">{probLabel(pi)}</span>} hint={`P10–P90 peak ${Math.max(...f.icu.p10).toFixed(0)}–${Math.max(...f.icu.p90).toFixed(0)} of ${f.icu_total.toFixed(0)} · ${dayLabel(f.breach_day_icu)}`} accent={pi >= 0.5 ? tierTok.E3.ink : undefined} />
      <Mini label="Peak occupied beds (P50)" value={<CountUp value={peak} />} hint={`P90 ${Math.max(...f.beds.p90).toFixed(0)} · of ${f.beds_total.toFixed(0)}`} />
      <Mini
        label={intervention ? "Intervention effect" : "Growth rate"}
        value={intervention && delta !== null ? <CountUp value={-delta * 100} suffix=" pp" /> : <CountUp value={f.growth_rate * 100} digits={1} suffix="%/d" />}
        hint={intervention ? "change in peak P(bed breach)" : `± ${(f.growth_se * 100).toFixed(1)}%/d (SE) on admissions`}
        accent={intervention ? color.good : undefined}
      />
    </motion.div>
  );
}

function Mini({ label, value, hint, accent }: { label: string; value: React.ReactNode; hint: string; accent?: string }) {
  return (
    <div className="rounded-xl border border-line/30 bg-white/50 p-3">
      <div className="label-caps">{label}</div>
      <div className="mt-1.5 text-2xl font-semibold leading-none" style={{ color: accent ?? color.text }}>
        {value}
      </div>
      <div className="mt-1 text-[11px] text-ink-3">{hint}</div>
    </div>
  );
}

function FanPanel({ f, kind }: { f: Forecast; kind: "beds" | "icu" }) {
  const band = kind === "beds" ? f.beds : f.icu;
  const hist = kind === "beds" ? f.history_beds : f.history_icu;
  const cap = kind === "beds" ? f.beds_total : f.icu_total;
  const prob = kind === "beds" ? f.breach_prob_beds : f.breach_prob_icu;
  const breachDay = kind === "beds" ? f.breach_day_beds : f.breach_day_icu;

  const option = useMemo<Option>(() => {
    const hDates = f.history_days;
    // History dates are derived from the first forecast date (consecutive days).
    const first = new Date(`${f.dates[0]}T00:00:00Z`).getTime();
    const xs = [...hDates, ...f.days].map((d) => shortDate(new Date(first - (f.days[0] - d) * 864e5).toISOString().slice(0, 10)));
    const lastHist = hist[hist.length - 1];
    const join = (arr: number[]) => [...hDates.map((_, i) => (i === hDates.length - 1 ? lastHist : null)), ...arr];
    return {
      grid: { left: 46, right: 64, top: 18, bottom: 26 },
      tooltip: {
        ...tooltip,
        formatter: (ps: { dataIndex: number }[]) => {
          const i = ps[0]?.dataIndex ?? 0;
          const j = i - hDates.length;
          if (j < 0) return `<div style="font-family:${font.mono};font-size:11px"><b>${xs[i]}</b><br/>observed ${hist[i]?.toFixed(0) ?? "–"} / ${cap.toFixed(0)}</div>`;
          return `<div style="font-family:${font.mono};font-size:11px"><b>${xs[i]}</b> · forecast<br/>P50 <b>${band.p50[j].toFixed(0)}</b><br/>P10–P90 ${band.p10[j].toFixed(0)}–${band.p90[j].toFixed(0)}<br/>capacity ${cap.toFixed(0)}<br/>P(breach) <b style="color:${prob[j] >= 0.5 ? "#E5535D" : "inherit"}">${(prob[j] * 100).toFixed(0)}%</b></div>`;
        },
      },
      xAxis: { type: "category", data: xs, boundaryGap: false, ...axis, axisLabel: { ...axis.axisLabel, interval: 6 }, splitLine: { show: false } },
      yAxis: { type: "value", scale: true, ...axis },
      series: [
        { name: "p10", type: "line", data: join(band.p10), stack: "fan", symbol: "none", lineStyle: { opacity: 0 }, silent: true, connectNulls: false },
        { name: "P10–P90", type: "line", data: [...hDates.map((_, i) => (i === hDates.length - 1 ? 0 : null)), ...band.p90.map((v, j) => v - band.p10[j])], stack: "fan", symbol: "none", lineStyle: { opacity: 0 }, areaStyle: { color: `${BAND}2e` }, silent: true },
        { name: "P50", type: "line", data: join(band.p50), symbol: "none", lineStyle: { color: BAND, width: 2, type: "dashed" } },
        {
          name: "Observed",
          type: "line",
          data: [...hist, ...f.days.map(() => null)],
          symbol: "none",
          lineStyle: { color: color.text, width: 2 },
          markLine: {
            silent: true,
            symbol: "none",
            data: [
              { yAxis: cap, lineStyle: { color: "#E5535D", width: 1.5 }, label: { formatter: `capacity ${cap.toFixed(0)}`, color: "#E5535D", fontSize: 10, position: "insideEndTop" } },
              { xAxis: xs[hDates.length], lineStyle: { color: "rgba(23,54,58,0.35)", type: "dotted" }, label: { formatter: "now", color: color.textMuted, fontSize: 10, position: "start" } },
              ...(breachDay !== null ? [{ xAxis: xs[hDates.length + f.days.indexOf(breachDay)], lineStyle: { color: "rgba(229,83,93,0.6)", type: "dashed" as const }, label: { formatter: "P≥50%", color: "#E5535D", fontSize: 10 } }] : []),
            ],
          },
        },
      ],
    };
  }, [f, band, hist, cap, prob, breachDay]);

  const Icon = kind === "beds" ? BedDouble : HeartPulse;
  return (
    <Panel
      title={
        <span className="flex items-center gap-2">
          <Icon size={15} className="text-accent-ink" /> {kind === "beds" ? "Occupied beds" : "ICU occupancy"}
        </span>
      }
      subtitle="Observed (solid) · median forecast (dashed) · P10–P90 band (shaded)"
      right={<span className="num text-xs text-ink-3">max P(breach) {probLabel(Math.max(...prob))}</span>}
      bodyClass="px-2 pb-2 pt-1"
    >
      <EChart option={option} height={300} />
      <div className="flex h-8 items-end gap-[2px] pb-1 pr-[64px]" style={{ paddingLeft: `calc(46px + (100% - 110px) * ${f.history_days.length / (f.history_days.length + f.days.length - 1)})` }} aria-label="Daily breach probability">
        {prob.map((p, i) => (
          <div key={i} className="flex-1 rounded-t-[2px]" title={`${shortDate(f.dates[i])}: P(breach) ${probLabel(p)}`} style={{ height: `${Math.max(4, p * 100)}%`, background: p >= 0.5 ? "#E5535D" : p >= 0.2 ? "#F2A65A" : "rgba(23,54,58,0.1)" }} />
        ))}
      </div>
      <div className="pr-[64px] text-right text-[10px] text-ink-3">Daily P(breach) over the forecast window</div>
    </Panel>
  );
}
