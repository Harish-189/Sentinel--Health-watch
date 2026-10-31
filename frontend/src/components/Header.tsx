import { AnimatePresence, motion } from "framer-motion";
import { ArrowUpRight, Bell, MapPin, Radio, Search } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useActions, useAnalysis, useDistricts } from "../lib/api";
import { useApp, type Page } from "../lib/state";
import { tier as tierTok } from "../theme";
import { TierChip } from "./ui";

// ------------------------------------------------------------------ per-page copy + primary CTA

export const PAGE_COPY: Record<Page, { title: string; subtitle: string; cta: string }> = {
  command: { title: "Command Center", subtitle: "Statewide evidence map, active signals and replay of how they emerged.", cta: "Run analysis" },
  signals: { title: "Signal Explorer", subtitle: "Every source against its seasonal baseline, with anomalies and lead-lag.", cta: "Investigate district" },
  investigation: { title: "Investigation", subtitle: "Agent case file: hypotheses, grounded evidence and the deterministic grade.", cta: "Re-run agents" },
  capacity: { title: "Capacity Forecast", subtitle: "14-day bed and ICU occupancy with P10–P90 bands and breach risk.", cta: "Review actions" },
  actions: { title: "Action Queue", subtitle: "Agent proposals awaiting a human decision, with the hash-chained audit log.", cta: "Investigate top signal" },
  evaluation: { title: "Evaluation", subtitle: "Sentinel against a single-threshold baseline across seeded simulations.", cta: "Open Scenario Lab" },
  lab: { title: "Scenario Lab", subtitle: "Inject a scenario and see exactly how the evidence changes.", cta: "Back to Command Center" },
};

/** Primary CTA per page: a deep-teal pill with an arrow. */
export function PrimaryCta() {
  const { page, go, rerun } = useApp();
  const analysis = useAnalysis();
  const top = analysis.data?.primary;
  const act: Record<Page, () => void> = {
    command: () => go("investigation", top),
    signals: () => go("investigation"),
    investigation: rerun,
    capacity: () => go("actions"),
    actions: () => go("investigation", top),
    evaluation: () => go("lab"),
    lab: () => go("command"),
  };
  return (
    <motion.button
      whileHover={{ y: -1 }}
      whileTap={{ scale: 0.97 }}
      transition={{ duration: 0.15 }}
      onClick={act[page]}
      className="inline-flex shrink-0 items-center gap-2 rounded-full bg-sidebar py-2.5 pl-5 pr-2.5 text-[13px] font-semibold text-cream shadow-[0_8px_20px_-10px_rgba(15,63,67,0.8)] outline-none transition-colors duration-150 hover:bg-[#0B3236] focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2"
    >
      {PAGE_COPY[page].cta}
      <span className="grid h-7 w-7 place-items-center rounded-full bg-accent text-sidebar">
        <ArrowUpRight size={15} strokeWidth={2.5} />
      </span>
    </motion.button>
  );
}

// ------------------------------------------------------------------ search pill

interface Hit {
  key: string;
  kind: "district" | "signal";
  label: string;
  sub: string;
  district: string;
  tier?: keyof typeof tierTok;
}

export function SearchPill() {
  const { go } = useApp();
  const districts = useDistricts();
  const analysis = useAnalysis();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const input = useRef<HTMLInputElement>(null);

  // "/" focuses search from anywhere (unless typing in a field).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (e.key === "/" && !["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName)) {
        e.preventDefault();
        input.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const hits = useMemo<Hit[]>(() => {
    const tierOf = (code: string) => analysis.data?.assessments.find((a) => a.district === code)?.gate.tier;
    const all: Hit[] = [
      ...(districts.data ?? []).map((d) => ({ key: d.code, kind: "district" as const, label: d.name, sub: d.code, district: d.code, tier: tierOf(d.code) })),
      ...(analysis.data?.assessments ?? [])
        .filter((a) => a.signal)
        .map((a) => ({
          key: a.signal!.signal_id,
          kind: "signal" as const,
          label: a.signal!.signal_id,
          sub: `${a.name} · ${a.signal!.syndrome} · ${a.signal!.independent_sources} sources`,
          district: a.district,
          tier: a.gate.tier,
        })),
    ];
    const s = q.trim().toLowerCase();
    return (s ? all.filter((h) => `${h.label} ${h.sub}`.toLowerCase().includes(s)) : all.filter((h) => h.kind === "signal")).slice(0, 7);
  }, [q, districts.data, analysis.data]);

  const pick = (h: Hit) => {
    go(h.kind === "district" ? "investigation" : "signals", h.district);
    setQ("");
    setOpen(false);
    input.current?.blur();
  };

  return (
    <div className="relative min-w-[200px] max-w-[340px] flex-1">
      <Search size={14} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-ink-3" />
      <input
        ref={input}
        value={q}
        onChange={(e) => {
          setQ(e.target.value);
          setActive(0);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 120)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") setActive((i) => Math.min(i + 1, hits.length - 1));
          else if (e.key === "ArrowUp") setActive((i) => Math.max(i - 1, 0));
          else if (e.key === "Enter" && hits[active]) pick(hits[active]);
          else if (e.key === "Escape") input.current?.blur();
          else return;
          e.preventDefault();
        }}
        placeholder="Search district or signal…"
        role="combobox"
        aria-expanded={open}
        aria-controls="search-results"
        aria-activedescendant={open && hits[active] ? `hit-${hits[active].key}` : undefined}
        className="w-full rounded-full border border-line/40 bg-white/80 py-2 pl-9 pr-9 text-[13px] text-ink outline-none transition-colors duration-150 placeholder:text-ink-3 focus:border-accent-strong focus:bg-white"
      />
      <kbd className="num pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 rounded border border-line/40 px-1.5 text-[10px] text-ink-3">/</kbd>
      <AnimatePresence>
        {open && hits.length > 0 && (
          <motion.ul
            id="search-results"
            role="listbox"
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.15 }}
            className="glass absolute left-0 right-0 top-[calc(100%+6px)] z-40 overflow-hidden p-1"
            style={{ background: "rgba(255,253,251,0.97)" }}
          >
            {!q && <li className="label-caps px-3 pb-1 pt-2">Active signals</li>}
            {hits.map((h, i) => (
              <li
                key={h.key}
                id={`hit-${h.key}`}
                role="option"
                aria-selected={i === active}
                onMouseDown={(e) => {
                  e.preventDefault();
                  pick(h);
                }}
                onMouseEnter={() => setActive(i)}
                className={`flex cursor-pointer items-center gap-2.5 rounded-lg px-3 py-2 text-[12.5px] ${i === active ? "bg-mint/60" : ""}`}
              >
                {h.kind === "district" ? <MapPin size={14} className="shrink-0 text-ink-3" /> : <Radio size={14} className="shrink-0 text-ink-3" />}
                <span className="min-w-0 flex-1">
                  <span className={`block truncate text-ink ${h.kind === "signal" ? "num text-[12px]" : "font-medium"}`}>{h.label}</span>
                  <span className="block truncate text-[11px] capitalize text-ink-3">{h.sub}</span>
                </span>
                {h.tier && <TierChip tier={h.tier} size="sm" />}
              </li>
            ))}
          </motion.ul>
        )}
      </AnimatePresence>
    </div>
  );
}

// ------------------------------------------------------------------ bell + avatar

export function NotificationBell() {
  const { go } = useApp();
  const actions = useActions();
  const [open, setOpen] = useState(false);
  const pending = (actions.data ?? []).filter((a) => a.status === "pending");
  return (
    <div className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        className="relative grid h-9 w-9 place-items-center rounded-full border border-line/40 bg-white/70 text-ink-2 outline-none transition-colors duration-150 hover:text-ink focus-visible:ring-2 focus-visible:ring-accent"
        aria-label={`Notifications: ${pending.length} pending approval${pending.length === 1 ? "" : "s"}`}
        aria-expanded={open}
      >
        <Bell size={16} />
        {pending.length > 0 && (
          <span className="absolute right-1.5 top-1.5 h-2.5 w-2.5 rounded-full border-2 border-white bg-[#E5535D]">
            <span className="absolute inset-0 animate-ping rounded-full bg-[#E5535D] opacity-60 motion-reduce:hidden" />
          </span>
        )}
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="glass absolute right-0 top-[calc(100%+8px)] z-40 w-80 p-3"
            style={{ background: "rgba(255,253,251,0.97)" }}
          >
            <div className="label-caps mb-2">Pending approvals · {pending.length}</div>
            {pending.length === 0 ? (
              <p className="py-3 text-center text-[12px] text-ink-3">Nothing waiting for a decision.</p>
            ) : (
              <ul className="flex flex-col gap-1">
                {pending.slice(0, 5).map((a) => (
                  <li key={a.ref} className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-[12px] hover:bg-mint/40">
                    <span className="num text-[10.5px] text-ink-3">{a.ref}</span>
                    <span className="min-w-0 flex-1 truncate text-ink">{a.title}</span>
                    <TierChip tier={a.signal_tier} size="sm" />
                  </li>
                ))}
              </ul>
            )}
            <button
              onMouseDown={(e) => {
                e.preventDefault();
                setOpen(false);
                go("actions");
              }}
              className="mt-2 w-full rounded-lg bg-sidebar py-2 text-[12px] font-semibold text-cream hover:bg-[#0B3236]"
            >
              Open Action Queue
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export function Avatar({ initials = "DO", name = "Duty officer" }: { initials?: string; name?: string }) {
  return (
    <span
      className="num grid h-9 w-9 shrink-0 select-none place-items-center rounded-full bg-gradient-to-br from-[#BADDD6] to-[#5FBDBF] text-[12px] font-bold text-sidebar ring-2 ring-white"
      title={`${name} (signed in)`}
      aria-label={`Signed in as ${name}`}
    >
      {initials}
    </span>
  );
}
