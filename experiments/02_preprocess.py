"""
02_preprocess.py
================
Reads raw UrbanEV zone-level data (read-only), fixes the one invalid coordinate
(TAZID 348), and writes three clean artefacts to data/processed/:

    zones_clean.csv          – 275-row zone metadata with all valid coordinates
    demand_hourly.parquet    – long-form hourly demand: one row per (time × zone)
    demand_hourly.csv        – same, CSV fallback for tooling that can't read Parquet

Coordinate fix for TAZID 348
-----------------------------
The raw zone-information.csv records (lon=0.0, lat=0.0) for TAZID 348.
The distance matrix already knows the true inter-zone distances, so we use the
three closest neighbours (by pre-computed Euclidean distance) as a 1/d weighted
mean to impute the missing centroid:

    Neighbour  dist (m)   lon           lat
    331          986.2    113.973509    22.527350
    330         1753.9    113.974616    22.534771
    1072        2540.0    113.945428    22.530248
    -----------------------------------------------
    Imputed              113.968239    22.530066

Usage
-----
    cd /path/to/EV
    .venv/bin/python experiments/02_preprocess.py

    # or with explicit paths:
    .venv/bin/python experiments/02_preprocess.py \
        --raw   data/raw/20220901-20230228_zone-cleaned-aggregated \
        --out   data/processed

Outputs (data/processed/)
--------------------------
zones_clean.csv
    TAZID, longitude, latitude, charge_count, area, perimeter,
    coord_imputed (bool flag)

demand_hourly.parquet  /  demand_hourly.csv
    time           – datetime64[ns], hourly
    zone_id        – int, Traffic Analysis Zone ID
    volume_kwh     – float, total energy delivered in the zone that hour (kWh)
    duration_h     – float, total active charging time (hours)
    occupancy      – float, raw occupied-pile count
    occ_norm       – float, occupancy / charge_count  (bounded [0,1] per zone)
    longitude      – float (imputed for zone 348)
    latitude       – float (imputed for zone 348)
    charge_count   – int, number of charging piles in the zone
    area_m2        – float, zone area in m²
    coord_imputed  – bool, True only for TAZID 348
"""

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ── logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def load_wide(path: Path, name: str) -> pd.DataFrame:
    """Load a wide-format zone CSV (rows = timestamps, cols = zone IDs)."""
    log.info("Loading %-12s  %s", name, path.name)
    df = pd.read_csv(path, parse_dates=["time"])
    log.info("  shape: %s", df.shape)
    return df


def wide_to_long(df: pd.DataFrame, value_name: str) -> pd.DataFrame:
    """
    Melt a wide-format demand file into long form.
    Input columns:  time | <zone_id> | <zone_id> | ...
    Output columns: time | zone_id (int) | <value_name>
    """
    long = df.melt(id_vars="time", var_name="zone_id", value_name=value_name)
    long["zone_id"] = long["zone_id"].astype(int)
    return long


def impute_coord_348(
    inf: pd.DataFrame,
    dist: pd.DataFrame,
    n_neighbors: int = 3,
) -> pd.DataFrame:
    """
    Replace (0.0, 0.0) for TAZID 348 with a 1/distance weighted mean of its
    n_neighbors nearest zones as measured by the pre-computed distance matrix.

    The raw data is NOT modified; we work on a copy returned from this function.
    """
    inf = inf.copy()
    bad_mask = (inf["longitude"] == 0) | (inf["latitude"] == 0)
    bad_zones = inf.loc[bad_mask, "TAZID"].tolist()

    if not bad_zones:
        log.info("No invalid coordinates found — nothing to impute.")
        inf["coord_imputed"] = False
        return inf

    log.info("Zones with invalid coordinates: %s", bad_zones)

    # distance.csv columns are zone IDs (as strings)
    for tazid in bad_zones:
        col = str(tazid)
        if col not in dist.columns:
            log.warning("TAZID %s not found in distance matrix — skipping.", tazid)
            continue

        # Sort by distance; exclude self (distance == 0)
        d_col = dist[col].copy()
        d_col.index = dist.columns.astype(int)  # zone IDs as int index
        d_col = d_col[d_col > 0].sort_values()
        nearest = d_col.head(n_neighbors)

        # Fetch coordinates for nearest neighbours
        neighbor_inf = inf[inf["TAZID"].isin(nearest.index)]

        weights = 1.0 / nearest.loc[neighbor_inf["TAZID"].values].values
        total_w = weights.sum()
        imp_lon = float((weights * neighbor_inf["longitude"].values).sum() / total_w)
        imp_lat = float((weights * neighbor_inf["latitude"].values).sum() / total_w)

        log.info(
            "  TAZID %d: imputed (lon=%.6f, lat=%.6f) from neighbours %s "
            "with distances %s",
            tazid,
            imp_lon,
            imp_lat,
            nearest.index.tolist(),
            [f"{v:.1f}m" for v in nearest.values],
        )

        idx = inf.index[inf["TAZID"] == tazid][0]
        inf.at[idx, "longitude"] = imp_lon
        inf.at[idx, "latitude"] = imp_lat

    inf["coord_imputed"] = inf["TAZID"].isin(bad_zones)
    return inf


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main(raw_dir: Path, out_dir: Path) -> None:
    # ── 0. Resolve paths ─────────────────────────────────────────────────────
    hour_dir = raw_dir / "charge_1hour"
    inf_path  = raw_dir / "zone-information.csv"
    dist_path = raw_dir / "distance.csv"

    for p in [hour_dir, inf_path, dist_path]:
        if not p.exists():
            log.error("Required path not found: %s", p)
            sys.exit(1)

    out_dir.mkdir(parents=True, exist_ok=True)

    # ── 1. Load raw zone metadata & distance matrix ──────────────────────────
    log.info("── Step 1: Load zone metadata ──────────────────────────────────")
    inf  = pd.read_csv(inf_path)
    dist = pd.read_csv(dist_path)
    log.info("  inf  shape: %s", inf.shape)
    log.info("  dist shape: %s", dist.shape)

    # ── 2. Fix TAZID 348 coordinate ──────────────────────────────────────────
    log.info("── Step 2: Impute invalid coordinate ───────────────────────────")
    zones = impute_coord_348(inf, dist, n_neighbors=3)

    # Sanity: no zeros remaining
    still_bad = zones[(zones["longitude"] == 0) | (zones["latitude"] == 0)]
    if not still_bad.empty:
        log.error("Imputation incomplete — zones still have 0-coords: %s",
                  still_bad["TAZID"].tolist())
        sys.exit(1)
    log.info("  All %d zones now have valid coordinates.", len(zones))

    # ── 3. Write zones_clean.csv ─────────────────────────────────────────────
    log.info("── Step 3: Write zones_clean.csv ───────────────────────────────")
    zones_out = zones.rename(columns={"area": "area_m2"})
    zones_out_path = out_dir / "zones_clean.csv"
    zones_out.to_csv(zones_out_path, index=False)
    log.info("  Saved: %s  (%d rows)", zones_out_path, len(zones_out))

    # ── 4. Load wide demand files ────────────────────────────────────────────
    log.info("── Step 4: Load hourly demand files ────────────────────────────")
    vol = load_wide(hour_dir / "volume.csv",    "volume")
    dur = load_wide(hour_dir / "duration.csv",  "duration")
    occ = load_wide(hour_dir / "occupancy.csv", "occupancy")

    # ── 5. Validate consistency ──────────────────────────────────────────────
    log.info("── Step 5: Validate consistency ────────────────────────────────")

    # Same timestamps
    for name, df in [("duration", dur), ("occupancy", occ)]:
        if not vol["time"].equals(df["time"]):
            log.error("Timestamp mismatch between volume and %s", name)
            sys.exit(1)
    log.info("  Timestamps consistent across all three files.")

    # Same zone columns
    vol_zones = set(vol.columns) - {"time"}
    dur_zones = set(dur.columns) - {"time"}
    occ_zones = set(occ.columns) - {"time"}
    if not (vol_zones == dur_zones == occ_zones):
        log.error("Zone column mismatch across demand files.")
        sys.exit(1)
    log.info("  Zone columns consistent: %d zones.", len(vol_zones))

    # Zone columns must match zones in inf
    inf_zone_ids = set(zones["TAZID"].astype(str))
    data_zone_ids = vol_zones
    extra = data_zone_ids - inf_zone_ids
    missing = inf_zone_ids - data_zone_ids
    if extra:
        log.warning("  Zones in demand data but not in inf (%d): %s",
                    len(extra), sorted(extra)[:10])
    if missing:
        log.warning("  Zones in inf but not in demand data (%d): %s",
                    len(missing), sorted(missing)[:10])
    log.info("  Zone cross-check complete.")

    # Null check
    for name, df in [("volume", vol), ("duration", dur), ("occupancy", occ)]:
        n_null = int(df.isnull().sum().sum())
        if n_null:
            log.warning("  %s has %d null values!", name, n_null)
        else:
            log.info("  %s: 0 nulls.", name)

    # ── 6. Melt to long form ─────────────────────────────────────────────────
    log.info("── Step 6: Melt to long form ───────────────────────────────────")
    vol_long = wide_to_long(vol, "volume_kwh")
    dur_long = wide_to_long(dur, "duration_h")
    occ_long = wide_to_long(occ, "occupancy")
    log.info("  vol_long shape: %s", vol_long.shape)

    # ── 7. Merge demand signals ───────────────────────────────────────────────
    log.info("── Step 7: Merge volume / duration / occupancy ─────────────────")
    demand = vol_long.merge(dur_long, on=["time", "zone_id"], how="inner")
    demand = demand.merge(occ_long,  on=["time", "zone_id"], how="inner")
    log.info("  demand shape after merge: %s", demand.shape)

    # ── 8. Join zone metadata ────────────────────────────────────────────────
    log.info("── Step 8: Join zone metadata ──────────────────────────────────")
    zone_cols = zones_out[
        ["TAZID", "longitude", "latitude", "charge_count", "area_m2",
         "coord_imputed"]
    ].rename(columns={"TAZID": "zone_id"})

    demand = demand.merge(zone_cols, on="zone_id", how="left")

    n_missing_meta = int(demand["longitude"].isnull().sum())
    if n_missing_meta:
        log.warning("  %d rows have no zone metadata after join!", n_missing_meta)
    else:
        log.info("  All rows matched to zone metadata.")

    # ── 9. Compute normalised occupancy ──────────────────────────────────────
    log.info("── Step 9: Compute occ_norm = occupancy / charge_count ─────────")
    demand["occ_norm"] = demand["occupancy"] / demand["charge_count"]
    # Clip to [0, 1] — values above 1.0 can occur when all piles are occupied
    # and rounding pushes slightly over; cap at 1 for model features
    demand["occ_norm"] = demand["occ_norm"].clip(upper=1.0)
    log.info("  occ_norm range: [%.4f, %.4f]", demand["occ_norm"].min(),
             demand["occ_norm"].max())

    # ── 10. Sort and finalise columns ────────────────────────────────────────
    log.info("── Step 10: Sort and finalise ───────────────────────────────────")
    demand = demand.sort_values(["time", "zone_id"]).reset_index(drop=True)

    col_order = [
        "time", "zone_id",
        "volume_kwh", "duration_h", "occupancy", "occ_norm",
        "longitude", "latitude", "charge_count", "area_m2",
        "coord_imputed",
    ]
    demand = demand[col_order]

    # ── 11. Final validation ─────────────────────────────────────────────────
    log.info("── Step 11: Final validation ────────────────────────────────────")
    expected_rows = len(vol_zones) * len(vol)  # zones × timestamps
    if len(demand) != expected_rows:
        log.error("  Row count mismatch: expected %d, got %d",
                  expected_rows, len(demand))
        sys.exit(1)

    n_null_final = int(demand.isnull().sum().sum())
    if n_null_final:
        null_by_col = demand.isnull().sum()
        log.warning("  Final null values: %s",
                    null_by_col[null_by_col > 0].to_dict())
    else:
        log.info("  No nulls in final dataset.")

    log.info("  Final shape       : %s", demand.shape)
    log.info("  Time range        : %s → %s",
             demand["time"].min(), demand["time"].max())
    log.info("  Unique zones      : %d", demand["zone_id"].nunique())
    log.info("  Unique timestamps : %d", demand["time"].nunique())
    log.info("  Imputed zones     : %d",
             demand[demand["coord_imputed"]]["zone_id"].nunique())

    # ── 12. Write outputs ────────────────────────────────────────────────────
    log.info("── Step 12: Write outputs ───────────────────────────────────────")

    parquet_path = out_dir / "demand_hourly.parquet"
    csv_path     = out_dir / "demand_hourly.csv"

    demand.to_parquet(parquet_path, index=False, engine="pyarrow"
                      if _has_pyarrow() else "fastparquet")
    log.info("  Saved: %s  (%.1f MB)", parquet_path,
             parquet_path.stat().st_size / 1e6)

    demand.to_csv(csv_path, index=False)
    log.info("  Saved: %s  (%.1f MB)", csv_path,
             csv_path.stat().st_size / 1e6)

    log.info("── Done ─────────────────────────────────────────────────────────")


def _has_pyarrow() -> bool:
    try:
        import pyarrow  # noqa: F401
        return True
    except ImportError:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(
        description="EVision — preprocess raw UrbanEV data into a clean "
                    "long-form hourly demand dataset."
    )
    parser.add_argument(
        "--raw",
        type=Path,
        default=repo_root / "data" / "raw" /
                "20220901-20230228_zone-cleaned-aggregated",
        help="Path to the raw zone-cleaned-aggregated directory.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=repo_root / "data" / "processed",
        help="Output directory for processed files.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    log.info("Raw dir : %s", args.raw)
    log.info("Out dir : %s", args.out)
    main(args.raw, args.out)
