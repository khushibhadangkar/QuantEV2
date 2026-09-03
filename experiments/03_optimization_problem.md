# EVision — Charger Placement: Candidate Zones

Zone 1026 (TAZID) anchors the cluster — highest demand-per-pile in the dataset
(48.6 kWh/pile/hour, 3 742 kWh/h absolute). The 7 nearest zones within 3 km
are selected as neighbours. All 8 zones are mutually reachable in the 3 km
proximity graph via at most one hop.

Source files:
- `data/processed/candidate_zones.csv`
- `data/processed/candidate_distance_matrix.csv`

---

## 1. The 8 candidate zones

| Label | TAZID | Longitude | Latitude | Mean predicted demand (kWh/h) | Existing piles | Demand / pile |
|:-----:|:-----:|----------:|----------:|------------------------------:|:--------------:|-------------:|
| **Z0** | **1026** | 114.080807 | 22.634883 | **3741.76** | 77 | **48.59** |
| Z1 | 746 | 114.072886 | 22.623009 | 236.74 | 115 | 2.06 |
| Z2 | 716 | 114.073896 | 22.609345 | 467.20 | 153 | 3.05 |
| Z3 | 965 | 114.098666 | 22.616885 | 383.59 | 129 | 2.97 |
| Z4 | 706 | 114.054821 | 22.633648 | 45.34 | 30 | 1.51 |
| Z5 | 745 | 114.060543 | 22.621869 | 38.94 | 28 | 1.39 |
| Z6 | 744 | 114.068025 | 22.649986 | 64.57 | 109 | 0.59 |
| Z7 | 737 | 114.084390 | 22.652124 | 20.51 | 36 | 0.57 |

Z0 is the only severely underserved zone (dpp = 48.6 vs. ≤ 3.1 for all others).
Total predicted demand across the cluster: **4 998.6 kWh/h**.

---

## 2. Pairwise distances (metres)

Euclidean distances between zone centroids, from the UrbanEV distance matrix.

|    |   Z0 |   Z1 |   Z2 |   Z3 |   Z4 |   Z5 |   Z6 |   Z7 |
|:--:|-----:|-----:|-----:|-----:|-----:|-----:|-----:|-----:|
| Z0 |    0 | 1547 | 2917 | 2709 | 2677 | 2534 | 2128 | 1945 |
| Z1 | 1547 |    0 | 1517 | 2737 | 2199 | 1275 | 3029 | 3435 |
| Z2 | 2917 | 1517 |    0 | 2682 | 3330 | 1951 | 4541 | 4860 |
| Z3 | 2709 | 2737 | 2682 |    0 | 4875 | 3959 | 4833 | 4170 |
| Z4 | 2677 | 2199 | 3330 | 4875 |    0 | 1431 | 2262 | 3665 |
| Z5 | 2534 | 1275 | 1951 | 3959 | 1431 |    0 | 3207 | 4152 |
| Z6 | 2128 | 3029 | 4541 | 4833 | 2262 | 3207 |    0 | 1699 |
| Z7 | 1945 | 3435 | 4860 | 4170 | 3665 | 4152 | 1699 |    0 |

---

## 3. Coverage relationships (3 km radius)

A zone is **covered** if a new station is placed within 3 km of it.
`A[i][j] = 1` means placing a station in j covers zone i.

**Coverage adjacency matrix** (1 = within 3 km, — = self):

|    | Z0 | Z1 | Z2 | Z3 | Z4 | Z5 | Z6 | Z7 |
|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| Z0 | — | 1 | 1 | 1 | 1 | 1 | 1 | 1 |
| Z1 | 1 | — | 1 | 1 | 1 | 1 | 0 | 0 |
| Z2 | 1 | 1 | — | 1 | 0 | 1 | 0 | 0 |
| Z3 | 1 | 1 | 1 | — | 0 | 0 | 0 | 0 |
| Z4 | 1 | 1 | 0 | 0 | — | 1 | 1 | 0 |
| Z5 | 1 | 1 | 1 | 0 | 1 | — | 0 | 0 |
| Z6 | 1 | 0 | 0 | 0 | 1 | 0 | — | 1 |
| Z7 | 1 | 0 | 0 | 0 | 0 | 0 | 1 | — |

**Per-zone coverage summary** — which station placements can cover each zone:

| Zone | Can be covered by stations placed in |
|:----:|--------------------------------------|
| Z0 | Z1, Z2, Z3, Z4, Z5, Z6, Z7 |
| Z1 | Z0, Z2, Z3, Z4, Z5 |
| Z2 | Z0, Z1, Z3, Z5 |
| Z3 | Z0, Z1, Z2 |
| Z4 | Z0, Z1, Z5, Z6 |
| Z5 | Z0, Z1, Z2, Z4 |
| Z6 | Z0, Z4, Z7 |
| Z7 | Z0, Z6 |

Key observations:
- **Z0 covers all 7 others** — it is the hub of the proximity graph.
- **Z7 is the most isolated** — reachable only from Z0 or Z6.
- **Z3 is reachable only from Z0, Z1, or Z2** — placing a station in Z1 or Z2 is the only way to cover Z3 without using Z0's slot.
- With budget K = 3, a single placement at Z0 already guarantees full coverage; the remaining 2 placements determine which high-demand zones also get direct stations.
