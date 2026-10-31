import { motion, useReducedMotion } from "framer-motion";
import { AlertTriangle, Inbox, RotateCw } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { useEvidence } from "../lib/evidence";
import { motion as m, tier as tierTok, type Tier } from "../theme";

export function Panel({
  title,
  subtitle,
  right,
  children,
  className = "",
  bodyClass = "p-4",
  delay = 0,
}: {
  title?: ReactNode;
  subtitle?: ReactNode;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClass?: string;
  delay?: number;
}) {
  return (
    <motion.section
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, ease: m.ease, delay }}
      className={`glass flex min-w-0 flex-col ${className}`}
    >
      {(title || right) && (
        <header className="flex items-start justify-between gap-3 border-b border-line/30 px-4 py-3">
          <div className="min-w-0">
            {title && <h2 className="truncate text-[13px] font-semibold tracking-wide text-ink">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-[11.5px] text-ink-3">{subtitle}</p>}
          </div>
          {right && <div className="flex shrink-0 items-center gap-2">{right}</div>}
        </header>
      )}
      <div className={`min-h-0 flex-1 ${bodyClass}`}>{children}</div>
    </motion.section>
  );
}

export function TierChip({ tier, size = "md", label = false }: { tier: Tier; size?: "sm" | "md" | "lg"; label?: boolean }) {
  const t = tierTok[tier];
  const Icon = t.icon;
  const sz = size === "lg" ? "px-3.5 py-1.5 text-base" : size === "sm" ? "px-1.5 py-0.5 text-[10.5px]" : "px-2 py-0.5 text-xs";
  return (
    <span
      className={`num inline-flex items-center gap-1.5 rounded-md border font-semibold ${sz} ${t.glow ? "pulse-glow" : ""}`}
      style={{
        color: t.ink,
        borderColor: `${t.color}aa`,
        background: `${t.color}2e`,
        ["--glow" as string]: `${t.color}88`,
      }}
      title={`${tier}: ${t.label}`}
    >
      <Icon size={size === "lg" ? 15 : size === "sm" ? 10 : 12} strokeWidth={2.4} aria-hidden />
      {tier}
      {label && <span className="font-sans font-medium opacity-90">· {t.label}</span>}
    </span>
  );
}

/** Evidence-ID chip: click to open the evidence drawer. */
export function IdChip({ id, dim = false }: { id: string; dim?: boolean }) {
  const { open, highlight, setHighlight } = useEvidence();
  const active = highlight === id;
  return (
    <button
      type="button"
      onClick={() => open(id)}
      onMouseEnter={() => setHighlight(id)}
      onMouseLeave={() => setHighlight(null)}
      className={`num inline-flex max-w-full items-center truncate rounded-md border px-1.5 py-[1px] text-[10.5px] transition-colors ${
        active
          ? "border-accent/70 bg-accent/15 text-accent-ink"
          : dim
            ? "border-line/30 bg-white/50 text-ink-3 hover:text-ink-2"
            : "border-accent/25 bg-accent/[0.06] text-accent-ink/90 hover:border-accent/60"
      }`}
      title={`Evidence ${id}: click to inspect`}
    >
      {id}
    </button>
  );
}

export function Badge({ children, color, className = "" }: { children: ReactNode; color: string; className?: string }) {
  return (
    <span
      className={`num inline-flex items-center gap-1 rounded px-1.5 py-[1px] text-[10px] font-semibold tracking-wider ${className}`}
      style={{ color, background: `${color}1f`, border: `1px solid ${color}55` }}
    >
      {children}
    </span>
  );
}

export function CountUp({ value, digits = 0, suffix = "", prefix = "", duration = 0.9 }: { value: number; digits?: number; suffix?: string; prefix?: string; duration?: number }) {
  const reduce = useReducedMotion();
  const [v, setV] = useState(reduce ? value : 0);
  useEffect(() => {
    if (reduce) {
      setV(value);
      return;
    }
    let raf = 0;
    const t0 = performance.now();
    const tick = (now: number) => {
      const p = Math.min(1, (now - t0) / (duration * 1000));
      setV(value * (1 - Math.pow(1 - p, 3))); // ease-out cubic
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value, duration, reduce]);
  return (
    <span className="num">
      {prefix}
      {v.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits })}
      {suffix}
    </span>
  );
}

export function Skeleton({ className = "h-4 w-full" }: { className?: string }) {
  return <div className={`shimmer ${className}`} />;
}

export function LoadingBlock({ label = "Computing", rows = 4 }: { label?: string; rows?: number }) {
  return (
    <div className="flex flex-col gap-2.5 p-1" role="status" aria-live="polite">
      <div className="flex items-center gap-2 text-xs text-ink-3">
        <span className="blink h-1.5 w-1.5 rounded-full bg-accent" />
        {label}…
      </div>
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className={`h-3.5 ${i % 3 === 2 ? "w-2/3" : "w-full"}`} />
      ))}
    </div>
  );
}

export function EmptyState({ title, body, icon }: { title: string; body?: string; icon?: ReactNode }) {
  return (
    <div className="flex h-full min-h-[120px] flex-col items-center justify-center gap-2 px-6 py-8 text-center">
      <div className="grid h-10 w-10 place-items-center rounded-full border border-line/30 bg-white/50 text-ink-3">
        {icon ?? <Inbox size={18} />}
      </div>
      <div className="text-sm font-medium text-ink-2">{title}</div>
      {body && <div className="max-w-sm text-xs leading-relaxed text-ink-3">{body}</div>}
    </div>
  );
}

export function ErrorState({ error, retry }: { error: unknown; retry?: () => void }) {
  const msg = error instanceof Error ? error.message : "Something went wrong";
  return (
    <div className="flex h-full min-h-[120px] flex-col items-center justify-center gap-2 px-6 py-8 text-center">
      <div className="grid h-10 w-10 place-items-center rounded-full border border-e3/30 bg-e3/10 text-e3">
        <AlertTriangle size={18} />
      </div>
      <div className="text-sm font-medium text-ink-2">Couldn't load this panel</div>
      <div className="num max-w-md text-[11px] text-ink-3">{msg}</div>
      {retry && (
        <button onClick={retry} className="mt-1 inline-flex items-center gap-1.5 rounded-lg border border-line/30 px-3 py-1.5 text-xs text-ink-2 hover:border-accent/50 hover:text-accent-ink">
          <RotateCw size={12} /> Retry
        </button>
      )}
    </div>
  );
}

/** Renders loading / error / content for a query result. */
export function Q<T>({ q, children, label, rows }: { q: { data?: T; isLoading: boolean; error: unknown; refetch: () => unknown }; children: (d: T) => ReactNode; label?: string; rows?: number }) {
  if (q.error && !q.data) return <ErrorState error={q.error} retry={() => q.refetch()} />;
  if (q.isLoading || q.data === undefined) return <LoadingBlock label={label} rows={rows} />;
  return <>{children(q.data)}</>;
}

export function Stat({ label, children, hint, accent }: { label: string; children: ReactNode; hint?: ReactNode; accent?: string }) {
  return (
    <div className="flex flex-col gap-1">
      <div className="label-caps">{label}</div>
      <div className="text-2xl font-semibold leading-none" style={{ color: accent }}>
        {children}
      </div>
      {hint && <div className="text-[11px] text-ink-3">{hint}</div>}
    </div>
  );
}

export function Toggle({ on, onChange, label }: { on: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      onClick={() => onChange(!on)}
      className="inline-flex items-center gap-2 text-xs text-ink-2"
    >
      <span className={`relative h-5 w-9 rounded-full border transition-colors ${on ? "border-accent/60 bg-accent/25" : "border-line/50 bg-ink/5"}`}>
        <span className={`absolute top-0.5 h-3.5 w-3.5 rounded-full transition-all ${on ? "left-[18px] bg-accent" : "left-0.5 bg-ink-3"}`} />
      </span>
      {label}
    </button>
  );
}

export function Segmented<T extends string>({ value, options, onChange }: { value: T; options: { value: T; label: ReactNode }[]; onChange: (v: T) => void }) {
  return (
    <div className="inline-flex rounded-lg border border-line/30 bg-white/50 p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          onClick={() => onChange(o.value)}
          className={`rounded-md px-2.5 py-1 text-xs transition-colors ${value === o.value ? "bg-accent/15 text-accent-ink" : "text-ink-3 hover:text-ink-2"}`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
