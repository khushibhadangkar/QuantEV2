"""
ai_model/features.py
======================
Feature engineering for hourly EV charging demand prediction.

Target: next-hour volume_kwh (i.e., volume_kwh shifted back by 1 row per zone,
        so each row's target is the demand in the *following* hour).

Features produced
-----------------
  Calendrical
    hour            int [0, 23]     hour of day
    day_of_week     int [0, 6]      Monday=0, Sunday=6
    is_weekend      int {0, 1}      Saturday/Sunday
    month           int [1, 12]

  Lag (per zone — computed within each zone group to prevent cross-zone leakage)
    lag_1h          float           volume_kwh 1 hour ago
    lag_24h         float           volume_kwh 24 hours ago
    lag_168h        float           volume_kwh 168 hours ago (1 week)

  Rolling window (per zone)
    rolling_mean_24h  float         mean volume_kwh over the trailing 24 hours
                                    (exclusive of the current hour, i.e. shift(1)
                                     before rolling, preventing leakage)

All lag/rolling operations are applied after sorting by [zone_id, time] and
computed strictly within each zone group so no zone's history bleeds into
another.  Rows with NaN features (the first 168 rows per zone) are dropped
before returning — those time-steps cannot safely be used for training or
evaluation.
"""

from __future__ import annotations

import logging
from typing import Tuple

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ── Public constants ──────────────────────────────────────────────────────────
FEATURE_COLS = [
    "hour",
    "day_of_week",
    "is_weekend",
    "month",
    "lag_1h",
    "lag_24h",
    "lag_168h",
    "rolling_mean_24h",
]
TARGET_COL = "target_volume_kwh"
KEY_COLS   = ["time", "zone_id"]      # retained alongside features for splitting


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Given the long-form demand frame (from demand_hourly.parquet), return a
    new DataFrame with FEATURE_COLS + TARGET_COL + KEY_COLS.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain at minimum: time (datetime64), zone_id (int),
        volume_kwh (float).

    Returns
    -------
    pd.DataFrame
        Rows with any NaN in features or target are dropped.
        Sorted by [zone_id, time].
    """
    log.info("Building features from %d rows across %d zones …",
             len(df), df.zone_id.nunique())

    # Work on a copy sorted by zone then time — mandatory for correct lags
    out = (
        df[["time", "zone_id", "volume_kwh"]]
        .copy()
        .sort_values(["zone_id", "time"])
        .reset_index(drop=True)
    )

    # ── Calendrical ──────────────────────────────────────────────────────────
    out["hour"]        = out["time"].dt.hour.astype(np.int8)
    out["day_of_week"] = out["time"].dt.dayofweek.astype(np.int8)
    out["is_weekend"]  = (out["day_of_week"] >= 5).astype(np.int8)
    out["month"]       = out["time"].dt.month.astype(np.int8)

    # ── Lag & rolling (per zone — groupby preserves sort order) ──────────────
    grp = out.groupby("zone_id", sort=False)["volume_kwh"]

    out["lag_1h"]   = grp.shift(1)
    out["lag_24h"]  = grp.shift(24)
    out["lag_168h"] = grp.shift(168)

    # rolling_mean_24h: mean of the 24 hours *before* the current hour
    # shift(1) moves the window entirely into the past → no leakage
    out["rolling_mean_24h"] = (
        grp.shift(1)
           .groupby(out["zone_id"])
           .transform(lambda s: s.rolling(window=24, min_periods=24).mean())
    )

    # ── Target: next-hour volume_kwh ─────────────────────────────────────────
    # shift(-1) per zone: target for row t is volume at t+1
    out[TARGET_COL] = grp.shift(-1)

    # ── Drop rows that cannot have complete features or a valid target ────────
    required = FEATURE_COLS + [TARGET_COL]
    n_before = len(out)
    out = out.dropna(subset=required).reset_index(drop=True)
    n_dropped = n_before - len(out)
    log.info("Dropped %d rows with NaN (lag warm-up + last step per zone). "
             "Remaining: %d", n_dropped, len(out))

    # Final column selection and dtype tightening
    out = out[KEY_COLS + FEATURE_COLS + [TARGET_COL]]
    out[FEATURE_COLS[:4]] = out[FEATURE_COLS[:4]].astype(np.int8)   # calendrical
    out[FEATURE_COLS[4:]] = out[FEATURE_COLS[4:]].astype(np.float32) # lag/rolling

    log.info("Feature matrix ready: %s", out.shape)
    return out


def chronological_split(
    feat: pd.DataFrame,
    train_frac: float = 0.70,
    val_frac:   float = 0.15,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Split feat into train / val / test using a strict chronological boundary
    on the **unique timestamp axis** — no zone's future leaks into another
    zone's training set.

    The boundary is computed on sorted unique timestamps, not on row indices,
    so the proportions are exact in time regardless of how many zones exist.

    Returns
    -------
    train_df, val_df, test_df  — all retain KEY_COLS + FEATURE_COLS + TARGET_COL
    """
    times = np.sort(feat["time"].unique())
    n = len(times)

    i_train = int(n * train_frac)
    i_val   = i_train + int(n * val_frac)

    t_train_end = times[i_train - 1]
    t_val_end   = times[i_val   - 1]

    train = feat[feat["time"] <= t_train_end].copy()
    val   = feat[(feat["time"] > t_train_end) & (feat["time"] <= t_val_end)].copy()
    test  = feat[feat["time"] > t_val_end].copy()

    log.info(
        "Chronological split on %d unique timestamps:\n"
        "  train : %s → %s  (%d timesteps, %d rows)\n"
        "  val   : %s → %s  (%d timesteps, %d rows)\n"
        "  test  : %s → %s  (%d timesteps, %d rows)",
        n,
        train["time"].min(), train["time"].max(),
        train["time"].nunique(), len(train),
        val["time"].min(),   val["time"].max(),
        val["time"].nunique(),   len(val),
        test["time"].min(),  test["time"].max(),
        test["time"].nunique(),  len(test),
    )

    # Sanity: no temporal overlap
    assert train["time"].max() < val["time"].min(), "Train/val overlap!"
    assert val["time"].max()   < test["time"].min(), "Val/test overlap!"

    return train, val, test
