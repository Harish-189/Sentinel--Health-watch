import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import {
  Activity,
  BedDouble,
  Beaker,
  CheckSquare,
  CircleHelp,
  Gauge,
  Hexagon,
  OctagonX,
  Radar,
  ScanSearch,
  ShieldCheck,
  WifiOff,
  X,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { post, useActions, useAnalysis, useSystem } from "../lib/api";
import { shortDate } from "../lib/format";
import { useApp, type Page } from "../lib/state";

const NAV: { page: Page; label: string; icon: typeof Activity; hint: string }[] = [
  { page: "command", label: "Command Center", icon: Radar, hint: "Map, active signals, replay" },
  { page: "signals", label: "Signal Explorer", icon: Activity, hint: "Per-source baselines" },
  { page: "investigation", label: "Investigation", icon: ScanSearch, hint: "Agent case file" },
  { page: "capacity", label: "Capacity Forecast", icon: BedDouble, hint: "Beds & ICU bands" },
  { page: "actions", label: "Action Queue", icon: CheckSquare, hint: "Human approval + audit" },
  { page: "evaluation", label: "Evaluation", icon: Gauge, hint: "vs threshold baseline" },
  { page: "lab", label: "Scenario Lab", icon: Beaker, hint: "Inject & compare" },
];

export function Sidebar() {
  const { page, go } = useApp();
  const actions = useActions();
  const pending = actions.data?.filter((a) => a.status === "pending").length ?? 0;
  return (
    <nav className="glass sticky top-3 z-20 flex h-[calc(100vh-24px)] w-[64px] shrink-0 flex-col items-stretch gap-1 p-2 xl:w-[220px]" aria-label="Primary">
      <div className="mb-3 flex items-center gap-2.5 px-1.5 pt-1.5">
        <div className="relative grid h-9 w-9 shrink-0 place-items-center">
          <Hexagon className="absolute text-accent" size={34} strokeWidth={1.5} />
          <span className="h-2 w-2 rounded-full bg-accent shadow-[0_0_12px_#22D3EE]" />
        </div>
        <div className="hidden xl:block">
          <div className="text-[15px] font-semibold tracking-[0.18em] text-ink">SENTINEL</div>
          <div className="text-[10px] tracking-wider text-ink-3">Early-warning · v0.3</div>
        </div>
      </div>
      {NAV.map(({ page: p, label, icon: Icon, hint }) => {
        const active = p === page;
        return (
          <button
            key={p}
            onClick={() => go(p)}
            className={`group relative flex items-center gap-3 rounded-xl px-2.5 py-2.5 text-left transition-colors ${
              active ? "bg-accent/10 text-accent" : "text-ink-2 hover:bg-white/[0.04] hover:text-ink"
            }`}
            title={label}
            aria-current={active ? "page" : undefined}
          >
            {active && <motion.span layoutId="nav-active" className="absolute inset-y-2 left-0 w-[3px] rounded-full bg-accent" />}
            <Icon size={18} className="shrink-0" />
            <span className="hidden min-w-0 flex-1 xl:block">
              <span className="block truncate text-[13px] font-medium">{label}</span>
              <span className="block truncate text-[10.5px] text-ink-3">{hint}</span>
            </span>
            {p === "actions" && pending > 0 && (
              <span className="num absolute right-1.5 top-1.5 rounded-full bg-e2 px-1.5 text-[10px] font-bold text-black xl:static">{pending}</span>
            )}
          </button>
        );
      })}
      <div className="mt-auto hidden rounded-xl border border-white/[0.06] bg-white/[0.02] p-3 text-[10.5px] leading-relaxed text-ink-3 xl:block">
        <ShieldCheck size={14} className="mb-1 text-good" />
        Aggregate, district-level data only. The LLM explains; a deterministic gate grades.
      </div>
    </nav>
  );
}

function Clock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  return (
    <div className="num text-right leading-tight">
      <div className="text-[15px] font-semibold text-ink">{now.toLocaleTimeString("en-GB")}</div>
      <div className="text-[10px] text-ink-3">{now.toLocaleDateString("en-GB", { weekday: "short", day: "2-digit", month: "short" })} · local</div>
    </div>
  );
}

export function TopBar({ title, onHelp }: { title: string; onHelp: () => void }) {
  const sys = useSystem();
  const analysis = useAnalysis();
  const { scenario } = useApp();
  const [killOpen, setKillOpen] = useState(false);
  const degraded = sys.data?.llm_mode !== "online";
  const killed = sys.data?.kill_switch ?? false;
  const offline = !!sys.error;

  return (
    <header className="glass sticky top-3 z-20 flex items-center gap-4 px-4 py-2.5">
      <div className="min-w-0 flex-1">
        <div className="label-caps">Sentinel · Regional public-health watch</div>
        <h1 className="truncate text-lg font-semibold text-ink">{title}</h1>
      </div>

      <div className="hidden items-center gap-2 lg:flex">
        <StatusPill
          tone={offline ? "critical" : degraded ? "warning" : "good"}
          icon={offline ? <WifiOff size={12} /> : <span className={`h-1.5 w-1.5 rounded-full ${degraded ? "bg-e2" : "bg-good"} blink`} />}
          label={offline ? "API offline" : degraded ? "Degraded · offline LLM" : "Normal · LLM online"}
          title={sys.data?.degraded_reason ?? sys.data?.model ?? ""}
        />
        <StatusPill
          tone="neutral"
          icon={<span className="h-1.5 w-1.5 rounded-full bg-accent" />}
          label={analysis.data ? `Data as of ${shortDate(analysis.data.as_of_date)}` : "Data loading…"}
          title={`Scenario: ${scenario.join(" + ")} · aggregates through ${analysis.data?.as_of_date ?? "…"}`}
        />
        {killed && <StatusPill tone="critical" icon={<OctagonX size={12} />} label="Actions halted" />}
      </div>

      <Clock />
      <button onClick={onHelp} className="grid h-9 w-9 place-items-center rounded-lg border border-white/10 text-ink-3 hover:border-accent/50 hover:text-accent" title="How to read this screen" aria-label="Help">
        <CircleHelp size={17} />
      </button>
      <button
        onClick={() => setKillOpen(true)}
        className={`inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-xs font-bold tracking-[0.14em] transition-colors ${
          killed ? "border-e3 bg-e3 text-white pulse-glow" : "border-e3/60 bg-e3/10 text-e3 hover:bg-e3/20"
        }`}
        style={{ ["--glow" as string]: "rgba(239,68,68,0.6)" }}
      >
        <OctagonX size={15} />
        {killed ? "KILL SWITCH ON" : "KILL SWITCH"}
      </button>
      <KillSwitchDialog open={killOpen} engaged={killed} onClose={() => setKillOpen(false)} />
    </header>
  );
}

function StatusPill({ tone, icon, label, title }: { tone: "good" | "warning" | "critical" | "neutral"; icon: ReactNode; label: string; title?: string }) {
  const cls = {
    good: "border-good/30 text-good",
    warning: "border-e2/35 text-e2",
    critical: "border-e3/40 text-e3",
    neutral: "border-white/10 text-ink-2",
  }[tone];
  return (
    <span title={title} className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border bg-white/[0.02] px-2.5 py-1 text-[11px] font-medium ${cls}`}>
      {icon}
      {label}
    </span>
  );
}

function KillSwitchDialog({ open, engaged, onClose }: { open: boolean; engaged: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const [reason, setReason] = useState("");
  const m = useMutation({
    mutationFn: () => post("/api/killswitch", { engaged: !engaged, actor: "duty_officer", reason }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["system"] });
      qc.invalidateQueries({ queryKey: ["actions"] });
      qc.invalidateQueries({ queryKey: ["audit"] });
      setReason("");
      onClose();
    },
  });
  return (
    <Modal open={open} onClose={onClose} title={engaged ? "Release kill switch" : "Engage kill switch"}>
      <p className="text-sm leading-relaxed text-ink-2">
        {engaged
          ? "Releasing re-enables approval of queued actions. Nothing executes automatically: every action still needs a human approval."
          : "Engaging immediately halts all action execution and blocks new action proposals. Analysis keeps running. This is written to the audit log."}
      </p>
      <label className="label-caps mt-4 block">Reason (required, audited)</label>
      <input
        autoFocus
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        placeholder={engaged ? "e.g. Review complete" : "e.g. Suspected data feed compromise"}
        className="mt-1.5 w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-ink outline-none focus:border-accent/60"
      />
      {m.error && <div className="mt-2 text-xs text-e3">{(m.error as Error).message}</div>}
      <div className="mt-5 flex justify-end gap-2">
        <button onClick={onClose} className="rounded-lg px-3 py-2 text-sm text-ink-3 hover:text-ink">
          Cancel
        </button>
        <button
          disabled={!reason.trim() || m.isPending}
          onClick={() => m.mutate()}
          className={`rounded-lg px-4 py-2 text-sm font-semibold disabled:opacity-40 ${engaged ? "bg-good/90 text-black" : "bg-e3 text-white"}`}
        >
          {engaged ? "Release" : "Engage kill switch"}
        </button>
      </div>
    </Modal>
  );
}

export function Modal({ open, onClose, title, children, width = 460 }: { open: boolean; onClose: () => void; title: string; children: ReactNode; width?: number }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  return (
    <AnimatePresence>
      {open && (
        <motion.div className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4 backdrop-blur-sm" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose}>
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-label={title}
            className="glass w-full p-5"
            style={{ maxWidth: width, background: "rgba(12,19,34,0.96)" }}
            initial={{ y: 14, scale: 0.98 }}
            animate={{ y: 0, scale: 1 }}
            exit={{ y: 8, opacity: 0 }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-base font-semibold text-ink">{title}</h3>
              <button onClick={onClose} className="text-ink-3 hover:text-ink" aria-label="Close">
                <X size={16} />
              </button>
            </div>
            {children}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export function Footer() {
  return (
    <footer className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-white/[0.06] px-1 pb-3 pt-3 text-[11px] text-ink-3">
      <span className="inline-flex items-center gap-1.5">
        <ShieldCheck size={13} className="text-good" />
        Population-level signals only. No individual diagnosis. Human approval required.
      </span>
      <span className="num">Synthetic data · fictional districts · seeded</span>
    </footer>
  );
}
