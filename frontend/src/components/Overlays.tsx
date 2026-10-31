import { AnimatePresence, motion } from "framer-motion";
import { ArrowRight, FileSearch, X } from "lucide-react";
import { useState } from "react";
import { useEvidence } from "../lib/evidence";
import { color, tier as tierTok, TIERS } from "../theme";

function fmt(v: unknown): string {
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(3);
  if (Array.isArray(v)) return v.length > 6 ? `[${v.slice(0, 6).map(fmt).join(", ")}, … +${v.length - 6}]` : `[${v.map(fmt).join(", ")}]`;
  if (v && typeof v === "object") return JSON.stringify(v);
  return String(v);
}

/** Side drawer showing the stored record behind an evidence ID. */
export function EvidenceDrawer() {
  const { openId, open, lookup } = useEvidence();
  const item = openId ? lookup(openId) : undefined;
  return (
    <AnimatePresence>
      {openId && (
        <motion.aside
          key="drawer"
          initial={{ x: 380, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          exit={{ x: 380, opacity: 0 }}
          transition={{ type: "spring", stiffness: 320, damping: 34 }}
          className="glass fixed bottom-3 right-3 top-3 z-40 flex w-[360px] flex-col"
          style={{ background: "rgba(255,252,250,0.97)" }}
          aria-label="Evidence record"
        >
          <header className="flex items-start justify-between border-b border-line/30 p-4">
            <div className="min-w-0">
              <div className="label-caps flex items-center gap-1.5">
                <FileSearch size={12} /> Evidence record
              </div>
              <div className="num mt-1 break-all text-sm font-semibold text-accent-ink">{openId}</div>
            </div>
            <button onClick={() => open(null)} className="text-ink-3 hover:text-ink" aria-label="Close">
              <X size={16} />
            </button>
          </header>
          <div className="flex-1 overflow-y-auto p-4">
            {!item ? (
              <p className="text-sm text-ink-3">This ID is cited but its record is not loaded on this page.</p>
            ) : (
              <>
                <div className="flex gap-2 text-[11px]">
                  <span className="rounded border border-line/30 px-1.5 py-0.5 text-ink-2">{item.kind}</span>
                  {item.district && <span className="num rounded border border-line/30 px-1.5 py-0.5 text-ink-2">{item.district}</span>}
                </div>
                <p className="mt-3 text-sm leading-relaxed text-ink">{item.summary}</p>
                <div className="label-caps mt-5">Stored fields</div>
                <dl className="mt-2 divide-y divide-line/25 rounded-lg border border-line/30">
                  {Object.entries(item.data).map(([k, v]) => (
                    <div key={k} className="grid grid-cols-[120px_1fr] gap-2 px-3 py-1.5 text-[11.5px]">
                      <dt className="truncate text-ink-3" title={k}>
                        {k}
                      </dt>
                      <dd className="num break-all text-ink-2">{fmt(v)}</dd>
                    </div>
                  ))}
                </dl>
                <p className="mt-4 text-[11px] leading-relaxed text-ink-3">
                  Every number the agents quote must match a field here. The Verifier drops claims that don't.
                </p>
              </>
            )}
          </div>
        </motion.aside>
      )}
    </AnimatePresence>
  );
}

const STEPS = [
  {
    title: "Welcome to Sentinel",
    body: "An early-warning console for eight Tamil Nadu districts. It fuses clinic visits, pharmacy sales, school absenteeism, mobility and lab data, all aggregated by district, to spot outbreaks early without flagging false alarms. Every number here is simulated: city names are real, the data is not.",
  },
  {
    title: "Evidence tiers, decided by code",
    body: "Each district gets a tier from a deterministic evidence gate, never from the LLM. Higher tiers need more independent corroboration.",
    tiers: true,
  },
  {
    title: "Every claim is traceable",
    body: "Teal chips like EV-ERD-CLI-respiratory-0706 are evidence IDs. Click any chip to see the stored record. Claims without valid evidence are dropped by the Verifier.",
  },
  {
    title: "Humans decide",
    body: "Agents only propose actions. Nothing runs until an officer approves it in the Action Queue, and the red KILL SWITCH halts everything. Try ▶ Replay on the Command Center to watch the outbreak emerge.",
  },
];

export function Onboarding({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [i, setI] = useState(0);
  const s = STEPS[i];
  const close = () => {
    setI(0);
    onClose();
  };
  return (
    <AnimatePresence>
      {open && (
        <motion.div className="fixed inset-0 z-50 grid place-items-center bg-ink/25 p-4 backdrop-blur-sm" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
          <motion.div className="glass w-full max-w-[520px] p-6" style={{ background: "rgba(255,252,250,0.97)" }} initial={{ y: 16 }} animate={{ y: 0 }}>
            <div className="flex items-center justify-between">
              <div className="num text-[11px] text-accent-ink">
                {i + 1} / {STEPS.length}
              </div>
              <button onClick={close} className="text-xs text-ink-3 hover:text-ink">
                Skip
              </button>
            </div>
            <AnimatePresence mode="wait">
              <motion.div key={i} initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -12 }} transition={{ duration: 0.2 }}>
                <h3 className="mt-3 text-xl font-semibold text-ink">{s.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-ink-2">{s.body}</p>
                {s.tiers && (
                  <div className="mt-4 grid grid-cols-4 gap-2">
                    {TIERS.map((t) => (
                      <div key={t} className="rounded-lg border p-2" style={{ borderColor: `${tierTok[t].color}55`, background: `${tierTok[t].color}12` }}>
                        <div className="num text-sm font-bold" style={{ color: tierTok[t].ink }}>
                          {t}
                        </div>
                        <div className="mt-0.5 text-[10.5px] leading-tight text-ink-2">{tierTok[t].label}</div>
                      </div>
                    ))}
                  </div>
                )}
              </motion.div>
            </AnimatePresence>
            <div className="mt-6 flex items-center justify-between">
              <div className="flex gap-1.5">
                {STEPS.map((_, k) => (
                  <span key={k} className="h-1.5 rounded-full transition-all" style={{ width: k === i ? 18 : 6, background: k === i ? color.accent : "rgba(23,54,58,0.18)" }} />
                ))}
              </div>
              <button
                onClick={() => (i < STEPS.length - 1 ? setI(i + 1) : close())}
                className="inline-flex items-center gap-1.5 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-ink hover:brightness-110"
              >
                {i < STEPS.length - 1 ? "Next" : "Start"} <ArrowRight size={14} />
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
