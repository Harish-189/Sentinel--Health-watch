// Design tokens: "mission control meets clinical calm". Every color the UI uses comes from here.

export const color = {
  bg: "#070B14",
  surface: "#0C1322", // chart surface (validated against the source palette)
  panel: "rgba(14, 21, 37, 0.62)",
  border: "rgba(255,255,255,0.08)",
  borderStrong: "rgba(255,255,255,0.14)",
  grid: "rgba(255,255,255,0.06)",
  text: "#E6EDF7",
  textSecondary: "#9AA8BD",
  textMuted: "#64748B",
  accent: "#22D3EE",
  good: "#10B981",
  warning: "#F59E0B",
  critical: "#EF4444",
} as const;

export type Tier = "E0" | "E1" | "E2" | "E3";
export const TIERS: Tier[] = ["E0", "E1", "E2", "E3"];

export const tier: Record<Tier, { color: string; label: string; short: string; glow: boolean }> = {
  E0: { color: "#64748B", label: "Background", short: "No signal", glow: false },
  E1: { color: "#3B82F6", label: "Single-stream anomaly", short: "Watch", glow: false },
  E2: { color: "#F59E0B", label: "Corroborated signal", short: "Investigate", glow: true },
  E3: { color: "#EF4444", label: "Intervention-grade", short: "Act", glow: true },
};

// Categorical source palette (dark steps, validated: adjacent CVD ΔE ≥ 8.4, contrast ≥ 3:1 on `surface`).
// Fixed order, color follows the source, never its rank.
export const source: Record<string, string> = {
  clinic: "#3987e5",
  pharmacy: "#d95926",
  absenteeism: "#199e70",
  mobility: "#c98500",
  lab: "#d55181",
  hospital: "#9085e9",
};
export const SOURCE_ORDER = ["pharmacy", "absenteeism", "mobility", "clinic", "lab", "hospital"];

export const confounderStatus = {
  ruled_out: { label: "PASS", color: "#10B981", hint: "Alternative ruled out" },
  explains: { label: "FAIL", color: "#EF4444", hint: "Alternative explains the signal" },
  inconclusive: { label: "INCONCLUSIVE", color: "#F59E0B", hint: "Cannot rule in or out" },
} as const;

export const font = {
  sans: '"Inter", system-ui, sans-serif',
  mono: '"JetBrains Mono", ui-monospace, monospace',
};

export const radius = { panel: 16, chip: 8 };

export const motion = {
  ease: [0.22, 1, 0.36, 1] as [number, number, number, number],
  stagger: 0.06,
};
