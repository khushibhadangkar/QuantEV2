"""
backend/api/routers/optimize.py
================================
Optimization router.

Endpoints
---------
POST /api/v1/optimize   Run the full AI → QUBO → QAOA pipeline.
GET  /api/v1/status     Pipeline readiness probe (cache warm / cold).
"""

from __future__ import annotations

import logging
import traceback
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from backend.api.services import optimizer as svc

log = logging.getLogger(__name__)
router = APIRouter()

ScenarioType = Literal[
    "all_hours",
    "morning_peak",
    "afternoon",
    "overnight",
    "weekday",
    "weekend",
]


# ─────────────────────────────────────────────────────────────────────────────
# Request model
# ─────────────────────────────────────────────────────────────────────────────

class OptimizeRequest(BaseModel):
    """
    Parameters for the optimization run.  All fields are optional — omitting
    them applies the validated defaults from experiments/08.
    """
    station_count: int = Field(
        default=3,
        ge=1,
        le=8,
        description="Number of charging stations to place.",
    )
    scenario: ScenarioType = Field(
        default="all_hours",
        description="Planning demand scenario (all_hours, morning_peak, afternoon, overnight, weekday, weekend).",
    )
    reps: int = Field(
        default=1,
        ge=1,
        le=5,
        description="QAOA ansatz depth p (1–5).  Higher = deeper circuit, longer runtime.",
    )
    shots: int = Field(
        default=2048,
        ge=128,
        le=16384,
        description="Simulator shots per circuit evaluation (128–16384).",
    )
    seed: int = Field(
        default=42,
        ge=0,
        description="Random seed for AerSimulator + COBYLA (reproducibility).",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "station_count": 3,
                "scenario": "all_hours",
                "reps": 1,
                "shots": 2048,
                "seed": 42,
            }
        }
    }


# ─────────────────────────────────────────────────────────────────────────────
# Response models
# ─────────────────────────────────────────────────────────────────────────────

class ZoneDetail(BaseModel):
    label: str
    tazid: int
    name_primary: Optional[str] = None
    name_secondary: Optional[str] = None
    longitude: float
    latitude: float
    predicted_demand_kwh_h: float
    qubo_c_value: float
    selected: bool
    self_demand_score: float
    proximity_spillover_score: float
    coverage_neighbors_count: int

class RecommendationResponse(BaseModel):
    selected_zones: list[str]
    scenario: str = "all_hours"
    method: str
    qubo_energy: float
    feasible: bool
    n_stations: int
    matches_qubo_optimum: bool
    predicted_demand: dict[str, float]
    total_candidate_demand_kwh_h: float
    zone_details: list[ZoneDetail]


class AIDemandResponse(BaseModel):
    model: str
    scenario: str = "all_hours"
    test_r2: Optional[float]
    test_mae: Optional[float]
    test_split_start: str
    test_split_end: str
    prediction_time_ms: float
    predicted_demand: dict[str, float]


class QUBOResponse(BaseModel):
    n_qubits: int
    budget_k: int
    lambda_: float = Field(alias="lambda")
    c_values: dict[str, float]
    global_minimum_energy: float

    model_config = {"populate_by_name": True}


class SampleEntry(BaseModel):
    bitstring: str
    probability: float
    qubo_energy: float
    n_stations: int
    feasible: bool
    zones: list[str]


class ClassicalResult(BaseModel):
    method: str
    selected_zones: list[str]
    objective_value: float
    qubo_energy: float
    feasible: bool
    n_stations: int
    covered_demand_kwh_h: float
    coverage_pct: float
    runtime_s: float


class QAOAResult(BaseModel):
    method: str
    reps: int
    seed: int
    shots: int
    selected_zones: list[str]
    best_bitstring: str
    qubo_energy: float
    objective_value: float
    feasible: bool
    n_stations: int
    success_probability: float
    circuit_depth: int
    n_qubits: int
    runtime_s: float
    eigenvalue: Optional[float]
    optimal_parameters: list[float]
    top10_samples: list[SampleEntry]
    matches_qubo_optimum: bool
    energy_gap: float


class OptimizeResponse(BaseModel):
    pipeline_runtime_s: float
    demand_prediction: AIDemandResponse
    qubo: QUBOResponse
    classical: ClassicalResult
    qaoa: QAOAResult
    recommendation: RecommendationResponse


# ─────────────────────────────────────────────────────────────────────────────
# Status response
# ─────────────────────────────────────────────────────────────────────────────

class StatusResponse(BaseModel):
    status: str
    cache_ready: bool
    message: str


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/status",
    response_model=StatusResponse,
    summary="Pipeline status",
    description="Returns whether the pipeline cache (RF model + parquet data) is warm.",
)
async def pipeline_status() -> StatusResponse:
    ready = svc._cache.ready
    return StatusResponse(
        status="ok",
        cache_ready=ready,
        message=(
            "Pipeline cache is warm — next /optimize call will be fast."
            if ready else
            "Pipeline cache is cold — first /optimize call will load data (~5 s)."
        ),
    )


@router.post(
    "/optimize",
    response_model=OptimizeResponse,
    status_code=status.HTTP_200_OK,
    summary="Run AI + QAOA optimization",
    description=(
        "Execute the full QuantEV pipeline: AI demand prediction → QUBO "
        "construction → QAOA optimisation (Aer simulator, no IBM Quantum). "
        "Returns recommended EV charging zones, QUBO energy, and per-stage details."
    ),
)
async def run_optimize(request: OptimizeRequest) -> OptimizeResponse:
    """
    Run the end-to-end pipeline and return structured results.

    - **reps**: QAOA ansatz depth (default 1)
    - **shots**: simulator shots per evaluation (default 2048)
    - **seed**: random seed for reproducibility (default 42)
    """
    log.info(
        "POST /optimize  reps=%d  shots=%d  seed=%d",
        request.reps, request.shots, request.seed,
    )
    try:
        raw = svc.run_pipeline(
            station_count=request.station_count,
            scenario=request.scenario,
            reps=request.reps,
            shots=request.shots,
            seed=request.seed,
        )
    except Exception as exc:
        log.error("Pipeline failed: %s\n%s", exc, traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Optimization pipeline failed: {exc}",
        )

    # Remap "lambda" key (Python reserved word) to alias field
    qubo_raw = dict(raw["qubo"])
    qubo_raw["lambda"] = qubo_raw.pop("lambda", qubo_raw.get("lambda_", qubo_raw.get("lambda", 10.0)))

    return OptimizeResponse(
        pipeline_runtime_s=raw["pipeline_runtime_s"],
        demand_prediction=AIDemandResponse(**raw["demand_prediction"]),
        qubo=QUBOResponse(**{**raw["qubo"], "lambda": raw["qubo"]["lambda"]}),
        classical=ClassicalResult(**raw["classical"]),
        qaoa=QAOAResult(**raw["qaoa"]),
        recommendation=RecommendationResponse(**raw["recommendation"]),
    )
