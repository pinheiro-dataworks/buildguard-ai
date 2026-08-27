"""Experiment tracking (Section 25) -- MLflow, zero-cost local/file-based.

Wraps MLflow's SQLite-backed local tracking
(`configs/base.yaml: paths.mlflow_tracking_uri`) with BuildGuard-specific
conventions: every run is tagged with its git SHA, so a run recorded today
can always be traced back to the exact code that produced it (Section 25:
"Track run_id, model, params, features, data version, metrics, plots,
artifacts, duration, git SHA").

SQLite, not MLflow's raw filesystem store: MLflow's filesystem tracking
backend (`file:./mlruns`) is now in maintenance mode and raises unless
`MLFLOW_ALLOW_FILE_STORE=true` is explicitly set (discovered while
building this module). SQLite is equally local and zero-cost -- a single
`.db` file, no server -- and is the backend MLflow itself now recommends.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import mlflow

from buildguard.config import PROJECT_ROOT


def get_git_sha(*, short: bool = True) -> str:
    """Current git commit SHA, or ``"unknown"`` outside a repo / on error.

    Never raises -- a training run's experiment tracking must not fail
    just because git metadata happens to be unavailable.
    """
    args = ["git", "rev-parse", "--short", "HEAD"] if short else ["git", "rev-parse", "HEAD"]
    try:
        result = subprocess.run(
            args, cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=5, check=True
        )
        return result.stdout.strip()
    except Exception:
        return "unknown"


def configure_tracking(
    tracking_uri: str, experiment_name: str, artifact_location: str | None = None
) -> None:
    """Point MLflow at `tracking_uri` and select (creating if needed) `experiment_name`.

    `artifact_location` only takes effect the first time the experiment is
    created (MLflow ignores it on later calls) -- tests pass a
    temp-directory location so a `pytest` run never writes into the repo's
    real `mlruns/`; production callers leave it unset and get MLflow's
    default local artifact root.
    """
    mlflow.set_tracking_uri(tracking_uri)
    if mlflow.get_experiment_by_name(experiment_name) is None:
        mlflow.create_experiment(experiment_name, artifact_location=artifact_location)
    mlflow.set_experiment(experiment_name)


def log_model_run(
    *,
    run_name: str,
    params: dict[str, Any],
    metrics: dict[str, float],
    model_path: Path | str | None = None,
    tags: dict[str, str] | None = None,
) -> str:
    """Log one MLflow run: params, metrics, a `git_sha` tag, and optionally a model artifact.

    `model_path` (if given) is attached as a plain run artifact via
    `mlflow.log_artifact`, not `mlflow.sklearn.log_model` -- BuildGuard's
    baselines (`buildguard.models.baselines`) are custom wrapper classes,
    not raw sklearn estimators, and MLflow's sklearn flavor refuses to
    serialize them by default (skops' `UntrustedTypesFoundException`,
    hit while building this module: a `LogisticRegressionBaseline` won
    the cost-overrun task outright). Logging the already-joblib-dumped
    file sidesteps that entirely and works uniformly for baselines and
    real sklearn pipelines alike.

    Returns the new run's `run_id`. Requires `configure_tracking` to have
    been called first (or MLflow's own default tracking URI, which this
    module never assumes).
    """
    all_tags = {"git_sha": get_git_sha(), **(tags or {})}
    with mlflow.start_run(run_name=run_name) as run:
        mlflow.log_params(params)
        mlflow.log_metrics(metrics)
        mlflow.set_tags(all_tags)
        if model_path is not None:
            mlflow.log_artifact(str(model_path))
        run_id: str = run.info.run_id
        return run_id
