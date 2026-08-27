#!/usr/bin/env python
"""Train and select the three core BuildGuard AI models (Section 6/13/14/15/25).

Usage::

    uv run python scripts/train.py
    make train

For each task -- cost-overrun classification, schedule-delay
classification, final-cost regression:

1. Assemble the task dataset: every feature-table row of a *resolved*
   project (Section 11), joined to that project's single outcome label
   (`buildguard.data.labels`).
2. Restrict to the **train** split; tune `RandomForest` and LightGBM via
   Optuna with `GroupKFold` (grouped by `project_id`) cross-validation
   (Sections 12/14/15).
3. Fit the mandatory baselines (Section 13) and the tuned candidates, all
   on train only.
4. Evaluate every candidate on the **calibration** split -- never on test
   (Section 12) -- and select the champion by that metric.
5. Log every candidate as one MLflow run (Section 25); save the champion
   pipeline to ``models/``.
6. Write a human-readable comparison to ``reports/experiments/``.

The **test** split is never touched by this script -- it is reserved for
exactly one final evaluation in a later phase (calibration/threshold
optimization must happen first).
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import joblib
import pandas as pd
from sklearn.metrics import mean_absolute_error, roc_auc_score

from buildguard.config import PROJECT_ROOT, BaseAppConfig, load_base_config
from buildguard.data.economic_index import DemoIndexProvider
from buildguard.data.labels import resolve_outcomes
from buildguard.data.split import chronological_project_split, filter_by_split
from buildguard.data.synthetic import generate_portfolio
from buildguard.features.pipeline import build_feature_table
from buildguard.models import baselines as bl
from buildguard.models import classification, regression
from buildguard.models.tracking import configure_tracking, get_git_sha, log_model_run

logger = logging.getLogger(__name__)

TaskType = Literal["classification", "regression"]


@dataclass(frozen=True)
class TaskSpec:
    name: str
    task_type: TaskType
    label_column: str


TASKS: tuple[TaskSpec, ...] = (
    TaskSpec("cost_overrun", "classification", "cost_overrun"),
    TaskSpec("schedule_delay", "classification", "schedule_delay"),
    TaskSpec("final_cost", "regression", "final_cost_real"),
)

_NON_FEATURE_COLUMNS = {
    "project_id",
    "snapshot_date",
    "planned_start_date",
    "planned_completion_date",
}


def _assemble_task_dataset(
    features: pd.DataFrame, outcomes: pd.DataFrame, label_column: str
) -> pd.DataFrame:
    """Every feature row of a resolved project, joined to its single outcome label."""
    resolved = outcomes.loc[outcomes["is_resolved"], ["project_id", label_column]]
    return features.merge(resolved, on="project_id", how="inner")


def _classification_baselines(cpi_threshold: float) -> dict[str, Any]:
    return {
        "dummy": bl.DummyClassifierBaseline(),
        "logistic_regression": bl.LogisticRegressionBaseline(),
        "cpi_rule": bl.CpiRuleBaseline(threshold=cpi_threshold),
    }


def _regression_baselines() -> dict[str, Any]:
    return {
        "mean": bl.MeanRegressionBaseline(),
        "median": bl.MedianRegressionBaseline(),
        "deterministic_eac": bl.DeterministicEacBaseline(),
        "linear_regression": bl.LinearRegressionBaseline(),
    }


def _run_classification_task(
    task: TaskSpec, train: pd.DataFrame, calibration: pd.DataFrame, cfg: BaseAppConfig
) -> dict[str, Any]:
    feature_cols = [c for c in train.columns if c not in _NON_FEATURE_COLUMNS | {task.label_column}]
    x_train, y_train = train[feature_cols], train[task.label_column].astype(bool)
    x_cal, y_cal = calibration[feature_cols], calibration[task.label_column].astype(bool)
    groups_train = train["project_id"]

    results: dict[str, dict[str, Any]] = {}
    fitted: dict[str, Any] = {}

    for name, model in _classification_baselines(cfg.baselines.cpi_risk_threshold).items():
        model.fit(x_train, y_train)
        auc = float(roc_auc_score(y_cal, model.predict_proba(x_cal)))
        results[name] = {"params": {}, "calibration_auc": auc}
        fitted[name] = model

    for family in ("random_forest", "lightgbm"):
        tuning = classification.tune_classifier(
            family,  # type: ignore[arg-type]
            x_train,
            y_train,
            groups_train,
            n_trials=cfg.training.optuna_n_trials,
            n_splits=cfg.training.cv_splits,
            seed=cfg.seed,
        )
        model = classification.fit_classifier(
            family,
            tuning.best_params,
            x_train,
            y_train,
            seed=cfg.seed,  # type: ignore[arg-type]
        )
        auc = float(roc_auc_score(y_cal, model.predict_proba(x_cal)[:, 1]))
        results[family] = {
            "params": tuning.best_params,
            "cv_auc": tuning.best_cv_auc,
            "calibration_auc": auc,
        }
        fitted[family] = model

    champion = max(results, key=lambda k: results[k]["calibration_auc"])
    return {
        "task": task.name,
        "metric": "calibration_auc",
        "higher_is_better": True,
        "results": results,
        "champion": champion,
        "champion_score": results[champion]["calibration_auc"],
        "champion_model": fitted[champion],
    }


def _run_regression_task(
    task: TaskSpec, train: pd.DataFrame, calibration: pd.DataFrame, cfg: BaseAppConfig
) -> dict[str, Any]:
    feature_cols = [c for c in train.columns if c not in _NON_FEATURE_COLUMNS | {task.label_column}]
    x_train, y_train = train[feature_cols], train[task.label_column]
    x_cal, y_cal = calibration[feature_cols], calibration[task.label_column]
    groups_train = train["project_id"]

    results: dict[str, dict[str, Any]] = {}
    fitted: dict[str, Any] = {}

    for name, model in _regression_baselines().items():
        model.fit(x_train, y_train)
        mae = float(mean_absolute_error(y_cal, model.predict(x_cal)))
        results[name] = {"params": {}, "calibration_mae": mae}
        fitted[name] = model

    for family in ("random_forest", "lightgbm"):
        tuning = regression.tune_regressor(
            family,  # type: ignore[arg-type]
            x_train,
            y_train,
            groups_train,
            n_trials=cfg.training.optuna_n_trials,
            n_splits=cfg.training.cv_splits,
            seed=cfg.seed,
        )
        model = regression.fit_regressor(
            family,
            tuning.best_params,
            x_train,
            y_train,
            seed=cfg.seed,  # type: ignore[arg-type]
        )
        mae = float(mean_absolute_error(y_cal, model.predict(x_cal)))
        results[family] = {
            "params": tuning.best_params,
            "cv_mae": tuning.best_cv_mae,
            "calibration_mae": mae,
        }
        fitted[family] = model

    champion = min(results, key=lambda k: results[k]["calibration_mae"])
    return {
        "task": task.name,
        "metric": "calibration_mae",
        "higher_is_better": False,
        "results": results,
        "champion": champion,
        "champion_score": results[champion]["calibration_mae"],
        "champion_model": fitted[champion],
    }


def _log_task_to_mlflow(
    task_result: dict[str, Any], data_version: str, champion_model_path: Path
) -> None:
    task_name = task_result["task"]
    for candidate_name, candidate in task_result["results"].items():
        is_champion = candidate_name == task_result["champion"]
        metrics = {k: v for k, v in candidate.items() if k != "params" and isinstance(v, float)}
        log_model_run(
            run_name=f"{task_name}-{candidate_name}",
            params={"family": candidate_name, "data_version": data_version, **candidate["params"]},
            metrics=metrics,
            model_path=champion_model_path if is_champion else None,
            tags={
                "task": task_name,
                "model_family": candidate_name,
                "champion": str(is_champion),
            },
        )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_base_config()
    data_version = get_git_sha()

    logger.info("Generating synthetic portfolio (seed=%s)...", cfg.seed)
    dataset = generate_portfolio(cfg)
    provider = DemoIndexProvider(
        reference_date=cfg.synthetic_data.reference_date,
        history_years=cfg.synthetic_data.history_years,
    )

    logger.info("Building leakage-safe feature table...")
    features = build_feature_table(
        dataset.projects, dataset.snapshots, dataset.change_orders, provider, cfg.features
    )
    outcomes = resolve_outcomes(
        dataset.projects,
        dataset.snapshots,
        provider,
        cfg.targets.cost_overrun_tolerance,
        cfg.targets.schedule_delay_tolerance_days,
    )
    logger.info(
        "%d / %d projects resolved (have a ground-truth outcome)",
        int(outcomes["is_resolved"].sum()),
        len(outcomes),
    )

    assignment = chronological_project_split(dataset.projects, cfg.split)

    configure_tracking(cfg.paths.mlflow_tracking_uri, cfg.training.mlflow_experiment_name)

    models_dir = PROJECT_ROOT / cfg.paths.models_dir
    models_dir.mkdir(parents=True, exist_ok=True)
    reports_dir = PROJECT_ROOT / cfg.paths.reports_dir / "experiments"
    reports_dir.mkdir(parents=True, exist_ok=True)

    summary: dict[str, Any] = {"git_sha": data_version, "seed": cfg.seed, "tasks": {}}

    for task in TASKS:
        logger.info("=== Task: %s (%s) ===", task.name, task.task_type)
        start = time.monotonic()

        task_data = _assemble_task_dataset(features, outcomes, task.label_column)
        train = filter_by_split(task_data, assignment.train_project_ids)
        calibration = filter_by_split(task_data, assignment.calibration_project_ids)
        logger.info("train rows=%d, calibration rows=%d", len(train), len(calibration))

        if task.task_type == "classification":
            result = _run_classification_task(task, train, calibration, cfg)
        else:
            result = _run_regression_task(task, train, calibration, cfg)

        elapsed = time.monotonic() - start
        logger.info(
            "Champion for %s: %s (%s=%.4f), %.1fs",
            task.name,
            result["champion"],
            result["metric"],
            result["champion_score"],
            elapsed,
        )

        model_path = models_dir / f"{task.name}_champion.joblib"
        joblib.dump(result["champion_model"], model_path)
        logger.info("Saved champion model to %s", model_path)

        _log_task_to_mlflow(result, data_version, model_path)

        summary["tasks"][task.name] = {
            "metric": result["metric"],
            "champion": result["champion"],
            "champion_score": result["champion_score"],
            "candidates": {name: dict(c) for name, c in result["results"].items()},
            "elapsed_seconds": round(elapsed, 1),
        }

    summary_path = reports_dir / "training_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    logger.info("Training summary written to %s", summary_path)


if __name__ == "__main__":
    main()
