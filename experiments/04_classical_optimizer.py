"""
experiments/04_classical_optimizer.py
=======================================
Exhaustive classical baseline for EV charger placement.

Reads
-----
  data/processed/candidate_zones.csv
  data/processed/candidate_distance_matrix.csv   (used only for reference;
                                                   coverage is taken from the
                                                   neighbors_3km column which
                                                   was derived from this matrix)

Writes (experiments/results/)
------------------------------
  classical_best.json        winning combination, covered demand, coverage %, runtime
  classical_all_results.csv  all 56 combinations ranked by covered demand
  classical_summary.txt      human-readable report

Usage
-----
    cd /path/to/EV
    .venv/bin/python experiments/04_classical_optimizer.py
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
import textwrap
from pathlib import Path

import numpy as np
import pandas as pd

# ── logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# I/O helpers
# ─────────────────────────────────────────────────────────────────────────────

def load_problem(zones_csv: Path, dist_csv: Path):
    """
    Build a PlacementProblem from the two processed CSVs.

    Coverage is derived from the neighbors_3km column (pre-computed at 3 km
    threshold) rather than re-thresholding the distance matrix, so the
    coverage relationships are exactly those documented in
    experiments/03_optimization_problem.md.
    """
    from backend.optimization.classical_solver import PlacementProblem

    zones = pd.read_csv(zones_csv)

    labels  = zones["label"].tolist()           # ['Z0', 'Z1', …, 'Z7']
    demands = zones["mean_pred_kwh"].to_numpy(dtype=float)
    n       = len(labels)
    idx_map = {lbl: i for i, lbl in enumerate(labels)}

    # ── Build coverage adjacency matrix ─────────────────────────────────────
    # coverage_adj[i, j] == True  →  placing a station in j covers zone i.
    # Self-coverage is always True (a station in zone i covers zone i itself).
    adj = np.eye(n, dtype=bool)   # initialise with self-coverage

    for _, row in zones.iterrows():
        i = idx_map[row["label"]]
        if pd.isna(row["neighbors_3km"]) or row["neighbors_3km"] == "":
            continue
        for nb_label in str(row["neighbors_3km"]).split("|"):
            nb_label = nb_label.strip()
            if nb_label in idx_map:
                j = idx_map[nb_label]
                adj[i, j] = True   # j covers i
                adj[j, i] = True   # symmetric: i covers j

    log.info("Loaded %d zones; total demand = %.2f kWh/h", n, demands.sum())
    log.info("Coverage adjacency matrix:\n%s",
             "\n".join(
                 "  " + labels[i] + ": " +
                 " ".join(labels[j] for j in range(n) if adj[i, j] and j != i)
                 for i in range(n)
             ))

    return PlacementProblem(
        labels       = labels,
        demands      = demands,
        coverage_adj = adj,
        budget       = 3,
    )


def write_results(output, results_dir: Path) -> None:
    """Write best.json, all_results.csv, and summary.txt."""
    from backend.optimization.classical_solver import SolverOutput

    results_dir.mkdir(parents=True, exist_ok=True)
    best = output.best

    # ── classical_best.json ──────────────────────────────────────────────────
    best_payload = {
        "solver":           output.solver,
        "budget_K":         output.problem.budget,
        "n_combinations":   output.n_combinations,
        "runtime_s":        round(output.runtime_s, 6),
        "winning_stations": best.stations,
        "covered_zones":    best.covered_zones,
        "covered_demand_kwh_h":  round(best.covered_demand, 4),
        "total_demand_kwh_h":    round(best.total_demand, 4),
        "coverage_pct":          round(best.coverage_pct, 4),
        "zone_details": [
            {
                "label":           output.problem.labels[i],
                "demand_kwh_h":    round(float(output.problem.demands[i]), 4),
                "selected":        i in best.station_idxs,
                "covered":         output.problem.labels[i] in best.covered_zones,
            }
            for i in range(output.problem.n)
        ],
    }
    best_path = results_dir / "classical_best.json"
    with open(best_path, "w") as f:
        json.dump(best_payload, f, indent=2)
    log.info("Saved %s", best_path)

    # ── classical_all_results.csv ────────────────────────────────────────────
    csv_path = results_dir / "classical_all_results.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "rank", "combo_idx",
            "station_1", "station_2", "station_3",
            "covered_zones", "covered_demand_kwh_h",
            "total_demand_kwh_h", "coverage_pct",
        ])
        for rank, r in enumerate(output.all_results, start=1):
            writer.writerow([
                rank,
                r.combo_idx,
                r.stations[0], r.stations[1], r.stations[2],
                "|".join(r.covered_zones),
                round(r.covered_demand, 4),
                round(r.total_demand, 4),
                round(r.coverage_pct, 4),
            ])
    log.info("Saved %s  (%d rows)", csv_path, len(output.all_results))

    # ── classical_summary.txt ────────────────────────────────────────────────
    labels  = output.problem.labels
    demands = output.problem.demands
    n       = output.problem.n

    lines = []
    lines.append("=" * 62)
    lines.append("  EVision — Classical Exhaustive Solver")
    lines.append("=" * 62)
    lines.append(f"  Solver            : {output.solver}")
    lines.append(f"  Zones evaluated   : {n}")
    lines.append(f"  Budget (K)        : {output.problem.budget}")
    lines.append(f"  Combinations      : {output.n_combinations}")
    lines.append(f"  Runtime           : {output.runtime_s*1000:.3f} ms")
    lines.append("")
    lines.append("  ── WINNING PLACEMENT ──────────────────────────────")
    lines.append(f"  Stations placed   : {', '.join(best.stations)}")
    lines.append(f"  Zones covered     : {', '.join(best.covered_zones)}")
    lines.append(f"  Covered demand    : {best.covered_demand:.4f} kWh/h")
    lines.append(f"  Total demand      : {best.total_demand:.4f} kWh/h")
    lines.append(f"  Coverage          : {best.coverage_pct:.4f} %")
    lines.append("")
    lines.append("  ── ZONE BREAKDOWN ─────────────────────────────────")
    lines.append(f"  {'Zone':<6}  {'Demand':>10}  {'Station':>8}  {'Covered':>8}")
    lines.append(f"  {'----':<6}  {'--------':>10}  {'-------':>8}  {'-------':>8}")
    for i in range(n):
        selected = "YES" if i in best.station_idxs else "-"
        covered  = "YES" if labels[i] in best.covered_zones else "NO"
        lines.append(
            f"  {labels[i]:<6}  {demands[i]:>10.2f}  {selected:>8}  {covered:>8}"
        )
    lines.append("")
    lines.append("  ── ALL 56 RESULTS (ranked by covered demand) ──────")
    lines.append(f"  {'Rank':>4}  {'Stations':<18}  {'Covered kWh/h':>14}  {'Coverage %':>10}")
    lines.append(f"  {'----':>4}  {'--------':<18}  {'--------------':>14}  {'----------':>10}")
    for rank, r in enumerate(output.all_results, start=1):
        station_str = "+".join(r.stations)
        lines.append(
            f"  {rank:>4}  {station_str:<18}  {r.covered_demand:>14.4f}  {r.coverage_pct:>10.4f}"
        )
    lines.append("=" * 62)

    summary_path = results_dir / "classical_summary.txt"
    with open(summary_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    log.info("Saved %s", summary_path)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent

    parser = argparse.ArgumentParser(
        description="EVision classical exhaustive charger-placement solver."
    )
    parser.add_argument(
        "--zones",
        type=Path,
        default=repo_root / "data" / "processed" / "candidate_zones.csv",
    )
    parser.add_argument(
        "--dist",
        type=Path,
        default=repo_root / "data" / "processed" / "candidate_distance_matrix.csv",
    )
    parser.add_argument(
        "--results",
        type=Path,
        default=repo_root / "experiments" / "results",
    )
    args = parser.parse_args()

    for p in [args.zones, args.dist]:
        if not p.exists():
            log.error("Required file not found: %s", p)
            return 1

    from backend.optimization.classical_solver import solve_exhaustive

    # ── 1. Load problem ───────────────────────────────────────────────────────
    log.info("── Step 1: Load problem")
    problem = load_problem(args.zones, args.dist)

    # ── 2. Solve ──────────────────────────────────────────────────────────────
    log.info("── Step 2: Exhaustive search over C(%d,%d) = 56 combinations",
             problem.n, problem.budget)
    output = solve_exhaustive(problem)

    log.info("  Runtime   : %.3f ms", output.runtime_s * 1000)
    log.info("  Best combo: %s", output.best.stations)
    log.info("  Covered   : %.4f kWh/h  (%.4f %%)",
             output.best.covered_demand, output.best.coverage_pct)

    # ── 3. Write results ──────────────────────────────────────────────────────
    log.info("── Step 3: Write results → %s", args.results)
    write_results(output, args.results)

    # ── Console summary ───────────────────────────────────────────────────────
    best = output.best
    print("\n" + "=" * 62)
    print("  EVision — Classical Solver Complete")
    print("=" * 62)
    print(f"  Combinations evaluated : {output.n_combinations}")
    print(f"  Runtime                : {output.runtime_s*1000:.3f} ms")
    print(f"  Winning stations       : {', '.join(best.stations)}")
    print(f"  Zones covered          : {', '.join(best.covered_zones)}")
    print(f"  Covered demand         : {best.covered_demand:.4f} kWh/h")
    print(f"  Coverage               : {best.coverage_pct:.4f} %")
    print("=" * 62 + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
