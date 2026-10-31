import { motion, useReducedMotion } from "framer-motion";
import type { Tier } from "../theme";
import { tier as tierTok } from "../theme";
import { TierChip } from "./ui";

export interface Callout {
  code: string;
  name: string;
  tier: Tier;
  stat: string; // e.g. "Respiratory visits +46% vs expected"
  observed: (number | null)[];
  expected: number[];
  evidenceId?: string;
}

export interface Anchor {
  x: number; // cell centre, container px
  y: number;
  side: "left" | "right";
}

const CARD_W = 244;
const CARD_H = 92;
const GAP = 10;

/** Lay cards out in the map's side gutters, sorted by cell height, pushed down to avoid overlaps. */
export function layoutCallouts(anchors: Record<string, Anchor>, codes: string[], bounds: { left: number; right: number; height: number }) {
  const out: Record<string, { x: number; y: number; ax: number; ay: number }> = {};
  for (const side of ["left", "right"] as const) {
    const list = codes.filter((c) => anchors[c]?.side === side).sort((a, b) => anchors[a].y - anchors[b].y);
    let floor = 8;
    for (const c of list) {
      const a = anchors[c];
      const y = Math.min(Math.max(floor, a.y - CARD_H / 2), bounds.height - CARD_H - 8);
      floor = y + CARD_H + GAP;
      const x = side === "left" ? Math.max(8, bounds.left - CARD_W - 28) : Math.min(bounds.right + 28, 99999);
      out[c] = { x, y, ax: a.x, ay: a.y };
    }
  }
  return out;
}

function Sparkline({ observed, expected, color }: { observed: (number | null)[]; expected: number[]; color: string }) {
  const W = 216;
  const H = 30;
  const vals = [...observed.filter((v): v is number => v !== null), ...expected];
  const lo = Math.min(...vals);
  const hi = Math.max(...vals);
  const sx = (i: number) => (i / Math.max(1, observed.length - 1)) * W;
  const sy = (v: number) => H - 2 - ((v - lo) / (hi - lo || 1)) * (H - 4);
  const line = (arr: (number | null)[]) =>
    arr.map((v, i) => (v === null ? "" : `${i === 0 || arr[i - 1] === null ? "M" : "L"}${sx(i).toFixed(1)},${sy(v).toFixed(1)}`)).join("");
  const obs = line(observed);
  const lastIdx = observed.length - 1;
  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} aria-hidden className="block">
      <path d={line(expected)} fill="none" stroke="rgba(23,54,58,0.35)" strokeWidth={1.2} strokeDasharray="3 3" />
      <path d={`${obs}L${sx(lastIdx)},${H}L0,${H}Z`} fill={color} opacity={0.12} />
      <path d={obs} fill="none" stroke={color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
      {observed[lastIdx] !== null && <circle cx={sx(lastIdx)} cy={sy(observed[lastIdx] as number)} r={3} fill={color} stroke="#fff" strokeWidth={1.5} />}
    </svg>
  );
}

export function CalloutLayer({ callouts, placed, onOpen }: { callouts: Callout[]; placed: Record<string, { x: number; y: number; ax: number; ay: number }>; onOpen: (code: string) => void }) {
  const reduce = useReducedMotion();
  return (
    <>
      <svg className="pointer-events-none absolute inset-0 h-full w-full" aria-hidden>
        {callouts.map((c) => {
          const p = placed[c.code];
          if (!p) return null;
          const left = p.x < p.ax;
          const x1 = left ? p.x + CARD_W : p.x;
          const y1 = p.y + CARD_H / 2;
          const col = tierTok[c.tier].color;
          return (
            <g key={c.code}>
              <path d={`M${x1},${y1} C${(x1 + p.ax) / 2},${y1} ${(x1 + p.ax) / 2},${p.ay} ${p.ax},${p.ay}`} fill="none" stroke={col} strokeWidth={1.5} strokeDasharray="3 4" opacity={0.8} />
              <circle cx={x1} cy={y1} r={3} fill={col} />
            </g>
          );
        })}
      </svg>
      {callouts.map((c, i) => {
        const p = placed[c.code];
        if (!p) return null;
        return (
          <motion.button
            key={c.code}
            onClick={() => onOpen(c.code)}
            initial={reduce ? false : { opacity: 0, x: p.x < p.ax ? -14 : 14, scale: 0.96 }}
            animate={{ opacity: 1, x: 0, scale: 1 }}
            transition={{ delay: reduce ? 0 : 0.15 + i * 0.12, duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
            className="glass absolute z-10 flex flex-col gap-1 px-3 py-2.5 text-left outline-none transition-shadow duration-150 hover:shadow-[0_14px_30px_-16px_rgba(15,63,67,0.6)] focus-visible:ring-2 focus-visible:ring-accent-strong"
            style={{ width: CARD_W, height: CARD_H, left: p.x, top: p.y, background: "rgba(255,255,255,0.72)", transition: "left 250ms, top 250ms" }}
            aria-label={`${c.name}: ${c.stat}. Open investigation`}
          >
            <span className="flex items-center justify-between gap-2">
              <span className="truncate text-[13px] font-semibold text-ink">{c.name}</span>
              <TierChip tier={c.tier} size="sm" />
            </span>
            <span className="truncate text-[11px] text-ink-2" title={c.stat}>
              {c.stat}
            </span>
            <Sparkline observed={c.observed} expected={c.expected} color={tierTok[c.tier].color} />
          </motion.button>
        );
      })}
    </>
  );
}

export const CALLOUT_SIZE = { w: CARD_W, h: CARD_H };
