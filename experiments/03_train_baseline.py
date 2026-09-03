"""
experiments/03_train_baseline.py
=================================
CLI entry point for the EVision demand-prediction baseline.

Delegates all logic to backend.ai.train.run(); this script only handles
path resolution, logging setup, and the exit code.

Usage
-----
    # from repo root, with the venv active:
    .venv/bin/python experiments/03_train_baseline.py

    # override paths:
    .venv/bin/python experiments/03_train_baseline.py \
        --parquet data/processed/demand_hourly.parquet \
        --models  models/

Output artefacts (default: models/)
------------------------------------
    baseline_rf.joblib        bare RandomForestRegressor
    feature_pipeline.joblib   full sklearn Pipeline (scaler + RF)
    metrics.json              MAE / RMSE / R² on val + test sets
"""

import argparse
import logging
import sys
from pathlib import Path

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parent.parent
    p = argparse.ArgumentParser(
        description="Train the EVision RandomForest demand-prediction baseline."
    )
    p.add_argument(
        "--parquet",
        type=Path,
        default=repo_root / "data" / "processed" / "demand_hourly.parquet",
        help="Path to the processed demand parquet file.",
    )
    p.add_argument(
        "--models",
        type=Path,
        default=repo_root / "ai_model" / "models",
        help="Directory where artefacts (model, pipeline, metrics) are saved.",
    )
    return p.parse_args()


def main() -> int:
    args = _parse_args()

    if not args.parquet.exists():
        log.error("Parquet file not found: %s", args.parquet)
        log.error("Run experiments/02_preprocess.py first.")
        return 1

    log.info("Parquet : %s", args.parquet)
    log.info("Models  : %s", args.models)

    # Import here so module-level logging in train.py is already configured
    from ai_model.train import run

    metrics = run(args.parquet, args.models)

    # Print a clean summary to stdout regardless of log level
    print("\n" + "=" * 52)
    print("  EVision — Baseline Training Complete")
    print("=" * 52)
    tm = metrics["test_metrics"]
    vm = metrics["val_metrics"]
    print(f"  {'Split':<8}  {'MAE':>10}  {'RMSE':>10}  {'R²':>8}")
    print(f"  {'-'*40}")
    print(f"  {'val':<8}  {vm['mae']:>10.4f}  {vm['rmse']:>10.4f}  {vm['r2']:>8.4f}")
    print(f"  {'test':<8}  {tm['mae']:>10.4f}  {tm['rmse']:>10.4f}  {tm['r2']:>8.4f}")
    print("=" * 52)
    print(f"  Artefacts → {args.models}")
    print("=" * 52 + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
