import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import {
  Activity,
  BedDouble,
  Beaker,
  CheckSquare,
  CircleHelp,
  FlaskConical,
  Gauge,
  Hexagon,
  OctagonX,
  PanelLeftClose,
  PanelLeftOpen,
  Radar,
  ScanSearch,
  ShieldCheck,
  WifiOff,
  X,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { post, useActions, useAnalysis, useSystem } from "../lib/api";
import { shortDate } from "../lib/format";
import { useApp, type Page } from "../lib/state";

interface NavItem {
  page: Page;
  label: string;
  icon: LucideIcon;
  hint: string;
}

const NAV_GROUPS: { title: string; items: NavItem[] }[] = [
  {
    title: "Monitor",
    items: [
      { page: "command", label: "Command Center", icon: Radar, hint: "Map, active signals, replay" },
      { page: "signals", label: "Signal Explorer", icon: Activity, hint: "Per-source baselines" },
    ],
  },
  {
    title: "Analyze",
    items: [
      { page: "investigation", label: "Investigation", icon: ScanSearch, hint: "Agent case file" },
      { page: "capacity", label: "Capacity Forecast", icon: BedDouble, hint: "Beds & ICU bands" },
    ],
  },
  {
    title: "Govern",
    items: [
      { page: "actions", label: "Action Queue", icon: CheckSquare, hint: "Human approval + audit" },
      { page: "evaluation", label: "Evaluation", icon: Gauge, hint: "vs threshold baseline" },
      { page: "lab", label: "Scenario Lab", icon: Beaker, hint: "Inject & compare" },
    ],
  },
];

const COLLAPSE_KEY = "sentinel.sidebar.collapsed";

export function Sidebar() {
  const { page, go } = useApp();
  const actions = useActions();
  const reduce = useReducedMotion();
  const pending = actions.data?.filter((a) => a.status === "pending").length ?? 0;
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem(COLLAPSE_KEY) === "1");
  const toggle = () => {
    localStorage.setItem(COLLAPSE_KEY, collapsed ? "0" : "1");
    setCollapsed(!collapsed);
  };
  const pill = reduce ? { duration: 0 } : { type: "spring" as const, stiffness: 520, damping: 40 };

  return (
    <motion.nav
      initial={false}
      animate={{ width: collapsed ? 72 : 236 }}
      transition={reduce ? { duration: 0 } : { duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
      className="sticky top-3 z-20 flex h-[calc(100vh-24px)] shrink-0 flex-col overflow-hidden rounded-2xl bg-sidebar p-2.5 text-cream shadow-[0_20px_40px_-24px_rgba(15,63,67,0.7)]"
      aria-label="Primary"
    >
      <div className={`mb-2 flex items-center gap-2.5 px-1.5 pt-1.5 ${collapsed ? "justify-center" : ""}`}>
        <div className="relative grid h-9 w-9 shrink-0 place-items-center">
          <Hexagon className="absolute text-accent" size={34} strokeWidth={1.6} />
          <span className="h-2 w-2 rounded-full bg-accent shadow-[0_0_12px_#5FBDBF]" />
        </div>
        {!collapsed && (
          <div className="min-w-0">
            <div className="text-[15px] font-semibold tracking-[0.18em] text-cream">SENTINEL</div>
            <div className="truncate text-[10px] tracking-wider text-cream/65">Tamil Nadu early warning</div>
          </div>
        )}
      </div>

      <button
        onClick={toggle}
        className={`mb-2 flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-[11px] text-cream/70 outline-none transition-colors duration-150 hover:bg-white/10 hover:text-cream focus-visible:ring-2 focus-visible:ring-accent ${collapsed ? "justify-center" : ""}`}
        aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        aria-expanded={!collapsed}
        title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
      >
        {collapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
        {!collapsed && "Collapse"}
      </button>

      <div className="flex flex-1 flex-col gap-3 overflow-y-auto overflow-x-hidden">
        {NAV_GROUPS.map((g) => (
          <div key={g.title} role="group" aria-label={g.title}>
            {collapsed ? (
              <div className="mx-auto mb-1.5 h-px w-6 bg-cream/15" />
            ) : (
              <div className="mb-1 px-2.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-cream/55">{g.title}</div>
            )}
            <div className="flex flex-col gap-0.5">
              {g.items.map(({ page: p, label, icon: Icon, hint }) => {
                const active = p === page;
                return (
                  <motion.button
                    key={p}
                    onClick={() => go(p)}
                    whileTap={reduce ? undefined : { scale: 0.97 }}
                    transition={{ duration: 0.15 }}
                    className={`group relative flex items-center gap-3 rounded-xl px-2.5 py-2.5 text-left outline-none transition-colors duration-150 focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-sidebar ${
                      collapsed ? "justify-center" : ""
                    } ${active ? "text-sidebar" : "text-cream/85 hover:bg-white/[0.08] hover:text-cream"}`}
                    title={collapsed ? `${label}: ${hint}` : undefined}
                    aria-current={active ? "page" : undefined}
                    aria-label={label}
                  >
                    {active && <motion.span layoutId="nav-pill" transition={pill} className="absolute inset-0 rounded-xl bg-cream shadow-[0_6px_16px_-8px_rgba(0,0,0,0.5)]" />}
                    <Icon size={18} className="relative shrink-0" />
                    {!collapsed && (
                      <span className="relative min-w-0 flex-1">
                        <span className="block truncate text-[13px] font-medium">{label}</span>
                        <span className={`block truncate text-[10.5px] ${active ? "text-sidebar/70" : "text-cream/55"}`}>{hint}</span>
                      </span>
                    )}
                    {p === "actions" && pending > 0 && (
                      <span className={`num grid min-w-5 place-items-center rounded-full bg-[#F2A65A] px-1.5 text-[10px] font-bold text-sidebar ${collapsed ? "absolute right-1 top-1" : "relative"}`}>
                        {!reduce && <span className="absolute inset-0 animate-ping rounded-full bg-[#F2A65A] opacity-50" />}
                        <span className="relative">{pending}</span>
                      </span>
                    )}
                  </motion.button>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      {!collapsed ? (
        <div className="mt-2 rounded-xl border border-cream/15 bg-white/[0.06] p-3 text-[10.5px] leading-relaxed text-cream/75">
          <FlaskConical size={14} className="mb-1 text-accent" />
          <b className="text-cream">Synthetic data · simulation.</b> Real city names, simulated numbers. Aggregate, district-level only; the LLM explains, a deterministic gate grades.
        </div>
      ) : (
        <div className="mx-auto mt-2 grid h-8 w-8 place-items-center rounded-lg bg-white/[0.06] text-accent" title="Synthetic data · simulation">
          <FlaskConical size={14} />
        </div>
      )}
    </motion.nav>
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
  const { scenarioLabel } = useApp();
  const [killOpen, setKillOpen] = useState(false);
  const degraded = sys.data?.llm_mode !== "online";
  const killed = sys.data?.kill_switch ?? false;
  const offline = !!sys.error;

  return (
    <header className="glass sticky top-3 z-20 flex items-center gap-4 px-4 py-2.5">
      <div className="min-w-0 flex-1">
        <div className="label-caps">Sentinel · Tamil Nadu public-health watch</div>
        <h1 className="truncate text-lg font-semibold text-ink">{title}</h1>
      </div>

      <span
        className="num inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border border-[#F2A65A] bg-[#F2A65A]/20 px-2.5 py-1 text-[10.5px] font-bold tracking-[0.12em] text-[#7A4308]"
        title="All surveillance numbers are simulated. City names are real; populations are simulated catchments."
      >
        <FlaskConical size={12} /> SYNTHETIC DATA · SIMULATION
      </span>
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
          title={`Scenario: ${scenarioLabel.join(" + ")} · aggregates through ${analysis.data?.as_of_date ?? "…"}`}
        />
        {killed && <StatusPill tone="critical" icon={<OctagonX size={12} />} label="Actions halted" />}
      </div>

      <Clock />
      <button onClick={onHelp} className="grid h-9 w-9 place-items-center rounded-lg border border-line/30 text-ink-3 hover:border-accent/50 hover:text-accent-ink" title="How to read this screen" aria-label="Help">
        <CircleHelp size={17} />
      </button>
      <button
        onClick={() => setKillOpen(true)}
        className={`inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-xs font-bold tracking-[0.14em] text-white transition-[filter,transform] duration-150 hover:brightness-110 active:scale-[0.98] ${
          killed ? "border-[#9F2731] bg-[#9F2731] pulse-glow" : "border-kill bg-kill"
        }`}
        style={{ ["--glow" as string]: "rgba(214,69,80,0.6)" }}
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
    neutral: "border-line/30 text-ink-2",
  }[tone];
  return (
    <span title={title} className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border bg-white/50 px-2.5 py-1 text-[11px] font-medium ${cls}`}>
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
        className="mt-1.5 w-full rounded-lg border border-line/30 bg-white/85 px-3 py-2 text-sm text-ink outline-none focus:border-accent/60"
      />
      {m.error && <div className="mt-2 text-xs text-e3">{(m.error as Error).message}</div>}
      <div className="mt-5 flex justify-end gap-2">
        <button onClick={onClose} className="rounded-lg px-3 py-2 text-sm text-ink-3 hover:text-ink">
          Cancel
        </button>
        <button
          disabled={!reason.trim() || m.isPending}
          onClick={() => m.mutate()}
          className={`rounded-lg px-4 py-2 text-sm font-semibold disabled:opacity-40 ${engaged ? "bg-good/90 text-ink" : "bg-e3 text-white"}`}
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
        <motion.div className="fixed inset-0 z-50 grid place-items-center bg-ink/25 p-4 backdrop-blur-sm" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose}>
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-label={title}
            className="glass w-full p-5"
            style={{ maxWidth: width, background: "rgba(255,252,250,0.97)" }}
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
    <footer className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-line/30 px-1 pb-3 pt-3 text-[11px] text-ink-3">
      <span className="inline-flex items-center gap-1.5">
        <ShieldCheck size={13} className="text-good" />
        Population-level signals only. No individual diagnosis. Human approval required.
      </span>
      <span className="num">Synthetic data · simulated catchments · seeded</span>
    </footer>
  );
}
