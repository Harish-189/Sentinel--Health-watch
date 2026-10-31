import { motion, useReducedMotion } from "framer-motion";
import { Droplets, Layers, Shapes, Thermometer, Wind, type LucideIcon } from "lucide-react";
import type { SyndromeFilter } from "../lib/state";
import type { AnalysisBundle } from "../lib/types";

export const SYNDROMES: { key: SyndromeFilter; label: string; icon: LucideIcon }[] = [
  { key: "all", label: "All signals", icon: Layers },
  { key: "respiratory", label: "Respiratory", icon: Wind },
  { key: "gastrointestinal", label: "Gastrointestinal", icon: Droplets },
  { key: "febrile_rash", label: "Febrile-rash", icon: Thermometer },
  { key: "other", label: "Other", icon: Shapes },
];

/**
 * Does a district match the syndrome filter? Respiratory/GI use the district's corroborated signal (what the gate
 * grades). Febrile-rash and Other have no signal of their own (they feed respiratory / both), so they match when the
 * district has a live clinic anomaly on that metric.
 */
export function matchesSyndrome(a: AnalysisBundle | undefined, district: string, syndrome: SyndromeFilter, frameSyndrome?: string | null): boolean {
  if (syndrome === "all") return true;
  if (syndrome === "respiratory" || syndrome === "gastrointestinal") {
    const s = frameSyndrome ?? a?.assessments.find((x) => x.district === district)?.signal?.syndrome;
    return s === syndrome;
  }
  const prefix = `EV-${district}-CLI-${syndrome}-`;
  return Object.keys(a?.evidence ?? {}).some((id) => id.startsWith(prefix));
}

export function SyndromeRow({ value, onChange, counts }: { value: SyndromeFilter; onChange: (s: SyndromeFilter) => void; counts?: Partial<Record<SyndromeFilter, number>> }) {
  const reduce = useReducedMotion();
  return (
    <div role="radiogroup" aria-label="Syndrome filter" className="flex flex-wrap gap-2">
      {SYNDROMES.map(({ key, label, icon: Icon }) => {
        const on = value === key;
        const n = counts?.[key];
        return (
          <motion.button
            key={key}
            role="radio"
            aria-checked={on}
            onClick={() => onChange(key)}
            whileTap={reduce ? undefined : { scale: 0.97 }}
            className={`relative flex min-w-[118px] items-center gap-2.5 rounded-2xl border px-3 py-2 text-left outline-none transition-colors duration-150 focus-visible:ring-2 focus-visible:ring-accent-strong ${
              on ? "border-accent-strong/60 text-ink" : "border-line/30 bg-white/55 text-ink-2 hover:bg-white/85 hover:text-ink"
            }`}
          >
            {on && <motion.span layoutId="syndrome-on" transition={reduce ? { duration: 0 } : { type: "spring", stiffness: 500, damping: 38 }} className="absolute inset-0 rounded-2xl bg-mint" />}
            <span className={`relative grid h-8 w-8 shrink-0 place-items-center rounded-xl ${on ? "bg-white/80 text-accent-ink" : "bg-mint/50 text-ink-2"}`}>
              <Icon size={16} />
            </span>
            <span className="relative min-w-0">
              <span className="block text-[12.5px] font-semibold leading-tight">{label}</span>
              {n !== undefined && (
                <span className="num block text-[10.5px] text-ink-3">
                  {n} district{n === 1 ? "" : "s"}
                </span>
              )}
            </span>
          </motion.button>
        );
      })}
    </div>
  );
}
