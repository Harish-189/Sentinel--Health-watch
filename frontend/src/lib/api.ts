import { useQuery } from "@tanstack/react-query";
import type {
  AnalysisBundle,
  AuditEntry,
  CaseFile,
  District,
  Forecast,
  PendingAction,
  Scenario,
  SeriesResponse,
  SystemStatus,
  Timeline,
} from "./types";
import { useApp } from "./state";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError(0, "Backend unreachable. Is the API running on :8000?");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* keep statusText */
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

export const post = <T,>(path: string, body: unknown) => api<T>(path, { method: "POST", body: JSON.stringify(body) });

export function qs(params: Record<string, string | number | boolean | null | undefined>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : "";
}

/** Scenario/seed parameters shared by every read query. */
export function useRunParams() {
  const { scenario, seed } = useApp();
  return { scenario: scenario.join("+"), seed };
}

const STATIC = { staleTime: Infinity, gcTime: Infinity } as const;

export const useDistricts = () => useQuery({ queryKey: ["districts"], queryFn: () => api<District[]>("/api/districts"), ...STATIC });
export const useScenarios = () => useQuery({ queryKey: ["scenarios"], queryFn: () => api<Scenario[]>("/api/scenarios"), ...STATIC });

export function useAnalysis(asOf?: number) {
  const p = useRunParams();
  return useQuery({
    queryKey: ["analysis", p, asOf],
    queryFn: () => api<AnalysisBundle>(`/api/analysis${qs({ ...p, as_of: asOf })}`),
    ...STATIC,
  });
}

export function useTimeline() {
  const p = useRunParams();
  return useQuery({ queryKey: ["timeline", p], queryFn: () => api<Timeline>(`/api/timeline${qs(p)}`), ...STATIC });
}

export function useSeries(district: string) {
  const p = useRunParams();
  return useQuery({
    queryKey: ["series", p, district],
    queryFn: () => api<SeriesResponse>(`/api/series${qs({ ...p, district })}`),
    ...STATIC,
  });
}

export function useForecast(district: string, intervention: boolean) {
  const p = useRunParams();
  return useQuery({
    queryKey: ["forecast", p, district, intervention],
    queryFn: () => api<Forecast>(`/api/forecast${qs({ ...p, district, intervention })}`),
    ...STATIC,
    placeholderData: (prev) => prev,
  });
}

export function useCaseFile(district?: string) {
  const p = useRunParams();
  return useQuery({
    queryKey: ["casefile", p, district],
    queryFn: () => api<CaseFile>(`/api/casefile${qs({ ...p, district })}`),
    ...STATIC,
  });
}

export const useSystem = () =>
  useQuery({ queryKey: ["system"], queryFn: () => api<SystemStatus>("/api/system"), refetchInterval: 10_000 });

export const useActions = () =>
  useQuery({ queryKey: ["actions"], queryFn: () => api<PendingAction[]>("/api/actions"), refetchInterval: 5_000 });

export const useAudit = () =>
  useQuery({
    queryKey: ["audit"],
    queryFn: () => api<{ verified: boolean; entries: AuditEntry[] }>("/api/audit?limit=200"),
    refetchInterval: 5_000,
  });

export function streamUrl(params: { scenario: string; seed: number; district?: string }): string {
  return `/api/analyze/stream${qs({ ...params, pace_ms: 380 })}`;
}
