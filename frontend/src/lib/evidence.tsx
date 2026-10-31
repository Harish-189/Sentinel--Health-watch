import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";
import type { EvidenceItem } from "./types";

interface EvidenceCtx {
  openId: string | null;
  open: (id: string | null) => void;
  highlight: string | null;
  setHighlight: (id: string | null) => void;
  lookup: (id: string) => EvidenceItem | undefined;
  register: (items: Record<string, EvidenceItem>) => void;
}

const Ctx = createContext<EvidenceCtx | null>(null);

export function EvidenceProvider({ children }: { children: ReactNode }) {
  const store = useRef<Record<string, EvidenceItem>>({});
  const [openId, open] = useState<string | null>(null);
  const [highlight, setHighlight] = useState<string | null>(null);
  const register = useCallback((items: Record<string, EvidenceItem>) => {
    Object.assign(store.current, items);
  }, []);
  const lookup = useCallback((id: string) => store.current[id], []);
  const value = useMemo(() => ({ openId, open, highlight, setHighlight, lookup, register }), [openId, highlight, lookup, register]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useEvidence(): EvidenceCtx {
  const v = useContext(Ctx);
  if (!v) throw new Error("useEvidence outside EvidenceProvider");
  return v;
}
