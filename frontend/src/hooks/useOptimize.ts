"use client";

import { useState, useCallback } from "react";
import { runOptimize, ApiClientError } from "@/lib/api";
import type { OptimizeResponse, AsyncState, PlanningScenario } from "@/types/api";

export type AppState = AsyncState<OptimizeResponse>;

export function useOptimize() {
  const [state, setState] = useState<AppState>({ status: "idle" });
  const [lastRunParams, setLastRunParams] = useState<{ stationCount: number; scenario: PlanningScenario } | null>(null);

  const run = useCallback(async (stationCount: number = 3, scenario: PlanningScenario = "all_hours") => {
    setState({ status: "loading" });
    setLastRunParams({ stationCount, scenario });
    try {
      const data = await runOptimize({ station_count: stationCount, scenario, reps: 1, shots: 2048, seed: 42 });
      console.info(
        "[QuantEV] Complete →",
        data.recommendation.selected_zones,
        `${data.pipeline_runtime_s.toFixed(1)}s`,
      );
      setState({ status: "success", data });
    } catch (err) {
      if (err instanceof ApiClientError) {
        console.error("[QuantEV] API error:", err.message, err.status, err.rawDetail);
        setState({ status: "error", message: err.message });
      } else if (err instanceof Error) {
        console.error("[QuantEV] Error:", err);
        setState({ status: "error", message: err.message });
      } else {
        console.error("[QuantEV] Unknown:", err);
        setState({
          status: "error",
          message: "Something went wrong. Check the console for details.",
        });
      }
    }
  }, []);

  const reset = useCallback(() => {
    setState({ status: "idle" });
    setLastRunParams(null);
  }, []);

  return { state, run, reset, lastRunParams };
}
