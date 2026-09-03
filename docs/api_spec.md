# EVision API — Endpoint Specification (Draft)

Base URL: `http://localhost:8000/api/v1`

---

## GET /health

**Purpose:** Liveness probe.

**Response 200**
```json
{
  "status": "ok",
  "service": "EVision API",
  "version": "0.1.0",
  "timestamp": "2026-08-08T00:00:00+00:00"
}
```

---

## POST /predict  _(planned)_

**Purpose:** Run the ML model to produce demand scores for each zone.

**Request body**
```json
{
  "zones": [
    { "id": "zone_01", "features": { "population": 12000, "poi_count": 34, ... } }
  ]
}
```

**Response 200**
```json
{
  "predictions": [
    { "zone_id": "zone_01", "demand_score": 0.82 }
  ]
}
```

---

## POST /optimize  _(planned)_

**Purpose:** Run QAOA and classical solvers, return selected zones and comparison metrics.

**Request body**
```json
{
  "demand_scores": { "zone_01": 0.82, "zone_02": 0.54 },
  "budget": 3,
  "solver": "both"
}
```

**Response 200**
```json
{
  "qaoa": {
    "selected_zones": ["zone_01", "zone_03"],
    "objective_value": 1.74,
    "runtime_ms": 320
  },
  "classical": {
    "selected_zones": ["zone_01", "zone_03"],
    "objective_value": 1.74,
    "runtime_ms": 2
  }
}
```
