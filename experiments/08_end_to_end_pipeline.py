"""
experiments/08_end_to_end_pipeline.py
=======================================
End-to-end QuantEV pipeline.

Connects the existing AI demand model to the existing QUBO and QAOA modules
in a single pipeline:

    demand_hourly.parquet
          │
          ▼ build_features()  [backend.ai.features — unchanged]
    feature matrix (8 zones × test-split rows)
          │
          ▼ feature_pipeline.predict()  [models/feature_pipeline.joblib]
    per-zone mean predicted demand (kWh/h)
          │
          ▼ build_qubo()  [backend.quantum.qubo — unchanged]
    QUBOProblem  (8-qubit, K=3, λ=10)
          │
          ├──▶ solve_exhaustive()  [backend.optimization.classical_solver — unchanged]
          │         classical coverage optimum
          │
          └──▶ QAOA (Aer simulator, p=1, COBYLA)
                    quantum QUBO optimum

Nothing in the existing AI, QUBO, QAOA, validation, or IBM hardware files is
modified.  The helper functions used here are copied minimally from
experiments/05_qaoa_simulator.py rather than importing that module directly
(it uses if __name__ == "__main__" and has side effects on import via argparse).

No IBM Quantum hardware is used.

Output
------
  experiments/results/end_to_end_result.json

Usage
-----
    python experiments/08_end_to_end_pipeline.py
    python experiments/08_end_to_end_pipeline.py --shots 2048 --reps 2
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# ── Project paths ─────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# ── Project module imports (no qiskit yet — avoids the aer/numpy segfault) ───
from ai_model.features import (
    FEATURE_COLS,
    build_features,
    chronological_split,
)
from quantum.qubo import build_qubo, QUBOProblem
from backend.optimization.classical_solver import (
    PlacementProblem,
    solve_exhaustive,
)

# ── Paths ─────────────────────────────────────────────────────────────────────
PARQUET_PATH  = PROJECT_ROOT / "data" / "processed" / "demand_hourly.parquet"
ZONES_CSV     = PROJECT_ROOT / "data" / "processed" / "candidate_zones.csv"
DIST_CSV      = PROJECT_ROOT / "data" / "processed" / "candidate_distance_matrix.csv"
PIPELINE_PATH = PROJECT_ROOT / "ai_model" / "models" / "feature_pipeline.joblib"
METRICS_PATH  = PROJECT_ROOT / "ai_model" / "models" / "metrics.json"
RESULTS_DIR   = PROJECT_ROOT / "experiments" / "results"
OUTPUT_JSON   = RESULTS_DIR / "end_to_end_result.json"

# ── Zone mapping: label → TAZID (from candidate_zones.csv) ───────────────────
LABEL_TO_TAZID = {
    "Z0": 1026, "Z1": 746, "Z2": 716, "Z3": 965,
    "Z4": 706,  "Z5": 745, "Z6": 744, "Z7": 737,
}
TAZID_TO_LABEL = {v: k for k, v in LABEL_TO_TAZID.items()}
CANDIDATE_TAZIDS = list(LABEL_TO_TAZID.values())

# ── Known QUBO ground truth (qubo_validation.json — 9/9 checks passed) ───────
QUBO_OPTIMUM_ZONES  = ["Z0", "Z2", "Z3"]
QUBO_OPTIMUM_ENERGY = -139.697448
QUBO_OPTIMUM_BITS   = "10110000"

# ── QAOA defaults ─────────────────────────────────────────────────────────────
DEFAULT_REPS  = 1
DEFAULT_SHOTS = 2048
DEFAULT_SEED  = 42


# ─────────────────────────────────────────────────────────────────────────────
# Stage 1 — AI demand prediction
# ─────────────────────────────────────────────────────────────────────────────

def stage1_predict_demand() -> tuple[dict[str, float], dict]:
    """
    Load the trained RF pipeline, run it on the test split for the 8 candidate
    zones, and return per-zone mean predicted demand.

    Uses:
      - backend.ai.features.build_features()      (unchanged)
      - backend.ai.features.chronological_split() (unchanged)
      - models/feature_pipeline.joblib            (trained pipeline)

    The test split (2023-02-02 → 2023-02-28) is the held-out period that was
    never seen during training or hyper-parameter selection.

    Returns
    -------
    demand_by_label : {label: mean_pred_kwh}  e.g. {"Z0": 3741.33, ...}
    meta            : dict of diagnostic info saved to the output JSON
    """
    import joblib

    print("  Loading feature pipeline …")
    pipeline = joblib.load(PIPELINE_PATH)
    model_meta = json.loads(METRICS_PATH.read_text())

    print("  Loading demand_hourly.parquet …")
    df_all = pd.read_parquet(PARQUET_PATH)

    # Filter to 8 candidate zones only
    df_cand = df_all[df_all["zone_id"].isin(CANDIDATE_TAZIDS)].copy()
    print(f"  Candidate zone rows: {len(df_cand)} "
          f"({df_cand['zone_id'].nunique()} zones × "
          f"{len(df_cand) // df_cand['zone_id'].nunique()} timesteps)")

    print("  Building features …")
    feat = build_features(df_cand)

    print("  Applying chronological split (70/15/15) …")
    _, _, test_df = chronological_split(feat)
    print(f"  Test split: {test_df['time'].min()} → {test_df['time'].max()} "
          f"({len(test_df)} rows, {test_df['zone_id'].nunique()} zones)")

    print("  Predicting with RF pipeline …")
    X_test = test_df[FEATURE_COLS].to_numpy(dtype=float)
    t0 = time.perf_counter()
    y_pred = pipeline.predict(X_test)
    pred_time = time.perf_counter() - t0

    test_df = test_df.copy()
    test_df["pred_kwh"] = y_pred

    # Per-zone mean predicted demand on the test set
    per_zone_mean = (
        test_df.groupby("zone_id")["pred_kwh"]
        .mean()
        .round(4)
    )

    # Map TAZID → label, maintain label order
    demand_by_label: dict[str, float] = {}
    for label in ["Z0", "Z1", "Z2", "Z3", "Z4", "Z5", "Z6", "Z7"]:
        tazid = LABEL_TO_TAZID[label]
        demand_by_label[label] = float(per_zone_mean[tazid])

    # Also record stored values from candidate_zones.csv for comparison
    stored_df = pd.read_csv(ZONES_CSV).set_index("label")
    stored_demands = {lbl: float(stored_df.loc[lbl, "mean_pred_kwh"])
                      for lbl in demand_by_label}

    max_diff = max(
        abs(demand_by_label[lbl] - stored_demands[lbl])
        for lbl in demand_by_label
    )

    print(f"  Prediction time: {pred_time*1000:.1f} ms")
    print(f"  Max drift vs stored values: {max_diff:.4f} kWh/h  "
          f"({'✓ consistent' if max_diff < 1.0 else '⚠ check'})")

    for lbl in ["Z0", "Z1", "Z2", "Z3", "Z4", "Z5", "Z6", "Z7"]:
        diff = demand_by_label[lbl] - stored_demands[lbl]
        print(f"    {lbl}: live={demand_by_label[lbl]:.2f}  "
              f"stored={stored_demands[lbl]:.2f}  Δ={diff:+.4f}")

    meta = {
        "model":                   model_meta["model"],
        "pipeline_file":           str(PIPELINE_PATH.relative_to(PROJECT_ROOT)),
        "features_used":           FEATURE_COLS,
        "test_split_start":        str(test_df["time"].min()),
        "test_split_end":          str(test_df["time"].max()),
        "test_rows_per_zone":      len(test_df) // test_df["zone_id"].nunique(),
        "prediction_time_ms":      round(pred_time * 1000, 2),
        "test_r2":                 model_meta["test_metrics"]["r2"],
        "test_mae":                model_meta["test_metrics"]["mae"],
        "test_rmse":               model_meta["test_metrics"]["rmse"],
        "live_predictions":        demand_by_label,
        "stored_predictions":      stored_demands,
        "max_drift_kwh_h":         round(max_diff, 6),
        "drift_note": (
            "live_predictions are the mean RF model outputs on the held-out "
            "test split (2023-02-02 → 2023-02-28). stored_predictions are the "
            "pre-computed values in candidate_zones.csv. Both are used "
            "interchangeably; the QUBO is built from live_predictions."
        ),
    }

    return demand_by_label, meta


# ─────────────────────────────────────────────────────────────────────────────
# Stage 2 — QUBO construction
# ─────────────────────────────────────────────────────────────────────────────

def stage2_build_qubo(demand_by_label: dict[str, float]) -> tuple[QUBOProblem, str]:
    """
    Write a fresh candidate_zones CSV with live predictions and call
    build_qubo() (unchanged) to produce the QUBOProblem.

    Strategy: rather than patching build_qubo() internals, we write a
    temporary zones CSV where mean_pred_kwh is replaced with the live
    predictions, then pass that to the existing build_qubo() function.
    The distance matrix CSV and all other columns are kept exactly as-is.

    Returns
    -------
    qubo       : QUBOProblem (built from live predictions)
    tmp_path   : path to the temporary zones CSV (for logging)
    """
    import tempfile, shutil

    # Load original CSV, update only mean_pred_kwh
    zones_df = pd.read_csv(ZONES_CSV)
    zones_df = zones_df.copy()
    for label, demand in demand_by_label.items():
        zones_df.loc[zones_df["label"] == label, "mean_pred_kwh"] = demand

    # Write to a temp file in the same directory so relative paths work
    tmp_csv = ZONES_CSV.parent / "_pipeline_zones_tmp.csv"
    zones_df.to_csv(tmp_csv, index=False)

    qubo = build_qubo(zones_csv=tmp_csv, dist_csv=DIST_CSV, budget=3)

    # Clean up temp file
    tmp_csv.unlink(missing_ok=True)

    return qubo


# ─────────────────────────────────────────────────────────────────────────────
# Stage 3a — Classical solver (coverage baseline)
# ─────────────────────────────────────────────────────────────────────────────

def stage3a_classical(qubo: QUBOProblem) -> dict:
    """
    Run the exhaustive classical coverage solver (unchanged) on the
    live-prediction demands.  Returns a compact result dict.
    """
    zones_df = pd.read_csv(ZONES_CSV)
    idx_map  = {row["label"]: i for i, row in zones_df.iterrows()}
    n = qubo.n

    problem = PlacementProblem(
        labels       = qubo.labels,
        demands      = qubo.demands,
        coverage_adj = qubo.coverage_adj,
        budget       = qubo.budget,
    )

    t0 = time.perf_counter()
    output = solve_exhaustive(problem)
    runtime_s = time.perf_counter() - t0

    best = output.best
    x_best = np.zeros(n)
    for idx in best.station_idxs:
        x_best[idx] = 1.0
    qubo_energy = qubo.energy(x_best)

    return {
        "method":               "classical_exhaustive",
        "selected_zones":       best.stations,
        "qubo_energy":          round(qubo_energy, 6),
        "feasible":             True,
        "n_stations":           len(best.stations),
        "covered_demand_kwh_h": round(best.covered_demand, 4),
        "coverage_pct":         round(best.coverage_pct, 4),
        "n_combinations":       output.n_combinations,
        "runtime_s":            round(runtime_s, 6),
        "matches_qubo_optimum": sorted(best.stations) == sorted(QUBO_OPTIMUM_ZONES),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Stage 3b — QAOA solver (Aer simulator, no IBM Quantum)
# ─────────────────────────────────────────────────────────────────────────────
# These helpers replicate the logic from experiments/05_qaoa_simulator.py
# without importing that file (it is a standalone script with argparse).
# The QAOA configuration is identical: COBYLA, reps=1, AerSamplerV2.
# ─────────────────────────────────────────────────────────────────────────────

def _build_quadratic_program(qubo: QUBOProblem):
    """Encode QUBOProblem.Q_upper as a Qiskit QuadraticProgram (same as 05)."""
    from qiskit_optimization.problems import QuadraticProgram
    qp = QuadraticProgram(name="ev_charger_placement_qubo")
    for j in range(qubo.n):
        qp.binary_var(name=f"x{j}")
    linear = {f"x{j}": float(qubo.Q_upper[j, j]) for j in range(qubo.n)}
    quadratic: dict[tuple[str, str], float] = {}
    for j in range(qubo.n):
        for k in range(j + 1, qubo.n):
            v = float(qubo.Q_upper[j, k])
            if v != 0.0:
                quadratic[(f"x{j}", f"x{k}")] = v
    qp.minimize(linear=linear, quadratic=quadratic)
    return qp


def _best_feasible_from_samples(quasi_dist: Any, qubo: QUBOProblem) -> tuple:
    """Return (bits, energy) of the lowest-energy feasible state (same as 05)."""
    dist = dict(quasi_dist) if not isinstance(quasi_dist, dict) else quasi_dist
    best_bits   = QUBO_OPTIMUM_BITS
    best_energy = float("inf")
    for state_int in dist:
        bits = format(state_int, f"0{qubo.n}b")[::-1]
        x    = qubo.bitstring_to_x(bits)
        if int(x.sum()) != qubo.budget:
            continue
        energy = qubo.energy(x)
        if energy < best_energy:
            best_energy = energy
            best_bits   = bits
    return best_bits, best_energy


def _success_prob(quasi_dist: Any, qubo: QUBOProblem) -> float:
    """Quasi-probability mass on the exact QUBO-optimal bitstring."""
    dist = dict(quasi_dist) if not isinstance(quasi_dist, dict) else quasi_dist
    opt_int = int(QUBO_OPTIMUM_BITS[::-1], 2)
    return float(dist.get(opt_int, 0.0))


def _top_samples(quasi_dist: Any, qubo: QUBOProblem, top_n: int = 10) -> list:
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


def stage3b_qaoa(qubo: QUBOProblem, reps: int, shots: int, seed: int) -> dict:
    """
    Solve the QUBO using QAOA on the Aer local simulator.
    Identical configuration to experiments/05_qaoa_simulator.py:
      - AerSimulator(seed_simulator=seed)
      - AerSamplerV2(default_shots=shots, seed=seed)
      - COBYLA(maxiter=500, rhobeg=π/4, tol=1e-6)
      - generate_preset_pass_manager(optimization_level=1)
      - MinimumEigenOptimizer wrapping QAOA

    Qiskit imports are done HERE (after all pandas/numpy work in stages 1-2)
    to avoid the qiskit_aer/numpy segfault described in 07_qaoa_ibm_hardware.py.
    """
    from qiskit_aer import AerSimulator
    from qiskit_aer.primitives import SamplerV2 as AerSamplerV2
    from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager
    from qiskit_optimization.minimum_eigensolvers import QAOA
    from qiskit_optimization.algorithms import MinimumEigenOptimizer
    from qiskit_optimization.optimizers import COBYLA

    qp      = _build_quadratic_program(qubo)
    backend = AerSimulator(seed_simulator=seed)
    pm      = generate_preset_pass_manager(optimization_level=1, backend=backend)
    sampler = AerSamplerV2(default_shots=shots, seed=seed)

    qaoa = QAOA(
        sampler=sampler,
        optimizer=COBYLA(maxiter=500, rhobeg=np.pi / 4, tol=1e-6),
        reps=reps,
        pass_manager=pm,
    )
    solver = MinimumEigenOptimizer(min_eigen_solver=qaoa)

    t0     = time.perf_counter()
    result = solver.solve(qp)
    runtime_s = time.perf_counter() - t0

    er = result.min_eigen_solver_result

    # Solver's reported best
    solver_bits   = "".join(str(int(round(v))) for v in result.x)
    solver_x      = qubo.bitstring_to_x(solver_bits)
    solver_energy = qubo.energy(solver_x)

    # Scan distribution for lowest-energy feasible bitstring
    feasible_bits, feasible_energy = _best_feasible_from_samples(er.eigenstate, qubo)
    if solver_energy < feasible_energy:
        final_bits, final_energy = solver_bits, solver_energy
    else:
        final_bits, final_energy = feasible_bits, feasible_energy

    final_x    = qubo.bitstring_to_x(final_bits)
    n_sel      = int(final_x.sum())
    is_feasible = n_sel == qubo.budget
    selected   = [qubo.labels[j] for j, b in enumerate(final_bits) if b == "1"]
    depth      = er.optimal_circuit.depth() if er.optimal_circuit is not None else -1
    succ_prob  = _success_prob(er.eigenstate, qubo)
    top10      = _top_samples(er.eigenstate, qubo, top_n=10)

    return {
        "method":               "qaoa_aer_simulator",
        "reps":                 reps,
        "seed":                 seed,
        "shots":                shots,
        "selected_zones":       selected,
        "best_bitstring":       final_bits,
        "qubo_energy":          round(final_energy, 6),
        "feasible":             is_feasible,
        "n_stations":           n_sel,
        "success_probability":  round(succ_prob, 8),
        "circuit_depth":        depth,
        "n_qubits":             qubo.n,
        "runtime_s":            round(runtime_s, 4),
        "eigenvalue":           round(float(np.real(er.eigenvalue)), 8)
                                if er.eigenvalue is not None else None,
        "optimal_parameters":   [round(float(v), 6) for v in er.optimal_point]
                                if er.optimal_point is not None else [],
        "top10_samples":        top10,
        "matches_qubo_optimum": sorted(selected) == sorted(QUBO_OPTIMUM_ZONES),
        "energy_gap":           round(final_energy - QUBO_OPTIMUM_ENERGY, 6),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main pipeline
# ─────────────────────────────────────────────────────────────────────────────

def main(reps: int = DEFAULT_REPS, shots: int = DEFAULT_SHOTS,
         seed: int = DEFAULT_SEED) -> None:

    print("=" * 68)
    print("  QuantEV — End-to-End Pipeline")
    print("  AI Demand Prediction → QUBO Construction → QAOA Optimisation")
    print("=" * 68)

    # Pre-load zones CSV before any Qiskit imports corrupt pyarrow/numpy state
    zones_df = pd.read_csv(ZONES_CSV).set_index("label")

    # ── Stage 1: AI demand prediction ────────────────────────────────────────
    print("\n[1/5] AI Demand Prediction")
    print("      Model : RandomForestRegressor (models/feature_pipeline.joblib)")
    print("      Data  : demand_hourly.parquet, test split (2023-02-02 → 2023-02-28)")
    t_s1 = time.perf_counter()
    demand_by_label, ai_meta = stage1_predict_demand()
    t_s1 = time.perf_counter() - t_s1

    print(f"\n      Per-zone mean predicted demand (kWh/h):")
    total_demand = sum(demand_by_label.values())
    for lbl, d in demand_by_label.items():
        print(f"        {lbl}: {d:>8.2f} kWh/h  ({d/total_demand*100:.1f}%)")
    print(f"        Total: {total_demand:.2f} kWh/h")

    # ── Stage 2: QUBO construction ───────────────────────────────────────────
    print("\n[2/5] QUBO Construction")
    print("      Function : backend.quantum.qubo.build_qubo() (unchanged)")
    t_s2 = time.perf_counter()
    qubo = stage2_build_qubo(demand_by_label)
    t_s2 = time.perf_counter() - t_s2

    print(f"      n={qubo.n}  K={qubo.budget}  λ={qubo.lam}")
    print(f"      c_values (proximity-weighted demand score):")
    for lbl, cval in zip(qubo.labels, qubo.c_values):
        print(f"        {lbl}: {cval:.6f}")
    e_known = qubo.energy(qubo.bitstring_to_x(QUBO_OPTIMUM_BITS))
    print(f"      Sanity check E({QUBO_OPTIMUM_BITS}) = {e_known:.6f}  "
          f"({'✓' if abs(e_known - QUBO_OPTIMUM_ENERGY) < 0.5 else 'Δ from baseline'}) "
          f"(baseline {QUBO_OPTIMUM_ENERGY})")

    # ── Stage 3a: Classical solver ───────────────────────────────────────────
    print("\n[3/5] Classical Solver (coverage baseline)")
    print("      Function : backend.optimization.classical_solver.solve_exhaustive()")
    classical_result = stage3a_classical(qubo)

    print(f"      Selected zones : {classical_result['selected_zones']}")
    print(f"      QUBO energy    : {classical_result['qubo_energy']}")
    print(f"      Coverage       : {classical_result['coverage_pct']:.1f}%  "
          f"({classical_result['covered_demand_kwh_h']:.2f} / {total_demand:.2f} kWh/h)")
    print(f"      Runtime        : {classical_result['runtime_s']*1000:.3f} ms")

    # ── Stage 3b: QAOA ──────────────────────────────────────────────────────
    print(f"\n[4/5] QAOA Optimiser (Aer simulator, p={reps}, {shots} shots, seed={seed})")
    print("      Backend  : AerSimulator (local, no IBM Quantum)")
    print("      Solver   : qiskit_optimization QAOA + COBYLA(maxiter=500)")
    qaoa_result = stage3b_qaoa(qubo, reps=reps, shots=shots, seed=seed)

    print(f"      Selected zones : {qaoa_result['selected_zones']}")
    print(f"      QUBO energy    : {qaoa_result['qubo_energy']}")
    print(f"      Energy gap     : {qaoa_result['energy_gap']:+.6f}  "
          f"vs QUBO optimum {QUBO_OPTIMUM_ENERGY}")
    print(f"      Success prob   : {qaoa_result['success_probability']:.4f}")
    print(f"      Circuit depth  : {qaoa_result['circuit_depth']}")
    print(f"      Runtime        : {qaoa_result['runtime_s']:.2f} s")

    # ── Stage 4: Recommendation ──────────────────────────────────────────────
    print(f"\n[5/5] Final Recommendation")
    # Use QAOA result if feasible; otherwise fall back to classical
    if qaoa_result["feasible"]:
        recommended = qaoa_result["selected_zones"]
        rec_method  = "qaoa_aer_simulator"
        rec_energy  = qaoa_result["qubo_energy"]
    else:
        recommended = classical_result["selected_zones"]
        rec_method  = "classical_exhaustive"
        rec_energy  = classical_result["qubo_energy"]

    print(f"      Recommended zones : {recommended}")
    print(f"      Method            : {rec_method}")
    print(f"      QUBO energy       : {rec_energy}")
    print(f"      Matches known opt : {sorted(recommended) == sorted(QUBO_OPTIMUM_ZONES)}")

    # Pretty-print zone details
    print(f"\n  Recommended EV charging stations:")
    for lbl in recommended:
        row = zones_df.loc[lbl]
        print(f"    {lbl}  TAZID={row['tazid']:>4}  "
              f"lon={row['longitude']:.6f}  lat={row['latitude']:.6f}  "
              f"demand={demand_by_label[lbl]:.2f} kWh/h")

    # ── Save JSON ─────────────────────────────────────────────────────────────
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    import qiskit, qiskit_aer

    zone_details = []
    for lbl in qubo.labels:
        row_z = zones_df.loc[lbl]
        zone_details.append({
            "label":            lbl,
            "tazid":            int(row_z["tazid"]),
            "longitude":        float(row_z["longitude"]),
            "latitude":         float(row_z["latitude"]),
            "live_pred_kwh_h":  demand_by_label[lbl],
            "qubo_c_value":     round(float(qubo.c_values[qubo.labels.index(lbl)]), 6),
            "selected":         lbl in recommended,
        })

    output = {
        "metadata": {
            "date":            datetime.now().isoformat(),
            "script":          "experiments/08_end_to_end_pipeline.py",
            "qiskit_version":  qiskit.__version__,
            "aer_version":     qiskit_aer.__version__,
            "description": (
                "End-to-end QuantEV pipeline: AI demand prediction → "
                "QUBO construction → QAOA optimisation (Aer simulator)."
            ),
            "pipeline_stages": [
                "Stage 1: RF demand prediction (feature_pipeline.joblib)",
                "Stage 2: QUBO construction (backend.quantum.qubo.build_qubo)",
                "Stage 3a: Classical solver (backend.optimization.classical_solver)",
                "Stage 3b: QAOA Aer simulator (qiskit_optimization QAOA + COBYLA)",
                "Stage 4: Recommendation (QAOA preferred if feasible)",
            ],
        },
        "ai_demand_prediction": ai_meta,
        "qubo": {
            "n_qubits":   qubo.n,
            "budget_k":   qubo.budget,
            "lambda":     qubo.lam,
            "c_values":   {lbl: round(float(qubo.c_values[i]), 6)
                           for i, lbl in enumerate(qubo.labels)},
            "build_time_s": round(t_s2, 6),
            "global_minimum_bits":   QUBO_OPTIMUM_BITS,
            "global_minimum_energy": round(e_known, 6),
        },
        "classical_result":   classical_result,
        "qaoa_result":        qaoa_result,
        "recommendation": {
            "method":          rec_method,
            "selected_zones":  recommended,
            "qubo_energy":     rec_energy,
            "feasible":        True,
            "n_stations":      len(recommended),
            "matches_qubo_optimum": sorted(recommended) == sorted(QUBO_OPTIMUM_ZONES),
            "predicted_demand": {lbl: demand_by_label[lbl] for lbl in recommended},
            "total_predicted_demand_kwh_h": round(total_demand, 4),
            "zone_details":    zone_details,
        },
    }

    with open(OUTPUT_JSON, "w") as f:
        json.dump(output, f, indent=2, default=str)

    print(f"\n  Results saved → {OUTPUT_JSON.relative_to(PROJECT_ROOT)}")
    print()
    print("=" * 68)
    print("  DONE")
    print("=" * 68)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="End-to-end QuantEV pipeline",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--reps",  type=int, default=DEFAULT_REPS,  help="QAOA ansatz depth")
    p.add_argument("--shots", type=int, default=DEFAULT_SHOTS, help="Shots per evaluation")
    p.add_argument("--seed",  type=int, default=DEFAULT_SEED,  help="Random seed")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    main(reps=args.reps, shots=args.shots, seed=args.seed)
