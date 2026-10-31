import { motion } from "framer-motion";
import { ChevronRight, Pause, Play, Radio, SkipBack } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { HexMap } from "../components/HexMap";
import { CountUp, EmptyState, ErrorState, IdChip, LoadingBlock, Panel, TierChip } from "../components/ui";
import { useActions, useAnalysis, useDistricts, useTimeline } from "../lib/api";
import { pct, shortDate } from "../lib/format";
import { useApp } from "../lib/state";
import type { AnalysisBundle, DistrictFrame, Timeline } from "../lib/types";
import { color, motion as mo, source as srcColor, tier as tierTok, TIERS, type Tier } from "../theme";

function framesFromAnalysis(a: AnalysisBundle): Record<string, DistrictFrame> {
  return Object.fromEntries(
    a.assessments.map((x) => [
      x.district,
      { tier: x.gate.tier, confidence: x.confidence.point, sources: x.signal?.independent_sources ?? 0, syndrome: x.signal?.syndrome ?? null, peak_z: x.signal?.peak_z ?? null },
    ]),
  );
}

export default function CommandCenter() {
  const analysis = useAnalysis();
  const districts = useDistricts();
  const timeline = useTimeline();
  const { go, district, setDistrict } = useApp();
  const [idx, setIdx] = useState<number | null>(null); // null = live (latest)
  const [playing, setPlaying] = useState(false);

  const frames = timeline.data?.frames ?? [];
  const last = frames.length - 1;
  const cur = idx ?? last;

  useEffect(() => {
    if (!playing || !frames.length) return;
    const t = setInterval(() => {
      setIdx((i) => {
        const n = (i ?? last) + 1;
        if (n >= last) {
          setPlaying(false);
          return null;
        }
        return n;
      });
    }, 420);
    return () => clearInterval(t);
  }, [playing, frames.length, last]);

  const liveFrames = useMemo(() => (analysis.data ? framesFromAnalysis(analysis.data) : {}), [analysis.data]);
  const isLive = idx === null;
  const view = !isLive && frames[cur] ? frames[cur].districts : liveFrames;
  const viewDate = !isLive && frames[cur] ? frames[cur].date : analysis.data?.as_of_date;

  if (analysis.error) return <Panel><ErrorState error={analysis.error} retry={() => analysis.refetch()} /></Panel>;

  return (
    <div className="grid grid-cols-1 gap-3 lg:grid-cols-[300px_minmax(0,1fr)] 2xl:grid-cols-[320px_minmax(0,1fr)_300px]">
      <ActiveSignals frames={view} names={Object.fromEntries((districts.data ?? []).map((d) => [d.code, d.name]))} loading={!analysis.data} analysis={isLive ? analysis.data : undefined} onOpen={(d) => go("investigation", d)} />

      <Panel
        title={
          <span className="flex items-center gap-2">
            District evidence map
            {isLive ? (
              <span className="inline-flex items-center gap-1 rounded-full border border-good/30 px-2 py-[1px] text-[10px] font-semibold text-good">
                <Radio size={10} className="blink" /> LIVE
              </span>
            ) : (
              <span className="num rounded-full border border-accent/40 px-2 py-[1px] text-[10px] font-semibold text-accent-ink">REPLAY</span>
            )}
          </span>
        }
        subtitle={viewDate ? `Aggregates through ${shortDate(viewDate)} · click a district to investigate` : "Loading…"}
        right={<TierLegend />}
        delay={0.05}
        bodyClass="p-2"
      >
        {districts.data && analysis.data ? (
          <HexMap
            districts={districts.data}
            frames={view}
            selected={district}
            onSelect={(d) => {
              setDistrict(d);
              go("investigation", d);
            }}
            height={620}
            scanning={playing || analysis.isFetching}
          />
        ) : (
          <div className="p-4">
            <LoadingBlock label="Running detectors across 8 districts" rows={8} />
          </div>
        )}
        <Scrubber timeline={timeline.data} loading={timeline.isLoading} error={timeline.error} cur={cur} isLive={isLive} playing={playing} onPlay={() => {
          if (!frames.length) return;
          if (isLive || cur >= last) setIdx(0);
          setPlaying((p) => !p);
        }} onSeek={(i) => {
          setPlaying(false);
          setIdx(i >= last ? null : i);
        }} />
      </Panel>

      <div className="lg:col-span-2 2xl:col-span-1">
        <Kpis analysis={analysis.data} timeline={timeline.data} />
      </div>
    </div>
  );
}

function TierLegend() {
  return (
    <div className="hidden items-center gap-2.5 md:flex">
      {TIERS.map((t) => (
        <span key={t} className="num inline-flex items-center gap-1 text-[10.5px] text-ink-3" title={tierTok[t].label}>
          <span className="h-2 w-2 rounded-sm" style={{ background: tierTok[t].color }} />
          {t} <span className="font-sans">{tierTok[t].short}</span>
        </span>
      ))}
    </div>
  );
}

function ActiveSignals({ frames, names, loading, analysis, onOpen }: { frames: Record<string, DistrictFrame>; names: Record<string, string>; loading: boolean; analysis?: AnalysisBundle; onOpen: (d: string) => void }) {
  const rows = Object.entries(frames)
    .filter(([, f]) => f.tier !== "E0")
    .sort((a, b) => TIERS.indexOf(b[1].tier) - TIERS.indexOf(a[1].tier) || b[1].confidence - a[1].confidence);
  return (
    <Panel title="Active signals" subtitle={`${rows.length} district${rows.length === 1 ? "" : "s"} above background`} bodyClass="p-2">
      {loading ? (
        <div className="p-2">
          <LoadingBlock rows={6} />
        </div>
      ) : rows.length === 0 ? (
        <EmptyState title="All quiet" body="No district shows a sustained anomaly. Detectors keep scoring every series against its seasonal baseline." />
      ) : (
        <ul className="flex flex-col gap-1.5">
          {rows.map(([code, f], i) => {
            const a = analysis?.assessments.find((x) => x.district === code);
            return (
              <motion.li key={code} layout initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * mo.stagger, ease: mo.ease }}>
                <button onClick={() => onOpen(code)} className="group w-full rounded-xl border border-line/30 bg-white/50 p-3 text-left transition-colors hover:border-accent/30 hover:bg-white/80" style={{ borderLeft: `3px solid ${tierTok[f.tier].color}` }}>
                  <div className="flex items-center justify-between gap-2">
                    <div className="min-w-0">
                      <div className="truncate text-[13px] font-semibold text-ink">{names[code] ?? code}</div>
                      <div className="text-[11px] capitalize text-ink-3">
                        {f.syndrome ?? "–"} · <span className="num">{f.sources}</span> source{f.sources === 1 ? "" : "s"}
                      </div>
                    </div>
                    <TierChip tier={f.tier} size="sm" />
                  </div>
                  <div className="mt-2 flex items-center gap-2">
                    <div className="h-1 flex-1 overflow-hidden rounded-full bg-ink/10">
                      <motion.div className="h-full rounded-full" style={{ background: tierTok[f.tier].color }} initial={{ width: 0 }} animate={{ width: pct(f.confidence) }} transition={{ duration: 0.6, ease: mo.ease }} />
                    </div>
                    <span className="num w-9 text-right text-[11px] text-ink-2">{pct(f.confidence)}</span>
                  </div>
                  {a?.signal && (
                    <div className="mt-2 flex items-center justify-between">
                      <div className="flex gap-1">
                        {a.signal.sources.map((s) => (
                          <span key={s} title={s} className="h-1.5 w-4 rounded-full" style={{ background: srcColor[s] ?? color.textMuted }} />
                        ))}
                      </div>
                      <span className="flex items-center gap-1 text-[10.5px] text-ink-3 group-hover:text-accent-ink">
                        Investigate <ChevronRight size={12} />
                      </span>
                    </div>
                  )}
                </button>
              </motion.li>
            );
          })}
        </ul>
      )}
    </Panel>
  );
}

function Scrubber({ timeline, loading, error, cur, isLive, playing, onPlay, onSeek }: { timeline?: Timeline; loading: boolean; error: unknown; cur: number; isLive: boolean; playing: boolean; onPlay: () => void; onSeek: (i: number) => void }) {
  if (error) return <div className="px-3 pb-2 text-xs text-e3">Replay unavailable: {(error as Error).message}</div>;
  if (loading || !timeline)
    return (
      <div className="flex items-center gap-3 border-t border-line/30 px-3 py-3 text-xs text-ink-3">
        <span className="blink h-1.5 w-1.5 rounded-full bg-accent" /> Building replay frames (causal re-analysis per day)…
      </div>
    );
  const frames = timeline.frames;
  const maxTier = (f: (typeof frames)[number]): Tier => TIERS[Math.max(0, ...Object.values(f.districts).map((d) => TIERS.indexOf(d.tier)))];
  const onsetIdx = frames.findIndex((f) => f.as_of >= timeline.onset_day);
  return (
    <div className="border-t border-line/30 px-3 pb-2 pt-5">
      <div className="flex items-center gap-3">
        <button onClick={onPlay} className="inline-flex items-center gap-1.5 rounded-lg border border-accent/40 bg-accent/10 px-3 py-1.5 text-xs font-semibold text-accent-ink hover:bg-accent/20" aria-label={playing ? "Pause replay" : "Play replay"}>
          {playing ? <Pause size={13} /> : <Play size={13} />} {playing ? "Pause" : "Replay"}
        </button>
        <button onClick={() => onSeek(frames.length - 1)} disabled={isLive} className="inline-flex items-center gap-1 rounded-lg px-2 py-1.5 text-xs text-ink-3 hover:text-ink disabled:opacity-40" title="Jump to live">
          <SkipBack size={13} className="rotate-180" /> Live
        </button>
        <div className="relative flex-1">
          <div className="flex h-7 gap-[2px]">
            {frames.map((f, i) => {
              const t = maxTier(f);
              return (
                <button
                  key={f.as_of}
                  onClick={() => onSeek(i)}
                  className="relative flex-1 rounded-[3px] transition-all"
                  style={{ background: t === "E0" ? "rgba(23,54,58,0.1)" : `${tierTok[t].color}${i === cur ? "ff" : "88"}`, outline: i === cur ? `2px solid ${color.accent}` : undefined, outlineOffset: 1 }}
                  title={`${shortDate(f.date)}: highest tier ${t}`}
                  aria-label={`Frame ${shortDate(f.date)}`}
                />
              );
            })}
          </div>
          {onsetIdx > 0 && (
            <div className="pointer-events-none absolute -top-1 bottom-0 border-l border-dashed border-line/60" style={{ left: `${(onsetIdx / frames.length) * 100}%` }}>
              <span className="absolute -top-3.5 left-1 whitespace-nowrap text-[9.5px] text-ink-3">scenario onset</span>
            </div>
          )}
        </div>
        <div className="num w-[86px] text-right text-xs text-ink-2">{shortDate(frames[cur]?.date ?? frames[frames.length - 1].date)}</div>
      </div>
      <div className="num mt-1 flex justify-between pl-[150px] pr-[98px] text-[10px] text-ink-3">
        <span>{shortDate(frames[0].date)}</span>
        <span>{shortDate(frames[frames.length - 1].date)}</span>
      </div>
    </div>
  );
}

function Kpis({ analysis, timeline }: { analysis?: AnalysisBundle; timeline?: Timeline }) {
  const actions = useActions();
  const districts = useDistricts();
  if (!analysis)
    return (
      <Panel title="Key indicators">
        <LoadingBlock rows={8} />
      </Panel>
    );
  const pop = Object.fromEntries((districts.data ?? []).map((d) => [d.code, d.population]));
  const elevated = analysis.assessments.filter((a) => TIERS.indexOf(a.gate.tier) >= 2);
  const e3 = analysis.assessments.filter((a) => a.gate.tier === "E3");
  const popWatch = elevated.reduce((s, a) => s + (pop[a.district] ?? 0), 0);
  const top = [...analysis.assessments].sort((a, b) => Math.max(...b.forecast.breach_prob_beds) - Math.max(...a.forecast.breach_prob_beds))[0];
  const breach = Math.max(...top.forecast.breach_prob_beds);
  const pending = actions.data?.filter((a) => a.status === "pending").length ?? 0;
  // Lead time: first replay frame where the primary district reached E2 vs. first frame at E3.
  const primary = analysis.primary;
  const firstAt = (t: Tier) => timeline?.frames.find((f) => TIERS.indexOf(f.districts[primary]?.tier ?? "E0") >= TIERS.indexOf(t));
  const e1 = firstAt("E1");
  const e3f = firstAt("E3");
  const ps = analysis.assessments.find((a) => a.district === primary)?.signal;

  const cards: { label: string; value: React.ReactNode; hint: string; ids: string[]; accent?: string }[] = [
    { label: "Intervention-grade (E3)", value: <CountUp value={e3.length} />, hint: e3.map((a) => a.name).join(", ") || "none", ids: e3.slice(0, 2).map((a) => a.gate.criteria.find((c) => c.tier === "E3")?.criterion_id ?? "").filter(Boolean), accent: e3.length ? tierTok.E3.ink : undefined },
    { label: "Simulated catchment under watch (E2+)", value: <CountUp value={popWatch / 1000} suffix="k" />, hint: `${elevated.length} of ${analysis.assessments.length} districts`, ids: elevated.slice(0, 2).map((a) => a.signal?.signal_id ?? "").filter(Boolean) },
    { label: `Peak P(bed breach) · ${top.name}`, value: <CountUp value={breach * 100} suffix="%" />, hint: "within 14 days, Monte Carlo P10–P90", ids: [top.forecast.forecast_id], accent: breach >= 0.5 ? tierTok.E3.ink : breach >= 0.2 ? tierTok.E2.ink : undefined },
    { label: "First signal → E3", value: e1 && e3f ? <CountUp value={e3f.as_of - e1.as_of} suffix=" d" /> : "–", hint: e1 ? `first anomaly ${shortDate(e1.date)}${ps ? ` · ${ps.sources.length} sources` : ""}` : "no escalation", ids: ps ? [ps.signal_id] : [] },
    { label: "Actions awaiting approval", value: <CountUp value={pending} />, hint: "nothing executes without a human", ids: [], accent: pending ? tierTok.E2.ink : undefined },
  ];
  return (
    <Panel title="Key indicators" subtitle={`As of ${shortDate(analysis.as_of_date)}`} delay={0.1}>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5 2xl:grid-cols-1">
        {cards.map((c, i) => (
          <motion.div key={c.label} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 + i * mo.stagger }} className="rounded-xl border border-line/30 bg-white/50 p-3">
            <div className="label-caps leading-snug">{c.label}</div>
            <div className="mt-1.5 text-[26px] font-semibold leading-none" style={{ color: c.accent ?? color.text }}>
              {c.value}
            </div>
            <div className="mt-1 truncate text-[11px] text-ink-3" title={c.hint}>
              {c.hint}
            </div>
            {c.ids.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1">
                {c.ids.map((id) => (
                  <IdChip key={id} id={id} dim />
                ))}
              </div>
            )}
          </motion.div>
        ))}
      </div>
    </Panel>
  );
}
