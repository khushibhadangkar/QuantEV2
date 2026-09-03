#!/usr/bin/env bash
# build.sh — Render build script
#
# 1. Install production-only Python dependencies (requirements-prod.txt)
# 2. Train the RandomForest pipeline if model artifacts are missing.
#    Model: n_estimators=50, max_depth=12 → ~2 MB on disk, ~390 MB RSS at runtime
#    Training takes ~5 s and stays well within Render free-tier build memory.
#
# The parquet training data (8.6 MB) is committed to the repo so this
# script is fully self-contained.

set -euo pipefail

echo "=== QuantEV build: $(date) ==="
echo "Python: $(python --version)"

# ── 1. Install production dependencies ───────────────────────────────────────
echo ""
echo "--- Installing production dependencies (requirements-prod.txt) ---"
pip install --upgrade pip --quiet
pip install -r requirements-prod.txt --quiet
echo "Dependencies installed."

# ── 2. Train model if artifacts are missing ──────────────────────────────────
MODELS_DIR="ai_model/models"
PIPELINE="$MODELS_DIR/feature_pipeline.joblib"
PARQUET="data/processed/demand_hourly.parquet"

if [ -f "$PIPELINE" ]; then
  echo ""
  echo "--- Model artifacts already present, skipping training ---"
  echo "  feature_pipeline.joblib: $(du -h "$PIPELINE" | cut -f1)"
else
  echo ""
  echo "--- Model artifacts missing — training RandomForest pipeline ---"
  echo "  Params: n_estimators=50, max_depth=12"
  echo "  Data  : $PARQUET ($(du -h "$PARQUET" | cut -f1))"

  if [ ! -f "$PARQUET" ]; then
    echo "ERROR: Training data not found at $PARQUET"
    echo "       The parquet file must be committed to the repository."
    exit 1
  fi

  mkdir -p "$MODELS_DIR"

  python - <<'PYEOF'
import logging, sys, time, json
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)

import joblib, pandas as pd, numpy as np
from pathlib import Path
from sklearn.ensemble import RandomForestRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import r2_score, mean_absolute_error

from ai_model.features import (
    build_features, chronological_split, FEATURE_COLS, TARGET_COL,
)

TAZIDS = [1026, 746, 716, 965, 706, 745, 744, 737]
MODELS = Path("ai_model/models")

t0 = time.perf_counter()

# Load filtered data
df = pd.read_parquet(
    "data/processed/demand_hourly.parquet",
    filters=[("zone_id", "in", TAZIDS)],
    dtype_backend="numpy_nullable",
)
feat = build_features(df); del df

train_df, val_df, test_df = chronological_split(feat); del feat

X_train = train_df[FEATURE_COLS].to_numpy(float)
y_train = train_df[TARGET_COL].to_numpy(float)
X_val   = val_df[FEATURE_COLS].to_numpy(float)
y_val   = val_df[TARGET_COL].to_numpy(float)
X_test  = test_df[FEATURE_COLS].to_numpy(float)
y_test  = test_df[TARGET_COL].to_numpy(float)

# Train slim model (fits in 512 MiB at inference time)
rf = RandomForestRegressor(
    n_estimators=50,
    max_depth=12,
    min_samples_leaf=4,
    max_features="sqrt",
    n_jobs=-1,
    random_state=42,
)
rf.fit(X_train, y_train)
elapsed = time.perf_counter() - t0

y_pred_test = rf.predict(X_test)
y_pred_val  = rf.predict(X_val)
r2_test  = r2_score(y_test, y_pred_test)
mae_test = mean_absolute_error(y_test, y_pred_test)
r2_val   = r2_score(y_val, y_pred_val)
mae_val  = mean_absolute_error(y_val, y_pred_val)

print(f"\nTraining complete in {elapsed:.1f}s")
print(f"  Val  R²={r2_val:.4f}  MAE={mae_val:.2f}")
print(f"  Test R²={r2_test:.4f}  MAE={mae_test:.2f}")
print(f"  Nodes: {sum(e.tree_.node_count for e in rf.estimators_):,}")

# Build pipeline (scaler is a no-op for RF but keeps API contract uniform)
pipe = Pipeline([("scaler", StandardScaler()), ("model", rf)])
pipe.fit(X_train, y_train)  # refit scaler on training data

joblib.dump(pipe, MODELS / "feature_pipeline.joblib", compress=3)
joblib.dump(rf,   MODELS / "baseline_rf.joblib",      compress=3)

# Write metrics
metrics = {
    "model": "RandomForestRegressor",
    "rf_params": {
        "n_estimators": 50, "max_depth": 12,
        "min_samples_leaf": 4, "max_features": "sqrt",
        "n_jobs": -1, "random_state": 42,
    },
    "train_time_s": round(elapsed, 2),
    "test_metrics": {"r2": round(r2_test, 6), "mae": round(mae_test, 4)},
    "val_metrics":  {"r2": round(r2_val,  6), "mae": round(mae_val,  4)},
    "note": "n_estimators=50 max_depth=12 for Render 512MiB free-tier.",
}
(MODELS / "metrics.json").write_text(json.dumps(metrics, indent=2))
print(f"\nArtifacts written to {MODELS}/")
for f in sorted(MODELS.iterdir()):
    print(f"  {f.name}: {f.stat().st_size/1e6:.2f} MB")
PYEOF

  echo ""
  echo "--- Model artifacts written ---"
fi

echo ""
echo "=== Build complete ==="
