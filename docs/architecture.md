# EVision — Architecture Notes

## Component Responsibilities

### `ai_model`
- Feature engineering from raw EV / geographic data
- Training and persisting a zone-level demand prediction model (scikit-learn)
- Inference: given zone features → predicted demand score (float 0–1)

### `backend/optimization`
- Classical station-placement solver
- Input: demand scores + zone adjacency graph + budget K (max stations)
- Algorithm: greedy top-K or scipy integer-programming baseline
- Output: list of selected zone IDs

### `quantum`
- QUBO formulation of the station-placement problem
- QAOA circuit construction via `qiskit.circuit` + `qiskit_optimization`
- Simulation via Qiskit Aer `AerSimulator` (statevector / shot-based)
- Output: list of selected zone IDs + energy landscape

### `backend/api`
- FastAPI app with versioned routes under `/api/v1/`
- Planned endpoints:
  - `GET  /health`           — liveness probe
  - `POST /predict`          — run ML demand prediction
  - `POST /optimize`         — run both solvers, return comparison payload
- Pydantic schemas for all request/response bodies
- CORS configured for Next.js dev server (port 3000)

### `frontend`
- Next.js 16 App Router, TypeScript, Tailwind CSS
- Leaflet map: render zones as GeoJSON polygons, colour-coded by demand score; markers for chosen stations
- Recharts: bar/line chart comparing QAOA vs classical objective value and runtime
- Fetches data from FastAPI via `NEXT_PUBLIC_API_BASE_URL`

## Key Design Decisions

| Decision | Rationale |
|---|---|
| QAOA on Aer simulator | No QPU access needed; statevector gives exact expectation values for small instances |
| Zone-level granularity | Keeps QUBO size tractable (< 20 binary variables for a hackathon demo) |
| Separate classical solver | Enables direct apples-to-apples comparison of quantum vs classical on the same problem |
| FastAPI over Flask | Native async, automatic OpenAPI docs, Pydantic validation |
| App Router (Next.js) | Server components + easy API route co-location if needed |
