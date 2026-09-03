# QuantEV (EVision) — AI + Quantum EV Charging Infrastructure Optimizer

QuantEV is an end-to-end framework designed to solve the electric vehicle (EV) charging station placement problem. It uses **Machine Learning (Random Forest)** to predict geographic demand and **Quantum Computing (QAOA)** alongside classical baseline solvers to optimize station locations. The results are visualized on an interactive GIS dashboard.

---

## Overview

EV adoption is growing rapidly, but charging infrastructure cannot simply be expanded everywhere. 

The real challenge is a **combinatorial infrastructure planning problem**:
* Where will charging demand increase?
* Which areas are underserved?
* Which candidate locations provide the greatest coverage?
* How many stations should be deployed?
* Which configuration provides the best trade-off between demand coverage and network efficiency?

**QuantEV** approaches this problem as an end-to-end decision intelligence pipeline. It uses a machine-learning model to estimate charging demand and then formulates infrastructure placement as a **Quadratic Unconstrained Binary Optimization (QUBO)** problem. The resulting optimization problem is solved using the **Quantum Approximate Optimization Algorithm (QAOA)** and evaluated against a classical baseline.

---

## Architecture & System Design

QuantEV is structured as a monorepo consisting of a FastAPI backend, a Next.js frontend, and a curated data pipeline.

### Technical Stack

| Layer | Component | Technologies |
|---|---|---|
| **Frontend** | GIS Dashboard | Next.js 16 (App Router), TypeScript, Tailwind CSS, Leaflet Map |
| **API** | REST Orchestrator | FastAPI, Uvicorn, Pydantic |
| **Quantum Optimization** | QAOA Solver | Qiskit 2.x, Qiskit Aer (Local Statevector Simulator), Qiskit Optimization |
| **Classical Optimization** | Baseline Solver | NumPy, Python itertools (exhaustive search) |
| **Machine Learning / Data** | Demand Forecast | Python 3.11+, Pandas, NumPy, Scikit-learn (RandomForestRegressor) |

### System Data Flow

```
                      +-----------------------------+
                      |     Raw EV / Geo Data       |
                      +--------------+--------------+
                                     |
                                     v
                      +-----------------------------+
                      |      ai_model               |
                      |   Feature Engineering &     |
                      |   Random Forest Regressor   |
                      +--------------+--------------+
                                     |
                                     v (Predicted Demand Score per Zone)
                      +-----------------------------+
                      |      backend/api            |
                      |   FastAPI POST /optimize    |
                      +-------+--------------+------+
                              |              |
                              |              v
                              |     +-----------------------+
                              |     |  backend/optimization |
                              |     |   Exhaustive Search   |
                              |     |     (Classical)       |
                              |     +--------+--------------+
                              |              |
                              v              |
                      +---------------------+ |
                      |    quantum          | |
                      |    QUBO Formulation | |
                      |     & QAOA Solver   | |
                      +-------+-------------+ |
                              |              |
                              v (Selected    v (Selected
                              |  Zones)      |  Zones)
                              +-------+------+
                                     |
                                     v
                      +-----------------------------+
                      |         frontend            |
                      |  Next.js + Leaflet Map &   |
                      |  Interactive Benchmarks     |
                      +-----------------------------+
```

---

## Monorepo Project Structure

```
EV/
├── ai_model/                    # AI demand forecasting package & artifacts
│   ├── features.py              # Lag & rolling window feature engineering
│   ├── train.py                 # RandomForestRegressor model training
│   └── models/                  # Saved ML estimators & evaluation metrics
├── backend/
│   ├── optimization/            # Classical baselines
│   │   └── classical_solver.py  # Combinatorial exhaustive search solver
│   └── api/                     # FastAPI endpoint orchestration
│       ├── routers/             # API routing (optimize, health, status)
│       └── services/            # Pipeline execution service
├── quantum/                     # Quantum optimization package
│   └── qubo.py                  # Mathematical formulation of QUBO matrix
├── data/
│   ├── raw/                     # Original hackathon datasets
│   └── processed/               # Parquet demand files, distances, and zones
├── docs/                        # Architecture & API specifications
│   ├── architecture.md
│   └── api_spec.md
├── experiments/                 # Jupyter notebooks for R&D
├── frontend/                    # Next.js 16 app (TypeScript + Tailwind)
│   ├── src/
│   │   ├── app/                 # React pages & CSS layouts
│   │   ├── components/          # Interactive map & solver controls
│   │   └── hooks/               # Custom state fetching hooks
│   └── package.json
├── build.sh                     # Build and compile pipeline script
├── pyproject.toml               # Python packaging configuration
├── render.yaml                  # Cloud hosting deployment specification
├── requirements.txt             # Development dependencies
└── requirements-prod.txt        # Production dependencies
```

---

## Machine Learning Pipeline (Demand Prediction)

The system forecasts EV charging demand for the next hour ($t+1$) in a target geographic zone based on historical data.

### Feature Engineering
For each geographic zone, the following features are dynamically constructed to capture temporal and rolling patterns:
* **Calendrical features**: `hour` [0–23], `day_of_week` [0–6], `is_weekend` [0 or 1], and `month` [1–12].
* **Lag features**: Trailing demand values at $t-1\text{h}$ (`lag_1h`), $t-24\text{h}$ (`lag_24h`), and $t-168\text{h}$ (`lag_168h` / 1 week).
* **Rolling window features**: Trailing 24-hour mean demand value (`rolling_mean_24h`), shifted by $t-1\text{h}$ to avoid data leakage.

### Model & Split
* **Split Strategy**: A strict chronological split of 70% training, 15% validation, and 15% testing is applied. This avoids data leakage across zone groups.
* **Model**: A `RandomForestRegressor` is wrapped in a Scikit-learn pipeline (utilizing a `StandardScaler` for modularity).
* **Render Free Tier Optimization**: A slim model configuration ($n\_estimators=50$, $max\_depth=12$) is pre-trained and serialized via `build.sh` to stay well within the memory limitations (512 MiB RSS limit) during cloud deployment.

---

## Mathematical Formulation & Quantum Optimization

To select the best charging station locations, QuantEV formulates the placement problem as a **Quadratic Unconstrained Binary Optimization (QUBO)** problem.

### 1. Objective Function (Proximity-Weighted Demand)
Standard classical coverage objectives (maximizing total covered demand) often suffer from degeneracies, producing dozens of identical solutions. To resolve this, QuantEV optimizes a **proximity-weighted coverage objective**:

$$f(x) = \sum_{i=1}^n \sum_{j=1}^n \frac{d_i}{D_{\text{eff}}(i,j)} \cdot A_{ij} \cdot x_j$$

Where:
* $x_j \in \{0, 1\}$ is the binary decision variable: $1$ if a station is placed in candidate zone $j$, $0$ otherwise.
* $d_i$ is the predicted demand score for zone $i$ (output from the ML model).
* $A_{ij} \in \{0, 1\}$ is the binary adjacency matrix indicating if zone $j$ is within 3 km of zone $i$.
* $D_{\text{eff}}(i,j)$ is the effective distance in meters, capped at a minimum $D_{\text{min}} = 100\text{ m}$ to avoid division by zero (self-coverage).

Maximizing $f(x)$ is mathematically equivalent to minimizing $-f(x)$. The linear coefficient is summarized as:

$$c_j = \sum_{i=1}^n \frac{d_i \cdot A_{ij}}{D_{\text{eff}}(i,j)}$$

### 2. Constraints (Budget)
We must place exactly $K$ stations (budget constraint):

$$\sum_{j=1}^n x_j = K$$

This hard constraint is converted into an unconstrained quadratic penalty:

$$P(x) = \lambda \left(\sum_{j=1}^n x_j - K\right)^2$$

Where $\lambda$ is a penalty scaling factor.

### 3. QUBO Hamiltonian Expansion
Combining the objective and constraint yields the QUBO Hamiltonian $H(x)$:

$$H(x) = -f(x) + \lambda \cdot P(x)$$

$$H(x) = \sum_{j=1}^n -c_j x_j + \lambda \left(\sum_{j=1}^n x_j - K\right)^2$$

Expanding the squared term (recalling that $x_j^2 = x_j$ for binary variables):

$$H(x) = \sum_{j=1}^n \left[-c_j + \lambda(1 - 2K)\right] x_j + 2\lambda \sum_{j < k} x_j x_k + \lambda K^2$$

The constant term $\lambda K^2$ is omitted during minimization. The final upper-triangular QUBO matrix $Q'$ is:

$$Q'[j,j] = -c_j + \lambda(1 - 2K)$$
$$Q'[j,k] = 2\lambda \quad (j < k)$$

### 4. Parameter Calibration
* **Penalty Weight ($\lambda$)**: The minimum $\lambda$ required to ensure all feasible solutions out-compete infeasible solutions is determined by the worst-case violation (a 4-station placement). For our 8-zone, $K=3$ problem:
  $$\Delta = c_{Z1} = 5.2847 \implies \lambda_{\text{min}} \approx 5.29$$
  We set **$\lambda = 10.0$** to guarantee a robust energy gap.
* **QAOA Solver**: Uses the Qiskit Aer `AerSimulator` coupled with a COBYLA optimizer (maximum 500 iterations). Supports adjustable circuit depth (`reps`), `shots` per step, and random `seed` for deterministic optimization paths.

---

## API Endpoints Reference

Base URL: `http://localhost:8000/api/v1`

### 1. Liveness Probe
* **Endpoint**: `GET /health`
* **Response**:
```json
{
  "status": "ok",
  "service": "EVision API",
  "version": "0.1.0",
  "timestamp": "2026-08-26T20:30:00+00:00"
}
```

### 2. Cache Readiness Check
* **Endpoint**: `GET /status`
* **Response**:
```json
{
  "status": "ok",
  "cache_ready": true,
  "message": "Pipeline cache is warm — next /optimize call will be fast."
}
```

### 3. Run Optimization Pipeline
* **Endpoint**: `POST /optimize`
* **Request Body**:
```json
{
  "reps": 1,
  "shots": 2048,
  "seed": 42
}
```
* **Response**:
```json
{
  "pipeline_runtime_s": 0.421,
  "demand_prediction": {
    "model": "RandomForestRegressor",
    "test_r2": 0.621,
    "test_mae": 284.14,
    "test_split_start": "2023-01-20T00:00:00",
    "test_split_end": "2023-02-28T23:00:00",
    "prediction_time_ms": 12.4,
    "predicted_demand": {
      "Z0": 3741.33,
      "Z1": 236.74,
      "Z2": 2182.11,
      "Z3": 1945.88,
      "Z4": 845.22,
      "Z5": 1102.54,
      "Z6": 724.89,
      "Z7": 1341.22
    }
  },
  "qubo": {
    "n_qubits": 8,
    "budget_k": 3,
    "lambda": 10.0,
    "c_values": {
      "Z0": 27.95,
      "Z1": 5.28,
      "Z2": 19.45,
      "Z3": 15.22,
      "Z4": 11.20,
      "Z5": 8.74,
      "Z6": 6.12,
      "Z7": 10.82
    },
    "global_minimum_energy": -139.697448
  },
  "classical": {
    "method": "classical_exhaustive",
    "selected_zones": ["Z0", "Z2", "Z3"],
    "qubo_energy": -139.697448,
    "feasible": true,
    "n_stations": 3,
    "covered_demand_kwh_h": 7869.32,
    "coverage_pct": 64.92,
    "runtime_s": 0.0012
  },
  "qaoa": {
    "method": "qaoa_aer_simulator",
    "reps": 1,
    "seed": 42,
    "shots": 2048,
    "selected_zones": ["Z0", "Z2", "Z3"],
    "best_bitstring": "10110000",
    "qubo_energy": -139.697448,
    "feasible": true,
    "n_stations": 3,
    "success_probability": 0.082,
    "circuit_depth": 14,
    "n_qubits": 8,
    "runtime_s": 0.284,
    "eigenvalue": -84.215,
    "optimal_parameters": [0.421, 0.812],
    "matches_qubo_optimum": true,
    "energy_gap": 0.0
  },
  "recommendation": {
    "selected_zones": ["Z0", "Z2", "Z3"],
    "method": "qaoa_aer_simulator",
    "qubo_energy": -139.697448,
    "feasible": true,
    "n_stations": 3,
    "matches_qubo_optimum": true,
    "predicted_demand": {
      "Z0": 3741.33,
      "Z2": 2182.11,
      "Z3": 1945.88
    },
    "total_candidate_demand_kwh_h": 12122.03,
    "zone_details": [
      {
        "label": "Z0",
        "tazid": 1026,
        "longitude": 139.73,
        "latitude": 35.68,
        "predicted_demand_kwh_h": 3741.33,
        "qubo_c_value": 27.95,
        "selected": true
      }
    ]
  }
}
```

---

## Installation & Local Development

### Prerequisites
* Python 3.11 or 3.12 (For production compilation, 3.14 is pinned in the Render config)
* Node.js 20+

### Backend Setup
1. Navigate to the root directory and activate your virtual environment:
   ```bash
   source .venv/bin/activate
   ```
2. Install the requirements:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the local build script to engineer features and train the RandomForest baseline model:
   ```bash
   ./build.sh
   ```
4. Start the FastAPI Uvicorn development server:
   ```bash
   uvicorn backend.api.main:app --reload --port 8000
   ```
   * Live Interactive Docs: [http://localhost:8000/docs](http://localhost:8000/docs)
   * API Health Check: [http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health)

### Frontend Setup
1. Navigate to the `frontend/` directory:
   ```bash
   cd frontend
   ```
2. Install the Node packages:
   ```bash
   npm install
   ```
3. Start the Next.js development server:
   ```bash
   npm run dev
   ```
4. Open the application in your browser:
   * Local Link: [http://localhost:3000](http://localhost:3000)

---

## Render Cloud Deployment

QuantEV is configured to deploy directly to the **Render** cloud platform. 

* **Blueprint Config**: Evaluated via `render.yaml`.
* **Build Optimization**: Uses `build.sh` to install requirements and conditionally train the machine learning estimator on Render's ephemeral disk.
* **Lazy-Loading Cache**: The backend uses an in-memory cache to save the RandomForest model and parquet files. Rather than loading them at startup (which triggers high peak memory usage and OOMs on Render's 512 MiB free tier), the cache is populated **lazily** during the first `/optimize` API request.
