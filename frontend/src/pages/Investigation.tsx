import { AnimatePresence, motion } from "framer-motion";
import { AlertOctagon, ArrowRight, Check, CheckCircle2, CircleDashed, Cpu, Loader2, RefreshCw, ShieldCheck, WifiOff, X } from "lucide-react";
import { useEffect } from "react";
import { DistrictPicker } from "../components/DistrictPicker";
import { EvidenceGraph } from "../components/EvidenceGraph";
import { Badge, CountUp, EmptyState, ErrorState, IdChip, LoadingBlock, Panel, TierChip } from "../components/ui";
import { useRunParams } from "../lib/api";
import { pct, titleCase } from "../lib/format";
import { useApp } from "../lib/state";
import { STEPS, useAnalyzeStream } from "../lib/stream";
import type { Assessment, CaseFile, Hypothesis, StepEvent } from "../lib/types";
import { color, confounderStatus, motion as mo, tier as tierTok, TIERS } from "../theme";

export default function Investigation() {
  const { district, setDistrict, go, rerunTick } = useApp();
  const p = useRunParams();
  const s = useAnalyzeStream({ ...p, district });
  const cf = s.casefile;
  // Header CTA "Re-run agents" bumps rerunTick.
  useEffect(() => {
    if (rerunTick) s.run();
  }, [rerunTick]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="flex flex-col gap-3">
      <Panel bodyClass="flex flex-wrap items-center gap-x-6 gap-y-3 px-4 py-3">
        <div>
          <div className="label-caps mb-1">Case file</div>
          <DistrictPicker value={district} onChange={setDistrict} />
        </div>
        <div className="flex min-w-0 max-w-full items-center gap-3">
          {cf ? <TierChip tier={cf.assessment.gate.tier} size="lg" label /> : <div className="shimmer h-9 w-48" />}
        </div>
        {cf && <Gauge a={cf.assessment} />}
        <div className="ml-auto flex flex-wrap items-center gap-2">
          {cf && <VerifierBadge cf={cf} />}
          {cf && <ModeBadge cf={cf} />}
          {s.running && <span className="inline-flex items-center gap-1.5 text-xs text-ink-3"><RefreshCw size={13} className="animate-spin" /> Agents running…</span>}
        </div>
      </Panel>

      <Stepper steps={s.steps} running={s.running} />

      {s.error && !cf && (
        <Panel>
          <ErrorState error={new Error(s.error)} retry={s.run} />
        </Panel>
      )}
      {!cf && !s.error && (
        <div className="grid grid-cols-1 gap-3 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
          <Panel title="Hypotheses">
            <LoadingBlock label="Agents are reasoning over the evidence packet" rows={7} />
          </Panel>
          <Panel title="Evidence gate">
            <LoadingBlock label="Waiting for the deterministic grade" rows={7} />
          </Panel>
        </div>
      )}

      {cf && (
        <>
          <div className="grid grid-cols-1 gap-3 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
            <Hypotheses cf={cf} />
            <div className="flex min-w-0 flex-col gap-3">
              <WhyPanel cf={cf} />
              <Checklist a={cf.assessment} />
            </div>
          </div>
          <Panel title="Evidence graph" subtitle="Every agent claim → the evidence IDs it cites → the feed or check they come from. Hover to trace; click an ID to inspect." delay={0.1} bodyClass="p-3">
            <EvidenceGraph hypotheses={cf.hypotheses} />
          </Panel>
          <Recommendations cf={cf} onQueue={() => go("actions")} />
        </>
      )}
    </div>
  );
}

function Gauge({ a }: { a: Assessment }) {
  const { point, low, high } = a.confidence;
  const c = tierTok[a.gate.tier].color;
  const R = 34;
  const arc = (from: number, to: number) => {
    const p = (v: number) => {
      const ang = Math.PI * (1 - v);
      return [44 + R * Math.cos(ang), 42 - R * Math.sin(ang)];
    };
    const [x1, y1] = p(from);
    const [x2, y2] = p(to);
    return `M${x1},${y1} A${R},${R} 0 0 1 ${x2},${y2}`;
  };
  return (
    <div className="flex items-center gap-3" title="Calibrated confidence with bootstrap P10–P90 interval">
      <svg width={88} height={50} viewBox="0 0 88 50" aria-hidden>
        <path d={arc(0, 1)} stroke="rgba(23,54,58,0.1)" strokeWidth={7} fill="none" strokeLinecap="round" />
        <path d={arc(low, Math.max(high, low + 0.01))} stroke={`${c}55`} strokeWidth={7} fill="none" />
        <motion.path d={arc(0, Math.max(point, 0.01))} stroke={c} strokeWidth={3} fill="none" strokeLinecap="round" initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 0.9, ease: mo.ease }} />
      </svg>
      <div>
        <div className="label-caps">Confidence</div>
        <div className="flex items-baseline gap-1.5 leading-none text-ink">
          <span className="text-2xl font-semibold">
            <CountUp value={point * 100} suffix="%" />
          </span>
          <span className="num text-[13px] font-medium text-ink-2">
            [{Math.round(low * 100)}–{Math.round(high * 100)}]
          </span>
        </div>
        <div className="mt-0.5 text-[10.5px] text-ink-3">bootstrap P10–P90 interval</div>
      </div>
    </div>
  );
}

function VerifierBadge({ cf }: { cf: CaseFile }) {
  const v = cf.verification;
  const all = v.grounded_claims === v.total_claims;
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-medium ${all ? "border-good/40 bg-good/10 text-good" : "border-e2/40 bg-e2/10 text-e2"}`} title={`Verifier: ${v.dropped.length} claim(s) dropped · critic ${v.critic}`}>
      <ShieldCheck size={14} />
      <span className="num">
        {v.grounded_claims}/{v.total_claims}
      </span>
      claims grounded
    </span>
  );
}

function ModeBadge({ cf }: { cf: CaseFile }) {
  const u = cf.usage;
  if (u.mode === "online")
    return (
      <span className="inline-flex items-center gap-1.5 rounded-lg border border-accent/30 px-2.5 py-1.5 text-xs text-accent-ink" title={`${u.model} · ${u.input_tokens + u.output_tokens} tokens · cache hits ${u.cache_hits}`}>
        <Cpu size={13} /> LLM · <span className="num">{u.calls} calls · ${u.cost_usd.toFixed(3)}</span>
      </span>
    );
  return (
    <span className="inline-flex items-center gap-1.5 rounded-lg border border-e2/35 bg-e2/[0.06] px-2.5 py-1.5 text-xs text-e2" title={u.degraded_reason ?? ""}>
      <WifiOff size={13} /> Degraded mode · rule-based reasoning
    </span>
  );
}

function Stepper({ steps, running }: { steps: Record<string, StepEvent>; running: boolean }) {
  return (
    <Panel bodyClass="px-3 py-3" delay={0.03}>
      <ol className="grid grid-cols-4 gap-2 lg:grid-cols-8">
        {STEPS.map((name, i) => {
          const ev = steps[name];
          const st = ev?.status;
          const done = st === "done" || st === "degraded" || st === "blocked";
          const tone = st === "degraded" ? color.warning : st === "blocked" ? color.critical : done ? color.accent : st === "running" ? color.accent : color.textMuted;
          return (
            <li key={name} className="relative">
              <div className="flex items-center gap-2">
                <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full border" style={{ borderColor: `${tone}${done || st === "running" ? "aa" : "33"}`, background: done ? `${tone}1f` : "transparent", color: tone }}>
                  {st === "running" ? <Loader2 size={14} className="animate-spin" /> : st === "blocked" ? <AlertOctagon size={14} /> : done ? <Check size={14} /> : running ? <CircleDashed size={14} /> : <span className="num text-[10px]">{i + 1}</span>}
                </span>
                <span className={`text-[12.5px] font-medium ${done || st === "running" ? "text-ink" : "text-ink-3"}`}>{name}</span>
                {i < STEPS.length - 1 && <span className="hidden h-px flex-1 lg:block" style={{ background: done ? `${tone}66` : "rgba(23,54,58,0.1)" }} />}
              </div>
              <AnimatePresence>
                {ev && ev.status !== "running" && (
                  <motion.div initial={{ opacity: 0, y: -3 }} animate={{ opacity: 1, y: 0 }} className="mt-1 pl-9 text-[10.5px] leading-snug text-ink-3">
                    <span className="line-clamp-2" title={ev.detail}>
                      {st === "degraded" ? "degraded · " : st === "blocked" ? "blocked · " : ""}
                      {ev.detail}
                    </span>
                    <span className="num text-ink-3/70">{ev.ms.toFixed(0)} ms</span>
                  </motion.div>
                )}
              </AnimatePresence>
            </li>
          );
        })}
      </ol>
    </Panel>
  );
}

function Hypotheses({ cf }: { cf: CaseFile }) {
  return (
    <Panel title="Ranked hypotheses" subtitle={`Epidemic and non-epidemic explanations · ${cf.usage.mode === "online" ? "LLM agent" : "rule-based agent"}, verified`} delay={0.05} bodyClass="flex flex-col gap-2.5 p-3">
      {cf.hypotheses.length === 0 && <EmptyState title="No hypotheses survived verification" />}
      {cf.hypotheses.map((h, i) => (
        <HypothesisCard key={h.hypothesis_id || i} h={h} i={i} />
      ))}
      {cf.verification.dropped.length > 0 && (
        <div className="rounded-xl border border-e2/25 bg-e2/[0.05] p-3">
          <div className="label-caps text-e2">Dropped by verifier</div>
          {cf.verification.dropped.map((d) => (
            <div key={d.claim_id} className="mt-1.5 text-[11.5px] text-ink-3">
              <span className="line-through">{d.text}</span> <span className="text-e2">({d.reason})</span>
            </div>
          ))}
        </div>
      )}
    </Panel>
  );
}

function HypothesisCard({ h, i }: { h: Hypothesis; i: number }) {
  const epi = h.kind === "epidemic";
  const c = epi ? tierTok.E3.color : "#6F8F8A";
  return (
    <motion.article initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 + i * mo.stagger, ease: mo.ease }} className="rounded-xl border border-line/30 bg-white/50 p-3.5" style={{ borderLeft: `3px solid ${c}` }}>
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="num text-[11px] text-ink-3">#{i + 1}</span>
            <h3 className="text-[14px] font-semibold text-ink">{h.title}</h3>
            <Badge color={epi ? tierTok.E3.ink : "#4A6B65"}>{epi ? "EPIDEMIC" : "NON-EPIDEMIC"}</Badge>
          </div>
          <p className="mt-1 text-[12.5px] leading-relaxed text-ink-2">{h.summary}</p>
        </div>
        <div className="w-24 shrink-0 text-right">
          <div className="text-xl font-semibold text-ink">
            <CountUp value={h.probability * 100} digits={h.probability < 0.1 ? 1 : 0} suffix="%" />
          </div>
          <div className="mt-1 h-1 overflow-hidden rounded-full bg-ink/10">
            <motion.div className="h-full rounded-full" style={{ background: c }} initial={{ width: 0 }} animate={{ width: pct(h.probability) }} transition={{ duration: 0.8, ease: mo.ease }} />
          </div>
        </div>
      </div>
      {h.claims.length > 0 && (
        <ul className="mt-2.5 flex flex-col gap-1.5 border-t border-line/30 pt-2.5">
          {h.claims.map((c) => (
            <li key={c.claim_id} className="flex gap-2 text-[12px] leading-relaxed text-ink-2">
              <CheckCircle2 size={13} className="mt-[3px] shrink-0 text-good" aria-label="grounded" />
              <div className="min-w-0">
                {c.text}
                <div className="mt-1 flex flex-wrap gap-1">
                  {c.evidence_ids.map((id) => (
                    <IdChip key={id} id={id} />
                  ))}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </motion.article>
  );
}

function WhyPanel({ cf }: { cf: CaseFile }) {
  const g = cf.assessment.gate;
  const isE3 = g.tier === "E3";
  const byTier = TIERS.slice(1).map((t) => ({ t, rows: g.criteria.filter((c) => c.tier === t) }));
  return (
    <Panel title={isE3 ? "Why E3?" : "Why not E3?"} subtitle="Deterministic evidence gate: the LLM never sets the tier" delay={0.08} bodyClass="p-3">
      <p className="mb-3 rounded-lg border border-line/30 bg-white/50 p-2.5 text-[12px] leading-relaxed text-ink-2">{cf.tier_explanation}</p>
      <div className="flex flex-col gap-3">
        {byTier.map(({ t, rows }) => (
          <div key={t}>
            <div className="mb-1 flex items-center gap-2">
              <TierChip tier={t} size="sm" />
              <span className="text-[11px] text-ink-3">{tierTok[t].label}</span>
            </div>
            <ul className="flex flex-col gap-1">
              {rows.map((c) => (
                <li key={c.criterion_id} className="grid grid-cols-[18px_1fr_auto] items-start gap-2 rounded-lg px-1.5 py-1 text-[12px] hover:bg-white/50">
                  {c.met ? <Check size={14} className="mt-[2px] text-good" /> : <X size={14} className="mt-[2px] text-e3" />}
                  <div className="min-w-0">
                    <div className={c.met ? "text-ink-2" : "text-ink"}>{c.label}</div>
                    <div className="text-[10.5px] text-ink-3">{c.detail}</div>
                  </div>
                  <div className="text-right">
                    <div className="num text-[11px] text-ink-2">{typeof c.value === "number" ? (Number.isInteger(c.value) ? c.value : c.value.toFixed(2)) : (c.value ?? "–")}</div>
                    <div className="num text-[10px] text-ink-3">{c.threshold}</div>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      {g.downgrades.length > 0 && (
        <div className="mt-3 rounded-lg border border-e2/30 bg-e2/[0.06] p-2.5 text-[12px] text-e2">
          <div className="label-caps text-e2">Downgrades applied</div>
          {g.downgrades.map((d) => (
            <div key={d} className="mt-1">
              ↓ {d}
            </div>
          ))}
        </div>
      )}
    </Panel>
  );
}

function Checklist({ a }: { a: Assessment }) {
  return (
    <Panel title="Alternative explanations" subtitle="PASS = alternative ruled out · FAIL = it explains the signal" delay={0.12} bodyClass="p-3">
      {a.confounders.length === 0 ? (
        <EmptyState title="Nothing to test" body="No signal, so there are no alternative explanations to check." />
      ) : (
        <ul className="flex flex-col gap-2">
          {a.confounders.map((c) => {
            const st = confounderStatus[c.status];
            return (
              <li key={c.confounder_id} className="rounded-lg border border-line/30 bg-white/50 p-2.5">
                <div className="flex items-center gap-2">
                  <Badge color={st.color}>{st.label}</Badge>
                  <span className="flex-1 text-[12.5px] font-medium text-ink">{c.label || titleCase(c.name)}</span>
                  <span className="num text-[11px] text-ink-3" title="Share of the excess this alternative explains">
                    explains {pct(c.explained_share)}
                  </span>
                </div>
                <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-ink/10">
                  <div className="h-full rounded-full" style={{ width: pct(c.explained_share), background: st.color }} />
                </div>
                <p className="mt-1.5 text-[11.5px] leading-relaxed text-ink-3">{c.summary}</p>
                <div className="mt-1.5 flex flex-wrap gap-1">
                  <IdChip id={c.confounder_id} />
                  {c.evidence_ids.slice(0, 2).map((id) => (
                    <IdChip key={id} id={id} dim />
                  ))}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </Panel>
  );
}

function Recommendations({ cf, onQueue }: { cf: CaseFile; onQueue: () => void }) {
  const blocked = cf.steps.find((s) => s.step === "Recommend")?.status === "blocked";
  return (
    <Panel
      title="Recommended actions"
      subtitle={`From the approved catalog, gated by tier ${cf.assessment.gate.tier}. Proposals only: a human approves each one.`}
      right={
        <button onClick={onQueue} className="inline-flex items-center gap-1 rounded-lg border border-accent/40 bg-accent/10 px-3 py-1.5 text-xs font-semibold text-accent-ink hover:bg-accent/20">
          Open Action Queue <ArrowRight size={13} />
        </button>
      }
      delay={0.15}
      bodyClass="p-3"
    >
      {blocked && <div className="mb-2 rounded-lg border border-e3/40 bg-e3/10 p-2.5 text-xs text-e3">Kill switch engaged: proposals were not queued.</div>}
      {cf.recommendations.length === 0 ? (
        <EmptyState title="No actions recommended" body="At this evidence tier the catalog allows no action, or nothing is warranted." />
      ) : (
        <div className="grid grid-cols-1 gap-2 md:grid-cols-2 2xl:grid-cols-3">
          {cf.recommendations.map((r, i) => (
            <motion.div key={r.action} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 + i * mo.stagger }} className="flex flex-col rounded-xl border border-line/30 bg-white/50 p-3">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[13px] font-semibold text-ink">{r.title}</span>
                <span className="num text-[10px] text-ink-3">min {r.min_tier}</span>
              </div>
              <p className="mt-1 flex-1 text-[12px] leading-relaxed text-ink-2">{r.rationale}</p>
              <div className="mt-2 flex flex-wrap items-center gap-1">
                {r.evidence_ids.slice(0, 3).map((id) => (
                  <IdChip key={id} id={id} />
                ))}
              </div>
              <div className="mt-2 flex items-center justify-between border-t border-line/30 pt-2 text-[11px]">
                <span className="text-ink-3">{r.source === "llm" ? "LLM recommender" : "Rule recommender"}</span>
                {r.pending_ref ? <span className="num text-e2">⏳ {r.pending_ref} · awaiting approval</span> : <span className="text-ink-3">not queued</span>}
              </div>
            </motion.div>
          ))}
        </div>
      )}
    </Panel>
  );
}
