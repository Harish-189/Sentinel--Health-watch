import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { Maximize2, Minimize2, Minus, Plus, RotateCcw } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type PointerEvent as RPointerEvent } from "react";
import { pct } from "../lib/format";
import type { District, DistrictFrame } from "../lib/types";
import { color, tier as tierTok, TIERS } from "../theme";

// ------------------------------------------------------------------ projection & geometry
// Stylized Tamil Nadu outline (lon, lat). Not survey-accurate: a recognisable silhouette for orientation only.
const OUTLINE: [number, number][] = [
  [80.3, 13.55], [79.7, 13.4], [78.9, 13.2], [78.0, 12.9], [77.6, 12.4], [77.6, 11.9], [76.8, 11.6], [76.6, 10.9],
  [76.9, 10.3], [77.2, 9.8], [77.3, 8.5], [77.55, 8.08], [78.1, 8.4], [78.15, 8.8], [79.3, 9.3], [79.85, 10.3],
  [79.85, 10.77], [79.8, 11.9], [80.27, 13.08],
];
const LON0 = 76.25;
const LAT0 = 13.85;
const K = 150; // px per degree of latitude
const COS = Math.cos((11 * Math.PI) / 180); // equirectangular, centred on ~11°N
const VB = { w: Math.round((80.75 - LON0) * COS * K), h: Math.round((LAT0 - 7.75) * K) };
const R = 44; // hex radius
const MIN_GAP = 132; // minimum centre distance between cells (keeps hexes + labels apart)

const project = (lon: number, lat: number): [number, number] => [(lon - LON0) * COS * K, (LAT0 - lat) * K];

/** Closed Catmull-Rom spline through the points, as cubic Béziers. */
function smoothPath(pts: [number, number][]): string {
  const n = pts.length;
  const p = (i: number) => pts[(i + n) % n];
  let d = `M${p(0)[0].toFixed(1)},${p(0)[1].toFixed(1)}`;
  for (let i = 0; i < n; i++) {
    const [p0, p1, p2, p3] = [p(i - 1), p(i), p(i + 1), p(i + 2)];
    const c1 = [p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6];
    const c2 = [p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6];
    d += `C${c1[0].toFixed(1)},${c1[1].toFixed(1)} ${c2[0].toFixed(1)},${c2[1].toFixed(1)} ${p2[0].toFixed(1)},${p2[1].toFixed(1)}`;
  }
  return `${d}Z`;
}

function hexPath(cx: number, cy: number, s: number): string {
  const pts = Array.from({ length: 6 }, (_, i) => {
    const a = (Math.PI / 180) * (60 * i - 30);
    return `${(cx + s * Math.cos(a)).toFixed(1)},${(cy + s * Math.sin(a)).toFixed(1)}`;
  });
  return `M${pts.join("L")}Z`;
}

/** Project districts, then nudge apart (symmetric relaxation) until every pair is at least MIN_GAP apart. */
function placeCells(districts: District[]): Record<string, [number, number]> {
  const pos = districts.map((d) => project(d.lon, d.lat));
  for (let iter = 0; iter < 80; iter++) {
    let moved = false;
    for (let i = 0; i < pos.length; i++)
      for (let j = i + 1; j < pos.length; j++) {
        const dx = pos[j][0] - pos[i][0];
        const dy = pos[j][1] - pos[i][1];
        const dist = Math.hypot(dx, dy) || 0.01;
        if (dist < MIN_GAP) {
          const push = (MIN_GAP - dist) / 2 / dist;
          pos[i] = [pos[i][0] - dx * push, pos[i][1] - dy * push];
          pos[j] = [pos[j][0] + dx * push, pos[j][1] + dy * push];
          moved = true;
        }
      }
    if (!moved) break;
  }
  return Object.fromEntries(districts.map((d, i) => [d.code, pos[i]]));
}

const SILHOUETTE = smoothPath(OUTLINE.map(([lon, lat]) => project(lon, lat)));
const level = (f?: DistrictFrame) => TIERS.indexOf(f?.tier ?? "E0");

// ------------------------------------------------------------------ component

interface View {
  k: number;
  x: number;
  y: number;
}
const HOME: View = { k: 1, x: 0, y: 0 };

export function HexMap({
  districts,
  frames,
  selected,
  onSelect,
  height = 420,
  scanning = false,
}: {
  districts: District[];
  frames: Record<string, DistrictFrame>;
  selected?: string;
  onSelect?: (code: string) => void;
  height?: number;
  scanning?: boolean;
}) {
  const reduce = useReducedMotion();
  const box = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<{ code: string; x: number; y: number } | null>(null);
  const [view, setView] = useState<View>(HOME);
  const [full, setFull] = useState(false);
  const drag = useRef<{ x: number; y: number; vx: number; vy: number } | null>(null);

  const pos = useMemo(() => placeCells(districts), [districts]);
  const edges = useMemo(
    () => districts.flatMap((d) => d.neighbors.filter((n) => n > d.code && pos[n]).map((n) => [d.code, n] as const)),
    [districts, pos],
  );

  useEffect(() => {
    const onFs = () => setFull(document.fullscreenElement === box.current);
    document.addEventListener("fullscreenchange", onFs);
    return () => document.removeEventListener("fullscreenchange", onFs);
  }, []);

  const zoom = (factor: number) =>
    setView((v) => {
      const k = Math.min(3, Math.max(1, v.k * factor));
      // Zoom about the viewBox centre.
      const cx = VB.w / 2;
      const cy = VB.h / 2;
      return k === 1 ? HOME : { k, x: cx - ((cx - v.x) * k) / v.k, y: cy - ((cy - v.y) * k) / v.k };
    });
  const toggleFull = () => (document.fullscreenElement ? document.exitFullscreen() : box.current?.requestFullscreen());

  const onDown = (e: RPointerEvent<SVGSVGElement>) => {
    if (view.k === 1) return;
    drag.current = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y };
    (e.target as Element).setPointerCapture?.(e.pointerId);
  };
  const onMove = (e: RPointerEvent<SVGSVGElement>) => {
    if (!drag.current || !box.current) return;
    const scale = VB.h / box.current.clientHeight; // screen px -> viewBox units (height-fitted)
    const d = drag.current;
    setView((v) => ({ ...v, x: d.vx + (e.clientX - d.x) * scale, y: d.vy + (e.clientY - d.y) * scale }));
  };
  const onUp = () => {
    drag.current = null;
  };
  const hoverAt = (code: string, e: React.MouseEvent) => {
    const r = box.current?.getBoundingClientRect();
    if (r) setHover({ code, x: e.clientX - r.left, y: e.clientY - r.top });
  };

  const hovered = hover ? districts.find((d) => d.code === hover.code) : undefined;
  const boxW = box.current?.clientWidth ?? 800;

  return (
    <div ref={box} className={`relative w-full overflow-hidden ${full ? "bg-bg" : ""}`} style={{ height: full ? "100vh" : height }}>
      <svg
        viewBox={`0 0 ${VB.w} ${VB.h}`}
        className={`h-full w-full ${view.k > 1 ? "cursor-grab active:cursor-grabbing" : ""}`}
        role="img"
        aria-label="Tamil Nadu district evidence map"
        onPointerDown={onDown}
        onPointerMove={onMove}
        onPointerUp={onUp}
        onPointerLeave={onUp}
      >
        <defs>
          <linearGradient id="tn-fill" x1="0" x2="0.4" y1="0" y2="1">
            <stop offset="0%" stopColor="#BADDD6" stopOpacity="0.75" />
            <stop offset="100%" stopColor="#BADDD6" stopOpacity="0.35" />
          </linearGradient>
          <filter id="tn-glow" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="9" />
          </filter>
          <linearGradient id="scan" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="#5FBDBF" stopOpacity="0" />
            <stop offset="85%" stopColor="#5FBDBF" stopOpacity="0.16" />
            <stop offset="100%" stopColor="#2E9EA3" stopOpacity="0.5" />
          </linearGradient>
          <clipPath id="tn-clip">
            <path d={SILHOUETTE} />
          </clipPath>
        </defs>

        <motion.g animate={{ x: view.x, y: view.y, scale: view.k }} transition={reduce || drag.current ? { duration: 0 } : { duration: 0.25 }} style={{ originX: 0, originY: 0 }}>
          {/* State silhouette: soft glow, mint fill, thin teal outline */}
          <path d={SILHOUETTE} fill="#5FBDBF" opacity={0.35} filter="url(#tn-glow)" />
          <path d={SILHOUETTE} fill="url(#tn-fill)" stroke="#5FBDBF" strokeWidth={1.5} strokeLinejoin="round" />

          {scanning && (
            <g clipPath="url(#tn-clip)" style={{ pointerEvents: "none" }}>
              <rect x={0} y={0} width={VB.w} height={VB.h * 0.2} fill="url(#scan)" className="scanline" style={{ transformBox: "view-box" }} />
            </g>
          )}

          {/* Adjacency network: faint for all edges, animated coral dashes where both ends are E2+ (spatial coherence) */}
          {edges.map(([a, b]) => {
            const hot = level(frames[a]) >= 2 && level(frames[b]) >= 2;
            return (
              <line
                key={`${a}-${b}`}
                x1={pos[a][0]}
                y1={pos[a][1]}
                x2={pos[b][0]}
                y2={pos[b][1]}
                stroke={hot ? tierTok.E3.color : "#2E9EA3"}
                strokeOpacity={hot ? 0.8 : 0.22}
                strokeWidth={hot ? 2.5 : 1.2}
                strokeDasharray={hot ? "5 6" : "2 5"}
              >
                {hot && !reduce && <animate attributeName="stroke-dashoffset" from="22" to="0" dur="1.1s" repeatCount="indefinite" />}
              </line>
            );
          })}

          {districts.map((d) => {
            const [cx, cy] = pos[d.code];
            const f = frames[d.code];
            const lv = level(f);
            const t = tierTok[f?.tier ?? "E0"];
            const isSel = selected === d.code;
            const Icon = t.icon;
            return (
              <g
                key={d.code}
                onMouseEnter={(e) => hoverAt(d.code, e)}
                onMouseMove={(e) => hoverAt(d.code, e)}
                onMouseLeave={() => setHover(null)}
                onClick={() => onSelect?.(d.code)}
                onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onSelect?.(d.code)}
                tabIndex={0}
                role="button"
                aria-label={`${d.name}: ${f?.tier ?? "E0"}, ${f?.sources ?? 0} sources`}
                className="cursor-pointer outline-none [&:focus-visible>path:first-of-type]:stroke-[#17363A]"
              >
                {lv >= 2 && (
                  <>
                    <path d={hexPath(cx, cy, R * 0.7)} fill="none" stroke={t.color} strokeWidth={2} className="ring-out" style={{ pointerEvents: "none" }} />
                    <path d={hexPath(cx, cy, R * 0.7)} fill="none" stroke={t.color} strokeWidth={1.5} className="ring-out" style={{ animationDelay: "1.2s", pointerEvents: "none" }} />
                  </>
                )}
                <motion.path
                  d={hexPath(cx, cy, R)}
                  initial={false}
                  animate={{ fill: lv === 0 ? "rgba(255,255,255,0.85)" : `${t.color}${lv >= 2 ? "e6" : "b3"}`, stroke: isSel ? "#17363A" : t.color }}
                  transition={{ duration: 0.45 }}
                  strokeWidth={isSel ? 2.6 : 1.6}
                  style={{ filter: hover?.code === d.code ? "brightness(1.08) drop-shadow(0 4px 8px rgba(15,63,67,0.25))" : "drop-shadow(0 2px 4px rgba(15,63,67,0.15))" }}
                />
                {/* Tier chip inside the cell */}
                <foreignObject x={cx - 30} y={cy - 22} width={60} height={24} style={{ pointerEvents: "none", overflow: "visible" }}>
                  <div className="num flex h-full items-center justify-center gap-1 text-[17px] font-bold" style={{ color: lv >= 2 ? "#FFFFFF" : t.ink }}>
                    <Icon size={15} strokeWidth={2.6} />
                    {f?.tier ?? "E0"}
                  </div>
                </foreignObject>
                <text x={cx} y={cy + 19} textAnchor="middle" fontSize={13} fontFamily="JetBrains Mono" fill={lv >= 2 ? "#FFFFFF" : color.textSecondary} style={{ pointerEvents: "none" }}>
                  {f && f.sources > 0 ? `${f.sources} src` : d.code}
                </text>
                {/* City label on a cream pill below the cell */}
                <g style={{ pointerEvents: "none" }}>
                  <rect x={cx - d.name.length * 4.9 - 9} y={cy + R + 5} width={d.name.length * 9.8 + 18} height={24} rx={12} fill="#FFFDFB" fillOpacity={0.92} stroke={isSel ? "#17363A" : "rgba(95,189,191,0.5)"} />
                  <text x={cx} y={cy + R + 22} textAnchor="middle" fontSize={15.5} fontWeight={600} fill={color.text}>
                    {d.name}
                  </text>
                </g>
              </g>
            );
          })}
        </motion.g>

        <g style={{ pointerEvents: "none" }} fill={color.textMuted} fontSize={10}>
          <text x={22} y={30} textAnchor="middle" fontSize={13} fontWeight={700} fill={color.textSecondary}>
            N
          </text>
          <path d="M22,36 l-6,14 l6,-4 l6,4 Z" fill={color.textSecondary} />
          <text x={VB.w - 12} y={VB.h - 14} textAnchor="end" fontSize={12}>
            Stylized outline · not to scale
          </text>
        </g>
      </svg>

      {/* Floating map controls */}
      <div className="absolute right-3 top-3 flex flex-col overflow-hidden rounded-full border border-line/50 bg-white/85 shadow-[0_6px_18px_-10px_rgba(15,63,67,0.5)] backdrop-blur" role="toolbar" aria-label="Map controls">
        {[
          { icon: Plus, label: "Zoom in", on: () => zoom(1.4), off: view.k >= 3 },
          { icon: Minus, label: "Zoom out", on: () => zoom(1 / 1.4), off: view.k <= 1 },
          { icon: RotateCcw, label: "Reset view", on: () => setView(HOME), off: view.k === 1 },
          { icon: full ? Minimize2 : Maximize2, label: full ? "Exit fullscreen" : "Fullscreen", on: toggleFull, off: false },
        ].map(({ icon: I, label, on, off }) => (
          <button
            key={label}
            onClick={on}
            disabled={off}
            title={label}
            aria-label={label}
            className="grid h-8 w-8 place-items-center text-ink-2 outline-none transition-colors duration-150 hover:bg-accent/20 hover:text-ink focus-visible:bg-accent/25 disabled:opacity-35"
          >
            <I size={14} />
          </button>
        ))}
      </div>

      <AnimatePresence>
        {hovered && hover && (
          <motion.div
            key={hovered.code}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="glass pointer-events-none absolute z-10 w-56 p-3 text-xs"
            style={{ left: Math.min(hover.x + 16, boxW - 236), top: Math.max(8, hover.y - 20), background: "rgba(255,253,251,0.95)" }}
          >
            <HoverCard d={hovered} f={frames[hovered.code]} />
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
        <span className="num font-bold" style={{ color: t.ink }}>
          {f?.tier ?? "E0"}
        </span>
      </div>
      <div className="mt-0.5 text-[11px]" style={{ color: t.ink }}>
        {t.label}
      </div>
      <dl className="num mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-[11px]">
        <dt className="text-ink-3">Sim. catchment</dt>
        <dd className="text-right text-ink-2">{(d.population / 1000).toFixed(0)}k</dd>
        <dt className="text-ink-3">Confidence</dt>
        <dd className="text-right text-ink-2">{f ? pct(f.confidence) : "–"}</dd>
        <dt className="text-ink-3">Sources</dt>
        <dd className="text-right text-ink-2">{f?.sources ?? 0}</dd>
        <dt className="text-ink-3">Syndrome</dt>
        <dd className="text-right capitalize text-ink-2">{f?.syndrome ?? "none"}</dd>
      </dl>
      <div className="mt-2 text-[10.5px] text-accent-ink">Click to investigate →</div>
    </>
  );
}
