"""
backend/api/services/optimizer.py
===================================
Pipeline service: AI demand prediction → QUBO construction → QAOA solve.

This module is the single source of truth for pipeline execution inside the
API.  It reuses every existing function unchanged:

    ai_model.features            build_features(), chronological_split()
    quantum.qubo                 build_qubo(), QUBOProblem
    backend.optimization.classical_solver   PlacementProblem, solve_exhaustive(), solve_proximity_weighted(), covered_demand()

The QAOA helpers are inlined here (same logic as experiments/05 and 08) because
those experiment scripts are standalone CLIs, not importable modules.

Import-order constraint
-----------------------
qiskit_aer patches numpy C-extensions on import, which corrupts pandas/pyarrow
CSV/parquet I/O if imported first.  All pandas work (data loading, feature
engineering, QUBO CSV writing) is completed before any Qiskit symbol is
imported.  The Qiskit imports live inside _solve_qaoa(), which is always called
after the data work is done.

Module-level cache
------------------
Loading demand_hourly.parquet (~120 MB) and the RF pipeline (~327 MB) on every
request would be unacceptable.  _PipelineCache holds them after the first
request and reuses them for all subsequent calls.  The cache is populated lazily
(on first POST /optimize) so the server starts instantly.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ai_model.features import (
    FEATURE_COLS,
    build_features,
    chronological_split,
)
from quantum.qubo import build_qubo, QUBOProblem, objective_value as qubo_objective_value

log = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────
_ROOT         = Path(__file__).resolve().parents[3]   # project root
_PARQUET      = _ROOT / "data" / "processed" / "demand_hourly.parquet"
_ZONES_CSV    = _ROOT / "data" / "processed" / "candidate_zones.csv"
_ZONE_NAMES_JSON = _ROOT / "data" / "processed" / "zone_names.json"
_DIST_CSV     = _ROOT / "data" / "processed" / "candidate_distance_matrix.csv"
_PIPELINE_PKL = _ROOT / "ai_model" / "models" / "feature_pipeline.joblib"
_METRICS_JSON = _ROOT / "ai_model" / "models" / "metrics.json"

# ── Zone mapping ──────────────────────────────────────────────────────────────
_LABEL_TO_TAZID: dict[str, int] = {
    "Z0": 1026, "Z1": 746, "Z2": 716, "Z3": 965,
    "Z4": 706,  "Z5": 745, "Z6": 744, "Z7": 737,
}
_CANDIDATE_TAZIDS = list(_LABEL_TO_TAZID.values())

# ── Known QUBO ground truth (qubo_validation.json — 9/9 checks passed) ───────
# These are kept for reference, but the pipeline now computes the optimum dynamically for any K.
_QUBO_OPT_ZONES_K3  = ["Z0", "Z2", "Z3"]
_QUBO_OPT_ENERGY_K3 = -139.697448
_QUBO_OPT_BITS_K3   = "10110000"


# ─────────────────────────────────────────────────────────────────────────────
# Module-level cache
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class _PipelineCache:
    """Holds expensive-to-load artefacts across requests."""
    pipeline:      Any   = field(default=None)   # sklearn Pipeline
    demand_data:   pd.DataFrame = field(default=None)   # 8-zone parquet subset
    feature_frame: pd.DataFrame = field(default=None)   # build_features output
    test_frame:    pd.DataFrame = field(default=None)   # chronological test split
    # Pre-extracted numpy arrays — immune to PyArrow allocator corruption
    # that can occur after Qiskit C-extension imports on the 2nd+ request.
    X_test_np:          Any   = field(default=None)   # np.ndarray (n_samples, n_features)
    test_zone_ids:      Any   = field(default=None)   # np.ndarray of zone_id per row
    test_hours_np:      Any   = field(default=None)   # np.ndarray of hour per row
    test_is_weekend_np: Any   = field(default=None)   # np.ndarray of is_weekend per row
    test_split_start:   str   = field(default="")
    test_split_end:     str   = field(default="")
    model_metrics:      dict  = field(default_factory=dict)
    zones_df:           pd.DataFrame = field(default=None)   # candidate_zones.csv
    zone_names:         dict[str, dict] = field(default_factory=dict) # zone_names.json
    ready:              bool  = field(default=False)

    # QAOA cached objects to save setup time
    qaoa_seed:          int   = field(default=None)
    qaoa_shots:         int   = field(default=None)
    qiskit_backend:     Any   = field(default=None)
    qiskit_pm:          Any   = field(default=None)
    qiskit_sampler:     Any   = field(default=None)


_cache = _PipelineCache()


def warm_up() -> None:
    """
    Warm-up is intentionally a no-op on Render free tier.

    The full pipeline (parquet + feature engineering + model) requires ~390 MB
    at peak load, which leaves only ~120 MB headroom against the 512 MiB limit.
    Loading at startup AND serving the first request simultaneously would OOM.

    Instead the cache is populated lazily on the first POST /optimize request.
    The health endpoint (/api/v1/health) stays fast and memory-free.
    The first optimize call will be ~3–5 s slower (one-time cost).
    """
    if _cache.ready:
        return
    log.info(
        "warm_up() skipped — cache will load lazily on first /optimize request "
        "(memory-constrained deployment)."
    )


def _load_cache() -> None:
    """
    Populate _cache on first call.  NOT thread-safe for concurrent first-requests,
    but FastAPI workers are single-threaded per process and the worst case is
    a harmless double load.

    Memory-conscious load order (critical for 512 MiB Render free tier):
      1. Read parquet with zone filter   → peak +145 MB
      2. Build features, extract numpy arrays, then DELETE all DataFrames
      3. THEN load the joblib pipeline   → +100 MB (no longer competing)
      4. Load tiny CSVs / JSON           → negligible
    Total peak: ~390 MB, leaving ~120 MB headroom.
    """
    if _cache.ready:
        return

    import gc
    import joblib

    # ── Pre-flight: verify all required files exist ───────────────────────────
    missing: list[str] = []
    for path, label in [
        (_PIPELINE_PKL, "ai_model/models/feature_pipeline.joblib"),
        (_METRICS_JSON,  "ai_model/models/metrics.json"),
        (_PARQUET,       "data/processed/demand_hourly.parquet"),
        (_ZONES_CSV,     "data/processed/candidate_zones.csv"),
        (_DIST_CSV,      "data/processed/candidate_distance_matrix.csv"),
    ]:
        if not path.exists():
            missing.append(label)
    if missing:
        msg = (
            "QuantEV cache load failed — required files missing:\n"
            + "\n".join(f"  • {f}" for f in missing)
            + "\n\nRe-deploy to trigger build.sh which trains the model."
        )
        log.critical(msg)
        raise RuntimeError(msg)

    # ── Step 1: load parquet filtered to the 8 candidate zones only ──────────
    # Using filters= pushes the row filter into the parquet reader so the full
    # 1.19 M-row file is never materialised in Python memory.
    log.info("Loading demand_hourly.parquet (8 candidate zones, filtered read) …")
    try:
        df_all = pd.read_parquet(
            _PARQUET,
            filters=[("zone_id", "in", _CANDIDATE_TAZIDS)],
            dtype_backend="numpy_nullable",
        )
    except TypeError:
        # Older pandas: dtype_backend not supported
        df_all = pd.read_parquet(
            _PARQUET,
            filters=[("zone_id", "in", _CANDIDATE_TAZIDS)],
        )
    _cache.demand_data = df_all   # keep only if needed; freed below after extraction

    # ── Step 2: feature engineering ───────────────────────────────────────────
    log.info("Building feature matrix …")
    _cache.feature_frame = build_features(df_all)
    del df_all
    gc.collect()

    # ── Step 3: chronological split ───────────────────────────────────────────
    log.info("Applying chronological split …")
    _, _, test_frame_raw = chronological_split(_cache.feature_frame)

    # Materialise columns as concrete numpy/Python types (guards against
    # PyArrow-backed strings that break after Qiskit C-extension imports).
    test_frame_raw = test_frame_raw.copy()
    test_frame_raw.columns = [str(c) for c in test_frame_raw.columns]
    for col in test_frame_raw.columns:
        ser = test_frame_raw[col]
        if "arrow" in str(ser.dtype).lower() or hasattr(ser.dtype, "pyarrow_dtype"):
            try:
                test_frame_raw[col] = ser.to_numpy(dtype=object if ser.dtype == object else None)
            except Exception:
                test_frame_raw[col] = ser.astype(object)
    _cache.test_frame = test_frame_raw

    # ── Step 4: extract numpy arrays, then FREE all DataFrames ───────────────
    # This is the critical step: delete the large DataFrames BEFORE loading the
    # pipeline so their memory is available for the pipeline load.
    _cache.X_test_np          = _cache.test_frame[FEATURE_COLS].to_numpy(dtype=float)
    _cache.test_zone_ids      = _cache.test_frame["zone_id"].to_numpy()
    _cache.test_hours_np      = _cache.test_frame["hour"].to_numpy(dtype=int)
    _cache.test_is_weekend_np = _cache.test_frame["is_weekend"].to_numpy(dtype=int)
    _cache.test_split_start   = str(_cache.test_frame["time"].min())
    _cache.test_split_end     = str(_cache.test_frame["time"].max())

    log.info(
        "X_test_np shape=%s, zone_ids=%d unique",
        _cache.X_test_np.shape,
        len(set(_cache.test_zone_ids)),
    )

    # Free the large DataFrames now — they are no longer needed
    del _cache.demand_data, _cache.feature_frame, _cache.test_frame
    _cache.demand_data   = None
    _cache.feature_frame = None
    _cache.test_frame    = None
    gc.collect()
    log.info("DataFrames freed before pipeline load.")

    # ── Step 5: load the pipeline (now that DataFrames are freed) ────────────
    log.info("Loading feature_pipeline.joblib …")
    try:
        _cache.pipeline = joblib.load(_PIPELINE_PKL)
    except Exception as exc:
        import sys as _sys
        msg = (
            f"Failed to load pipeline artefact.\n"
            f"  Python  : {_sys.version.split()[0]}\n"
            f"  File    : {_PIPELINE_PKL}\n"
            f"  Error   : {type(exc).__name__}: {exc}\n"
            f"Likely cause: model was serialised with a different sklearn/numpy "
            f"version. Re-run build.sh to regenerate."
        )
        log.critical(msg)
        raise RuntimeError(msg) from exc

    # ── Step 6: lightweight artefacts ────────────────────────────────────────
    log.info("Loading model metrics …")
    _cache.model_metrics = json.loads(_METRICS_JSON.read_text())

    log.info("Loading candidate zones CSV …")
    _cache.zones_df = pd.read_csv(_ZONES_CSV)
    if _ZONE_NAMES_JSON.exists():
        _cache.zone_names = json.loads(_ZONE_NAMES_JSON.read_text(encoding="utf-8"))
    else:
        _cache.zone_names = {}

    _cache.ready = True
    log.info(
        "Cache ready — test split: %s → %s, %d rows, %d zones",
        _cache.test_split_start,
        _cache.test_split_end,
        len(_cache.X_test_np),
        len(set(_cache.test_zone_ids)),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Stage 1 — AI demand prediction (scenario-conditioned)
# ─────────────────────────────────────────────────────────────────────────────

VALID_SCENARIOS = {
    "all_hours",
    "morning_peak",
    "afternoon",
    "overnight",
    "weekday",
    "weekend",
}


def _predict_demand(scenario: str = "all_hours") -> tuple[dict[str, float], dict]:
    """
    Run the RF pipeline on the test split filtered by scenario and return
    per-zone mean predicted demand (kWh/h).

    Parameters
    ----------
    scenario : str
        One of 'all_hours', 'morning_peak', 'afternoon', 'overnight', 'weekday', 'weekend'.

    Returns
    -------
    demand_by_label  : {"Z0": 3741.33, "Z1": 236.74, ...}
    ai_meta          : diagnostics dict included in the API response
    """
    if scenario not in VALID_SCENARIOS:
        raise ValueError(f"Invalid scenario '{scenario}'. Must be one of {sorted(VALID_SCENARIOS)}")

    _load_cache()

    # Use pre-extracted numpy arrays
    X_test     = _cache.X_test_np
    zone_ids   = _cache.test_zone_ids
    hours      = _cache.test_hours_np
    is_weekend = _cache.test_is_weekend_np

    # Scenario filtering mask
    if scenario == "morning_peak":
        mask = np.isin(hours, [7, 8, 9, 10, 11])
    elif scenario == "afternoon":
        mask = np.isin(hours, [12, 13, 14, 15, 16, 17, 18])
    elif scenario == "overnight":
        mask = np.isin(hours, [0, 1, 2, 3, 4, 5, 6])
    elif scenario == "weekday":
        mask = (is_weekend == 0)
    elif scenario == "weekend":
        mask = (is_weekend == 1)
    else:  # "all_hours"
        mask = np.ones(len(X_test), dtype=bool)

    X_sub        = X_test[mask]
    zone_ids_sub = zone_ids[mask]

    t0      = time.perf_counter()
    y_pred  = _cache.pipeline.predict(X_sub)
    pred_ms = (time.perf_counter() - t0) * 1000

    # Aggregate per zone using the scenario-masked zone_id array
    demand_by_label: dict[str, float] = {}
    for lbl, tazid in _LABEL_TO_TAZID.items():
        z_mask = zone_ids_sub == tazid
        if z_mask.any():
            demand_by_label[lbl] = round(float(y_pred[z_mask].mean()), 4)
        else:
            demand_by_label[lbl] = 0.0

    ai_meta = {
        "model":             _cache.model_metrics.get("model", "RandomForestRegressor"),
        "scenario":          scenario,
        "test_r2":           _cache.model_metrics.get("test_metrics", {}).get("r2"),
        "test_mae":          _cache.model_metrics.get("test_metrics", {}).get("mae"),
        "test_split_start":  _cache.test_split_start,
        "test_split_end":    _cache.test_split_end,
        "prediction_time_ms": round(pred_ms, 2),
        "predicted_demand":  demand_by_label,
    }
    log.info("AI prediction (%s) done in %.1f ms", scenario, pred_ms)
    return demand_by_label, ai_meta


# ─────────────────────────────────────────────────────────────────────────────
# Stage 2 — QUBO construction
# ─────────────────────────────────────────────────────────────────────────────

def _build_qubo_from_predictions(demand_by_label: dict[str, float], station_count: int) -> QUBOProblem:
    """
    Build QUBO from live predictions by passing an in-memory DataFrame
    directly to build_qubo().  No temporary file is created.
    The distance matrix and all other columns are unchanged.
    """
    _load_cache()

    zones_df = _cache.zones_df.copy()
    for lbl, d in demand_by_label.items():
        zones_df.loc[zones_df["label"] == lbl, "mean_pred_kwh"] = d

    qubo = build_qubo(zones_csv=zones_df, dist_csv=_DIST_CSV, budget=station_count)

    log.info(
        "QUBO built: n=%d  K=%d  λ=%.1f",
        qubo.n, qubo.budget, qubo.lam
    )
    return qubo

def _get_qubo_global_minimum(qubo: QUBOProblem) -> tuple[str, float, list[str]]:
    """
    Compute the absolute global minimum of the QUBO by exhaustive evaluation over all 2^n states.
    For n=8, this is only 256 evaluations, which takes < 1 ms.
    """
    best_energy = float("inf")
    best_bits = None
    for val in range(2**qubo.n):
        bits = format(val, f"0{qubo.n}b")
        x = np.array([int(b) for b in bits], dtype=float)
        e = qubo.energy(x)
        if e < best_energy:
            best_energy = e
            best_bits = bits

    best_zones = [qubo.labels[j] for j, b in enumerate(best_bits) if b == "1"]
    return best_bits, best_energy, best_zones


# ─────────────────────────────────────────────────────────────────────────────
# Stage 3b — QAOA (Aer simulator, lazy Qiskit imports)
# ─────────────────────────────────────────────────────────────────────────────

def _build_qp(qubo: QUBOProblem):
    """Encode QUBOProblem.Q_upper as a Qiskit QuadraticProgram."""
    from qiskit_optimization.problems import QuadraticProgram
    qp = QuadraticProgram("ev_charger_placement_qubo")
    for j in range(qubo.n):
        qp.binary_var(f"x{j}")
    linear    = {f"x{j}": float(qubo.Q_upper[j, j]) for j in range(qubo.n)}
    quadratic = {
        (f"x{j}", f"x{k}"): float(qubo.Q_upper[j, k])
        for j in range(qubo.n)
        for k in range(j + 1, qubo.n)
        if qubo.Q_upper[j, k] != 0.0
    }
    qp.minimize(linear=linear, quadratic=quadratic)
    return qp


def _best_feasible(quasi_dist: Any, qubo: QUBOProblem) -> tuple[str, float]:
    dist = dict(quasi_dist) if not isinstance(quasi_dist, dict) else quasi_dist
    best_bits, best_e = "", float("inf")
    for state_int in dist:
        bits = format(state_int, f"0{qubo.n}b")[::-1]
        x    = qubo.bitstring_to_x(bits)
        if int(x.sum()) != qubo.budget:
            continue
        e = qubo.energy(x)
        if e < best_e:
            best_e, best_bits = e, bits
    return best_bits, best_e


def _success_prob(quasi_dist: Any, qubo: QUBOProblem, opt_bits: str) -> float:
    dist    = dict(quasi_dist) if not isinstance(quasi_dist, dict) else quasi_dist
    opt_int = int(opt_bits[::-1], 2)
    return round(float(dist.get(opt_int, 0.0)), 8)


def _top_samples(quasi_dist: Any, qubo: QUBOProblem, top_n: int = 10) -> list[dict]:
    dist = dict(quasi_dist) if not isinstance(quasi_dist, dict) else quasi_dist
    rows = []
    for state_int, prob in dist.items():
        bits = format(state_int, f"0{qubo.n}b")[::-1]
        x    = qubo.bitstring_to_x(bits)
        rows.append({
            "bitstring":   bits,
            "probability": round(float(prob), 8),
            "qubo_energy": round(float(qubo.energy(x)), 6),
            "n_stations":  int(x.sum()),
            "feasible":    int(x.sum()) == qubo.budget,
            "zones":       [qubo.labels[j] for j, b in enumerate(bits) if b == "1"],
        })
    rows.sort(key=lambda r: (-r["probability"], r["qubo_energy"]))
    return rows[:top_n]


def _solve_qaoa(qubo: QUBOProblem, reps: int, shots: int, seed: int, opt_bits: str, opt_energy: float, opt_zones: list[str]) -> dict:
    """
    Solve the QUBO with QAOA on the Aer local simulator.
    Qiskit symbols are imported HERE — after all pandas/parquet work is done —
    to respect the import-order constraint.
    """
    # ── Lazy Qiskit imports ───────────────────────────────────────────────────
    from qiskit_aer import AerSimulator
    from qiskit_aer.primitives import SamplerV2 as AerSamplerV2
    from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager
    from qiskit_optimization.minimum_eigensolvers import QAOA
    from qiskit_optimization.algorithms import MinimumEigenOptimizer
    from qiskit_optimization.optimizers import COBYLA

    qp      = _build_qp(qubo)
    
    # ── Reuse cached QAOA infrastructure ──────────────────────────────────────
    if _cache.qiskit_backend is None or _cache.qaoa_seed != seed or _cache.qaoa_shots != shots:
        _cache.qiskit_backend = AerSimulator(seed_simulator=seed)
        _cache.qiskit_pm      = generate_preset_pass_manager(optimization_level=1, backend=_cache.qiskit_backend)
        _cache.qiskit_sampler = AerSamplerV2(default_shots=shots, seed=seed)
        _cache.qaoa_seed      = seed
        _cache.qaoa_shots     = shots

    backend = _cache.qiskit_backend
    pm      = _cache.qiskit_pm
    sampler = _cache.qiskit_sampler

    initial_point = np.random.default_rng(seed).random(2 * reps)

    qaoa = QAOA(
        sampler=sampler,
        optimizer=COBYLA(maxiter=50, rhobeg=np.pi / 4, tol=1e-6),
        reps=reps,
        initial_point=initial_point,
        pass_manager=pm,
    )

    t0     = time.perf_counter()
    result = MinimumEigenOptimizer(min_eigen_solver=qaoa).solve(qp)
    rt     = time.perf_counter() - t0

    er = result.min_eigen_solver_result

    # Solver argmin
    solver_bits   = "".join(str(int(round(v))) for v in result.x)
    solver_energy = qubo.energy(qubo.bitstring_to_x(solver_bits))

    # Best feasible from full distribution
    feasible_bits, feasible_energy = _best_feasible(er.eigenstate, qubo)

    final_bits  = solver_bits  if solver_energy <= feasible_energy else feasible_bits
    final_energy = min(solver_energy, feasible_energy)

    final_x     = qubo.bitstring_to_x(final_bits)
    n_sel       = int(final_x.sum())
    selected    = [qubo.labels[j] for j, b in enumerate(final_bits) if b == "1"]
    depth       = er.optimal_circuit.depth() if er.optimal_circuit is not None else -1
    succ_prob   = _success_prob(er.eigenstate, qubo, opt_bits)
    top10       = _top_samples(er.eigenstate, qubo, top_n=10)

    log.info(
        "QAOA done: zones=%s  energy=%.4f  depth=%d  t=%.2fs",
        selected, final_energy, depth, rt,
    )

    return {
        "method":               "qaoa_aer_simulator",
        "reps":                 reps,
        "seed":                 seed,
        "shots":                shots,
        "selected_zones":       selected,
        "best_bitstring":       final_bits,
        "qubo_energy":          round(final_energy, 6),
        "objective_value":      round(float(qubo.c_values @ final_x), 6),
        "feasible":             n_sel == qubo.budget,
        "n_stations":           n_sel,
        "success_probability":  succ_prob,
        "circuit_depth":        depth,
        "n_qubits":             qubo.n,
        "runtime_s":            round(rt, 4),
        "eigenvalue":           round(float(np.real(er.eigenvalue)), 8)
                                if er.eigenvalue is not None else None,
        "optimal_parameters":   [round(float(v), 6) for v in er.optimal_point]
                                if er.optimal_point is not None else [],
        "top10_samples":        top10,
        "matches_qubo_optimum": sorted(selected) == sorted(opt_zones),
        "energy_gap":           round(final_energy - opt_energy, 6),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Public API — single entry point called by the router
# ─────────────────────────────────────────────────────────────────────────────

def run_pipeline(
    station_count: int = 3,
    scenario: str = "all_hours",
    reps:  int = 1,
    shots: int = 2048,
    seed:  int = 42,
) -> dict:
    """
    Execute the full AI → QUBO → QAOA pipeline and return a structured result.

    Parameters
    ----------
    station_count : number of stations to place
    scenario : demand scenario name (all_hours, morning_peak, afternoon, overnight, weekday, weekend)
    reps  : QAOA ansatz depth (p)
    shots : simulator shots per circuit evaluation
    seed  : random seed for AerSimulator + COBYLA

    Returns
    -------
    dict with keys:
        pipeline_runtime_s, demand_prediction, qubo, classical, qaoa,
        recommendation
    """
    t_total = time.perf_counter()

    # ── 1. AI demand prediction (scenario-conditioned) ────────────────────────
    log.info("Pipeline stage 1: AI demand prediction (scenario=%s)", scenario)
    demand_by_label, ai_meta = _predict_demand(scenario=scenario)

    # ── 2. QUBO ───────────────────────────────────────────────────────────────
    log.info("Pipeline stage 2: QUBO construction")
    qubo = _build_qubo_from_predictions(demand_by_label, station_count)

    opt_bits, opt_energy, opt_zones = _get_qubo_global_minimum(qubo)

    qubo_meta = {
        "n_qubits":     qubo.n,
        "budget_k":     qubo.budget,
        "lambda":       qubo.lam,
        "c_values":     {lbl: round(float(qubo.c_values[i]), 6)
                         for i, lbl in enumerate(qubo.labels)},
        "global_minimum_energy": round(opt_energy, 6),
    }

    # ── 3a. Classical solver ──────────────────────────────────────────────────
    log.info("Pipeline stage 3a: classical solver")
    from backend.optimization.classical_solver import solve_proximity_weighted
    classical = solve_proximity_weighted(qubo)

    # ── 3b. QAOA ──────────────────────────────────────────────────────────────
    log.info("Pipeline stage 3b: QAOA (reps=%d shots=%d seed=%d)", reps, shots, seed)
    qaoa = _solve_qaoa(
        qubo, reps=reps, shots=shots, seed=seed,
        opt_bits=opt_bits, opt_energy=opt_energy, opt_zones=opt_zones
    )

    # ── 4. Recommendation (QAOA preferred if feasible) ─────────────────────
    if qaoa["feasible"]:
        rec_zones  = qaoa["selected_zones"]
        rec_method = "qaoa_aer_simulator"
        rec_energy = qaoa["qubo_energy"]
    else:
        rec_zones  = classical["selected_zones"]
        rec_method = "classical_exhaustive"
        rec_energy = classical["qubo_energy"]

    total_demand = sum(demand_by_label.values())

    zones_df   = _cache.zones_df.set_index("label")
    zone_details = []
    for lbl in qubo.labels:
        row = zones_df.loc[lbl]
        names = _cache.zone_names.get(lbl, {})
        idx = qubo.labels.index(lbl)

        d_j = demand_by_label[lbl]
        c_j = float(qubo.c_values[idx])
        self_demand_score = d_j / 100.0
        proximity_spillover_score = c_j - self_demand_score
        coverage_neighbors_count = int(qubo.coverage_adj[idx].sum()) - 1

        zone_details.append({
            "label":           lbl,
            "tazid":           int(row["tazid"]),
            "name_primary":    names.get("primary"),
            "name_secondary":  names.get("secondary"),
            "longitude":       float(row["longitude"]),
            "latitude":        float(row["latitude"]),
            "predicted_demand_kwh_h": d_j,
            "qubo_c_value":    round(c_j, 6),
            "selected":        lbl in rec_zones,
            "self_demand_score": round(self_demand_score, 6),
            "proximity_spillover_score": round(proximity_spillover_score, 6),
            "coverage_neighbors_count": coverage_neighbors_count,
        })

    pipeline_runtime = round(time.perf_counter() - t_total, 3)
    log.info("Pipeline complete in %.2f s → %s (scenario=%s, K=%d)", pipeline_runtime, rec_zones, scenario, station_count)

    return {
        "pipeline_runtime_s": pipeline_runtime,
        "demand_prediction":  ai_meta,
        "qubo":               qubo_meta,
        "classical":          classical,
        "qaoa":               qaoa,
        "recommendation": {
            "selected_zones":               rec_zones,
            "scenario":                     scenario,
            "method":                       rec_method,
            "qubo_energy":                  rec_energy,
            "feasible":                     True,
            "n_stations":                   len(rec_zones),
            "matches_qubo_optimum":         sorted(rec_zones) == sorted(opt_zones),
            "predicted_demand":             {z: demand_by_label[z] for z in rec_zones},
            "total_candidate_demand_kwh_h": round(total_demand, 4),
            "zone_details":                 zone_details,
        },
    }
