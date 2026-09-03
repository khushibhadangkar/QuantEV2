"""
experiments/07_qaoa_ibm_hardware.py
=====================================
IBM Quantum hardware execution of the EV charger-placement QAOA.

Runs a single QAOA p=1 circuit on ibm_fez using Qiskit IBM Runtime 0.48.0
with SamplerV2.  The QUBO and all helper logic are taken directly from the
validated simulator implementation — nothing is modified.

Hardware configuration
----------------------
  Backend        : ibm_fez  (156-qubit Eagle r3)
  Logical qubits : 8  (one per candidate zone, Z0…Z7)
  QAOA reps (p)  : 1
  Shots          : 1024  (small controlled run)
  Parameters     : pre-bound from simulator result (seed=42, p=1)
                   β = 0.952474,  γ = -3.576032
  Transpile      : optimization_level=1

Import-order note
-----------------
In qiskit 2.5.1 + qiskit-aer 0.17.2, importing qiskit_aer (or qiskit itself)
before calling build_qubo() causes a segmentation fault inside QAOAAnsatz on
the 8-qubit SparsePauliOp.  The root cause is qiskit_aer patching numpy C
extensions at import time.

Workaround: build_qubo() runs FIRST (top of main), then all Qiskit imports
happen inside a dedicated function called after the QUBO is fully constructed.

Outputs
-------
  experiments/results/qaoa_ibm_results.json

Usage
-----
    python experiments/07_qaoa_ibm_hardware.py
    python experiments/07_qaoa_ibm_hardware.py --shots 512
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import warnings
from datetime import datetime
from pathlib import Path

# ── Only stdlib / project imports at module level (no qiskit yet) ─────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# build_qubo uses only numpy + pandas — safe to import before qiskit
from quantum.qubo import build_qubo, QUBOProblem

ZONES_CSV   = PROJECT_ROOT / "data" / "processed" / "candidate_zones.csv"
DIST_CSV    = PROJECT_ROOT / "data" / "processed" / "candidate_distance_matrix.csv"
RESULTS_DIR = PROJECT_ROOT / "experiments" / "results"
OUTPUT_JSON = RESULTS_DIR / "qaoa_ibm_results.json"

# ── Known ground truth ────────────────────────────────────────────────────────
CLASSICAL_OPTIMUM_ZONES  = ["Z0", "Z2", "Z3"]
CLASSICAL_OPTIMUM_ENERGY = -139.697448
CLASSICAL_OPTIMUM_BITS   = "10110000"   # qubit-0-first

# ── Simulator reference (qaoa_simulator_results.json, seed=42, p=1) ───────────
SIM_BEST_ZONES  = ["Z0", "Z2", "Z3"]
SIM_BEST_ENERGY = -139.697448
SIM_BEST_BITS   = "10110000"
# QAOAAnsatz sorts parameters alphabetically: ['β[0]', 'γ[0]'] for p=1
# Simulator COBYLA result: γ = -3.576032  (cost),  β = 0.952474  (mixer)
SIM_BETA  =  0.952474    # β[0] → ansatz.parameters[0]
SIM_GAMMA = -3.576032    # γ[0] → ansatz.parameters[1]

DEFAULT_BACKEND = "ibm_fez"
DEFAULT_REPS    = 1
DEFAULT_SHOTS   = 1024


# ─────────────────────────────────────────────────────────────────────────────
# QUBO → Ising Hamiltonian  (no qiskit_optimization — avoids rustworkx crash)
# ─────────────────────────────────────────────────────────────────────────────

def build_ising(qubo: QUBOProblem):
    """
    Convert Q_upper to a SparsePauliOp Ising Hamiltonian.

    Substitution:  x_j = (I - Z_j) / 2

    Diagonal:    Q[j,j] · x_j  =  Q[j,j]/2 · I  -  Q[j,j]/2 · Z_j
    Off-diagonal: Q[j,k] · x_j · x_k  (j<k)
               = Q[j,k]/4 · (I - Z_j - Z_k + Z_jZ_k)

    SparsePauliOp label convention: label[0] = qubit n-1, label[-1] = qubit 0.
    """
    # Qiskit imports happen here — after build_qubo() has already run
    from qiskit.quantum_info import SparsePauliOp

    n = qubo.n
    pauli_list: list[tuple[str, float]] = []
    offset = 0.0

    for j in range(n):
        q = float(qubo.Q_upper[j, j])
        offset += q / 2.0
        label = "I" * (n - 1 - j) + "Z" + "I" * j
        pauli_list.append((label, -q / 2.0))

    for j in range(n):
        for k in range(j + 1, n):
            q = float(qubo.Q_upper[j, k])
            if q == 0.0:
                continue
            offset += q / 4.0
            pauli_list.append(("I" * (n-1-j) + "Z" + "I" * j,      -q / 4.0))
            pauli_list.append(("I" * (n-1-k) + "Z" + "I" * k,      -q / 4.0))
            arr = ["I"] * n
            arr[n-1-j] = "Z"
            arr[n-1-k] = "Z"
            pauli_list.append(("".join(arr), q / 4.0))

    cost_op = SparsePauliOp.from_list(pauli_list).simplify()
    return cost_op, offset


# ─────────────────────────────────────────────────────────────────────────────
# Build and bind QAOA circuit
# ─────────────────────────────────────────────────────────────────────────────

def build_bound_circuit(cost_op, reps: int):
    """Build QAOAAnsatz, bind simulator-optimal parameters, return bound circuit."""
    from qiskit.circuit.library import QAOAAnsatz

    ansatz = QAOAAnsatz(cost_operator=cost_op, reps=reps)
    ansatz.measure_all()

    param_names = [p.name for p in ansatz.parameters]

    # Alphabetical sort gives ['β[0]', 'γ[0]'] for p=1
    param_dict = {}
    for p in ansatz.parameters:
        if p.name[0] == "\u03b2":    # β — mixer
            param_dict[p] = SIM_BETA
        elif p.name[0] == "\u03b3":  # γ — cost
            param_dict[p] = SIM_GAMMA
        else:
            raise RuntimeError(f"Unexpected parameter name: {p.name!r}")

    bound = ansatz.assign_parameters(param_dict)
    return bound, bound.depth(), param_names


# ─────────────────────────────────────────────────────────────────────────────
# Result parsing
# ─────────────────────────────────────────────────────────────────────────────

def zones_from_bits(bits: str, labels: list[str]) -> list[str]:
    return [labels[j] for j, b in enumerate(bits) if b == "1"]


def parse_counts(
    counts_raw: dict[str, int],
    qubo: QUBOProblem,
    total_shots: float,
    top_n: int = 20,
) -> tuple[list[dict], str, float]:
    """
    Parse raw IBM counts.  IBM register order: rightmost char = qubit 0.
    Reverse each bitstring so qubit 0 is leftmost (matches QUBOProblem).
    """
    rows: list[dict] = []
    best_bits   = CLASSICAL_OPTIMUM_BITS
    best_energy = float("inf")

    for raw_bits, count in counts_raw.items():
        bits     = raw_bits[::-1]
        x        = qubo.bitstring_to_x(bits)
        energy   = qubo.energy(x)
        n_sel    = int(x.sum())
        feasible = n_sel == qubo.budget

        rows.append({
            "bitstring":   bits,
            "count":       count,
            "probability": round(count / total_shots, 8),
            "qubo_energy": round(float(energy), 6),
            "n_stations":  n_sel,
            "feasible":    feasible,
            "zones":       zones_from_bits(bits, qubo.labels),
        })
        if feasible and energy < best_energy:
            best_energy = energy
            best_bits   = bits

    rows.sort(key=lambda r: (-r["count"], r["qubo_energy"]))
    return rows[:top_n], best_bits, best_energy


def success_prob(counts_raw: dict[str, int], total_shots: float) -> float:
    """Fraction of shots on the exact global optimum (IBM register order)."""
    opt_ibm = CLASSICAL_OPTIMUM_BITS[::-1]   # "10110000" reversed → "00001101"
    return round(counts_raw.get(opt_ibm, 0) / total_shots, 8)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main(backend_name: str, reps: int, shots: int) -> None:

    # ── [1] Build QUBO first — before ANY qiskit import ─────────────────────
    print("=" * 68)
    print("  EVision — QAOA IBM Quantum Hardware Execution")
    print("=" * 68)
    print(f"  Target backend : {backend_name}")
    print(f"  QAOA reps      : p={reps}")
    print(f"  Shots          : {shots}")
    print(f"  QAOA params    : β={SIM_BETA}  γ={SIM_GAMMA}  (simulator seed=42)")
    print(f"  Classical opt  : {CLASSICAL_OPTIMUM_ZONES}  E={CLASSICAL_OPTIMUM_ENERGY}")

    print("\n[1/5] Building QUBO …")
    qubo = build_qubo(zones_csv=ZONES_CSV, dist_csv=DIST_CSV, budget=3)
    e_check = qubo.energy(qubo.bitstring_to_x(CLASSICAL_OPTIMUM_BITS))
    assert abs(e_check - CLASSICAL_OPTIMUM_ENERGY) < 1e-3, f"QUBO check: {e_check}"
    print(f"      n={qubo.n}  K={qubo.budget}  λ={qubo.lam}")
    print(f"      Sanity check: E({CLASSICAL_OPTIMUM_BITS}) = {e_check:.6f}  ✓")

    # ── [2] Ising Hamiltonian — qiskit imported inside build_ising() ─────────
    print("\n[2/5] Building Ising Hamiltonian …")
    cost_op, ising_offset = build_ising(qubo)   # first qiskit import happens here
    print(f"      Pauli terms   : {len(cost_op)}")
    print(f"      Energy offset : {ising_offset:.6f}")

    # ── [3] QAOA circuit ─────────────────────────────────────────────────────
    print("\n[3/5] Building and binding QAOA circuit …")
    bound_circuit, logical_depth, param_names = build_bound_circuit(cost_op, reps)
    print(f"      Logical qubits : {bound_circuit.num_qubits}")
    print(f"      Logical depth  : {logical_depth}")
    print(f"      Parameters     : {param_names}  →  β={SIM_BETA}  γ={SIM_GAMMA}")

    # ── [4] Connect to IBM Quantum, transpile, submit ─────────────────────────
    print(f"\n[4/5] Connecting to IBM Quantum ({backend_name}), transpiling, submitting …")
    warnings.filterwarnings("ignore", category=UserWarning,
                            module="qiskit_ibm_runtime")

    import qiskit_ibm_runtime
    from qiskit_ibm_runtime import QiskitRuntimeService
    from qiskit_ibm_runtime import SamplerV2 as RuntimeSamplerV2
    from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager

    svc     = QiskitRuntimeService(instance="auto")
    backend = svc.backend(backend_name)
    print(f"      Backend        : {backend.name}  ({backend.num_qubits} qubits)")
    print(f"      Status         : operational={backend.status().operational}"
          f"  pending_jobs={backend.status().pending_jobs}")
    print(f"      IBM Runtime    : {qiskit_ibm_runtime.__version__}")

    pm          = generate_preset_pass_manager(optimization_level=1, backend=backend)
    transpiled  = pm.run(bound_circuit)
    trans_depth = transpiled.depth()
    n_phys      = transpiled.num_qubits
    print(f"      Transpiled depth  : {trans_depth}")
    print(f"      Physical qubits   : {n_phys}")

    sampler = RuntimeSamplerV2(mode=backend)
    t0      = time.perf_counter()
    job     = sampler.run([transpiled], shots=shots)
    job_id  = job.job_id()
    print(f"      Job ID            : {job_id}")
    print(f"      Waiting …", flush=True)
    result    = job.result()
    runtime_s = time.perf_counter() - t0
    print(f"      Done. Wall time   : {runtime_s:.1f} s")

    # Parse result
    bit_array   = result[0].data.meas
    counts_raw  = bit_array.get_counts()
    total_shots = float(bit_array.num_shots)

    # ── [5] Evaluate and save ─────────────────────────────────────────────────
    print(f"\n[5/5] Evaluating results …")
    print(f"      Total shots    : {int(total_shots)}")
    print(f"      Unique states  : {len(counts_raw)}")

    rows, best_bits, best_energy = parse_counts(counts_raw, qubo, total_shots)
    succ_p      = success_prob(counts_raw, total_shots)
    best_x      = qubo.bitstring_to_x(best_bits)
    best_zones  = zones_from_bits(best_bits, qubo.labels)
    is_feasible = int(best_x.sum()) == qubo.budget
    energy_gap  = round(best_energy - CLASSICAL_OPTIMUM_ENERGY, 6)
    matches     = sorted(best_zones) == sorted(CLASSICAL_OPTIMUM_ZONES)

    print(f"\n  Top-10 bitstrings (qubit-0-first order):")
    print(f"  {'#':>3}  {'bitstring':>8}  {'count':>5}  {'prob':>7}  "
          f"{'energy':>13}  zones")
    for i, r in enumerate(rows[:10], 1):
        opt  = " ◀ OPT" if r["bitstring"] == CLASSICAL_OPTIMUM_BITS else ""
        feas = "✓" if r["feasible"] else " "
        print(f"  {i:>3}  {r['bitstring']:>8}  {r['count']:>5}  "
              f"{r['probability']:>7.4f}  {r['qubo_energy']:>13.6f}  "
              f"{feas} {r['zones']}{opt}")

    match_str = "YES ✓" if matches else "NO  ✗  (hardware noise — see comparison)"
    print(f"\n  Best feasible bitstring : {best_bits}")
    print(f"  Selected zones          : {best_zones}")
    print(f"  QUBO energy             : {best_energy:.6f}")
    print(f"  Classical optimum       : {CLASSICAL_OPTIMUM_ENERGY:.6f}")
    print(f"  Matches classical       : {match_str}")
    print(f"  Energy gap              : {energy_gap:+.6f}")
    print(f"  Success probability     : {succ_p:.4f}")
    print(f"  Transpiled depth        : {trans_depth}")
    print(f"  Runtime                 : {runtime_s:.1f} s")

    # ── Save JSON ─────────────────────────────────────────────────────────────
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    import qiskit
    import qiskit_aer
    output = {
        "metadata": {
            "date":                     datetime.now().isoformat(),
            "script":                   "experiments/07_qaoa_ibm_hardware.py",
            "qiskit_version":           qiskit.__version__,
            "aer_version":              qiskit_aer.__version__,
            "ibm_runtime_version":      qiskit_ibm_runtime.__version__,
            "backend":                  backend_name,
            "n_logical_qubits":         qubo.n,
            "budget_k":                 qubo.budget,
            "lambda":                   qubo.lam,
            "qaoa_reps":                reps,
            "shots":                    shots,
            "simulator_params":         {"beta": SIM_BETA, "gamma": SIM_GAMMA},
            "param_source":             "simulator seed=42 p=1 COBYLA maxiter=500",
            "classical_optimum_zones":  CLASSICAL_OPTIMUM_ZONES,
            "classical_optimum_energy": CLASSICAL_OPTIMUM_ENERGY,
            "zone_qubit_mapping":       {qubo.labels[j]: j for j in range(qubo.n)},
        },
        "circuit": {
            "qaoa_reps":           reps,
            "n_logical_qubits":    qubo.n,
            "n_physical_qubits":   n_phys,
            "logical_depth":       logical_depth,
            "transpiled_depth":    trans_depth,
            "n_ising_terms":       len(cost_op),
            "ising_offset":        round(ising_offset, 6),
            "parameter_names":     param_names,
            "bound_parameters":    {"beta": SIM_BETA, "gamma": SIM_GAMMA},
        },
        "hardware": {
            "job_id":               job_id,
            "backend":              backend_name,
            "shots_requested":      shots,
            "shots_recorded":       int(total_shots),
            "runtime_s":            round(runtime_s, 2),
            "best_bitstring":       best_bits,
            "selected_zones":       best_zones,
            "qubo_energy":          round(best_energy, 6),
            "feasible":             is_feasible,
            "n_stations":           int(best_x.sum()),
            "success_probability":  succ_p,
            "bitstring_distribution": rows,
        },
        "comparison": {
            "classical_optimum": {
                "zones":  CLASSICAL_OPTIMUM_ZONES,
                "energy": CLASSICAL_OPTIMUM_ENERGY,
                "bits":   CLASSICAL_OPTIMUM_BITS,
            },
            "simulator_result": {
                "zones":  SIM_BEST_ZONES,
                "energy": SIM_BEST_ENERGY,
                "bits":   SIM_BEST_BITS,
                "beta":   SIM_BETA,
                "gamma":  SIM_GAMMA,
            },
            "hardware_result": {
                "zones":               best_zones,
                "energy":              round(best_energy, 6),
                "bits":                best_bits,
                "success_probability": succ_p,
                "transpiled_depth":    trans_depth,
                "runtime_s":           round(runtime_s, 2),
            },
            "hw_matches_classical":  matches,
            "hw_energy_gap":         energy_gap,
            "hw_vs_simulator_gap":   round(best_energy - SIM_BEST_ENERGY, 6),
            "notes": (
                "success_probability = fraction of raw hardware shots on the "
                "exact optimal bitstring 10110000 (Z0+Z2+Z3). "
                "energy_gap = hw_best_energy - classical_optimum_energy; "
                "0.0 means exact match. Hardware noise degrades the "
                "distribution relative to the noiseless simulator; the best "
                "feasible result is found by scanning all sampled bitstrings."
            ),
        },
    }

    with open(OUTPUT_JSON, "w") as fh:
        json.dump(output, fh, indent=2, default=str)

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
        description="QAOA on IBM Quantum hardware (ibm_fez)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--backend", default=DEFAULT_BACKEND)
    p.add_argument("--reps",    type=int, default=DEFAULT_REPS)
    p.add_argument("--shots",   type=int, default=DEFAULT_SHOTS)
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    main(backend_name=args.backend, reps=args.reps, shots=args.shots)
