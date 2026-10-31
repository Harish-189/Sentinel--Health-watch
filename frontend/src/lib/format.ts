export const pct = (x: number, digits = 0) => `${(x * 100).toFixed(digits)}%`;
export const num = (x: number, digits = 0) =>
  x.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
export const signed = (x: number, digits = 1) => `${x >= 0 ? "+" : ""}${x.toFixed(digits)}`;

const SOURCE_LABEL: Record<string, string> = {
  clinic: "Clinic visits",
  pharmacy: "Pharmacy OTC",
  absenteeism: "School absenteeism",
  mobility: "Mobility",
  lab: "Lab",
  hospital: "Hospital",
};
export const sourceLabel = (s: string) => SOURCE_LABEL[s] ?? s;

export function metricLabel(metric: string): string {
  return metric
    .replace(/_/g, " ")
    .replace(/\bili\b/i, "ILI")
    .replace(/\bgi\b/i, "GI")
    .replace(/\bicu\b/i, "ICU")
    .replace(/^\w/, (c) => c.toUpperCase());
}

export function shortDate(iso: string): string {
  const d = new Date(`${iso}T00:00:00Z`);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
}

export const titleCase = (s: string) => s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

/** Monte Carlo probability: never a bare 0% / 100% (finite simulations can't prove certainty). */
export function probLabel(p: number): string {
  if (p >= 0.99) return "≥99%";
  if (p < 0.01) return "<1%";
  return `${Math.round(p * 100)}%`;
}

/** Confidence with its bootstrap P10–P90 interval, e.g. "98% [91–100]". */
export const confLabel = (c: { point: number; low: number; high: number }) =>
  `${Math.round(c.point * 100)}% [${Math.round(c.low * 100)}–${Math.round(c.high * 100)}]`;
