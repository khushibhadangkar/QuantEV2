"""
ai_model/train.py
===================
Trains a RandomForestRegressor baseline for next-hour EV charging demand
(volume_kwh) and persists the model, feature pipeline, and evaluation metrics.

Artefacts written to models/
-----------------------------
  baseline_rf.joblib        trained RandomForestRegressor
  feature_pipeline.joblib   sklearn Pipeline (StandardScaler → passthrough,
                             kept for future compatibility with linear models;
                             RF itself is scale-invariant, but the pipeline
                             wrapper lets the API call .transform() uniformly)
  metrics.json              MAE, RMSE, R² on val and test sets + split metadata

Usage (called from experiments/03_train_baseline.py)
-----------------------------------------------------
  from backend.ai.train import run
  run(parquet_path, models_dir)
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Dict, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from ai_model.features import (
    FEATURE_COLS,
    TARGET_COL,
    build_features,
    chronological_split,
)

log = logging.getLogger(__name__)

# ── Hyperparameters ────────────────────────────────────────────────────────────
RF_PARAMS: Dict = {
    "n_estimators":      50,
    "max_depth":         12,
    "min_samples_leaf":  4,
    "max_features":      "sqrt",
    "n_jobs":            -1,
    "random_state":      42,
}


# ─────────────────────────────────────────────────────────────────────────────
# Evaluation helpers
# ─────────────────────────────────────────────────────────────────────────────

def _evaluate(
    model: Pipeline,
    X: np.ndarray,
    y: np.ndarray,
    split_name: str,
) -> Dict[str, float]:
    """Return MAE, RMSE, R² for a given split."""
    y_pred = model.predict(X)
    mae  = float(mean_absolute_error(y, y_pred))
    rmse = float(np.sqrt(mean_squared_error(y, y_pred)))
    r2   = float(r2_score(y, y_pred))
    log.info(
        "  %-6s  MAE=%.4f  RMSE=%.4f  R²=%.4f",
        split_name, mae, rmse, r2,
    )
    return {"mae": mae, "rmse": rmse, "r2": r2}


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────

def run(parquet_path: Path, models_dir: Path) -> Dict:
    """
    Full pipeline: load → engineer features → split → train → evaluate → save.

    Returns the metrics dict so callers can inspect results programmatically.
    """
    models_dir.mkdir(parents=True, exist_ok=True)

    # ── 1. Load processed data ────────────────────────────────────────────────
    log.info("── Step 1: Load %s", parquet_path)
    df = pd.read_parquet(parquet_path)
    log.info("  Loaded: %s rows × %s cols", *df.shape)

    # ── 2. Build features ─────────────────────────────────────────────────────
    log.info("── Step 2: Feature engineering")
    feat = build_features(df)
    log.info("  Feature matrix: %s", feat.shape)

    # ── 3. Chronological split ────────────────────────────────────────────────
    log.info("── Step 3: Chronological split (70 / 15 / 15)")
    train_df, val_df, test_df = chronological_split(feat)

    # Extract arrays — feature matrix is already float32 for lag/rolling cols
    X_train = train_df[FEATURE_COLS].to_numpy(dtype=np.float32)
    y_train = train_df[TARGET_COL].to_numpy(dtype=np.float32)
    X_val   = val_df[FEATURE_COLS].to_numpy(dtype=np.float32)
    y_val   = val_df[TARGET_COL].to_numpy(dtype=np.float32)
    X_test  = test_df[FEATURE_COLS].to_numpy(dtype=np.float32)
    y_test  = test_df[TARGET_COL].to_numpy(dtype=np.float32)

    log.info(
        "  X_train: %s  X_val: %s  X_test: %s",
        X_train.shape, X_val.shape, X_test.shape,
    )

    # ── 4. Build sklearn Pipeline ─────────────────────────────────────────────
    # StandardScaler is included so the pipeline contract is consistent for the
    # FastAPI inference path. RF is scale-invariant so this is a no-op for the
    # tree, but keeps the API uniform if other estimators are swapped in later.
    log.info("── Step 4: Build pipeline")
    pipeline = Pipeline([
        ("scaler", StandardScaler()),
        ("model",  RandomForestRegressor(**RF_PARAMS)),
    ])
    log.info("  RF params: %s", RF_PARAMS)

    # ── 5. Train ──────────────────────────────────────────────────────────────
    log.info("── Step 5: Train RandomForestRegressor …")
    t0 = time.perf_counter()
    pipeline.fit(X_train, y_train)
    elapsed = time.perf_counter() - t0
    log.info("  Training complete in %.1f s", elapsed)

    # ── 6. Evaluate ───────────────────────────────────────────────────────────
    log.info("── Step 6: Evaluate")
    val_metrics  = _evaluate(pipeline, X_val,  y_val,  "val")
    test_metrics = _evaluate(pipeline, X_test, y_test, "test")

    # Feature importances (RF native)
    rf_model = pipeline.named_steps["model"]
    importances = dict(zip(FEATURE_COLS, rf_model.feature_importances_.round(6).tolist()))
    log.info("  Feature importances:")
    for feat_name, imp in sorted(importances.items(), key=lambda x: -x[1]):
        log.info("    %-20s %.4f", feat_name, imp)

    # ── 7. Assemble metrics payload ───────────────────────────────────────────
    metrics = {
        "model":           "RandomForestRegressor",
        "target":          TARGET_COL,
        "features":        FEATURE_COLS,
        "rf_params":       RF_PARAMS,
        "train_time_s":    round(elapsed, 2),
        "split": {
            "train_start":  str(train_df["time"].min()),
            "train_end":    str(train_df["time"].max()),
            "train_rows":   len(train_df),
            "val_start":    str(val_df["time"].min()),
            "val_end":      str(val_df["time"].max()),
            "val_rows":     len(val_df),
            "test_start":   str(test_df["time"].min()),
            "test_end":     str(test_df["time"].max()),
            "test_rows":    len(test_df),
        },
        "val_metrics":     val_metrics,
        "test_metrics":    test_metrics,
        "feature_importances": importances,
    }

    # ── 8. Save artefacts ─────────────────────────────────────────────────────
    log.info("── Step 7: Save artefacts to %s", models_dir)

    pipeline_path = models_dir / "feature_pipeline.joblib"
    model_path    = models_dir / "baseline_rf.joblib"
    metrics_path  = models_dir / "metrics.json"

    # Save the full pipeline (scaler + model together for clean inference)
    joblib.dump(pipeline, pipeline_path, compress=3)
    log.info("  Saved pipeline : %s  (%.1f MB)",
             pipeline_path, pipeline_path.stat().st_size / 1e6)

    # Also save the bare RF so it's easy to inspect without loading scaler
    joblib.dump(rf_model, model_path, compress=3)
    log.info("  Saved RF model : %s  (%.1f MB)",
             model_path, model_path.stat().st_size / 1e6)

    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2)
    log.info("  Saved metrics  : %s", metrics_path)

    log.info("── Done")
    log.info(
        "  Test  MAE=%.4f  RMSE=%.4f  R²=%.4f",
        test_metrics["mae"], test_metrics["rmse"], test_metrics["r2"],
    )

    return metrics
