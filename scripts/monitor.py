#!/usr/bin/env python
"""Data quality, drift, and performance monitoring (Section 23/24).

Usage::

    uv run python scripts/monitor.py
    make monitor

Everything Section 23 asks to be *implemented, not just documented*, run
against the real generated portfolio and the real trained/calibrated
champions -- never simulated drift on synthetic data invented just to make
a demo look interesting:

- **Data quality**: missing values, schema violations, unexpected
  categories, range violations, and duplicate keys on the Projects,
  Project Snapshots, and Change Orders tables (`buildguard.monitoring.data_quality`).
- **Feature drift**: PSI/KS/Wasserstein (numeric) and PSI (categorical)
  between the **train** split (reference) and the **test** split (current)
  -- the same two splits every other Section-18/47 comparison in this
  project already uses, standing in for "the next batch of production
  data" in the absence of real production history.
- **Prediction drift**: the same methods applied to model *outputs*
  (calibrated probabilities, predicted final cost) and to risk-band
  proportions, comparing the **calibration** split (reference -- what the
  threshold was tuned against) to the **test** split (current).
- **Performance monitoring**: reuses `buildguard.evaluation`'s metrics,
  comparing each task's **training-time calibration-split baseline**
  (`reports/experiments/training_summary.json` / `calibration_summary.json`)
  against its **genuinely held-out test-split result**
  (`reports/experiments/test_set_metrics.json`, Session J) -- this is a
  real comparison of two different runs, not a trivial self-comparison.
- **Operational monitoring**: real (not simulated) inference latency,
  timing repeated calls into each champion's own `predict`/`predict_proba`
  -- there is no deployed API yet (Phase 8), so there is no live request
  volume/error-rate to report yet; that half of this module activates once
  the FastAPI service exists and starts appending to the same log shape.
- **Retraining triggers** (Section 24): evaluates the triggers that can
  actually be computed from a single run (PSI above threshold, performance
  drop, calibration deterioration, schema violations) against the signals
  above. Two triggers Section 24 names -- new labeled-data volume and
  scheduled quarterly evaluation -- are calendar/volume-driven policy, not
  something one script run can evaluate; they are documented, not computed
  (see `docs/MONITORING.md`). **Never auto-retrains** -- this script only
  flags; the Detect -> Investigate -> Validate -> Retrain -> Compare ->
  Approve -> Release workflow past "Detect" is always a human decision.

Writes `reports/monitoring/monitoring_report.json`.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

import buildguard
from _common import (
    assemble_task_dataset,
    feature_columns,
    filter_by_split,
    load_training_dataset,
    positive_class_proba,
)
from buildguard.config import PROJECT_ROOT, MonitoringConfig, load_base_config
from buildguard.data import contracts
from buildguard.data.enums import ConstructionStandard, ProjectType, values
from buildguard.data.split import SplitAssignment
from buildguard.data.synthetic import PortfolioDataset
from buildguard.models.preprocessing import CATEGORICAL_FEATURE_COLUMNS, NUMERIC_FEATURE_COLUMNS
from buildguard.models.thresholds import risk_band
from buildguard.models.tracking import configure_tracking, get_git_sha, log_model_run
from buildguard.monitoring.data_quality import DataQualityReport, run_data_quality_checks
from buildguard.monitoring.drift import DriftResult, categorical_drift, drift_report, numeric_drift
from buildguard.monitoring.performance import (
    compare_classification_metrics,
    compare_regression_metrics,
    measure_inference_latency,
)

logger = logging.getLogger(__name__)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _run_data_quality(dataset: PortfolioDataset) -> dict[str, DataQualityReport]:
    project_categories = {
        "project_type": set(values(ProjectType)),
        "construction_standard": set(values(ConstructionStandard)),
    }
    return {
        "projects": run_data_quality_checks(
            dataset.projects,
            schema_validator=contracts.validate_projects,
            expected_categories=project_categories,
            key_columns=["project_id"],
        ),
        "snapshots": run_data_quality_checks(
            dataset.snapshots,
            schema_validator=contracts.validate_project_snapshots,
            key_columns=["project_id", "snapshot_date"],
        ),
        "change_orders": run_data_quality_checks(
            dataset.change_orders,
            schema_validator=contracts.validate_change_orders,
            key_columns=["change_order_id"],
        ),
    }


def _feature_drift(
    features: pd.DataFrame, assignment: SplitAssignment, monitoring_cfg: MonitoringConfig
) -> list[DriftResult]:
    reference = filter_by_split(features, assignment.train_project_ids)
    current = filter_by_split(features, assignment.test_project_ids)
    return drift_report(
        reference,
        current,
        list(NUMERIC_FEATURE_COLUMNS),
        list(CATEGORICAL_FEATURE_COLUMNS),
        monitoring_cfg.psi_warning_threshold,
        monitoring_cfg.psi_critical_threshold,
    )


def _prediction_drift_classification(
    task_name: str,
    label_column: str,
    models_dir: Path,
    features: pd.DataFrame,
    outcomes: pd.DataFrame,
    assignment: SplitAssignment,
    threshold: float,
    monitoring_cfg: MonitoringConfig,
) -> dict[str, Any]:
    data = assemble_task_dataset(features, outcomes, label_column)
    reference = filter_by_split(data, assignment.calibration_project_ids)
    current = filter_by_split(data, assignment.test_project_ids)
    cols = feature_columns(reference, label_column)

    champion = joblib.load(models_dir / f"{task_name}_champion.joblib")
    reference_proba = positive_class_proba(champion, reference[cols])
    current_proba = positive_class_proba(champion, current[cols])

    proba_drift = numeric_drift(
        "predicted_probability",
        pd.Series(reference_proba),
        pd.Series(current_proba),
        monitoring_cfg.psi_warning_threshold,
        monitoring_cfg.psi_critical_threshold,
    )
    reference_bands = pd.Series(risk_band(reference_proba, threshold))
    current_bands = pd.Series(risk_band(current_proba, threshold))
    band_drift = categorical_drift(
        "risk_band",
        reference_bands,
        current_bands,
        monitoring_cfg.psi_warning_threshold,
        monitoring_cfg.psi_critical_threshold,
    )

    return {
        "probability_drift": asdict(proba_drift),
        "risk_band_drift": asdict(band_drift),
        "calibration_split_band_proportions": reference_bands.value_counts(
            normalize=True
        ).to_dict(),
        "test_split_band_proportions": current_bands.value_counts(normalize=True).to_dict(),
    }


def _prediction_drift_final_cost(
    models_dir: Path,
    features: pd.DataFrame,
    outcomes: pd.DataFrame,
    assignment: SplitAssignment,
    monitoring_cfg: MonitoringConfig,
) -> dict[str, Any]:
    label_column = "final_cost_real"
    data = assemble_task_dataset(features, outcomes, label_column)
    reference = filter_by_split(data, assignment.calibration_project_ids)
    current = filter_by_split(data, assignment.test_project_ids)
    cols = feature_columns(reference, label_column)

    champion = joblib.load(models_dir / "final_cost_champion.joblib")
    reference_pred = champion.predict(reference[cols])
    current_pred = champion.predict(current[cols])

    drift = numeric_drift(
        "predicted_final_cost",
        pd.Series(reference_pred),
        pd.Series(current_pred),
        monitoring_cfg.psi_warning_threshold,
        monitoring_cfg.psi_critical_threshold,
    )
    return {"predicted_cost_drift": asdict(drift)}


def _performance_monitoring(
    training_summary: dict[str, Any],
    calibration_summary: dict[str, Any],
    test_metrics: dict[str, Any],
    monitoring_cfg: MonitoringConfig,
) -> dict[str, Any]:
    results: dict[str, Any] = {}

    for task_name in ("cost_overrun", "schedule_delay"):
        champion = training_summary["tasks"][task_name]["champion"]
        cal_method = calibration_summary["tasks"][task_name]["calibration_method"]
        baseline = {
            "roc_auc": training_summary["tasks"][task_name]["candidates"][champion][
                "calibration_auc"
            ],
            "brier_score": calibration_summary["tasks"][task_name]["brier_scores"][cal_method],
            "recall": calibration_summary["tasks"][task_name]["recall_at_threshold"],
        }
        current = {
            "roc_auc": test_metrics["tasks"][task_name]["test_metrics"]["roc_auc"],
            "brier_score": test_metrics["tasks"][task_name]["test_metrics"]["brier_score"],
            "recall": test_metrics["tasks"][task_name]["test_metrics"]["recall"],
        }
        comparisons = compare_classification_metrics(
            baseline, current, monitoring_cfg.performance_drop_threshold
        )
        results[task_name] = {
            "baseline": baseline,
            "current": current,
            "comparisons": [asdict(c) for c in comparisons],
        }

    champion = training_summary["tasks"]["final_cost"]["champion"]
    baseline = {
        "mae": training_summary["tasks"]["final_cost"]["candidates"][champion]["calibration_mae"]
    }
    current = {"mae": test_metrics["tasks"]["final_cost"]["test_metrics"]["mae"]}
    comparisons = compare_regression_metrics(
        baseline, current, monitoring_cfg.performance_drop_threshold
    )
    results["final_cost"] = {
        "baseline": baseline,
        "current": current,
        "comparisons": [asdict(c) for c in comparisons],
    }
    return results


def _operational_monitoring(
    models_dir: Path,
    features: pd.DataFrame,
    outcomes: pd.DataFrame,
    assignment: SplitAssignment,
    data_version: str,
) -> dict[str, Any]:
    tasks = (
        ("cost_overrun", "cost_overrun", "predict_proba"),
        ("schedule_delay", "schedule_delay", "predict_proba"),
        ("final_cost", "final_cost_real", "predict"),
    )
    results: dict[str, Any] = {}
    for task_name, label_column, predict_attr in tasks:
        data = assemble_task_dataset(features, outcomes, label_column)
        test = filter_by_split(data, assignment.test_project_ids)
        cols = feature_columns(test, label_column)
        champion = joblib.load(models_dir / f"{task_name}_champion.joblib")
        predict_fn = getattr(champion, predict_attr)
        summary = measure_inference_latency(
            predict_fn, test[cols], task_name, buildguard.__version__, data_version, n_calls=100
        )
        results[task_name] = asdict(summary)
    return results


def _evaluate_retraining_triggers(
    data_quality: dict[str, DataQualityReport],
    feature_drift_results: list[DriftResult],
    performance: dict[str, Any],
) -> list[dict[str, Any]]:
    """Section 24's computable triggers, evaluated -- never acted on -- against this run's signals."""
    triggers: list[dict[str, Any]] = []

    drifted_columns = [d.column for d in feature_drift_results if d.psi_severity == "significant"]
    triggers.append(
        {
            "trigger": "psi_above_critical_threshold",
            "fired": bool(drifted_columns),
            "detail": f"{len(drifted_columns)} feature(s) significantly drifted: {drifted_columns}"
            if drifted_columns
            else "no feature exceeded the PSI critical threshold",
        }
    )

    degraded = [
        f"{task}.{c['metric_name']}"
        for task, result in performance.items()
        for c in result["comparisons"]
        if c["is_degraded"] and c["metric_name"] != "brier_score"
    ]
    triggers.append(
        {
            "trigger": "performance_drop_above_threshold",
            "fired": bool(degraded),
            "detail": f"degraded metrics: {degraded}"
            if degraded
            else "no performance metric degraded",
        }
    )

    calibration_degraded = [
        task
        for task, result in performance.items()
        for c in result["comparisons"]
        if c["metric_name"] == "brier_score" and c["is_degraded"]
    ]
    triggers.append(
        {
            "trigger": "calibration_deterioration",
            "fired": bool(calibration_degraded),
            "detail": f"calibration degraded for: {calibration_degraded}"
            if calibration_degraded
            else "no task's held-out Brier score degraded beyond threshold",
        }
    )

    schema_issues = [name for name, report in data_quality.items() if report.schema_violations]
    triggers.append(
        {
            "trigger": "schema_changes",
            "fired": bool(schema_issues),
            "detail": f"schema violations in: {schema_issues}"
            if schema_issues
            else "no schema violations",
        }
    )

    triggers.append(
        {
            "trigger": "new_labeled_data_volume_above_n",
            "fired": None,
            "detail": "calendar/volume-driven policy trigger, not computed by a single run -- see docs/MONITORING.md",
        }
    )
    triggers.append(
        {
            "trigger": "scheduled_quarterly_evaluation",
            "fired": None,
            "detail": "calendar-driven policy trigger, not computed by a single run -- see docs/MONITORING.md",
        }
    )

    return triggers


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_base_config()
    data_version = get_git_sha()

    logger.info("Generating synthetic portfolio and feature table (seed=%s)...", cfg.seed)
    training_dataset = load_training_dataset(cfg)
    dataset = training_dataset.raw
    features, outcomes, assignment = (
        training_dataset.features,
        training_dataset.outcomes,
        training_dataset.assignment,
    )

    configure_tracking(cfg.paths.mlflow_tracking_uri, cfg.training.mlflow_experiment_name)
    models_dir = PROJECT_ROOT / cfg.paths.models_dir
    reports_dir = PROJECT_ROOT / cfg.paths.reports_dir
    monitoring_dir = reports_dir / "monitoring"
    monitoring_dir.mkdir(parents=True, exist_ok=True)

    training_summary = _load_json(reports_dir / "experiments" / "training_summary.json")
    calibration_summary = _load_json(reports_dir / "experiments" / "calibration_summary.json")
    test_metrics = _load_json(reports_dir / "experiments" / "test_set_metrics.json")

    logger.info("Running data quality checks...")
    data_quality = _run_data_quality(dataset)
    for name, report in data_quality.items():
        logger.info("data quality (%s): clean=%s, n_rows=%d", name, report.is_clean, report.n_rows)

    logger.info("Running feature drift (train vs. test split)...")
    feature_drift_results = _feature_drift(features, assignment, cfg.monitoring)
    significant = [d.column for d in feature_drift_results if d.psi_severity == "significant"]
    logger.info(
        "feature drift: %d column(s) checked, %d significant",
        len(feature_drift_results),
        len(significant),
    )

    logger.info("Running prediction drift (calibration vs. test split)...")
    prediction_drift = {
        "cost_overrun": _prediction_drift_classification(
            "cost_overrun",
            "cost_overrun",
            models_dir,
            features,
            outcomes,
            assignment,
            calibration_summary["tasks"]["cost_overrun"]["threshold"],
            cfg.monitoring,
        ),
        "schedule_delay": _prediction_drift_classification(
            "schedule_delay",
            "schedule_delay",
            models_dir,
            features,
            outcomes,
            assignment,
            calibration_summary["tasks"]["schedule_delay"]["threshold"],
            cfg.monitoring,
        ),
        "final_cost": _prediction_drift_final_cost(
            models_dir, features, outcomes, assignment, cfg.monitoring
        ),
    }

    logger.info(
        "Comparing performance: calibration-split baseline vs. held-out test-split result..."
    )
    performance = _performance_monitoring(
        training_summary, calibration_summary, test_metrics, cfg.monitoring
    )
    for task_name, result in performance.items():
        for c in result["comparisons"]:
            logger.info(
                "%s.%s: baseline=%.4f current=%.4f degraded=%s",
                task_name,
                c["metric_name"],
                c["baseline_value"],
                c["current_value"],
                c["is_degraded"],
            )

    logger.info("Measuring real local inference latency (no live API yet -- Phase 8)...")
    operational = _operational_monitoring(models_dir, features, outcomes, assignment, data_version)
    for task_name, summary in operational.items():
        logger.info(
            "%s latency: p50=%.2fms p95=%.2fms (n=%d)",
            task_name,
            summary["latency_p50_ms"],
            summary["latency_p95_ms"],
            summary["n_predictions"],
        )

    triggers = _evaluate_retraining_triggers(data_quality, feature_drift_results, performance)
    fired = [t["trigger"] for t in triggers if t["fired"]]
    logger.info("Retraining triggers fired: %s", fired or "none")

    report = {
        "git_sha": data_version,
        "data_quality": {name: asdict(r) for name, r in data_quality.items()},
        "feature_drift": [asdict(d) for d in feature_drift_results],
        "prediction_drift": prediction_drift,
        "performance": performance,
        "operational": operational,
        "retraining_triggers": triggers,
    }
    report_path = monitoring_dir / "monitoring_report.json"
    report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    logger.info("Monitoring report written to %s", report_path)

    log_model_run(
        run_name="monitoring-run",
        params={"data_version": data_version},
        metrics={
            "n_significant_feature_drift": float(len(significant)),
            "n_retraining_triggers_fired": float(len(fired)),
        },
        tags={"stage": "monitoring"},
    )


if __name__ == "__main__":
    main()
