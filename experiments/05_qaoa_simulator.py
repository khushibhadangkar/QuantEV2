"""
experiments/05_qaoa_simulator.py
=================================
Day 7 — QAOA on the Aer local simulator.

Problem
-------
Use the validated 8-qubit QUBO from backend/quantum/qubo.py to run QAOA on
the EV charger-placement problem (select K=3 zones out of 8 candidates).

QUBO recap (from qubo_validation.json / qubo_summary.txt):
  - n = 8 binary variables (qubits), one per candidate zone
  - Objective: maximise demand-weighted proximity  Σ_j c_j·x_j
  - Constraint: exactly K=3 stations  →  penalty λ·(Σ x_j − K)²,  λ=10
  - Known global minimum: {Z0, Z2, Z3},  E_QUBO = -139.697448
  - Feasibility gap (best feasible vs best infeasible): 4.7153 energy units

Approach
--------
  1. Rebuild the QUBO from processed CSVs (no modification to qubo.py).
  2. Encode it as a Qiskit QuadraticProgram using Q_upper directly.
  3. Run QAOA with reps ∈ {1, 2} using:
       - Sampler  : qiskit_aer.primitives.SamplerV2  (Aer local simulator)
       - Optimizer: COBYLA (gradient-free, reliable for small circuits)
       - shots    : 8192 per evaluation
  4. Collect the best bitstring from each run, evaluate against the QUBO,
     compare to the classical optimum, and pick the overall best.
  5. Save full results to experiments/results/qaoa_simulator_results.json.

Outputs saved
-------------
  experiments/results/qaoa_simulator_results.json
    {
      "metadata": { date, qiskit_version, aer_version, n_qubits, budget,
                    lambda, shots, classical_optimum_energy },
      "runs": [
        { "reps": int,
          "best_bitstring": str,          # e.g. "11001000" (qubit 0 = leftmost)
          "selected_zones": list[str],    # e.g. ["Z0", "Z2", "Z3"]
          "qubo_energy": float,
          "feasible": bool,
          "n_stations": int,
          "circuit_depth": int,
          "n_qubits": int,
          "runtime_s": float,
          "eigenvalue": float,
          "optimizer_evals": int,
          "optimal_parameters": list[float],
          "top10_samples": list[{bitstring, probability, qubo_energy}]
        }, ...
      ],
      "best_run": { ... same structure as one run entry ... },
      "validation": {
        "classical_optimum_zones": ["Z0", "Z2", "Z3"],
        "classical_optimum_energy": -139.697448,
        "qaoa_matches_classical": bool,
        "qaoa_energy": float,
        "energy_gap": float,          # qaoa_energy - classical_optimum_energy
        "energy_gap_pct": float,
        "all_runs_feasible": bool
      }
    }

Usage
-----
    python experiments/05_qaoa_simulator.py
    python experiments/05_qaoa_simulator.py --reps 1 2 3 --shots 4096
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
import qiskit
import qiskit_aer
from qiskit_aer import AerSimulator
from qiskit_aer.primitives import SamplerV2 as AerSamplerV2
from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager
from qiskit_optimization.minimum_eigensolvers import QAOA
from qiskit_optimization.algorithms import MinimumEigenOptimizer
from qiskit_optimization.optimizers import COBYLA
from qiskit_optimization.problems import QuadraticProgram

# ── Project paths ─────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from quantum.qubo import build_qubo, QUBOProblem

ZONES_CSV = PROJECT_ROOT / "data" / "processed" / "candidate_zones.csv"
DIST_CSV  = PROJECT_ROOT / "data" / "processed" / "candidate_distance_matrix.csv"
RESULTS_DIR = PROJECT_ROOT / "experiments" / "results"
OUTPUT_JSON = RESULTS_DIR / "qaoa_simulator_results.json"

# ── Known classical optimum (from qubo_validation.json, all 9/9 checks pass) ──
CLASSICAL_OPTIMUM_ZONES  = ["Z0", "Z2", "Z3"]
CLASSICAL_OPTIMUM_ENERGY = -139.697448   # H(x) for x = {Z0, Z2, Z3}
CLASSICAL_OPTIMUM_BITS   = "10110000"    # qubit-order: q0=Z0, q1=Z1, …, q7=Z7
                                          # Z0→1, Z1→0, Z2→1, Z3→1, Z4→0, …

# ── Default hyper-parameters ──────────────────────────────────────────────────
DEFAULT_REPS  = [1, 2]   # QAOA layers to try
DEFAULT_SHOTS = 8192     # samples per circuit evaluation


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def build_quadratic_program(qubo: QUBOProblem) -> QuadraticProgram:
    """
    Encode the QUBO as a Qiskit QuadraticProgram.

    We read directly from QUBOProblem.Q_upper (the validated upper-triangular
    matrix) to guarantee no drift from the source of truth.

    The QuadraticProgram minimises:
        H(x) = Σ_j Q_upper[j,j]·x_j  +  Σ_{j<k} Q_upper[j,k]·x_j·x_k

    which is exactly the QUBO Hamiltonian (constant λK² omitted — it shifts
    the energy uniformly and does not affect the minimum).
    """
    qp = QuadraticProgram(name="ev_charger_placement_qubo")

    # Declare binary variables x_0 … x_{n-1}
    for j in range(qubo.n):
        qp.binary_var(name=f"x{j}")   # x0 ↔ Z0, x1 ↔ Z1, …

    # Linear (diagonal) terms
    linear = {f"x{j}": float(qubo.Q_upper[j, j]) for j in range(qubo.n)}

    # Quadratic (off-diagonal) terms — upper-triangular only
    quadratic: dict[tuple[str, str], float] = {}
    for j in range(qubo.n):
        for k in range(j + 1, qubo.n):
            q_val = float(qubo.Q_upper[j, k])
            if q_val != 0.0:
                quadratic[(f"x{j}", f"x{k}")] = q_val

    qp.minimize(linear=linear, quadratic=quadratic)
    return qp


def bitstring_from_result(x_array: np.ndarray) -> str:
    """
    Convert the solver's x vector (length n, values 0.0/1.0) to a bitstring.
    Position 0 = Z0 = leftmost character.
    """
    return "".join(str(int(round(v))) for v in x_array)


def zones_from_bitstring(bitstring: str, labels: list[str]) -> list[str]:
    """Return zone labels for positions where the bitstring is '1'."""
    return [labels[j] for j, b in enumerate(bitstring) if b == "1"]


def top_samples(
    quasi_dist: Any,
    qubo: QUBOProblem,
    n: int = 10,
) -> list[dict]:
    """
    Extract the top-n most probable bitstrings from the quasi-probability
    distribution returned by the QAOA sampler, evaluate each against the QUBO,
    and return a sorted list of {bitstring, probability, qubo_energy, zones}.

    The quasi-distribution keys are integers; we convert each to an n-bit
    binary string in little-endian order (qubit 0 = bit 0 = leftmost character)
    to match QUBOProblem conventions.
    """
    num_qubits = qubo.n
    items: list[dict] = []

    # quasi_dist may be a QuasiDistribution or a dict-like
    dist_dict: dict[int, float] = dict(quasi_dist) if not isinstance(quasi_dist, dict) else quasi_dist

    for state_int, prob in dist_dict.items():
        # Convert integer to bitstring, qubit 0 is LSB (little-endian)
        bits = format(state_int, f"0{num_qubits}b")[::-1]   # reverse → q0 first
        x = qubo.bitstring_to_x(bits)
        energy = qubo.energy(x)
        n_selected = int(x.sum())
        items.append({
            "bitstring":  bits,
            "probability": float(prob),
            "qubo_energy": round(energy, 6),
            "n_stations":  n_selected,
            "feasible":    n_selected == qubo.budget,
            "zones":       zones_from_bitstring(bits, qubo.labels),
        })

    # Sort by probability descending, energy ascending as tiebreak
    items.sort(key=lambda d: (-d["probability"], d["qubo_energy"]))
    return items[:n]


def best_feasible_from_samples(
    quasi_dist: Any,
    qubo: QUBOProblem,
) -> tuple[str, float] | tuple[None, None]:
    """
    Return the lowest-energy feasible bitstring (k=3) from the full sample
    distribution, or (None, None) if no feasible sample exists.
    """
    num_qubits = qubo.n
    dist_dict: dict[int, float] = dict(quasi_dist) if not isinstance(quasi_dist, dict) else quasi_dist

    best_bits: str | None   = None
    best_energy: float       = float("inf")

    for state_int in dist_dict:
        bits = format(state_int, f"0{num_qubits}b")[::-1]
        x = qubo.bitstring_to_x(bits)
        if int(x.sum()) != qubo.budget:
            continue
        energy = qubo.energy(x)
        if energy < best_energy:
            best_energy = energy
            best_bits   = bits

    if best_bits is None:
        return None, None
    return best_bits, best_energy


# ─────────────────────────────────────────────────────────────────────────────
# Single QAOA run
# ─────────────────────────────────────────────────────────────────────────────

def run_qaoa_once(
    qp: QuadraticProgram,
    qubo: QUBOProblem,
    reps: int,
    shots: int,
    seed: int = 42,
) -> dict:
    """
    Execute one QAOA run with the given number of ansatz layers (reps).

    Uses:
      - AerSimulator as the backend (local simulation, no IBM Quantum)
      - SamplerV2 (Aer) for sampling
      - COBYLA optimizer (gradient-free, robust for QAOA p≤3)
      - generate_preset_pass_manager(optimization_level=1) for transpilation

    Returns a result dict with all fields needed for the JSON output.
    """
    print(f"\n{'─'*60}")
    print(f"  Running QAOA  reps={reps}  shots={shots}  seed={seed}")
    print(f"{'─'*60}")

    # ── Backend & sampler ────────────────────────────────────────────────────
    backend = AerSimulator(seed_simulator=seed)
    pm = generate_preset_pass_manager(optimization_level=1, backend=backend)

    sampler = AerSamplerV2(default_shots=shots, seed=seed)

    # ── QAOA ────────────────────────────────────────────────────────────────
    optimizer_obj = COBYLA(
        maxiter=500,   # generous for p=2
        rhobeg=np.pi / 4,
        tol=1e-6,
    )

    qaoa = QAOA(
        sampler=sampler,
        optimizer=optimizer_obj,
        reps=reps,
        pass_manager=pm,
    )

    solver = MinimumEigenOptimizer(min_eigen_solver=qaoa)

    t0 = time.perf_counter()
    result = solver.solve(qp)
    runtime_s = time.perf_counter() - t0

    # ── Extract information ──────────────────────────────────────────────────
    eigen_result = result.min_eigen_solver_result

    # Best bitstring from the solver's reported optimal point
    solver_bits = bitstring_from_result(result.x)
    solver_x    = qubo.bitstring_to_x(solver_bits)
    solver_energy = qubo.energy(solver_x)

    # Also scan full sample distribution for the best *feasible* bitstring
    # (the solver's argmin might occasionally be infeasible due to COBYLA
    #  landing near but not on a feasible minimum)
    feasible_bits, feasible_energy = best_feasible_from_samples(
        eigen_result.eigenstate, qubo
    )

    # Decide which bitstring to report: prefer the lowest-energy feasible one
    if feasible_bits is not None and feasible_energy <= solver_energy:
        final_bits   = feasible_bits
        final_energy = feasible_energy
    else:
        final_bits   = solver_bits
        final_energy = solver_energy

    final_x       = qubo.bitstring_to_x(final_bits)
    n_selected    = int(final_x.sum())
    is_feasible   = n_selected == qubo.budget
    selected      = zones_from_bitstring(final_bits, qubo.labels)

    # Circuit depth from the transpiled optimal circuit
    circuit_depth = (
        eigen_result.optimal_circuit.depth()
        if eigen_result.optimal_circuit is not None
        else -1
    )

    # Top-10 samples from the distribution
    top10 = top_samples(eigen_result.eigenstate, qubo, n=10)

    # Summary print
    status_sym = "✓" if is_feasible else "✗"
    match_sym  = "✓" if selected == CLASSICAL_OPTIMUM_ZONES else "✗"
    print(f"  Best bitstring  : {final_bits}  ({status_sym} feasible)")
    print(f"  Selected zones  : {selected}")
    print(f"  QUBO energy     : {final_energy:.6f}")
    print(f"  Classical optim : {CLASSICAL_OPTIMUM_ENERGY:.6f}  {match_sym} match")
    print(f"  Circuit depth   : {circuit_depth}")
    print(f"  Runtime         : {runtime_s:.2f} s")
    print(f"  Optimizer evals : {eigen_result.optimizer_evals}")

    return {
        "reps":               reps,
        "best_bitstring":     final_bits,
        "selected_zones":     selected,
        "qubo_energy":        round(final_energy, 6),
        "feasible":           is_feasible,
        "n_stations":         n_selected,
        "circuit_depth":      circuit_depth,
        "n_qubits":           qubo.n,
        "shots":              shots,
        "runtime_s":          round(runtime_s, 4),
        "eigenvalue":         float(np.real(eigen_result.eigenvalue))
                              if eigen_result.eigenvalue is not None else None,
        "optimizer_evals":    eigen_result.optimizer_evals,
        "optimal_parameters": [round(float(v), 6)
                                for v in eigen_result.optimal_point]
                               if eigen_result.optimal_point is not None else [],
        "top10_samples":      top10,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main(reps_list: list[int], shots: int, seed: int = 42) -> None:
    print("=" * 60)
    print("  EVision — Day 7: QAOA Simulator Experiment")
    print("=" * 60)
    print(f"  Qiskit version : {qiskit.__version__}")
    print(f"  Aer version    : {qiskit_aer.__version__}")
    print(f"  Backend        : AerSimulator (local, no IBM Quantum)")
    print(f"  Qubits         : 8  (Z0…Z7)")
    print(f"  Budget K       : 3")
    print(f"  Penalty λ      : 10.0")
    print(f"  QAOA reps      : {reps_list}")
    print(f"  Shots          : {shots}")
    print(f"  Classical opt  : {CLASSICAL_OPTIMUM_ZONES}  E={CLASSICAL_OPTIMUM_ENERGY}")

    # ── Build QUBO ───────────────────────────────────────────────────────────
    print("\n[1/4] Building QUBO from processed CSVs …")
    qubo = build_qubo(zones_csv=ZONES_CSV, dist_csv=DIST_CSV, budget=3)
    print(f"      n={qubo.n}  K={qubo.budget}  λ={qubo.lam}")

    # Cross-check: energy of the known winner
    x_opt = qubo.bitstring_to_x(CLASSICAL_OPTIMUM_BITS)
    e_opt = qubo.energy(x_opt)
    assert abs(e_opt - CLASSICAL_OPTIMUM_ENERGY) < 1e-3, (
        f"QUBO energy mismatch: got {e_opt:.6f}, expected {CLASSICAL_OPTIMUM_ENERGY}"
    )
    print(f"      QUBO cross-check passed: E({CLASSICAL_OPTIMUM_BITS}) = {e_opt:.6f}")

    # ── Build QuadraticProgram ───────────────────────────────────────────────
    print("\n[2/4] Encoding as Qiskit QuadraticProgram …")
    qp = build_quadratic_program(qubo)
    print(f"      Variables : {qp.get_num_vars()}")
    print(f"      Objective : {qp.objective.sense.name}")

    # ── Run QAOA for each reps value ─────────────────────────────────────────
    print(f"\n[3/4] Running QAOA (reps={reps_list}) …")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    runs: list[dict] = []

    for r in reps_list:
        run_result = run_qaoa_once(qp, qubo, reps=r, shots=shots, seed=seed)
        runs.append(run_result)

    # ── Pick best run ────────────────────────────────────────────────────────
    # Prefer feasible runs; among those, lowest QUBO energy
    feasible_runs = [rr for rr in runs if rr["feasible"]]
    candidate_runs = feasible_runs if feasible_runs else runs
    best_run = min(candidate_runs, key=lambda rr: rr["qubo_energy"])

    # ── Validation ───────────────────────────────────────────────────────────
    print(f"\n[4/4] Validation …")
    qaoa_energy      = best_run["qubo_energy"]
    qaoa_zones_sorted = sorted(best_run["selected_zones"])
    classical_sorted  = sorted(CLASSICAL_OPTIMUM_ZONES)
    matches_classical = qaoa_zones_sorted == classical_sorted
    energy_gap        = round(qaoa_energy - CLASSICAL_OPTIMUM_ENERGY, 6)
    energy_gap_pct    = (
        round(abs(energy_gap) / abs(CLASSICAL_OPTIMUM_ENERGY) * 100, 4)
        if CLASSICAL_OPTIMUM_ENERGY != 0 else 0.0
    )
    all_feasible = all(rr["feasible"] for rr in runs)

    validation = {
        "classical_optimum_zones":   CLASSICAL_OPTIMUM_ZONES,
        "classical_optimum_energy":  CLASSICAL_OPTIMUM_ENERGY,
        "qaoa_matches_classical":    matches_classical,
        "qaoa_zones":                best_run["selected_zones"],
        "qaoa_energy":               qaoa_energy,
        "energy_gap":                energy_gap,
        "energy_gap_pct":            energy_gap_pct,
        "all_runs_feasible":         all_feasible,
    }

    print(f"  QAOA best zones  : {best_run['selected_zones']}")
    print(f"  QAOA QUBO energy : {qaoa_energy}")
    print(f"  Classical energy : {CLASSICAL_OPTIMUM_ENERGY}")
    print(f"  Energy gap       : {energy_gap:+.6f} ({energy_gap_pct:.4f} %)")
    print(f"  Matches classical: {'YES ✓' if matches_classical else 'NO  ✗  (see notes)'}")
    print(f"  All runs feasible: {all_feasible}")

    if not matches_classical:
        print()
        print("  NOTE: QAOA did not recover the exact classical optimum.")
        print("  This is expected for QAOA p≤2 on a landscape with a small")
        print("  feasibility gap (4.72 energy units). The feasible energy gap")
        print("  to rank-2 (Z0+Z1+Z2) is only 0.19 units, well within the")
        print("  approximation error of shallow circuits.")
        print("  Try --reps 3 or higher for better convergence.")

    # ── Assemble and save JSON ───────────────────────────────────────────────
    output = {
        "metadata": {
            "date":                    datetime.now().isoformat(),
            "qiskit_version":          qiskit.__version__,
            "aer_version":             qiskit_aer.__version__,
            "backend":                 "AerSimulator (local)",
            "n_qubits":                qubo.n,
            "budget_k":                qubo.budget,
            "lambda":                  qubo.lam,
            "shots":                   shots,
            "reps_tested":             reps_list,
            "classical_optimum_zones": CLASSICAL_OPTIMUM_ZONES,
            "classical_optimum_energy": CLASSICAL_OPTIMUM_ENERGY,
            "zone_mapping": {
                qubo.labels[j]: {
                    "qubit_index": j,
                    "tazid":       int(qubo.demands[j])  # placeholder; real TAZID in CSV
                }
                for j in range(qubo.n)
            },
        },
        "runs":       runs,
        "best_run":   best_run,
        "validation": validation,
    }

    with open(OUTPUT_JSON, "w") as f:
        json.dump(output, f, indent=2, default=str)

    print(f"\n  Results saved → {OUTPUT_JSON.relative_to(PROJECT_ROOT)}")
    print()
    print("=" * 60)
    print("  DONE")
    print("=" * 60)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Day 7 — QAOA on Aer simulator for EV charger placement",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--reps",
        nargs="+",
        type=int,
        default=DEFAULT_REPS,
        metavar="P",
        help="QAOA ansatz depth (number of layers) to run; accepts multiple values",
    )
    parser.add_argument(
        "--shots",
        type=int,
        default=DEFAULT_SHOTS,
        help="Number of shots per circuit evaluation",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducibility",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    main(reps_list=args.reps, shots=args.shots, seed=args.seed)
