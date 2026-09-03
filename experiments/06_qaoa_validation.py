"""
experiments/06_qaoa_validation.py
==================================
QAOA robustness validation across reps × seeds.

Runs QAOA for every combination of:
    reps  ∈ {1, 2, 3}          (QAOA ansatz depth / layers)
    seeds ∈ {42, 7, 21, 100}   (simulator + COBYLA random seed)

That gives 12 independent runs. For each run we record:
    - best_bitstring         the lowest-energy feasible bitstring found
    - selected_zones         zone labels (e.g. ["Z0","Z2","Z3"])
    - qubo_energy            H(x) for the best bitstring
    - success_probability    fraction of shots that sampled the global optimum
                             bitstring "10110000" (= Z0+Z2+Z3, E=-139.697448)
    - feasible               True if exactly 3 zones selected
    - circuit_depth          depth of the transpiled QAOA circuit
    - runtime_s              wall-clock time for solver.solve()
    - n_qubits               always 8
    - shots                  always 8192

Outputs
-------
    experiments/results/qaoa_validation.json        full results + per-run data
    experiments/results/qaoa_validation_summary.csv summary table, one row per run

QUBO source of truth (unchanged)
---------------------------------
    backend/quantum/qubo.py   — build_qubo()
    Classical optimum : {Z0, Z2, Z3},  E = -139.697448
    Feasibility gap   : 4.7153 energy units (best feasible vs best infeasible)

Usage
-----
    python experiments/06_qaoa_validation.py
    python experiments/06_qaoa_validation.py --shots 4096
"""

from __future__ import annotations

import argparse
import csv
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

ZONES_CSV   = PROJECT_ROOT / "data" / "processed" / "candidate_zones.csv"
DIST_CSV    = PROJECT_ROOT / "data" / "processed" / "candidate_distance_matrix.csv"
RESULTS_DIR = PROJECT_ROOT / "experiments" / "results"
OUTPUT_JSON = RESULTS_DIR / "qaoa_validation.json"
OUTPUT_CSV  = RESULTS_DIR / "qaoa_validation_summary.csv"

# ── Ground truth ──────────────────────────────────────────────────────────────
CLASSICAL_OPTIMUM_ZONES  = ["Z0", "Z2", "Z3"]
CLASSICAL_OPTIMUM_ENERGY = -139.697448
CLASSICAL_OPTIMUM_BITS   = "10110000"   # q0=Z0 leftmost

# ── Validation grid ───────────────────────────────────────────────────────────
DEFAULT_REPS_LIST  = [1, 2, 3]
DEFAULT_SEEDS_LIST = [42, 7, 21, 100]
DEFAULT_SHOTS      = 2048


# ─────────────────────────────────────────────────────────────────────────────
# QUBO → QuadraticProgram  (identical to 05_qaoa_simulator.py — no changes)
# ─────────────────────────────────────────────────────────────────────────────

def build_quadratic_program(qubo: QUBOProblem) -> QuadraticProgram:
    """Encode QUBOProblem.Q_upper as a Qiskit QuadraticProgram."""
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


# ─────────────────────────────────────────────────────────────────────────────
# Distribution helpers
# ─────────────────────────────────────────────────────────────────────────────

def _as_dict(quasi_dist: Any) -> dict[int, float]:
    return dict(quasi_dist) if not isinstance(quasi_dist, dict) else quasi_dist


def success_probability(quasi_dist: Any, optimal_bits: str) -> float:
    """
    Fraction of shots (quasi-probability mass) on the global optimum bitstring.

    The optimal bitstring is "10110000" in qubit-0-first (little-endian) order.
    We convert it to the integer key used by the quasi-distribution.
    """
    # Convert bitstring (q0=lsb) → integer key
    optimal_int = int(optimal_bits[::-1], 2)   # reverse → MSB-first then parse
    dist = _as_dict(quasi_dist)
    return float(dist.get(optimal_int, 0.0))


def best_feasible(quasi_dist: Any, qubo: QUBOProblem) -> tuple[str, float, float]:
    """
    Scan the full distribution for the lowest-energy feasible (k=3) bitstring.

    Returns (bitstring, qubo_energy, probability_of_that_bitstring).
    Falls back to the highest-probability feasible state if all energies tie.
    """
    dist = _as_dict(quasi_dist)
    n = qubo.n
    best_bits   = CLASSICAL_OPTIMUM_BITS   # fallback
    best_energy = float("inf")
    best_prob   = 0.0

    for state_int, prob in dist.items():
        bits = format(state_int, f"0{n}b")[::-1]   # little-endian → q0 first
        x = qubo.bitstring_to_x(bits)
        if int(x.sum()) != qubo.budget:
            continue
        energy = qubo.energy(x)
        if energy < best_energy or (energy == best_energy and prob > best_prob):
            best_energy = energy
            best_bits   = bits
            best_prob   = prob

    return best_bits, best_energy, best_prob


def zones_from_bits(bits: str, labels: list[str]) -> list[str]:
    return [labels[j] for j, b in enumerate(bits) if b == "1"]


def top_samples(quasi_dist: Any, qubo: QUBOProblem, top_n: int = 10) -> list[dict]:
    dist = _as_dict(quasi_dist)
    n = qubo.n
    rows = []
    for state_int, prob in dist.items():
        bits = format(state_int, f"0{n}b")[::-1]
        x    = qubo.bitstring_to_x(bits)
        rows.append({
            "bitstring":  bits,
            "probability": round(float(prob), 8),
            "qubo_energy": round(float(qubo.energy(x)), 6),
            "n_stations":  int(x.sum()),
            "feasible":    int(x.sum()) == qubo.budget,
            "zones":       zones_from_bits(bits, qubo.labels),
        })
    rows.sort(key=lambda r: (-r["probability"], r["qubo_energy"]))
    return rows[:top_n]


# ─────────────────────────────────────────────────────────────────────────────
# Single run
# ─────────────────────────────────────────────────────────────────────────────

def run_one(
    qp:    QuadraticProgram,
    qubo:  QUBOProblem,
    reps:  int,
    seed:  int,
    shots: int,
) -> dict:
    """
    Execute one QAOA run (reps, seed) and return a fully populated result dict.

    Backend   : AerSimulator(seed_simulator=seed)  — local only, no IBM Quantum
    Sampler   : AerSamplerV2(default_shots=shots, seed=seed)
    Optimizer : COBYLA(maxiter=500, rhobeg=π/4, tol=1e-6)
    Transpiler: generate_preset_pass_manager(optimization_level=1, backend=backend)
    """
    backend = AerSimulator(seed_simulator=seed)
    pm      = generate_preset_pass_manager(optimization_level=1, backend=backend)
    sampler = AerSamplerV2(default_shots=shots, seed=seed)

    qaoa = QAOA(
        sampler=sampler,
        optimizer=COBYLA(maxiter=50, rhobeg=np.pi / 4, tol=1e-6),
        reps=reps,
        pass_manager=pm,
    )
    solver = MinimumEigenOptimizer(min_eigen_solver=qaoa)

    t0 = time.perf_counter()
    result = solver.solve(qp)
    runtime_s = time.perf_counter() - t0

    er = result.min_eigen_solver_result   # SamplingVQEResult

    # ── Best feasible bitstring ───────────────────────────────────────────────
    # We always scan the full distribution rather than trusting result.x,
    # because COBYLA can occasionally return an infeasible argmin when the
    # landscape is flat near the boundary.
    best_bits, best_energy, _ = best_feasible(er.eigenstate, qubo)

    # Cross-check against solver's own answer; take the lower energy
    solver_bits   = "".join(str(int(round(v))) for v in result.x)
    solver_x      = qubo.bitstring_to_x(solver_bits)
    solver_energy = qubo.energy(solver_x)
    if solver_energy < best_energy:
        best_bits   = solver_bits
        best_energy = solver_energy

    x_best     = qubo.bitstring_to_x(best_bits)
    n_sel      = int(x_best.sum())
    is_feasible = n_sel == qubo.budget
    selected   = zones_from_bits(best_bits, qubo.labels)

    # ── Success probability ───────────────────────────────────────────────────
    # = quasi-probability mass on the exact global optimum bitstring
    succ_prob = success_probability(er.eigenstate, CLASSICAL_OPTIMUM_BITS)

    # ── Circuit depth ─────────────────────────────────────────────────────────
    depth = er.optimal_circuit.depth() if er.optimal_circuit is not None else -1

    # ── Matches ground truth? ─────────────────────────────────────────────────
    matches = sorted(selected) == sorted(CLASSICAL_OPTIMUM_ZONES)
    energy_gap = round(best_energy - CLASSICAL_OPTIMUM_ENERGY, 6)

    status = "✓" if matches else ("~" if is_feasible else "✗")
    print(
        f"  reps={reps} seed={seed:>3} | {best_bits} | "
        f"zones={selected} | E={best_energy:>12.6f} | "
        f"p_opt={succ_prob:.4f} | depth={depth} | {runtime_s:.2f}s  [{status}]"
    )

    return {
        "reps":                reps,
        "seed":                seed,
        "best_bitstring":      best_bits,
        "selected_zones":      selected,
        "qubo_energy":         round(best_energy, 6),
        "energy_gap":          energy_gap,
        "feasible":            is_feasible,
        "n_stations":          n_sel,
        "matches_classical":   matches,
        "success_probability": round(succ_prob, 8),
        "circuit_depth":       depth,
        "n_qubits":            qubo.n,
        "shots":               shots,
        "runtime_s":           round(runtime_s, 4),
        "eigenvalue":          round(float(np.real(er.eigenvalue)), 8)
                               if er.eigenvalue is not None else None,
        "optimizer_evals":     er.optimizer_evals,
        "optimal_parameters":  [round(float(v), 6) for v in er.optimal_point]
                               if er.optimal_point is not None else [],
        "top10_samples":       top_samples(er.eigenstate, qubo, top_n=10),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Summary statistics helpers
# ─────────────────────────────────────────────────────────────────────────────

def per_reps_stats(runs: list[dict]) -> dict[int, dict]:
    """Aggregate success rate, mean energy gap, etc. grouped by reps."""
    from collections import defaultdict
    groups: dict[int, list[dict]] = defaultdict(list)
    for r in runs:
        groups[r["reps"]].append(r)

    stats = {}
    for reps, group in sorted(groups.items()):
        n = len(group)
        n_match    = sum(1 for r in group if r["matches_classical"])
        n_feasible = sum(1 for r in group if r["feasible"])
        mean_succ  = sum(r["success_probability"] for r in group) / n
        mean_gap   = sum(r["energy_gap"] for r in group) / n
        mean_depth = sum(r["circuit_depth"] for r in group) / n
        mean_rt    = sum(r["runtime_s"] for r in group) / n
        stats[reps] = {
            "n_runs":              n,
            "n_classical_match":   n_match,
            "match_rate":          round(n_match / n, 4),
            "n_feasible":          n_feasible,
            "feasibility_rate":    round(n_feasible / n, 4),
            "mean_success_prob":   round(mean_succ, 6),
            "mean_energy_gap":     round(mean_gap, 6),
            "mean_circuit_depth":  round(mean_depth, 2),
            "mean_runtime_s":      round(mean_rt, 4),
        }
    return stats


# ─────────────────────────────────────────────────────────────────────────────
# CSV writer
# ─────────────────────────────────────────────────────────────────────────────

CSV_FIELDS = [
    "reps",
    "seed",
    "best_bitstring",
    "selected_zones",
    "qubo_energy",
    "energy_gap",
    "feasible",
    "matches_classical",
    "success_probability",
    "circuit_depth",
    "n_qubits",
    "shots",
    "runtime_s",
    "eigenvalue",
    "optimizer_evals",
    "optimal_parameters",
]


def write_csv(runs: list[dict], path: Path) -> None:
    with open(path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for r in runs:
            row = dict(r)
            # Flatten lists to readable strings for CSV
            row["selected_zones"]     = "|".join(r["selected_zones"])
            row["optimal_parameters"] = "|".join(f"{v:.6f}" for v in r["optimal_parameters"])
            writer.writerow(row)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main(reps_list: list[int], seeds: list[int], shots: int) -> None:
    n_runs = len(reps_list) * len(seeds)

    print("=" * 72)
    print("  EVision — QAOA Robustness Validation")
    print("=" * 72)
    print(f"  Qiskit        : {qiskit.__version__}")
    print(f"  Aer           : {qiskit_aer.__version__}")
    print(f"  Backend       : AerSimulator (local)  — no IBM Quantum")
    print(f"  Qubits        : 8  (Z0…Z7)")
    print(f"  Budget K      : 3,  penalty λ = 10.0")
    print(f"  QAOA reps     : {reps_list}")
    print(f"  Seeds         : {seeds}")
    print(f"  Shots/run     : {shots}")
    print(f"  Total runs    : {n_runs}  ({len(reps_list)} reps × {len(seeds)} seeds)")
    print(f"  Ground truth  : {CLASSICAL_OPTIMUM_ZONES}  E={CLASSICAL_OPTIMUM_ENERGY}")
    print("=" * 72)

    # ── Build QUBO once ──────────────────────────────────────────────────────
    print("\n[1/4] Building QUBO …")
    qubo = build_qubo(zones_csv=ZONES_CSV, dist_csv=DIST_CSV, budget=3)
    x_opt  = qubo.bitstring_to_x(CLASSICAL_OPTIMUM_BITS)
    e_check = qubo.energy(x_opt)
    assert abs(e_check - CLASSICAL_OPTIMUM_ENERGY) < 1e-3, (
        f"QUBO energy sanity check failed: {e_check:.6f}"
    )
    print(f"      n={qubo.n}  K={qubo.budget}  λ={qubo.lam}")
    print(f"      Sanity check: E(10110000) = {e_check:.6f}  ✓")

    # ── Build QuadraticProgram once ──────────────────────────────────────────
    print("\n[2/4] Encoding QuadraticProgram …")
    qp = build_quadratic_program(qubo)
    print(f"      {qp.get_num_vars()} binary variables, objective={qp.objective.sense.name}")

    # ── Execute all runs ─────────────────────────────────────────────────────
    print(f"\n[3/4] Running {n_runs} QAOA configurations …")
    print(f"  {'reps':>4} {'seed':>4} | {'bitstring':>8} | {'zones':<20} | "
          f"{'energy':>12} | {'p_opt':>6} | {'depth':>5} | {'time':>5}  [match]")
    print(f"  {'-'*4} {'-'*4}-+-{'-'*8}-+-{'-'*20}-+"
          f"-{'-'*12}-+-{'-'*6}-+-{'-'*5}-+-{'-'*5}")

    all_runs: list[dict] = []
    run_idx = 0
    for reps in reps_list:
        for seed in seeds:
            run_idx += 1
            print(f"  [{run_idx:>2}/{n_runs}]", end="  ")
            result = run_one(qp, qubo, reps=reps, seed=seed, shots=shots)
            all_runs.append(result)

    # ── Aggregate statistics ─────────────────────────────────────────────────
    print(f"\n[4/4] Computing statistics and saving …")
    stats_by_reps = per_reps_stats(all_runs)

    total_match    = sum(1 for r in all_runs if r["matches_classical"])
    total_feasible = sum(1 for r in all_runs if r["feasible"])
    overall_match_rate     = round(total_match    / n_runs, 4)
    overall_feasible_rate  = round(total_feasible / n_runs, 4)
    overall_mean_succ_prob = round(
        sum(r["success_probability"] for r in all_runs) / n_runs, 6
    )
    best_overall = min(
        (r for r in all_runs if r["feasible"]),
        key=lambda r: r["qubo_energy"],
        default=min(all_runs, key=lambda r: r["qubo_energy"]),
    )

    # ── Print summary table ──────────────────────────────────────────────────
    print()
    print("  ┌─────────────────────────────────────────────────────────────────┐")
    print("  │  Summary by QAOA depth (p)                                      │")
    print("  ├────────┬──────────────┬──────────────┬─────────────┬────────────┤")
    print("  │  reps  │  match_rate  │ feasib_rate  │ mean_p_opt  │ mean_depth │")
    print("  ├────────┼──────────────┼──────────────┼─────────────┼────────────┤")
    for reps, s in stats_by_reps.items():
        print(
            f"  │  p={reps}   │  {s['match_rate']:.2f} ({s['n_classical_match']}/{s['n_runs']})  "
            f"│  {s['feasibility_rate']:.2f} ({s['n_feasible']}/{s['n_runs']})  "
            f"│  {s['mean_success_prob']:.4f}     "
            f"│  {s['mean_circuit_depth']:>6.1f}    │"
        )
    print("  ├────────┴──────────────┴──────────────┴─────────────┴────────────┤")
    print(f"  │  Overall  match={overall_match_rate:.2f} ({total_match}/{n_runs})"
          f"  feasible={overall_feasible_rate:.2f} ({total_feasible}/{n_runs})"
          f"  p_opt={overall_mean_succ_prob:.4f}  │")
    print("  └─────────────────────────────────────────────────────────────────┘")
    print()
    print(f"  Best run overall : reps={best_overall['reps']}  seed={best_overall['seed']}")
    print(f"    Bitstring       : {best_overall['best_bitstring']}")
    print(f"    Zones           : {best_overall['selected_zones']}")
    print(f"    QUBO energy     : {best_overall['qubo_energy']}")
    print(f"    Energy gap      : {best_overall['energy_gap']:+.6f}")
    print(f"    Success prob    : {best_overall['success_probability']:.4f}")
    print(f"    Circuit depth   : {best_overall['circuit_depth']}")

    # ── Assemble JSON ────────────────────────────────────────────────────────
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    output_json = {
        "metadata": {
            "date":                     datetime.now().isoformat(),
            "script":                   "experiments/06_qaoa_validation.py",
            "qiskit_version":           qiskit.__version__,
            "aer_version":              qiskit_aer.__version__,
            "backend":                  "AerSimulator (local, no IBM Quantum)",
            "n_qubits":                 qubo.n,
            "budget_k":                 qubo.budget,
            "lambda":                   qubo.lam,
            "shots":                    shots,
            "reps_tested":              reps_list,
            "seeds_tested":             seeds,
            "n_total_runs":             n_runs,
            "classical_optimum_zones":  CLASSICAL_OPTIMUM_ZONES,
            "classical_optimum_energy": CLASSICAL_OPTIMUM_ENERGY,
            "classical_optimum_bits":   CLASSICAL_OPTIMUM_BITS,
            "zone_qubit_mapping":       {qubo.labels[j]: j for j in range(qubo.n)},
        },
        "runs": all_runs,
        "best_run": best_overall,
        "summary": {
            "overall": {
                "n_runs":                n_runs,
                "n_classical_match":     total_match,
                "match_rate":            overall_match_rate,
                "n_feasible":            total_feasible,
                "feasibility_rate":      overall_feasible_rate,
                "mean_success_prob":     overall_mean_succ_prob,
                "best_qubo_energy":      best_overall["qubo_energy"],
                "best_energy_gap":       best_overall["energy_gap"],
            },
            "by_reps": stats_by_reps,
        },
        "validation": {
            "classical_optimum_zones":   CLASSICAL_OPTIMUM_ZONES,
            "classical_optimum_energy":  CLASSICAL_OPTIMUM_ENERGY,
            "qaoa_ever_matches":         total_match > 0,
            "qaoa_always_matches":       total_match == n_runs,
            "qaoa_always_feasible":      total_feasible == n_runs,
            "best_energy_gap_to_opt":    best_overall["energy_gap"],
            "notes": (
                "success_probability = fraction of shots landing on the exact "
                "global optimum bitstring 10110000 (Z0+Z2+Z3, E=-139.697448). "
                "energy_gap = run_energy - classical_optimum_energy; "
                "0.0 means exact match."
            ),
        },
    }

    with open(OUTPUT_JSON, "w") as f:
        json.dump(output_json, f, indent=2, default=str)

    # ── Write CSV ────────────────────────────────────────────────────────────
    write_csv(all_runs, OUTPUT_CSV)

    print()
    print(f"  Saved: {OUTPUT_JSON.relative_to(PROJECT_ROOT)}")
    print(f"  Saved: {OUTPUT_CSV.relative_to(PROJECT_ROOT)}")
    print()
    print("=" * 72)
    print("  DONE")
    print("=" * 72)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="QAOA robustness validation — reps × seeds grid",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--reps",
        nargs="+",
        type=int,
        default=DEFAULT_REPS_LIST,
        metavar="P",
        help="QAOA ansatz depths to evaluate (space-separated)",
    )
    parser.add_argument(
        "--seeds",
        nargs="+",
        type=int,
        default=DEFAULT_SEEDS_LIST,
        metavar="S",
        help="Random seeds to evaluate (space-separated)",
    )
    parser.add_argument(
        "--shots",
        type=int,
        default=DEFAULT_SHOTS,
        help="Shots per circuit evaluation",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    main(reps_list=args.reps, seeds=args.seeds, shots=args.shots)
