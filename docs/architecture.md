# QuantEV — Complete System Architecture & Directory Guide

QuantEV is an AI + Quantum Decision Intelligence platform that optimizes urban electric vehicle (EV) charging infrastructure. This document provides a complete directory map, architectural overview, and component breakdown.

---

## 1. High-Level System Architecture

```
                                    ┌──────────────────────────────────┐
                                    │    Frontend (Next.js 16 App)     │
                                    │  - GIS Leaflet Map               │
                                    │  - Planning Controls (K, Radius) │
                                    │  - Executive Tender Modal        │
                                    │  - Quantum Advantage Modal       │
                                    └─────────────────┬────────────────┘
                                                      │ REST API (JSON)
                                                      ▼
                                    ┌──────────────────────────────────┐
                                    │      Backend (FastAPI Engine)    │
                                    │  - /api/v1/optimize              │
                                    │  - /api/v1/cities                │
                                    │  - Optimizer Service Orchestrator│
                                    └────────┬──────────────┬──────────┘
                                             │              │
                   ┌─────────────────────────┘              └──────────────────────────┐
                   ▼                                                                   ▼
┌──────────────────────────────────────┐                             ┌──────────────────────────────────────┐
│        AI Demand Predictor           │                             │       Quantum Optimization Engine    │
│  - RandomForestRegressor Baseline    │                             │  - QUBO Matrix Formulation (qubo.py) │
│  - Temporal Lag & Rolling Pipeline   │ ──(Predicted Demands d_i)─► │  - QAOA Quantum Circuit (Sim & QPU)  │
│  - Output: kWh/h per candidate zone  │                             │  - Classical Baseline Solver         │
└──────────────────────────────────────┘                             └──────────────────┬───────────────────┘
                                                                                        │
                                                                                        ▼
                                                                     ┌──────────────────────────────────────┐
                                                                     │       Physical Quantum Cloud         │
                                                                     │  - IBM Quantum QPU: ibm_fez          │
                                                                     │  - 156-Qubit Heron Architecture      │
                                                                     │  - Qiskit IBM Runtime (SamplerV2)    │
                                                                     └──────────────────────────────────────┘
```

---

## 2. Master Directory & File Index

### 📁 `frontend/` — Next.js 16 Web Application
Interactive decision cockpit built with Next.js 16 (React 19), TypeScript, Leaflet GIS, and glassmorphic styling.

* **`src/app/`**:
  * [`page.tsx`](file:///Users/khushi/Downloads/QuantEV-main-2/frontend/src/app/page.tsx) — Main dashboard orchestrating state, maps, API polling, and modals.
  * [`layout.tsx`](file:///Users/khushi/Downloads/QuantEV-main-2/frontend/src/app/layout.tsx) — HTML shell, root metadata, and Inter typography imports.
  * [`globals.css`](file:///Users/khushi/Downloads/QuantEV-main-2/frontend/src/app/globals.css) — Custom dark-mode design system, glassmorphism, pulse animations, and GIS markers.
* **`src/components/`**:
  * [`ChargingMap.tsx`](file:///Users/khushi/Downloads/QuantEV-main-2/frontend/src/components/ChargingMap.tsx) — Interactive Leaflet GIS map with 3 km station coverage halos, heatmaps, and zone popups.
  * [`PlanningControls.tsx`](file:///Users/khushi/Downloads/QuantEV-main-2/frontend/src/components/PlanningControls.tsx) — Budget slider ($K=1..6$), solver mode selection (Quantum QAOA vs Classical), and run trigger.
  * [`ResultPanel.tsx`](file:///Users/khushi/Downloads/QuantEV-main-2/frontend/src/components/ResultPanel.tsx) — Real-time financial metrics (CapEx, OpEx, Revenue, Payback, IRR), selected sites, and energy stats.
  * [`QuantumAdvantageModal.tsx`](file:///Users/khushi/Downloads/QuantEV-main-2/frontend/src/components/QuantumAdvantageModal.tsx) — Deep-dive modal comparing Classical vs Quantum, scaling cliffs ($2.53 \times 10^{17}$), and tie-break metrics.
  * [`ExecutiveReportModal.tsx`](file:///Users/khushi/Downloads/QuantEV-main-2/frontend/src/components/ExecutiveReportModal.tsx) — Bankable municipal tender proposal and PDF/Markdown exporter.
  * [`CountryCitySelector.tsx`](file:///Users/khushi/Downloads/QuantEV-main-2/frontend/src/components/CountryCitySelector.tsx) — Multi-city switcher (Shenzhen, Delhi, London, New York).
  * [`OptimizationSequence.tsx`](file:///Users/khushi/Downloads/QuantEV-main-2/frontend/src/components/OptimizationSequence.tsx) — Real-time visual pipeline showing AI inference $\rightarrow$ QUBO $\rightarrow$ QAOA state.
* **`src/lib/` & `src/types/`**:
  * [`api.ts`](file:///Users/khushi/Downloads/QuantEV-main-2/frontend/src/lib/api.ts) — Typed fetch client connecting to FastAPI.
  * [`types/api.ts`](file:///Users/khushi/Downloads/QuantEV-main-2/frontend/src/types/api.ts) — TypeScript interfaces for optimization requests, responses, ROI metrics, and geographic zones.

---

### 📁 `backend/` — FastAPI REST API & Core Engine
Python 3.11 backend serving high-performance endpoints and managing solver pipelines.

* **`backend/api/`**:
  * [`main.py`](file:///Users/khushi/Downloads/QuantEV-main-2/backend/api/main.py) — FastAPI entry point, CORS middleware, lifespan events, and route mounting.
  * [`routers/optimize.py`](file:///Users/khushi/Downloads/QuantEV-main-2/backend/api/routers/optimize.py) — `/api/v1/optimize`, `/api/v1/cities`, `/api/v1/hardware-results` endpoints.
  * [`routers/health.py`](file:///Users/khushi/Downloads/QuantEV-main-2/backend/api/routers/health.py) — Liveness check (`/health`) and system info.
* **`backend/api/services/`**:
  * [`optimizer.py`](file:///Users/khushi/Downloads/QuantEV-main-2/backend/api/services/optimizer.py) — Orchestrates AI demand loading, QUBO building, solver dispatching, and financial ROI models.
* **`backend/data/`**:
  * [`city_manager.py`](file:///Users/khushi/Downloads/QuantEV-main-2/backend/data/city_manager.py) — Multi-city data loader and coordinate normalizer.
  * [`loader.py`](file:///Users/khushi/Downloads/QuantEV-main-2/backend/data/loader.py) — CSV and Parquet ingestion routines.
* **`backend/optimization/`**:
  * [`classical_solver.py`](file:///Users/khushi/Downloads/QuantEV-main-2/backend/optimization/classical_solver.py) — Classical exhaustive set-cover solver and proximity-weighted baseline.

---

### 📁 `ai_model/` — Predictive Demand Forecasting
Supervised machine learning pipeline forecasting next-hour charging volume per Traffic Analysis Zone.

* [`train.py`](file:///Users/khushi/Downloads/QuantEV-main-2/ai_model/train.py) — Training script for temporal train/val/test splits on 1.14M rows of Shenzhen mobility telemetry.
* [`features.py`](file:///Users/khushi/Downloads/QuantEV-main-2/ai_model/features.py) — Lag generator (`lag_1h`, `lag_24h`, `lag_168h`, `rolling_mean_24h`, cyclical hour/day).
* **`models/`**:
  * [`feature_pipeline.joblib`](file:///Users/khushi/Downloads/QuantEV-main-2/ai_model/models/feature_pipeline.joblib) — Serialized end-to-end transformer and model pipeline.
  * [`baseline_rf.joblib`](file:///Users/khushi/Downloads/QuantEV-main-2/ai_model/models/baseline_rf.joblib) — Trained Scikit-Learn `RandomForestRegressor`.
  * [`metrics.json`](file:///Users/khushi/Downloads/QuantEV-main-2/ai_model/models/metrics.json) — Evaluation metrics ($R^2 = 0.9330$, $\text{MAE} = 55.13$, feature importances).

---

### 📁 `quantum/` — Quantum QUBO Formulation
Formulates station placement as a physical energy minimization problem.

* [`qubo.py`](file:///Users/khushi/Downloads/QuantEV-main-2/quantum/qubo.py) — Constructs the upper-triangular matrix $Q'$, symmetric $Q_{\text{sym}}$, demand-proximity weights $c_j$, penalty parameter $\lambda = 10.0$, and Ising spin operator transformations.

---

### 📁 `experiments/` — Solvers, IBM Quantum Execution & Benchmarks
Stand-alone experimental pipeline documenting every development milestone.

* [`01_data_exploration.ipynb`](file:///Users/khushi/Downloads/QuantEV-main-2/experiments/01_data_exploration.ipynb) — Exploratory data analysis on Shenzhen electric taxi trajectories.
* [`02_preprocess.py`](file:///Users/khushi/Downloads/QuantEV-main-2/experiments/02_preprocess.py) — Data cleaning, TAZ aggregation, distance matrix calculation.
* [`03_optimization_problem.md`](file:///Users/khushi/Downloads/QuantEV-main-2/experiments/03_optimization_problem.md) — Mathematical specification of the 8 candidate zones around hub Z0.
* [`03_train_baseline.py`](file:///Users/khushi/Downloads/QuantEV-main-2/experiments/03_train_baseline.py) — Train baseline model script.
* [`04_classical_optimizer.py`](file:///Users/khushi/Downloads/QuantEV-main-2/experiments/04_classical_optimizer.py) — Classical exhaustive search across all $\binom{8}{3} = 56$ combinations.
* [`05_qaoa_simulator.py`](file:///Users/khushi/Downloads/QuantEV-main-2/experiments/05_qaoa_simulator.py) — QAOA implementation on Qiskit Aer local noiseless simulator.
* [`06_qaoa_validation.py`](file:///Users/khushi/Downloads/QuantEV-main-2/experiments/06_qaoa_validation.py) — 12-run parameter sweep testing reproducibility across depths $p=1,2,3$ and random seeds.
* [`07_qaoa_ibm_hardware.py`](file:///Users/khushi/Downloads/QuantEV-main-2/experiments/07_qaoa_ibm_hardware.py) — **Physical IBM Quantum execution** on `ibm_fez` (Heron 156Q QPU, Job `d9s2ebfpemts73ct7qqg`).
* [`07_quantum_classical_comparison.py`](file:///Users/khushi/Downloads/QuantEV-main-2/experiments/07_quantum_classical_comparison.py) — Cross-method evaluation comparing Classical, Simulator, and Hardware.
* [`08_end_to_end_pipeline.py`](file:///Users/khushi/Downloads/QuantEV-main-2/experiments/08_end_to_end_pipeline.py) — Unified pipeline testing AI $\rightarrow$ QUBO $\rightarrow$ QAOA.
* **`results/`**:
  * [`qaoa_ibm_results.json`](file:///Users/khushi/Downloads/QuantEV-main-2/experiments/results/qaoa_ibm_results.json) — Raw QPU bitstrings, shots, and physical execution telemetry.
  * [`quantum_classical_comparison.json`](file:///Users/khushi/Downloads/QuantEV-main-2/experiments/results/quantum_classical_comparison.json) — Full benchmarking comparison matrix.
  * [`qubo_summary.txt`](file:///Users/khushi/Downloads/QuantEV-main-2/experiments/results/qubo_summary.txt) — 256-state energy landscape and validation report.
  * [`classical_best.json`](file:///Users/khushi/Downloads/QuantEV-main-2/experiments/results/classical_best.json) — Winning output of the classical exhaustive solver.

---

### 📁 `data/` — Datasets
* **`raw/`**:
  * `detailed_ev_charging_stations.csv` — Geographic coordinates and attributes of charging facilities.
* **`processed/`**:
  * `candidate_zones.csv` — The 8 candidate urban zones with centroids and existing pile counts.
  * `candidate_distance_matrix.csv` — Pairwise Euclidean distance matrix (in meters).
  * `demand_hourly.parquet` — Aggregated time-series demand dataset for model training.
  * `cities/` — Processed candidate zones and distance matrices for international cities.

---

## 3. How to Run Each Component

### 1. Launch FastAPI Backend
```bash
source .venv/bin/activate
uvicorn backend.api.main:app --reload --port 8000
```
* Interactive OpenAPI Swagger Docs: [http://localhost:8000/docs](http://localhost:8000/docs)

### 2. Launch Next.js Frontend
```bash
cd frontend
npm run dev
```
* Dashboard UI: [http://localhost:3000](http://localhost:3000)

### 3. Run the AI Model Training
```bash
source .venv/bin/activate
python ai_model/train.py
```

### 4. Run Quantum Simulators and Hardware Scripts
* **QAOA Aer Simulator**:
  ```bash
  python experiments/05_qaoa_simulator.py --reps 1 2 3 --shots 4096
  ```
* **IBM Quantum Hardware Run (Requires IBM Quantum API Token)**:
  ```bash
  python experiments/07_qaoa_ibm_hardware.py --backend ibm_fez --shots 1024
  ```
* **Comparative Evaluation**:
  ```bash
  python experiments/07_quantum_classical_comparison.py
  ```

