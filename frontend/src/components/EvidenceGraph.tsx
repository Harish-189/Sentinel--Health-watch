import { useMemo, useState } from "react";
import { useEvidence } from "../lib/evidence";
import type { Hypothesis } from "../lib/types";
import { color, source as srcColor } from "../theme";

const CODE_SOURCE: Record<string, string> = { CLI: "clinic", PHA: "pharmacy", ABS: "absenteeism", MOB: "mobility", LAB: "lab", CAP: "hospital", ENV: "environment", MET: "meta" };

/** Which upstream feed or analysis stage an evidence ID comes from. */
export function originOf(id: string): string {
  const [prefix, , code] = id.split("-");
  if (prefix === "EV" || prefix === "SR") return CODE_SOURCE[code] ?? "other";
  return { SG: "correlation", CF: "confounder checks", CAL: "calendar", GT: "evidence gate", FC: "forecast" }[prefix] ?? "other";
}
const originColor = (o: string) => srcColor[o] ?? (o === "calendar" ? "#94a3b8" : o === "environment" ? "#7dd3fc" : color.accent);

interface Node {
  id: string;
  label: string;
  y: number;
  color: string;
}

export function EvidenceGraph({ hypotheses }: { hypotheses: Hypothesis[] }) {
  const { highlight, setHighlight, open } = useEvidence();
  const [hoverClaim, setHoverClaim] = useState<string | null>(null);

  const g = useMemo(() => {
    const claims = hypotheses.flatMap((h) => h.claims.map((c) => ({ ...c, hyp: h }))).slice(0, 14);
    const ids = [...new Set(claims.flatMap((c) => c.evidence_ids))];
    const origins = [...new Set(ids.map(originOf))];
    const ROW = 26;
    const rows = Math.max(claims.length, ids.length, origins.length);
    const H = rows * ROW + 20;
    const place = (n: number, i: number) => 18 + (i + 0.5) * ((H - 36) / n);
    const cN: Node[] = claims.map((c, i) => ({ id: c.claim_id || `c${i}`, label: c.text, y: place(claims.length, i), color: c.hyp.kind === "epidemic" ? "#EF4444" : "#94a3b8" }));
    const eN: Node[] = ids.map((id, i) => ({ id, label: id, y: place(ids.length, i), color: originColor(originOf(id)) }));
    const oN: Node[] = origins.map((o, i) => ({ id: o, label: o, y: place(origins.length, i), color: originColor(o) }));
    const ce = claims.flatMap((c, i) => c.evidence_ids.map((e) => ({ from: cN[i].id, to: e })));
    const eo = ids.map((e) => ({ from: e, to: originOf(e) }));
    return { claims, cN, eN, oN, ce, eo, H };
  }, [hypotheses]);

  const W = 1000;
  const X = { claimR: 420, eviL: 520, eviR: 720, orig: 810 };
  const yOf = (list: Node[], id: string) => list.find((n) => n.id === id)?.y ?? 0;
  const activeClaimIds = hoverClaim ? new Set(g.ce.filter((l) => l.from === hoverClaim).map((l) => l.to)) : null;
  const isLit = (claimId: string, evId: string) => (hoverClaim ? hoverClaim === claimId : highlight ? highlight === evId : false);
  const anyActive = !!hoverClaim || !!highlight;
  const curve = (x1: number, y1: number, x2: number, y2: number) => `M${x1},${y1} C${(x1 + x2) / 2},${y1} ${(x1 + x2) / 2},${y2} ${x2},${y2}`;

  if (!g.claims.length) return <div className="p-6 text-center text-sm text-ink-3">No grounded claims to graph.</div>;

  return (
    <div className="w-full overflow-x-auto">
      <svg viewBox={`0 0 ${W} ${g.H}`} className="h-auto w-full min-w-[760px]">
        {["Claims (agents)", "Evidence IDs", "Origin"].map((t, i) => (
          <text key={t} x={[8, X.eviL, X.orig][i]} y={10} fill={color.textMuted} fontSize={10} fontWeight={600} letterSpacing="0.1em">
            {t.toUpperCase()}
          </text>
        ))}
        {g.ce.map((l, i) => {
          const lit = isLit(l.from, l.to);
          return <path key={i} d={curve(X.claimR, yOf(g.cN, l.from), X.eviL, yOf(g.eN, l.to))} fill="none" stroke={lit ? color.accent : "rgba(148,163,184,0.22)"} strokeWidth={lit ? 1.8 : 1} opacity={anyActive && !lit ? 0.35 : 1} />;
        })}
        {g.eo.map((l, i) => {
          const lit = (activeClaimIds?.has(l.from) ?? false) || highlight === l.from;
          return <path key={i} d={curve(X.eviR, yOf(g.eN, l.from), X.orig, yOf(g.oN, l.to))} fill="none" stroke={lit ? originColor(l.to) : "rgba(148,163,184,0.18)"} strokeWidth={lit ? 1.8 : 1} opacity={anyActive && !lit ? 0.35 : 1} />;
        })}
        {g.cN.map((n) => (
          <g key={n.id} onMouseEnter={() => setHoverClaim(n.id)} onMouseLeave={() => setHoverClaim(null)} className="cursor-default">
            <rect x={4} y={n.y - 10} width={X.claimR - 4} height={20} rx={6} fill={hoverClaim === n.id ? "rgba(34,211,238,0.10)" : "rgba(255,255,255,0.025)"} stroke="rgba(255,255,255,0.06)" />
            <circle cx={14} cy={n.y} r={3} fill={n.color} />
            <text x={24} y={n.y + 3.5} fill={color.textSecondary} fontSize={11}>
              {n.label.length > 66 ? `${n.label.slice(0, 64)}…` : n.label}
            </text>
            <title>{n.label}</title>
          </g>
        ))}
        {g.eN.map((n) => {
          const lit = highlight === n.id || (activeClaimIds?.has(n.id) ?? false);
          return (
            <g key={n.id} onMouseEnter={() => setHighlight(n.id)} onMouseLeave={() => setHighlight(null)} onClick={() => open(n.id)} className="cursor-pointer">
              <rect x={X.eviL} y={n.y - 9} width={X.eviR - X.eviL} height={18} rx={5} fill={lit ? "rgba(34,211,238,0.14)" : "rgba(34,211,238,0.04)"} stroke={lit ? "rgba(34,211,238,0.7)" : "rgba(34,211,238,0.22)"} />
              <text x={X.eviL + 8} y={n.y + 3.5} fill={lit ? color.accent : "rgba(34,211,238,0.85)"} fontSize={10} fontFamily="JetBrains Mono">
                {n.label.length > 30 ? `${n.label.slice(0, 29)}…` : n.label}
              </text>
              <title>{n.label}</title>
            </g>
          );
        })}
        {g.oN.map((n) => (
          <g key={n.id}>
            <circle cx={X.orig + 6} cy={n.y} r={5} fill={n.color} stroke={color.surface} strokeWidth={2} />
            <text x={X.orig + 18} y={n.y + 4} fill={color.text} fontSize={11.5} style={{ textTransform: "capitalize" }}>
              {n.label}
            </text>
          </g>
        ))}
      </svg>
    </div>
  );
}
