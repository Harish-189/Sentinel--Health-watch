import { AnimatePresence, motion } from "framer-motion";
import { useMemo, useState } from "react";
import { pct } from "../lib/format";
import type { District, DistrictFrame } from "../lib/types";
import { color, tier as tierTok, TIERS } from "../theme";

const SIZE = 62;
const SQ3 = Math.sqrt(3);

function center(q: number, r: number): [number, number] {
  return [SIZE * SQ3 * (q + r / 2), SIZE * 1.5 * r];
}

function hexPath(cx: number, cy: number, s: number): string {
  const pts = Array.from({ length: 6 }, (_, i) => {
    const a = (Math.PI / 180) * (60 * i - 30);
    return `${(cx + s * Math.cos(a)).toFixed(1)},${(cy + s * Math.sin(a)).toFixed(1)}`;
  });
  return `M${pts.join("L")}Z`;
}

export function HexMap({
  districts,
  frames,
  selected,
  onSelect,
  height = 420,
}: {
  districts: District[];
  frames: Record<string, DistrictFrame>;
  selected?: string;
  onSelect?: (code: string) => void;
  height?: number;
}) {
  const [hover, setHover] = useState<string | null>(null);
  const layout = useMemo(() => {
    const pts = districts.map((d) => ({ d, c: center(d.q, d.r) }));
    const xs = pts.map((p) => p.c[0]);
    const ys = pts.map((p) => p.c[1]);
    const pad = SIZE * 1.25;
    const vb = [Math.min(...xs) - pad, Math.min(...ys) - pad, Math.max(...xs) - Math.min(...xs) + 2 * pad, Math.max(...ys) - Math.min(...ys) + 2 * pad];
    return { pts, vb };
  }, [districts]);

  const pos = Object.fromEntries(layout.pts.map((p) => [p.d.code, p.c]));
  // Links between adjacent districts that both carry a corroborated (E2+) signal: visible spatial spread.
  const links = districts.flatMap((d) =>
    d.neighbors
      .filter((n) => n > d.code && TIERS.indexOf(frames[d.code]?.tier ?? "E0") >= 2 && TIERS.indexOf(frames[n]?.tier ?? "E0") >= 2)
      .map((n) => [d.code, n] as const),
  );
  const hovered = hover ? layout.pts.find((p) => p.d.code === hover) : undefined;
  const [vx, vy, vw, vh] = layout.vb;

  return (
    <div className="relative w-full overflow-hidden" style={{ height }}>
      <svg viewBox={layout.vb.join(" ")} className="h-full w-full" role="img" aria-label="District evidence map">
        <defs>
          <radialGradient id="hexglow">
            <stop offset="0%" stopColor="#22D3EE" stopOpacity="0.12" />
            <stop offset="100%" stopColor="#22D3EE" stopOpacity="0" />
          </radialGradient>
          <linearGradient id="scan" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="#22D3EE" stopOpacity="0" />
            <stop offset="85%" stopColor="#22D3EE" stopOpacity="0.10" />
            <stop offset="100%" stopColor="#22D3EE" stopOpacity="0.35" />
          </linearGradient>
          <clipPath id="mapclip">
            {layout.pts.map(({ d, c }) => (
              <path key={d.code} d={hexPath(c[0], c[1], SIZE - 3)} />
            ))}
          </clipPath>
        </defs>
        <ellipse cx={vx + vw / 2} cy={vy + vh / 2} rx={vw / 2} ry={vh / 2} fill="url(#hexglow)" />

        {links.map(([a, b]) => (
          <line key={`${a}-${b}`} x1={pos[a][0]} y1={pos[a][1]} x2={pos[b][0]} y2={pos[b][1]} stroke={color.critical} strokeOpacity={0.45} strokeWidth={2} strokeDasharray="4 6">
            <animate attributeName="stroke-dashoffset" from="20" to="0" dur="1.2s" repeatCount="indefinite" />
          </line>
        ))}

        {layout.pts.map(({ d, c }) => {
          const f = frames[d.code];
          const t = tierTok[f?.tier ?? "E0"];
          const level = TIERS.indexOf(f?.tier ?? "E0");
          const isSel = selected === d.code;
          return (
            <g
              key={d.code}
              onMouseEnter={() => setHover(d.code)}
              onMouseLeave={() => setHover(null)}
              onClick={() => onSelect?.(d.code)}
              onKeyDown={(e) => e.key === "Enter" && onSelect?.(d.code)}
              tabIndex={0}
              role="button"
              aria-label={`${d.name}: ${f?.tier ?? "E0"}`}
              className="cursor-pointer outline-none"
            >
              <motion.path
                d={hexPath(c[0], c[1], SIZE - 3)}
                initial={false}
                animate={{ fill: level === 0 ? "rgba(100,116,139,0.10)" : `${t.color}${level >= 2 ? "38" : "26"}`, stroke: isSel ? color.accent : level === 0 ? "rgba(255,255,255,0.12)" : t.color }}
                transition={{ duration: 0.5 }}
                strokeWidth={isSel ? 2.5 : 1.5}
                style={{ filter: hover === d.code ? "brightness(1.35)" : undefined }}
              />
              {level >= 2 && (
                <>
                  <path d={hexPath(c[0], c[1], SIZE * 0.62)} fill="none" stroke={t.color} strokeWidth={1.5} className="ring-out" style={{ pointerEvents: "none" }} />
                  <path d={hexPath(c[0], c[1], SIZE * 0.62)} fill="none" stroke={t.color} strokeWidth={1.2} className="ring-out" style={{ animationDelay: "1.2s", pointerEvents: "none" }} />
                </>
              )}
              <text x={c[0]} y={c[1] - 14} textAnchor="middle" fill={color.text} fontSize={13} fontWeight={600} style={{ pointerEvents: "none" }}>
                {d.name}
              </text>
              <text x={c[0]} y={c[1] + 6} textAnchor="middle" fill={level === 0 ? color.textMuted : t.color} fontSize={15} fontWeight={700} fontFamily="JetBrains Mono" style={{ pointerEvents: "none" }}>
                {f?.tier ?? "E0"}
              </text>
              <text x={c[0]} y={c[1] + 24} textAnchor="middle" fill={color.textMuted} fontSize={10.5} fontFamily="JetBrains Mono" style={{ pointerEvents: "none" }}>
                {d.code}
                {f && f.sources > 0 ? ` · ${f.sources} src` : ""}
              </text>
            </g>
          );
        })}

        <g clipPath="url(#mapclip)" style={{ pointerEvents: "none" }}>
          <rect x={vx} y={vy} width={vw} height={vh * 0.22} fill="url(#scan)" className="scanline" style={{ transformBox: "view-box" }} />
        </g>
      </svg>

      <AnimatePresence>
        {hovered && (
          <motion.div
            key={hovered.d.code}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="glass pointer-events-none absolute z-10 w-56 p-3 text-xs"
            style={{
              left: `${Math.min(70, Math.max(2, ((hovered.c[0] - vx) / vw) * 100 + 6))}%`,
              top: `${Math.min(62, Math.max(2, ((hovered.c[1] - vy) / vh) * 100 - 18))}%`,
            }}
          >
            <HoverCard d={hovered.d} f={frames[hovered.d.code]} />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function HoverCard({ d, f }: { d: District; f?: DistrictFrame }) {
  const t = tierTok[f?.tier ?? "E0"];
  return (
    <>
      <div className="flex items-center justify-between">
        <span className="font-semibold text-ink">{d.name}</span>
        <span className="num font-bold" style={{ color: t.color }}>
          {f?.tier ?? "E0"}
        </span>
      </div>
      <div className="mt-0.5 text-[11px]" style={{ color: t.color }}>
        {t.label}
      </div>
      <dl className="num mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-[11px]">
        <dt className="text-ink-3">Population</dt>
        <dd className="text-right text-ink-2">{(d.population / 1000).toFixed(0)}k</dd>
        <dt className="text-ink-3">Confidence</dt>
        <dd className="text-right text-ink-2">{f ? pct(f.confidence) : "–"}</dd>
        <dt className="text-ink-3">Sources</dt>
        <dd className="text-right text-ink-2">{f?.sources ?? 0}</dd>
        <dt className="text-ink-3">Syndrome</dt>
        <dd className="text-right capitalize text-ink-2">{f?.syndrome ?? "none"}</dd>
      </dl>
      <div className="mt-2 text-[10.5px] text-ink-3">Click to investigate →</div>
    </>
  );
}
