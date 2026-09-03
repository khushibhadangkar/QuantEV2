/**
 * TypeScript types mirroring the FastAPI OptimizeResponse schema exactly.
 * Field names match the backend Pydantic models 1:1.
 * Zone labels (Z0–Z7) are never hardcoded — they come from the API.
 */

// ── Request ─────────────────────────────────────────────────────────────────

export type PlanningScenario =
  | "all_hours"
  | "morning_peak"
  | "afternoon"
  | "overnight"
  | "weekday"
  | "weekend";

export interface OptimizeRequest {
  station_count?: number; // 1-8
  scenario?: PlanningScenario;
  reps?: number;   // 1–5, default 1
  shots?: number;  // 128–16384, default 2048
  seed?: number;   // ≥ 0, default 42
}

// ── Sub-models ───────────────────────────────────────────────────────────────

export interface ZoneDetail {
  label: string;
  tazid: number;
  name_primary?: string;
  name_secondary?: string;
  longitude: number;
  latitude: number;
  predicted_demand_kwh_h: number;
  qubo_c_value: number;
  selected: boolean;
  self_demand_score: number;
  proximity_spillover_score: number;
  coverage_neighbors_count: number;
}

export interface RecommendationResponse {
  selected_zones: string[];
  scenario?: string;
  method: string;
  qubo_energy: number;
  feasible: boolean;
  n_stations: number;
  matches_qubo_optimum: boolean;
  predicted_demand: Record<string, number>;
  total_candidate_demand_kwh_h: number;
  zone_details: ZoneDetail[];
}

export interface AIDemandResponse {
  model: string;
  scenario?: string;
  test_r2: number | null;
  test_mae: number | null;
  test_split_start: string;
  test_split_end: string;
  prediction_time_ms: number;
  predicted_demand: Record<string, number>;
}

export interface QUBOResponse {
  n_qubits: number;
  budget_k: number;
  lambda: number;
  c_values: Record<string, number>;
  global_minimum_energy: number;
}

export interface SampleEntry {
  bitstring: string;
  probability: number;
  qubo_energy: number;
  n_stations: number;
  feasible: boolean;
  zones: string[];
}

export interface ClassicalResult {
  method: string;
  selected_zones: string[];
  objective_value: number;
  qubo_energy: number;
  feasible: boolean;
  n_stations: number;
  covered_demand_kwh_h: number;
  coverage_pct: number;
  runtime_s: number;
}

export interface QAOAResult {
  method: string;
  reps: number;
  seed: number;
  shots: number;
  selected_zones: string[];
  best_bitstring: string;
  qubo_energy: number;
  objective_value: number;
  feasible: boolean;
  n_stations: number;
  success_probability: number;
  circuit_depth: number;
  n_qubits: number;
  runtime_s: number;
  eigenvalue: number | null;
  optimal_parameters: number[];
  top10_samples: SampleEntry[];
  matches_qubo_optimum: boolean;
  energy_gap: number;
}

// ── Top-level response ───────────────────────────────────────────────────────

export interface OptimizeResponse {
  pipeline_runtime_s: number;
  demand_prediction: AIDemandResponse;
  qubo: QUBOResponse;
  classical: ClassicalResult;
  qaoa: QAOAResult;
  recommendation: RecommendationResponse;
}

// ── API error shape ──────────────────────────────────────────────────────────

export interface ApiError {
  detail: string;
}

// ── UI state ─────────────────────────────────────────────────────────────────

export type AsyncState<T> =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "success"; data: T }
  | { status: "error"; message: string };
