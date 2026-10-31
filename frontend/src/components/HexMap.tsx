import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { Maximize2, Minimize2, Minus, Plus, RotateCcw } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type PointerEvent as RPointerEvent } from "react";
import { pct } from "../lib/format";
import type { District, DistrictFrame } from "../lib/types";
import { color, tier as tierTok, TIERS } from "../theme";

// ------------------------------------------------------------------ projection & geometry
// Tamil Nadu outline (lon, lat), traced from reference/geometric-map-tamil-nadu-…avif (158 points after
// Douglas-Peucker) and fitted to the state's extent. Stylized for orientation; not survey-accurate.
const OUTLINE: [number, number][] = [
  [80.066, 13.57], [80.332, 13.459], [80.35, 13.317], [80.263, 12.971], [80.263, 12.805], [80.153, 12.469], [79.905, 12.112], [79.845, 11.963],
  [79.777, 11.956], [79.703, 11.883], [79.749, 11.887], [79.809, 11.828], [79.767, 11.554], [79.845, 11.371], [79.864, 10.996], [79.754, 10.993],
  [79.721, 10.934], [79.859, 10.83], [79.891, 10.321], [79.85, 10.286], [79.721, 10.283], [79.396, 10.328], [79.286, 10.259], [79.235, 10.155],
  [79.267, 10.051], [78.997, 9.715], [78.909, 9.49], [79.038, 9.337], [79.18, 9.292], [78.854, 9.258], [78.721, 9.195], [78.671, 9.202],
  [78.657, 9.164], [78.579, 9.136], [78.418, 9.119], [78.198, 8.939], [78.171, 8.8], [78.207, 8.804], [78.235, 8.755], [78.194, 8.755],
  [78.143, 8.69], [78.143, 8.503], [78.074, 8.423], [78.079, 8.378], [77.822, 8.25], [77.749, 8.177], [77.593, 8.142], [77.561, 8.08],
  [77.317, 8.125], [77.097, 8.302], [77.207, 8.461], [77.184, 8.503], [77.262, 8.551], [77.152, 8.752], [77.212, 8.794], [77.239, 8.873],
  [77.129, 9.022], [77.249, 9.157], [77.267, 9.306], [77.391, 9.507], [77.299, 9.594], [77.258, 9.573], [77.157, 9.614], [77.23, 9.812],
  [77.203, 9.909], [77.258, 9.975], [77.189, 10.117], [77.258, 10.148], [77.276, 10.221], [77.203, 10.352], [77.088, 10.307], [76.987, 10.221],
  [76.9, 10.241], [76.826, 10.304], [76.831, 10.591], [76.803, 10.64], [76.872, 10.657], [76.895, 10.799], [76.808, 10.879], [76.652, 10.938],
  [76.684, 11.028], [76.739, 11.069], [76.739, 11.128], [76.689, 11.166], [76.721, 11.225], [76.459, 11.194], [76.446, 11.246], [76.519, 11.291],
  [76.542, 11.35], [76.363, 11.464], [76.244, 11.474], [76.23, 11.589], [76.28, 11.62], [76.358, 11.613], [76.51, 11.724], [76.588, 11.634],
  [76.831, 11.62], [76.9, 11.807], [77.024, 11.828], [77.088, 11.758], [77.106, 11.79], [77.244, 11.828], [77.336, 11.79], [77.418, 11.79],
  [77.483, 11.956], [77.666, 11.98], [77.762, 12.126], [77.735, 12.171], [77.62, 12.209], [77.505, 12.198], [77.464, 12.219], [77.46, 12.264],
  [77.606, 12.389], [77.616, 12.472], [77.574, 12.489], [77.597, 12.514], [77.57, 12.562], [77.588, 12.683], [77.694, 12.694], [77.753, 12.732],
  [77.781, 12.86], [77.827, 12.888], [77.932, 12.908], [77.987, 12.846], [78.015, 12.881], [78.056, 12.87], [78.143, 12.798], [78.226, 12.784],
  [78.24, 12.735], [78.373, 12.642], [78.441, 12.649], [78.487, 12.704], [78.478, 12.759], [78.542, 12.742], [78.634, 12.95], [78.607, 13.002],
  [78.703, 13.089], [78.978, 13.109], [79.079, 13.047], [79.148, 13.04], [79.212, 13.165], [79.253, 13.179], [79.322, 13.151], [79.409, 13.227],
  [79.368, 13.334], [79.414, 13.355], [79.533, 13.345], [79.57, 13.286], [79.671, 13.314], [79.749, 13.234], [79.767, 13.248], [79.712, 13.3],
  [79.749, 13.334], [79.845, 13.338], [79.928, 13.386], [79.923, 13.438], [79.997, 13.515], [79.978, 13.556],
];
const LON0 = 76.0;
const LAT0 = 13.85;
const K = 150; // px per degree of latitude
const COS = Math.cos((11 * Math.PI) / 180); // equirectangular, centred on ~11°N
const VB = { w: Math.round((80.6 - LON0) * COS * K), h: Math.round((LAT0 - 7.85) * K) };
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
