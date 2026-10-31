import { motion } from "framer-motion";
import { ArrowUpRight, FlaskConical, UserRound } from "lucide-react";
import { useState } from "react";
import type { District, DistrictFrame } from "../lib/types";
import { tier as tierTok, TIERS } from "../theme";

// ------------------------------------------------------------------ State Pulse

const WEIGHT: Record<string, number> = { E0: 0, E1: 1, E2: 2, E3: 3 };

/** Statewide Alert Index (0–100): population-weighted mean tier weight, E0=0 … E3=3, scaled to 100. */
export function alertIndex(districts: District[], frames: Record<string, DistrictFrame>) {
  const total = districts.reduce((s, d) => s + d.population, 0) || 1;
  const score = districts.reduce((s, d) => s + d.population * WEIGHT[frames[d.code]?.tier ?? "E0"], 0);
  const counts = Object.fromEntries(TIERS.map((t) => [t, districts.filter((d) => (frames[d.code]?.tier ?? "E0") === t).length]));
  return { index: Math.round((score / (3 * total)) * 100), counts };
}

export function StatePulse({ districts, frames }: { districts: District[]; frames: Record<string, DistrictFrame> }) {
  const [hover, setHover] = useState(false);
  const { index, counts } = alertIndex(districts, frames);
  const band = index >= 40 ? "high" : index >= 15 ? "elevated" : "calm";
  const c = band === "high" ? { a: "#FFAFB3", b: "#E5535D", ink: tierTok.E3.ink } : band === "elevated" ? { a: "#FBD6A8", b: "#F2A65A", ink: tierTok.E2.ink } : { a: "#BADDD6", b: "#2E9EA3", ink: tierTok.E1.ink };
  const period = (1.6 - (index / 100) * 1.0).toFixed(2); // 1.6 s calm → 0.6 s at index 100
  const bpm = Math.round(60 / Number(period));

  return (
    <div
      className="glass relative overflow-visible p-3.5"
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      onFocus={() => setHover(true)}
      onBlur={() => setHover(false)}
      tabIndex={0}
      aria-label={`State Pulse: alert index ${index} of 100, ${band}`}
      style={{ ["--beat" as string]: `${period}s` }}
    >
      <div className="flex items-center gap-3">
        <svg width="74" height="66" viewBox="0 0 74 66" aria-hidden className="shrink-0 overflow-visible">
          <defs>
            <linearGradient id="heart-g" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stopColor={c.a} />
              <stop offset="100%" stopColor={c.b} />
            </linearGradient>
            <filter id="heart-glow" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation="4" result="b" />
              <feMerge>
                <feMergeNode in="b" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>
          <g className="heartbeat" style={{ transformOrigin: "37px 34px" }}>
            <path d="M37 60 C14 44 4 32 4 20 C4 10 12 3 21 3 C28 3 33 7 37 13 C41 7 46 3 53 3 C62 3 70 10 70 20 C70 32 60 44 37 60 Z" fill="url(#heart-g)" filter="url(#heart-glow)" />
          </g>
          <path className="ecg" d="M2 34 H20 L25 34 L29 22 L34 46 L39 14 L43 38 L47 34 H72" fill="none" stroke="#fff" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" pathLength={100} />
        </svg>
        <div className="min-w-0">
          <div className="label-caps">State Pulse</div>
          <div className="mt-0.5 flex items-baseline gap-1.5">
            <span className="num text-[26px] font-semibold leading-none" style={{ color: c.ink }}>
              {index}
            </span>
            <span className="text-[11px] text-ink-3">/ 100 · {band}</span>
          </div>
          <div className="num mt-0.5 text-[10.5px] text-ink-3">{bpm} beats/min · alert index</div>
        </div>
      </div>
      <p className="mt-2 text-[10.5px] leading-snug text-ink-3">Aggregate index, not individual vitals.</p>

      {hover && (
        <motion.div
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          className="glass absolute bottom-[calc(100%+8px)] left-0 z-30 w-72 p-3 text-[11.5px] leading-relaxed text-ink-2"
          style={{ background: "rgba(255,253,251,0.97)" }}
          role="tooltip"
        >
          <div className="mb-1 font-semibold text-ink">How the Alert Index is computed</div>
          Population-weighted mean of district tiers (E0 = 0, E1 = 1, E2 = 2, E3 = 3), divided by 3 and scaled to 100.
          Weights are simulated catchment populations.
          <div className="num mt-2 grid grid-cols-4 gap-1 text-center">
            {TIERS.map((t) => (
              <span key={t} className="rounded-md py-1" style={{ background: `${tierTok[t].color}33`, color: tierTok[t].ink }}>
                {t} · {counts[t]}
              </span>
            ))}
          </div>
          <div className="mt-2 text-[10.5px] text-ink-3">Beat rate and colour follow the index. Not a clinical or individual measure.</div>
        </motion.div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ Insight card

export function InsightCard({ onOpen }: { onOpen: () => void }) {
  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.35 }} className="relative isolate shrink-0 overflow-hidden rounded-2xl border border-white/60 p-4 text-sidebar shadow-[0_18px_36px_-24px_rgba(15,63,67,0.6)]">
      {/* blurred gradient blobs */}
      <div className="absolute inset-0 -z-10 bg-gradient-to-br from-[#BADDD6] via-[#E8F3EF] to-[#FFD3D5]" />
      <div className="absolute -right-10 -top-12 -z-10 h-36 w-36 rounded-full bg-[#5FBDBF] opacity-50 blur-2xl" />
      <div className="absolute -bottom-14 -left-8 -z-10 h-36 w-36 rounded-full bg-[#FFAFB3] opacity-70 blur-2xl" />
      <div className="flex items-center gap-1.5 text-[10.5px] font-semibold uppercase tracking-[0.14em] text-sidebar/70">
        <FlaskConical size={12} /> Scenario Lab
      </div>
      <h3 className="mt-1.5 text-[17px] font-semibold leading-snug">Test a surprise scenario</h3>
      <p className="mt-1 text-[12px] leading-snug text-sidebar/75">Inject a holiday rush, a reporting change or a lab backlog and watch the gate refuse to escalate.</p>
      <div className="mt-3 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2" title="3 human reviewers on duty">
          <div className="flex -space-x-2">
            {[0, 1, 2].map((i) => (
              <span key={i} className="grid h-7 w-7 place-items-center rounded-full border-2 border-white bg-sidebar text-cream" style={{ opacity: 1 - i * 0.12 }}>
                <UserRound size={13} />
              </span>
            ))}
          </div>
          <span className="text-[11px] font-medium leading-tight text-sidebar/80">
            3 human reviewers
            <br />
            on duty
          </span>
        </div>
        <button onClick={onOpen} className="inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-full bg-sidebar py-1.5 pl-3 pr-1.5 text-[12px] font-semibold text-cream outline-none transition-colors duration-150 hover:bg-[#0B3236] focus-visible:ring-2 focus-visible:ring-accent">
          Open lab
          <span className="grid h-5 w-5 place-items-center rounded-full bg-accent text-sidebar">
            <ArrowUpRight size={12} strokeWidth={2.5} />
          </span>
        </button>
      </div>
    </motion.div>
  );
}
