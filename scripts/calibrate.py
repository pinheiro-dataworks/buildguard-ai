#!/usr/bin/env python
"""Calibrate probabilities, optimize thresholds, and quantify uncertainty
for the three champion models (Section 16/17/19).

Usage::

    uv run python scripts/calibrate.py
    make calibrate

Loads the already-trained champions from ``models/*_champion.joblib``
(produced by ``scripts/train.py`` / ``make train``) and regenerates the
same deterministic portfolio (same seed -> identical features/split), then
works on the **calibration** split only (Section 12 -- test stays
untouched):

- ``cost_overrun`` / ``schedule_delay``: compares raw vs. sigmoid vs.
  isotonic calibration (Section 16), then optimizes a business-cost
  threshold (Section 17) against `configs/business.yaml`'s cost matrix,
  using the *calibrated* probabilities. The calibrated model (or the raw
  champion, if calibration didn't help) replaces the saved artifact.
- ``final_cost``: fits a split-conformal interval (Section 19) around the
  champion's point predictions and checks its own coverage.

Every task's outcome is logged as one MLflow run and appended to
``reports/experiments/calibration_summary.json``.

**Not idempotent -- run ``make train`` first, every time.** Because the
calibrated model replaces the saved champion artifact in place, running
this script twice in a row calibrates an *already-calibrated* model a
second time, which silently produces a different (and wrong) comparison.
The intended flow (Section 24: Detect -> Investigate -> Validate data ->
Retrain candidate -> Compare vs. champion -> Approve -> Release) always
regenerates a fresh, uncalibrated candidate via ``scripts/train.py``
immediately before this script runs -- never calibrate the same artifact
twice.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from _common import (
    assemble_task_dataset,
    feature_columns,
    filter_by_split,
    load_training_dataset,
    positive_class_proba,
)
from buildguard.config import PROJECT_ROOT, load_base_config, load_business_config
from buildguard.models.calibration import evaluate_calibration_methods
from buildguard.models.thresholds import optimize_threshold
from buildguard.models.tracking import configure_tracking, get_git_sha, log_model_run
from buildguard.models.uncertainty import (
    empirical_coverage,
    fit_conformal_quantile,
    predict_interval,
)

logger = logging.getLogger(__name__)


def _calibrate_classification_task(
    task_name: str,
    label_column: str,
    models_dir: Path,
    calibration: pd.DataFrame,
    false_negative_cost: float,
    false_positive_cost: float,
    data_version: str,
) -> dict[str, Any]:
    cols = feature_columns(calibration, label_column)
    x_cal = calibration[cols]
    y_cal = calibration[label_column].astype(bool)

    model_path = models_dir / f"{task_name}_champion.joblib"
    champion = joblib.load(model_path)

    comparison = evaluate_calibration_methods(champion, x_cal, y_cal)
    calibrated_proba = positive_class_proba(comparison.calibrated_model, x_cal)
    threshold_result = optimize_threshold(
        y_cal, calibrated_proba, false_negative_cost, false_positive_cost
    )

    joblib.dump(comparison.calibrated_model, model_path)
    logger.info(
        "%s: calibration=%s, threshold=%.3f, expected_cost=%.2f, precision=%.3f, recall=%.3f",
        task_name,
        comparison.best_method,
        threshold_result.threshold,
        threshold_result.expected_cost,
        threshold_result.precision,
        threshold_result.recall,
    )

    log_model_run(
        run_name=f"{task_name}-calibration",
        params={
            "calibration_method": comparison.best_method,
            "threshold": threshold_result.threshold,
            "data_version": data_version,
        },
        metrics={
            f"brier_{method}": curve.brier_score for method, curve in comparison.curves.items()
        }
        | {
            "expected_business_cost": threshold_result.expected_cost,
            "precision": threshold_result.precision,
            "recall": threshold_result.recall,
        },
        model_path=model_path,
        tags={"task": task_name, "stage": "calibration_threshold"},
    )

    return {
        "task": task_name,
        "calibration_method": comparison.best_method,
        "brier_scores": {m: c.brier_score for m, c in comparison.curves.items()},
        "threshold": threshold_result.threshold,
        "expected_business_cost": threshold_result.expected_cost,
        "precision_at_threshold": threshold_result.precision,
        "recall_at_threshold": threshold_result.recall,
        "confusion_at_threshold": {
            "true_positives": threshold_result.true_positives,
            "false_positives": threshold_result.false_positives,
            "true_negatives": threshold_result.true_negatives,
            "false_negatives": threshold_result.false_negatives,
        },
    }


def _quantify_final_cost_uncertainty(
    models_dir: Path, calibration: pd.DataFrame, coverage: float, data_version: str
) -> dict[str, Any]:
    label_column = "final_cost_real"
    cols = feature_columns(calibration, label_column)
    x_cal = calibration[cols]
    y_cal = calibration[label_column].to_numpy()

    model_path = models_dir / "final_cost_champion.joblib"
    champion = joblib.load(model_path)
    point_prediction = champion.predict(x_cal)

    interval = fit_conformal_quantile(y_cal, point_prediction, coverage=coverage)
    lower, upper = predict_interval(point_prediction, interval)
    in_sample_coverage = empirical_coverage(y_cal, lower, upper)

    logger.info(
        "final_cost: target_coverage=%.2f, quantile=$%.0f, in-sample coverage=%.3f",
        coverage,
        interval.quantile,
        in_sample_coverage,
    )

    log_model_run(
        run_name="final_cost-uncertainty",
        params={"target_coverage": coverage, "data_version": data_version},
        metrics={
            "conformal_quantile": interval.quantile,
            "in_sample_coverage": in_sample_coverage,
        },
        tags={"task": "final_cost", "stage": "uncertainty"},
    )

    return {
        "task": "final_cost",
        "target_coverage": coverage,
        "conformal_quantile": interval.quantile,
        "in_sample_coverage": in_sample_coverage,
        "example_interval_width": 2 * interval.quantile,
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_base_config()
    business_cfg = load_business_config()
    data_version = get_git_sha()

    logger.info("Generating synthetic portfolio and feature table (seed=%s)...", cfg.seed)
    training_dataset = load_training_dataset(cfg)
    features, outcomes, assignment = (
        training_dataset.features,
        training_dataset.outcomes,
        training_dataset.assignment,
    )

    configure_tracking(cfg.paths.mlflow_tracking_uri, cfg.training.mlflow_experiment_name)
    models_dir = PROJECT_ROOT / cfg.paths.models_dir
    reports_dir = PROJECT_ROOT / cfg.paths.reports_dir / "experiments"
    reports_dir.mkdir(parents=True, exist_ok=True)

    cost_overrun_data = assemble_task_dataset(features, outcomes, "cost_overrun")
    cost_overrun_cal = filter_by_split(cost_overrun_data, assignment.calibration_project_ids)
    cost_overrun_result = _calibrate_classification_task(
        "cost_overrun",
        "cost_overrun",
        models_dir,
        cost_overrun_cal,
        business_cfg.cost_risk.false_negative_cost,
        business_cfg.cost_risk.false_positive_cost,
        data_version,
    )

    schedule_delay_data = assemble_task_dataset(features, outcomes, "schedule_delay")
    schedule_delay_cal = filter_by_split(schedule_delay_data, assignment.calibration_project_ids)
    schedule_delay_result = _calibrate_classification_task(
        "schedule_delay",
        "schedule_delay",
        models_dir,
        schedule_delay_cal,
        business_cfg.schedule_risk.false_negative_cost,
        business_cfg.schedule_risk.false_positive_cost,
        data_version,
    )

    final_cost_data = assemble_task_dataset(features, outcomes, "final_cost_real")
    final_cost_cal = filter_by_split(final_cost_data, assignment.calibration_project_ids)
    final_cost_result = _quantify_final_cost_uncertainty(
        models_dir, final_cost_cal, cfg.uncertainty.target_coverage, data_version
    )

    summary = {
        "git_sha": data_version,
        "tasks": {
            "cost_overrun": cost_overrun_result,
            "schedule_delay": schedule_delay_result,
            "final_cost": final_cost_result,
        },
    }
    summary_path = reports_dir / "calibration_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    logger.info("Calibration summary written to %s", summary_path)


if __name__ == "__main__":
    main()
