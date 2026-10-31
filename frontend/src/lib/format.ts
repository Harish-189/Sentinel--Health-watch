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
