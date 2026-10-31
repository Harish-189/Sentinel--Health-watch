// Design tokens: "clinical calm" light theme. Every color the UI uses comes from here (and index.css @theme).
import { AlertTriangle, CircleDot, Eye, Siren, type LucideIcon } from "lucide-react";

export const color = {
  bg: "#FBE4DA", // cream
  mint: "#BADDD6",
  pink: "#FFAFB3",
  surface: "#FFFFFF", // chart surface (panels are white 65% over cream)
  panel: "rgba(255,255,255,0.65)",
  border: "rgba(95,189,191,0.35)",
  borderStrong: "rgba(95,189,191,0.6)",
  grid: "rgba(23,54,58,0.07)",
  text: "#17363A",
  textSecondary: "#4F6F72",
  textMuted: "#557477",
  accent: "#5FBDBF",
  accentHover: "#2E9EA3",
  accentInk: "#1B7378", // accent for text (AA on white and cream)
  sidebar: "#0F3F43",
  sidebarInk: "#FBF1EA",
  good: "#1F8A5B",
  warning: "#B86A14",
  critical: "#C93A45",
  kill: "#D64550",
} as const;

export type Tier = "E0" | "E1" | "E2" | "E3";
export const TIERS: Tier[] = ["E0", "E1", "E2", "E3"];

// `color` fills marks and borders; `ink` is the darker step used for text on light surfaces (AA).
export const tier: Record<Tier, { color: string; ink: string; label: string; short: string; glow: boolean; icon: LucideIcon }> = {
  E0: { color: "#9DBFB8", ink: "#4A6B65", label: "Background", short: "No signal", glow: false, icon: CircleDot },
  E1: { color: "#2E9EA3", ink: "#1B6E72", label: "Single-stream anomaly", short: "Watch", glow: false, icon: Eye },
  E2: { color: "#F2A65A", ink: "#985510", label: "Corroborated signal", short: "Investigate", glow: true, icon: AlertTriangle },
  E3: { color: "#E5535D", ink: "#B32632", label: "Intervention-grade", short: "Act", glow: true, icon: Siren },
};

// Categorical source palette (light steps, validated on white: adjacent CVD ΔE ≥ 8, normal-vision ≥ 15).
// Fixed order; color follows the source, never its rank. Low-contrast slots always ship with direct labels.
export const source: Record<string, string> = {
  clinic: "#2a78d6",
  pharmacy: "#eb6834",
  absenteeism: "#1baf7a",
  mobility: "#eda100",
  lab: "#e87ba4",
  hospital: "#6250d6",
};
export const SOURCE_ORDER = ["pharmacy", "absenteeism", "mobility", "clinic", "lab", "hospital"];

export const confounderStatus = {
  ruled_out: { label: "PASS", color: "#1F8A5B", hint: "Alternative ruled out" },
  explains: { label: "FAIL", color: "#B32632", hint: "Alternative explains the signal" },
  inconclusive: { label: "INCONCLUSIVE", color: "#985510", hint: "Cannot rule in or out" },
} as const;

export const font = {
  sans: '"Inter", system-ui, sans-serif',
  mono: '"JetBrains Mono", ui-monospace, monospace',
};

export const radius = { panel: 16, chip: 8 };

export const motion = {
  ease: [0.22, 1, 0.36, 1] as [number, number, number, number],
  stagger: 0.06,
  fast: 0.18,
};
