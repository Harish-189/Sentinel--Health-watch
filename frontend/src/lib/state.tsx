import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useSystem } from "./api";

export type Page = "command" | "signals" | "investigation" | "capacity" | "actions" | "evaluation" | "lab";
export const PAGES: Page[] = ["command", "signals", "investigation", "capacity", "actions", "evaluation", "lab"];

interface AppState {
  page: Page;
  go: (page: Page, district?: string) => void;
  /** Selected district; defaults to the server's configured primary district. */
  district: string;
  setDistrict: (d: string) => void;
  /** Scenario override; null = the server's demo scenario. */
  scenario: string[] | null;
  setScenario: (s: string[] | null) => void;
  /** Seed override; null = the server's demo seed. */
  seed: number | null;
  /** The scenario actually being shown (resolved from the server defaults). */
  scenarioLabel: string[];
  ready: boolean;
}

const Ctx = createContext<AppState | null>(null);

function pageFromHash(): Page {
  const h = window.location.hash.replace(/^#\/?/, "").split("?")[0] as Page;
  return PAGES.includes(h) ? h : "command";
}

export function AppProvider({ children }: { children: ReactNode }) {
  const sys = useSystem();
  const [page, setPage] = useState<Page>(pageFromHash);
  const [chosen, setDistrict] = useState<string | null>(null);
  const [scenario, setScenario] = useState<string[] | null>(null);

  useEffect(() => {
    const onHash = () => setPage(pageFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const go = useCallback((p: Page, d?: string) => {
    if (d) setDistrict(d);
    window.location.hash = `/${p}`;
    setPage(p);
    window.scrollTo({ top: 0 });
  }, []);

  const district = chosen ?? sys.data?.default_district ?? "";
  const scenarioLabel = scenario ?? sys.data?.demo_scenario.split("+") ?? [];
  const value = useMemo(
    () => ({ page, go, district, setDistrict, scenario, setScenario, seed: null, scenarioLabel, ready: !!sys.data }),
    [page, go, district, scenario, scenarioLabel.join("+"), sys.data], // eslint-disable-line react-hooks/exhaustive-deps
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useApp(): AppState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useApp outside AppProvider");
  return v;
}
