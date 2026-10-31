import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export type Page = "command" | "signals" | "investigation" | "capacity" | "actions" | "evaluation" | "lab";
export const PAGES: Page[] = ["command", "signals", "investigation", "capacity", "actions", "evaluation", "lab"];

interface AppState {
  page: Page;
  go: (page: Page, district?: string) => void;
  district: string;
  setDistrict: (d: string) => void;
  scenario: string[];
  setScenario: (s: string[]) => void;
  seed: number;
}

const Ctx = createContext<AppState | null>(null);
export const DEMO_SEED = 7;

function pageFromHash(): Page {
  const h = window.location.hash.replace(/^#\/?/, "").split("?")[0] as Page;
  return PAGES.includes(h) ? h : "command";
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [page, setPage] = useState<Page>(pageFromHash);
  const [district, setDistrict] = useState("D3");
  const [scenario, setScenario] = useState<string[]>(["true_outbreak"]);

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

  const value = useMemo(
    () => ({ page, go, district, setDistrict, scenario, setScenario, seed: DEMO_SEED }),
    [page, go, district, scenario],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useApp(): AppState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useApp outside AppProvider");
  return v;
}
