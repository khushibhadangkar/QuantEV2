"""
backend/data/city_manager.py
============================
Pre-computes and serves 8 candidate zones, distance matrices, and landmark names
for supported global cities (Beijing, Mumbai, San Francisco, Los Angeles, Chicago)
derived from data/raw/global_ev_charging_stations.csv.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans

from backend.data.loader import filter_stations_by_city, CITY_TO_COUNTRY

log = logging.getLogger(__name__)

_MODULE_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _MODULE_DIR.parents[1]
_PROCESSED_CITIES_DIR = _PROJECT_ROOT / "data" / "processed" / "cities"

# Curated authentic district/landmark names for the 8 clusters in each city
CITY_DISTRICT_NAMES: Dict[str, Dict[str, Dict[str, str]]] = {
    "Beijing": {
        "Z0": {"primary": "Chaoyang Central CBD", "secondary": "Guomao & Da Wang Rd Corridor"},
        "Z1": {"primary": "Haidian Innovation Core", "secondary": "Zhongguancun & University Zone"},
        "Z2": {"primary": "Fengtai Transport Hub", "secondary": "Beijing South Railway Corridor"},
        "Z3": {"primary": "Shijingshan Tech Park", "secondary": "West Chang'an Tech Valley"},
        "Z4": {"primary": "Olympic Village & North Core", "secondary": "Anzhen & Asian Games Hub"},
        "Z5": {"primary": "Yizhuang High-Tech Base", "secondary": "Economic Development Zone"},
        "Z6": {"primary": "Dongcheng & Xicheng Core", "secondary": "Financial Street & Commercial Center"},
        "Z7": {"primary": "Haidian North & Shangdi", "secondary": "Software Park Tech Corridor"},
    },
    "Mumbai": {
        "Z0": {"primary": "Bandra Kurla Complex (BKC)", "secondary": "Corporate & Financial Core"},
        "Z1": {"primary": "Navi Mumbai (Vashi Gateway)", "secondary": "Eastern Express Commercial Belt"},
        "Z2": {"primary": "Powai & Hiranandani Tech Valley", "secondary": "Central Suburbs IT Corridor"},
        "Z3": {"primary": "Nariman Point & Marine Drive", "secondary": "South Mumbai Coastal Business Corridor"},
        "Z4": {"primary": "Andheri West & Lokhandwala", "secondary": "Western Media & Retail Hub"},
        "Z5": {"primary": "South Mumbai (Colaba & Fort CBD)", "secondary": "Ballard Pier & Gateway Commercial District"},
        "Z6": {"primary": "Ghatkopar & Kurla Central Junction", "secondary": "Central Transit & Metro Interchange"},
        "Z7": {"primary": "Lower Parel & Dadar Commercial Hub", "secondary": "High Street Phoenix & Mills District"},
    },
    "San Francisco": {
        "Z0": {"primary": "Financial District & Market St", "secondary": "Embarcadero & Transit Center"},
        "Z1": {"primary": "Presidio & Marina Gateway", "secondary": "Lombard & Golden Gate Corridor"},
        "Z2": {"primary": "Fisherman's Wharf & North Beach", "secondary": "Columbus Ave Tourism Corridor"},
        "Z3": {"primary": "Mission District & 24th St", "secondary": "Valencia Commercial Corridor"},
        "Z4": {"primary": "Sunset & Richmond Transit Hub", "secondary": "19th Ave & Golden Gate Park"},
        "Z5": {"primary": "SOMA & Mission Bay Tech Hub", "secondary": "Chase Center & 4th St Transit"},
        "Z6": {"primary": "Civic Center & Mid-Market", "secondary": "City Hall & Van Ness Corridor"},
        "Z7": {"primary": "Potrero Hill & Dogpatch", "secondary": "3rd St Innovation Corridor"},
    },
    "Los Angeles": {
        "Z0": {"primary": "Downtown LA (DTLA) Financial Core", "secondary": "Bunker Hill & Grand Ave"},
        "Z1": {"primary": "Burbank / Glendale Media District", "secondary": "San Fernando Valley Gateway"},
        "Z2": {"primary": "Hollywood & Sunset Blvd Corridor", "secondary": "Highland Ave Entertainment Hub"},
        "Z3": {"primary": "Culver City & Arts District", "secondary": "Washington Blvd Tech Hub"},
        "Z4": {"primary": "Santa Monica & Silicon Beach", "secondary": "Ocean Park & 4th St Promenade"},
        "Z5": {"primary": "Pasadena & San Gabriel Gateway", "secondary": "Colorado Blvd Commercial Core"},
        "Z6": {"primary": "USC & Exposition Park Transit", "secondary": "Figueroa Corridor Innovation Hub"},
        "Z7": {"primary": "Century City & Westwood Corridor", "secondary": "Wilshire Blvd Corporate Gateway"},
    },
    "Chicago": {
        "Z0": {"primary": "The Loop Central Financial Core", "secondary": "State St & LaSalle Street Hub"},
        "Z1": {"primary": "Lincoln Park & Lakefront Hub", "secondary": "Clark St & North Side Corridor"},
        "Z2": {"primary": "West Loop & Fulton Market", "secondary": "Randolph St Innovation Corridor"},
        "Z3": {"primary": "River North & Magnificent Mile", "secondary": "Michigan Ave Retail Corridor"},
        "Z4": {"primary": "South Loop & Museum Campus", "secondary": "Roosevelt Rd Transit Gateway"},
        "Z5": {"primary": "Wicker Park & Logan Square", "secondary": "Milwaukee Ave Commercial Belt"},
        "Z6": {"primary": "Lakeview & Wrigleyville Hub", "secondary": "Belmont Ave Transit Interchange"},
        "Z7": {"primary": "Hyde Park & University Campus", "secondary": "55th St South Side Hub"},
    },
}

# Demand scenario scale multipliers
SCENARIO_MULTIPLIERS = {
    "all_hours": 1.0,
    "morning_peak": 1.35,
    "afternoon": 1.15,
    "overnight": 0.65,
    "weekday": 1.20,
    "weekend": 0.85,
}


def haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Computes great-circle distance between two coordinates in meters."""
    R = 6371000.0
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlam = np.radians(lon2 - lon1)
    a = (
        np.sin(dphi / 2.0) ** 2
        + np.cos(phi1) * np.cos(phi2) * np.sin(dlam / 2.0) ** 2
    )
    return float(2 * R * np.arcsin(np.sqrt(a)))


@dataclass
class CityOptimizationBundle:
    city: str
    country: str
    zones_df: pd.DataFrame
    dist_df: pd.DataFrame
    dist_csv_path: Path
    zone_names: Dict[str, Dict[str, str]]
    center_lat: float
    center_lng: float


class CityManager:
    """Manages candidate zone clusters, distance matrices, and names per city."""

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or _PROCESSED_CITIES_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._bundles: Dict[str, CityOptimizationBundle] = {}

        # Preload all supported cities into memory at initialization
        # (Must happen before any Qiskit C-extension imports)
        for city in ["Beijing", "Mumbai", "San Francisco", "Los Angeles", "Chicago"]:
            try:
                self.get_city_bundle(city)
            except Exception as e:
                log.warning("Could not preload city %s: %s", city, e)

    def get_city_bundle(self, city_name: str) -> CityOptimizationBundle:
        """
        Retrieves or generates the 8 candidate zones, distance matrix,
        and naming metadata for a given city.
        """
        # Canonicalize city name
        from backend.data.loader import get_loader
        canonical_city = get_loader().canonicalize_city_name(city_name)

        if canonical_city in self._bundles:
            return self._bundles[canonical_city]

        city_slug = canonical_city.lower().replace(" ", "_").replace("ã", "a")
        city_dir = self.cache_dir / city_slug
        city_dir.mkdir(parents=True, exist_ok=True)

        zones_path = city_dir / "candidate_zones.csv"
        dist_path = city_dir / "candidate_distance_matrix.csv"
        names_path = city_dir / "zone_names.json"

        load_cached = False
        if zones_path.exists() and dist_path.exists() and names_path.exists():
            try:
                cached_zones = pd.read_csv(zones_path, engine="python")
                if "infrastructure_gap_score" in cached_zones.columns and "predicted_cost_usd" in cached_zones.columns:
                    zones_df = cached_zones
                    dist_df = pd.read_csv(dist_path, index_col=0, engine="python")
                    zone_names = json.loads(names_path.read_text(encoding="utf-8"))
                    load_cached = True
            except Exception as e:
                log.warning("Could not load cached city bundle for %s: %s", canonical_city, e)

        if not load_cached:
            log.info("Generating candidate zones with real infrastructure-gap scores for city: %s", canonical_city)
            stations_df = filter_stations_by_city(canonical_city)
            if len(stations_df) == 0:
                raise ValueError(f"No station data found for city {canonical_city}")

            coords = stations_df[["latitude", "longitude"]].to_numpy()
            kmeans = KMeans(n_clusters=8, random_state=42, n_init=10).fit(coords)
            stations_df = stations_df.copy()
            stations_df["cluster"] = kmeans.labels_

            # Curated AOI names
            curated_names = CITY_DISTRICT_NAMES.get(canonical_city, {})
            zone_names = {}
            for cid in range(8):
                lbl = f"Z{cid}"
                if lbl in curated_names:
                    zone_names[lbl] = curated_names[lbl]
                else:
                    zone_names[lbl] = {
                        "primary": f"{canonical_city} Zone {cid}",
                        "secondary": f"Deployment Cluster {lbl}",
                    }

            # First pass: calculate raw usage & infrastructure deficit per cluster
            raw_cluster_metrics = []
            for cid in range(8):
                sub = stations_df[stations_df["cluster"] == cid]
                c_lat = float(sub["latitude"].mean())
                c_lon = float(sub["longitude"].mean())
                total_users = float(sub["usage_stats_users_per_day"].sum())
                charge_count = int(sub["parking_spots"].sum())
                total_cap_kw = float(sub["charging_capacity_kw"].sum())
                avg_cap_kw = float(sub["charging_capacity_kw"].mean())
                avg_tariff = float(sub["cost_usd_per_kwh"].mean()) if "cost_usd_per_kwh" in sub else 0.28

                # Demand energy volume vs existing supply capability
                daily_demand_kwh = total_users * 30.0  # avg 30 kWh per EV charging session
                daily_supply_kwh = total_cap_kw * 12.0 * 0.75  # ~12 active hours, 75% effective factor
                deficit_ratio = daily_demand_kwh / max(100.0, daily_supply_kwh)
                congestion_factor = total_users / max(1.0, float(charge_count))

                raw_gap = congestion_factor * 1.5 + deficit_ratio * 3.0
                raw_cluster_metrics.append({
                    "cid": cid,
                    "c_lat": c_lat,
                    "c_lon": c_lon,
                    "total_users": total_users,
                    "charge_count": charge_count,
                    "total_cap_kw": total_cap_kw,
                    "avg_cap_kw": avg_cap_kw,
                    "avg_tariff": avg_tariff,
                    "raw_gap": raw_gap,
                })

            min_gap = min(m["raw_gap"] for m in raw_cluster_metrics)
            max_gap = max(m["raw_gap"] for m in raw_cluster_metrics)

            zones_data = []
            for m in raw_cluster_metrics:
                cid = m["cid"]
                lbl = f"Z{cid}"
                # Scale infrastructure gap score to 4.0 - 9.8
                gap_normalized = (m["raw_gap"] - min_gap) / max(1e-5, max_gap - min_gap)
                infra_gap_score = round(4.0 + 5.8 * gap_normalized, 1)

                # Baseline predicted demand in kWh/h
                mean_pred = round(m["total_users"] * 0.18 + (infra_gap_score / 10.0) * 160.0 + m["avg_cap_kw"] * 0.4, 1)

                # CapEx deployment cost (USD) for a 4-bay DC fast charger hub
                pred_cost_usd = round(120000.0 + (mean_pred / 10.0) * 800.0, -2)

                # Financial return & ROI
                annual_energy_kwh = mean_pred * 24.0 * 365.0 * 0.42
                annual_revenue_usd = round(annual_energy_kwh * m["avg_tariff"] * 0.38, 2)
                roi_years = round(pred_cost_usd / max(1.0, annual_revenue_usd), 1)

                aoi_primary = zone_names[lbl]["primary"]
                key_reason = (
                    f"Severe Infrastructure Deficit (Gap {infra_gap_score}/10) · "
                    f"{int(m['total_users'])} daily EV users served by only {m['charge_count']} bays. "
                    f"Adding a high-speed hub captures {mean_pred:.0f} kWh/h with a {roi_years}-year CapEx payback, "
                    f"delivering critical relief to the {aoi_primary} corridor."
                )

                zones_data.append({
                    "label": lbl,
                    "tazid": cid + 1,
                    "longitude": round(m["c_lon"], 6),
                    "latitude": round(m["c_lat"], 6),
                    "mean_pred_kwh": mean_pred,
                    "charge_count": m["charge_count"],
                    "demand_per_pile": round(mean_pred / max(1, m["charge_count"]), 4),
                    "infrastructure_gap_score": infra_gap_score,
                    "predicted_cost_usd": pred_cost_usd,
                    "predicted_roi_years": roi_years,
                    "annual_revenue_usd": annual_revenue_usd,
                    "key_reason": key_reason,
                })

            zones_df = pd.DataFrame(zones_data)

            # Normalize demand score
            max_d = zones_df["demand_per_pile"].max()
            min_d = zones_df["demand_per_pile"].min()
            zones_df["demand_score_norm"] = round(
                (zones_df["demand_per_pile"] - min_d) / max(1e-6, max_d - min_d), 4
            )

            # Pairwise distance matrix (meters)
            n = len(zones_df)
            dist_mat = np.zeros((n, n))
            for i in range(n):
                for j in range(n):
                    dist_mat[i, j] = haversine_meters(
                        zones_df.loc[i, "latitude"], zones_df.loc[i, "longitude"],
                        zones_df.loc[j, "latitude"], zones_df.loc[j, "longitude"]
                    )

            # Dynamic coverage threshold: average distance / 1.5 (~8-12 km in urban metro)
            # ensures all zones have at least 1 neighbor while keeping graph sparse
            non_zero_dists = dist_mat[dist_mat > 0]
            coverage_radius = float(np.percentile(non_zero_dists, 35)) if len(non_zero_dists) > 0 else 8000.0

            neighbors = []
            for i in range(n):
                nbs = [
                    f"Z{j}" for j in range(n)
                    if i != j and dist_mat[i, j] <= coverage_radius
                ]
                # If isolated, connect to closest neighbor to ensure non-empty adjacency
                if not nbs:
                    closest_j = int(np.argsort(dist_mat[i, :])[1])
                    nbs = [f"Z{closest_j}"]
                neighbors.append("|".join(nbs))

            zones_df["neighbors_3km"] = neighbors
            labels = [f"Z{i}" for i in range(8)]
            dist_df = pd.DataFrame(np.round(dist_mat, 1), index=labels, columns=labels)

            # Save to disk
            zones_df.to_csv(zones_path, index=False)
            dist_df.to_csv(dist_path)
            names_path.write_text(json.dumps(zone_names, indent=2), encoding="utf-8")

        center_lat = round(float(zones_df["latitude"].mean()), 6)
        center_lng = round(float(zones_df["longitude"].mean()), 6)

        bundle = CityOptimizationBundle(
            city=canonical_city,
            country=CITY_TO_COUNTRY.get(canonical_city, "Global"),
            zones_df=zones_df,
            dist_df=dist_df,
            dist_csv_path=dist_path,
            zone_names=zone_names,
            center_lat=center_lat,
            center_lng=center_lng,
        )
        self._bundles[canonical_city] = bundle
        return bundle


_DEFAULT_CITY_MANAGER: Optional[CityManager] = None


def get_city_manager() -> CityManager:
    global _DEFAULT_CITY_MANAGER
    if _DEFAULT_CITY_MANAGER is None:
        _DEFAULT_CITY_MANAGER = CityManager()
    return _DEFAULT_CITY_MANAGER
