import type { Assessment } from "./types";

/** One-line plain-language "why" for a district, built only from deterministic gate results. */
export function whyLine(a: Assessment): string {
  const crit = Object.fromEntries(a.gate.criteria.map((c) => [c.key, c]));
  const parts: string[] = [];
  if (a.gate.downgrades.length) parts.push(`capped: ${a.gate.downgrades[0].split(":")[0].toLowerCase()}`);
  const explains = a.confounders.filter((c) => c.status === "explains").sort((x, y) => y.explained_share - x.explained_share);
  if (explains.length) parts.push(`${explains[0].label.split(" /")[0].toLowerCase()} explains ${Math.round(explains[0].explained_share * 100)}%`);
  if (crit.e3_lab?.met) parts.push("lab positivity up, tests stable");
  else if (a.signal && crit.e3_lab) parts.push("no lab confirmation yet");
  if (crit.e2_sources?.met && a.signal) parts.push(`${a.signal.independent_sources} sources agree`);
  else if (a.signal) parts.push(`${a.signal.independent_sources} source${a.signal.independent_sources === 1 ? "" : "s"} only`);
  if (crit.e3_spatial?.met) parts.push("neighbours corroborate");
  const ruled = a.confounders.filter((c) => c.status === "ruled_out").map((c) => c.name);
  if (!explains.length && ruled.includes("holiday")) parts.push("holiday ruled out");
  const line = parts.slice(0, 3).join(", ");
  return line ? line[0].toUpperCase() + line.slice(1) : "Within expected range";
}
