import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { streamUrl } from "./api";
import { useEvidence } from "./evidence";
import type { CaseFile, StepEvent } from "./types";

export const STEPS = ["Detect", "Correlate", "Confounders", "Hypothesize", "Verify", "Grade", "Forecast", "Recommend"] as const;

export interface StreamState {
  steps: Record<string, StepEvent>;
  casefile: CaseFile | null;
  running: boolean;
  error: string | null;
}

/** Runs the agent pipeline over SSE: step events animate the stepper, the final event is the case file. */
export function useAnalyzeStream(params: { scenario?: string; seed?: number; district: string }) {
  const qc = useQueryClient();
  const { register } = useEvidence();
  const [state, setState] = useState<StreamState>({ steps: {}, casefile: null, running: false, error: null });
  const es = useRef<EventSource | null>(null);

  const run = useCallback(() => {
    es.current?.close();
    setState({ steps: {}, casefile: null, running: true, error: null });
    const src = new EventSource(streamUrl(params));
    es.current = src;
    src.addEventListener("step", (e) => {
      const ev = JSON.parse((e as MessageEvent).data) as StepEvent;
      setState((s) => ({ ...s, steps: { ...s.steps, [ev.step]: ev } }));
    });
    src.addEventListener("casefile", (e) => {
      const cf = JSON.parse((e as MessageEvent).data) as CaseFile;
      register(cf.evidence);
      setState((s) => ({ ...s, casefile: cf, running: false }));
      src.close();
      qc.invalidateQueries({ queryKey: ["actions"] });
      qc.invalidateQueries({ queryKey: ["audit"] });
    });
    src.onerror = () => {
      src.close();
      setState((s) => (s.casefile ? s : { ...s, running: false, error: "Stream interrupted. Is the API running?" }));
    };
  }, [params.scenario, params.seed, params.district, qc, register]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    run();
    return () => es.current?.close();
  }, [run]);

  return { ...state, run };
}
