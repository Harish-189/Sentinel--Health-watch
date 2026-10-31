import { useMutation } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowRight, Beaker, FileUp, RotateCcw, ShieldAlert, Sparkles, Zap } from "lucide-react";
import { useRef, useState } from "react";
import { Badge, EmptyState, ErrorState, LoadingBlock, Panel, TierChip } from "../components/ui";
import { api, post, useScenarios } from "../lib/api";
import { titleCase } from "../lib/format";
import { useApp } from "../lib/state";
import type { EvidenceDelta } from "../lib/types";
import { tier as tierTok } from "../theme";

const QUIET = "noise_only";

export default function ScenarioLab() {
  const scenarios = useScenarios();
  const { scenarioLabel, setScenario, go } = useApp();
  const [base, setBase] = useState<"console" | "quiet">("console");
  const baseList = base === "console" ? scenarioLabel : [QUIET];
  const file = useRef<HTMLInputElement>(null);

  const inject = useMutation({ mutationFn: (name: string) => post<EvidenceDelta>("/api/scenario/inject", { inject: name, base: baseList.join("+") }) });
  const upload = useMutation({
    mutationFn: (csv: string) => post<{ upload: string; rows: number; delta: EvidenceDelta }>("/api/data/upload", { csv, base: baseList.join("+") }),
  });
  const delta = upload.data?.delta ?? inject.data;
  const busy = inject.isPending || upload.isPending;
  const err = inject.error ?? upload.error;

  const send = (csv: string) => {
    inject.reset();
    upload.mutate(csv);
  };
  const choices = (scenarios.data ?? []).filter((s) => s.name !== QUIET && !baseList.includes(s.name));

  return (
    <div className="grid grid-cols-1 gap-3 xl:grid-cols-[380px_minmax(0,1fr)]">
      <div className="flex flex-col gap-3">
        <Panel title="Base world" bodyClass="flex flex-col gap-2 p-3">
          <div className="flex gap-2">
            {(["console", "quiet"] as const).map((b) => (
              <button key={b} onClick={() => setBase(b)} className={`flex-1 rounded-xl border px-3 py-2 text-left text-[12px] ${base === b ? "border-accent-strong/60 bg-mint" : "border-line/30 bg-white/55"}`}>
                <div className="font-semibold text-ink">{b === "console" ? "Current console" : "Quiet world"}</div>
                <div className="truncate text-[10.5px] text-ink-3">{b === "console" ? scenarioLabel.map(titleCase).join(" + ") : "noise only"}</div>
              </button>
            ))}
          </div>
          {scenarioLabel.some((s) => s.startsWith("upload:")) || base === "console" ? (
            <button onClick={() => setScenario(null)} className="inline-flex items-center gap-1 self-start text-[11px] text-ink-3 hover:text-ink">
              <RotateCcw size={11} /> Reset console to the demo scenario
            </button>
          ) : null}
        </Panel>

        <Panel title="Inject a scenario" subtitle="The whole pipeline re-runs; the gate decides the tier" bodyClass="flex flex-col gap-1.5 p-2">
          {choices.map((s) => (
            <button key={s.name} disabled={busy} onClick={() => { upload.reset(); inject.mutate(s.name); }} className="group flex items-start gap-3 rounded-xl border border-line/25 bg-white/55 p-3 text-left transition-colors hover:border-accent-strong/50 hover:bg-white disabled:opacity-50">
              <span className={`mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-lg ${s.is_epidemic ? "bg-[#E5535D]/15 text-e3" : "bg-mint text-accent-ink"}`}>
                {s.is_epidemic ? <Zap size={15} /> : <Sparkles size={15} />}
              </span>
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-2 text-[13px] font-semibold text-ink">
                  {titleCase(s.name)}
                  <Badge color={s.is_epidemic ? "#B32632" : "#1B6E72"}>{s.is_epidemic ? "EPIDEMIC" : "DECOY"}</Badge>
                </span>
                <span className="mt-0.5 block text-[11.5px] leading-snug text-ink-3">{s.description}</span>
              </span>
              <ArrowRight size={14} className="mt-2 text-ink-3 group-hover:text-accent-ink" />
            </button>
          ))}
        </Panel>

        <Panel title="Upload aggregates (CSV)" subtitle="day, district, source, metric, value · person-level fields are rejected" bodyClass="flex flex-col gap-2 p-3">
          <input ref={file} type="file" accept=".csv,text/csv" className="hidden" onChange={async (e) => { const f = e.target.files?.[0]; if (f) send(await f.text()); e.target.value = ""; }} />
          <button disabled={busy} onClick={() => file.current?.click()} className="flex items-center justify-center gap-2 rounded-xl border-2 border-dashed border-line/50 bg-white/40 py-5 text-[12.5px] text-ink-2 hover:bg-white/70">
            <FileUp size={16} /> Choose a CSV file
          </button>
          <div className="flex gap-2">
            <button disabled={busy} onClick={async () => send((await api<{ csv: string }>("/api/data/sample")).csv)} className="flex-1 rounded-lg bg-sidebar px-3 py-2 text-[12px] font-semibold text-cream disabled:opacity-50">
              Use sample (GI cluster, Tiruchirappalli)
            </button>
            <button disabled={busy} onClick={() => send("day,district,source,metric,value,patient_name\n720,TRY,clinic,respiratory,40,R. Kumar\n")} className="inline-flex items-center gap-1 rounded-lg border border-e3/40 px-3 py-2 text-[12px] text-e3" title="Demonstrates the privacy guardrail">
              <ShieldAlert size={13} /> Try PII
            </button>
          </div>
        </Panel>
      </div>

      <div className="min-w-0">
        {busy ? (
          <Panel title="Re-running the pipeline"><LoadingBlock label="Detect → correlate → confounders → grade" rows={8} /></Panel>
        ) : err ? (
          <Panel title={(err as Error).message.includes("PII") ? "Rejected at ingestion" : "Injection failed"}><ErrorState error={err} /></Panel>
        ) : delta ? (
          <DeltaView d={delta} onApply={() => { setScenario(delta.applied); go("command"); }} />
        ) : (
          <Panel title="Evidence delta"><EmptyState icon={<Beaker size={18} />} title="Pick a scenario or upload a CSV" body="The system re-grades every district and shows what changed, which tier moved and why, in a second or two." /></Panel>
        )}
      </div>
    </div>
  );
}

function DeltaView({ d, onApply }: { d: EvidenceDelta; onApply: () => void }) {
  const moved = d.districts.filter((x) => x.move !== 0);
  return (
    <AnimatePresence mode="wait">
      <motion.div key={d.injected + d.base.join()} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="flex flex-col gap-3">
        <Panel
          title={<span className="flex items-center gap-2">Evidence delta <Badge color="#1B6E72">re-graded in {(d.latency_ms / 1000).toFixed(2)} s</Badge></span>}
          subtitle={`Injected: ${d.injected_label} · ${d.expected}`}
          right={<button onClick={onApply} className="inline-flex items-center gap-1.5 rounded-full bg-sidebar px-4 py-2 text-xs font-semibold text-cream">Apply to console <ArrowRight size={13} /></button>}
          bodyClass="grid grid-cols-2 gap-2 p-3 md:grid-cols-4"
        >
          {d.districts.map((x, i) => (
            <motion.div key={x.district} initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: i * 0.05 }} className={`rounded-xl border p-2.5 ${x.move ? "border-transparent shadow-[0_0_0_2px_var(--c)]" : "border-line/25 bg-white/45"}`} style={{ ["--c" as string]: x.move ? tierTok[x.after].color : "transparent", background: x.move ? `${tierTok[x.after].color}1f` : undefined }}>
              <div className="truncate text-[12.5px] font-semibold text-ink">{x.name}</div>
              <div className="mt-1.5 flex items-center gap-1.5">
                <TierChip tier={x.before} size="sm" />
                <ArrowRight size={12} className={x.move ? "text-ink" : "text-ink-3"} />
                <TierChip tier={x.after} size="sm" />
              </div>
              <div className="num mt-1 text-[10.5px] text-ink-3">
                conf {Math.round(x.conf_before * 100)}% → {Math.round(x.conf_after * 100)}%
              </div>
            </motion.div>
          ))}
        </Panel>

        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          <Panel title="Why it changed" subtitle={`${moved.length} tier move(s) · deterministic explanation`} bodyClass="flex flex-col gap-2 p-3">
            {d.explanation.map((l, i) => (
              <motion.p key={i} initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.2 + i * 0.08 }} className={`text-[12.5px] leading-relaxed ${i === 0 ? "font-semibold text-ink" : "text-ink-2"}`}>
                {l}
              </motion.p>
            ))}
            {d.signals.length > 0 && (
              <div className="mt-1 flex flex-wrap gap-1.5">
                {d.signals.map((s) => (
                  <Badge key={s.district} color={s.change === "cleared" ? "#4A6B65" : "#985510"}>
                    {s.name}: {s.change.replace("_", " ")} ({s.after_sources.length || s.before_sources.length} src)
                  </Badge>
                ))}
              </div>
            )}
          </Panel>
          <Panel title={`Hypothesis movement · ${d.focus_name}`} subtitle="Before (outline) vs after (solid), rule-based agent" bodyClass="flex flex-col gap-2.5 p-3">
            {d.hypotheses.map((h, i) => {
              const c = h.kind === "epidemic" ? "#E5535D" : "#5FBDBF";
              return (
                <div key={h.category}>
                  <div className="flex justify-between text-[11.5px]">
                    <span className="truncate text-ink">{h.title}</span>
                    <span className="num text-ink-2">
                      {Math.round(h.before * 100)}% → <b>{Math.round(h.after * 100)}%</b>
                    </span>
                  </div>
                  <div className="relative mt-1 h-2.5 rounded-full bg-ink/5">
                    <div className="absolute inset-y-0 left-0 rounded-full border" style={{ width: `${h.before * 100}%`, borderColor: c }} />
                    <motion.div className="absolute inset-y-0 left-0 rounded-full" style={{ background: c }} initial={{ width: `${h.before * 100}%` }} animate={{ width: `${h.after * 100}%` }} transition={{ delay: 0.3 + i * 0.08, duration: 0.7 }} />
                  </div>
                </div>
              );
            })}
          </Panel>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}
