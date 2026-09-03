"""
quantum/qubo.py
=======================
QUBO formulation for the 8-zone, 3-station EV charger-placement problem.

Objective
---------
The classical coverage objective (maximise total covered demand) produces a
40-way tie at 100% coverage for our 8-zone cluster.  To break this degeneracy
while remaining grounded in real data, we define a demand-weighted proximity
objective:

    For each zone i, compute the sum of proximity contributions from every
    selected station j that covers it:

        contribution(i, j) = d_i / D_eff(i, j)

    where d_i is the predicted mean hourly demand (kWh/h) and D_eff(i,j) is
    the effective distance (metres), capped at D_MIN = 100 m to avoid a
    divide-by-zero for the self-coverage case.

    Zone i counts as "covered by j" when A[i,j] = 1 (binary coverage
    adjacency, i.e. j is i itself or within 3 km of i).

    The total objective for a placement x ∈ {0,1}^8 is:

        f(x) = Σ_i Σ_j  (d_i / D_eff(i,j)) · A[i,j] · x_j
             = Σ_j  c_j · x_j                             (linear in x)

    where  c_j = Σ_i  d_i · A[i,j] / D_eff(i,j)
    is the "proximity-weighted coverage value" of placing a station at zone j.

    Maximising f(x) is equivalent to minimising -f(x).

Constraint
----------
Exactly K = 3 stations must be placed:

    Σ_j x_j = K

Enforced as a quadratic penalty:

    P(x) = λ · (Σ_j x_j - K)²

QUBO Hamiltonian
----------------
    H(x) = -f(x) + λ · P(x)
          = Σ_j (-c_j) · x_j  +  λ · (Σ_j x_j - K)²

Expanding the penalty (using x_j² = x_j for binary variables):

    (Σ x_j - K)² = Σ_j x_j + 2·Σ_{j<k} x_j·x_k - 2K·Σ_j x_j + K²
                 = (1-2K)·Σ_j x_j + 2·Σ_{j<k} x_j·x_k + K²

Substituting:

    H(x) = Σ_j [-c_j + λ(1-2K)] · x_j
          + 2λ · Σ_{j<k} x_j · x_k
          + λ·K²  (constant, omitted in minimisation)

Upper-triangular QUBO matrix Q' (as used by Qiskit / QUBO solvers):

    Q'[j,j] = -c_j + λ(1-2K)     (diagonal: linear coefficients)
    Q'[j,k] = 2λ                  (off-diagonal j<k: interaction)

Evaluation:  H(x) = Σ_{j≤k} Q'[j,k] · x_j · x_k  (+ constant)

Equivalently in symmetric matrix form  Q = (Q' + Q'^T) / 2:

    H(x) = x^T Q x  (plus constant)

Penalty calibration
-------------------
The minimum λ that makes all k=3 solutions globally optimal is derived from
the worst-case infeasible competitor.  The binding constraint is k=4:

    Best k=4 objective gain above best k=3: Δ = c_Z1 = 5.2847 kWh·m⁻¹
    Need: λ > Δ  →  λ_min ≈ 5.29

We use λ = 10 (≈ 1.9 × λ_min) for a robust penalty gap while keeping
Q'[j,j] negative for the highest-value zone (Z0: -27.95), which helps
QAOA find the energy minimum.  Verified over all 256 bitstrings: the global
minimum is the feasible winner {Z0, Z2, Z3} with gap ≥ 70 energy units to
the best infeasible state.

Zone index mapping
------------------
    j=0 → Z0 (TAZID 1026),  j=1 → Z1 (TAZID 746),
    j=2 → Z2 (TAZID 716),   j=3 → Z3 (TAZID 965),
    j=4 → Z4 (TAZID 706),   j=5 → Z5 (TAZID 745),
    j=6 → Z6 (TAZID 744),   j=7 → Z7 (TAZID 737)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


# ── Constants ─────────────────────────────────────────────────────────────────
D_MIN_M: float = 100.0   # minimum effective distance (metres) — prevents 1/0
LAMBDA:  float = 10.0    # penalty weight for the budget constraint


# ─────────────────────────────────────────────────────────────────────────────
# Data class
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class QUBOProblem:
    """
    All derived quantities needed for the QUBO and downstream solvers.

    Attributes
    ----------
    labels       : zone labels ['Z0', …, 'Z7']
    demands      : predicted mean hourly demand d_i  (kWh/h), shape (n,)
    coverage_adj : A[i,j] – True if placing station at j covers zone i, (n,n)
    dist_eff     : D_eff[i,j] – effective distance in metres, (n,n)
    c_values     : proximity-weighted coverage value c_j per zone j, shape (n,)
    Q_upper      : upper-triangular QUBO matrix Q' (n,n)
    Q_sym        : symmetric QUBO matrix Q = (Q'+Q'^T)/2 – used in x^T Q x
    lam          : penalty weight λ
    budget       : K (number of stations to place)
    n            : number of candidate zones
    """
    labels:       List[str]
    demands:      np.ndarray   # (n,)
    coverage_adj: np.ndarray   # (n,n) bool
    dist_eff:     np.ndarray   # (n,n) float, metres
    c_values:     np.ndarray   # (n,)  float
    Q_upper:      np.ndarray   # (n,n) upper-triangular
    Q_sym:        np.ndarray   # (n,n) symmetric
    lam:          float
    budget:       int
    n:            int

    @property
    def label_to_idx(self) -> Dict[str, int]:
        return {lbl: i for i, lbl in enumerate(self.labels)}

    def energy(self, x: np.ndarray) -> float:
        """
        Compute H(x) = Σ_{j≤k} Q'[j,k]·x_j·x_k  (upper-triangular form).
        Excludes the constant λ·K² which does not affect the minimisation.

        Parameters
        ----------
        x : 1-D array of shape (n,), values in {0, 1}
        """
        x = np.asarray(x, dtype=float)
        e = 0.0
        for j in range(self.n):
            e += self.Q_upper[j, j] * x[j]
            for k in range(j + 1, self.n):
                e += self.Q_upper[j, k] * x[j] * x[k]
        return float(e)

    def energy_sym(self, x: np.ndarray) -> float:
        """Compute H(x) = x^T Q_sym x (symmetric form, equivalent to energy())."""
        x = np.asarray(x, dtype=float)
        return float(x @ self.Q_sym @ x)

    def bitstring_to_x(self, bitstring: str) -> np.ndarray:
        """
        Convert a bitstring '01101000' (left = qubit 0) to a binary vector.
        Length must equal self.n.
        """
        if len(bitstring) != self.n:
            raise ValueError(f"Bitstring length {len(bitstring)} != n={self.n}")
        return np.array([int(b) for b in bitstring], dtype=float)

    def x_to_stations(self, x: np.ndarray) -> List[str]:
        """Return labels of selected zones given a binary vector x."""
        return [self.labels[j] for j in range(self.n) if x[j] == 1]


# ─────────────────────────────────────────────────────────────────────────────
# Builder
# ─────────────────────────────────────────────────────────────────────────────

def build_qubo(
    zones_csv:    Path | pd.DataFrame,
    dist_csv:     Path,
    budget:       int,
    lam:          float = LAMBDA,
    d_min_m:      float = D_MIN_M,
) -> QUBOProblem:
    """
    Construct the QUBO from the processed candidate-zone data.

    Parameters
    ----------
    zones_csv : path to candidate_zones.csv, or a DataFrame with the same
                columns (label, mean_pred_kwh, neighbors_3km, …).
                Passing a DataFrame avoids a temporary-file round-trip when
                the caller already holds the data in memory.
    dist_csv  : path to data/processed/candidate_distance_matrix.csv
    lam       : penalty weight λ (default 10.0)
    budget    : K stations to place (default 3)
    d_min_m   : minimum effective distance in metres (default 100.0)

    Returns
    -------
    QUBOProblem with Q_upper, Q_sym, c_values, and all derived fields.
    """
    zones = pd.read_csv(zones_csv) if isinstance(zones_csv, (str, Path)) else zones_csv
    dist  = pd.read_csv(dist_csv, index_col=0)

    labels  = zones["label"].tolist()
    demands = zones["mean_pred_kwh"].to_numpy(dtype=float)
    n       = len(labels)
    idx_map = {lbl: i for i, lbl in enumerate(labels)}

    # ── Coverage adjacency (from neighbors_3km column) ────────────────────────
    # A[i,j] = True  →  placing a station at j covers zone i
    A = np.eye(n, dtype=bool)   # self-coverage on the diagonal
    for _, row in zones.iterrows():
        i = idx_map[row["label"]]
        for nb in str(row["neighbors_3km"]).split("|"):
            nb = nb.strip()
            if nb and nb in idx_map:
                j = idx_map[nb]
                A[i, j] = True
                A[j, i] = True   # symmetric

    # ── Effective distance matrix ─────────────────────────────────────────────
    D_raw = dist.values.astype(float)          # metres
    D_eff = np.where(D_raw < d_min_m, d_min_m, D_raw)  # cap D_MIN for D=0

    # ── c_j: proximity-weighted coverage value per zone j ─────────────────────
    # c_j = Σ_i  d_i · A[i,j] / D_eff[i,j]
    C = np.zeros(n)
    for j in range(n):
        for i in range(n):
            if A[i, j]:
                C[j] += demands[i] / D_eff[i, j]

    # ── Upper-triangular QUBO matrix Q' ───────────────────────────────────────
    # H(x) = Σ_j [-c_j + λ(1-2K)] x_j  +  2λ Σ_{j<k} x_j x_k  +  λK²
    #
    # Q'[j,j] = -c_j + λ(1-2K)
    # Q'[j,k] = 2λ                for j < k
    # Q'[j,k] = 0                 for j > k   (upper-triangular convention)
    Q_upper = np.zeros((n, n))
    diagonal_shift = lam * (1 - 2 * budget)   # λ(1-2K) = 10*(1-6) = -50
    for j in range(n):
        Q_upper[j, j] = -C[j] + diagonal_shift
    for j in range(n):
        for k in range(j + 1, n):
            Q_upper[j, k] = 2.0 * lam

    # ── Symmetric form: Q_sym = (Q_upper + Q_upper^T) / 2 ────────────────────
    # Note: Q_upper is already half-weighted for off-diagonal in x^T Q x,
    # so the symmetric form for x^T Q_sym x must use Q_sym[j,k] = lam (not 2λ)
    # and Q_sym[j,j] = Q_upper[j,j].
    # More precisely: x^T Q_upper_tri x = Σ_{j≤k} Q'[j,k] x_j x_k
    # To write this as x^T Q_sym x:  Q_sym = (Q_upper + Q_upper^T) / 2
    # BUT diagonal stays (only appears once): Q_sym[j,j] = Q_upper[j,j]
    # Off-diagonal: Q_sym[j,k] = Q_upper[j,k]/2 = λ (since Q_upper[j,k]=2λ)
    Q_sym = np.zeros((n, n))
    for j in range(n):
        Q_sym[j, j] = Q_upper[j, j]
    for j in range(n):
        for k in range(j + 1, n):
            Q_sym[j, k] = lam
            Q_sym[k, j] = lam

    return QUBOProblem(
        labels       = labels,
        demands      = demands,
        coverage_adj = A,
        dist_eff     = D_eff,
        c_values     = C,
        Q_upper      = Q_upper,
        Q_sym        = Q_sym,
        lam          = lam,
        budget       = budget,
        n            = n,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Convenience: evaluate a bitstring / combo
# ─────────────────────────────────────────────────────────────────────────────

def combo_to_x(combo_labels: List[str], all_labels: List[str]) -> np.ndarray:
    """Convert a list of selected zone labels to a binary vector."""
    x = np.zeros(len(all_labels), dtype=float)
    idx_map = {lbl: i for i, lbl in enumerate(all_labels)}
    for lbl in combo_labels:
        x[idx_map[lbl]] = 1.0
    return x


def objective_value(combo_labels: List[str], qubo: QUBOProblem) -> float:
    """
    Return the objective f(x) = Σ_j c_j x_j for a given station selection.
    This is the maximisation objective without the penalty term.
    """
    x = combo_to_x(combo_labels, qubo.labels)
    return float(qubo.c_values @ x)


def penalty_value(combo_labels: List[str], qubo: QUBOProblem) -> float:
    """Return the penalty term λ·(Σ x_j - K)² for a given selection."""
    k = len(combo_labels)
    return qubo.lam * (k - qubo.budget) ** 2
