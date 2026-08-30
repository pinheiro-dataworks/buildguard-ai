#!/usr/bin/env python
"""Package trained/calibrated model artifacts for distribution (Section 25/33).

Usage::

    uv run python scripts/package_model.py

Bundles `models/*.joblib` with a `MANIFEST.json` -- Section 25's exact
metadata fields (`model_name, semantic_version, training_date,
data_version, git_sha, metrics, threshold, calibration_method`) per task
-- into `dist/buildguard-models-v{version}.tar.gz`, suitable as a GitHub
Release asset (Section 54: "packaged artifacts in-repo or as release
assets when size permits"). Reads real numbers only, from
`reports/experiments/{training,calibration}_summary.json` and (if
present) `test_set_metrics.json` -- never fabricates a metric that
doesn't already exist on disk from a real `make train`/`calibrate`/
`evaluate` run.
"""

from __future__ import annotations

import json
import logging
import tarfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import buildguard
from buildguard.config import PROJECT_ROOT, load_base_config
from buildguard.models.tracking import get_git_sha

logger = logging.getLogger(__name__)

CLASSIFICATION_TASKS = ("cost_overrun", "schedule_delay")


def _load_json(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def _classification_entry(
    task_name: str,
    packaged_at: str,
    training_summary: dict[str, Any],
    calibration_summary: dict[str, Any],
) -> dict[str, Any]:
    champion_family = training_summary["tasks"][task_name]["champion"]
    cal = calibration_summary["tasks"][task_name]
    method = cal["calibration_method"]
    return {
        "model_name": f"buildguard-{task_name.replace('_', '-')}",
        "semantic_version": buildguard.__version__,
        "family": champion_family,
        "training_date": packaged_at,
        "data_version": training_summary["git_sha"],
        "git_sha": calibration_summary["git_sha"],
        "threshold": cal["threshold"],
        "calibration_method": method,
        "metrics": {
            "calibration_auc": training_summary["tasks"][task_name]["champion_score"],
            "brier_score": cal["brier_scores"][method],
            "precision_at_threshold": cal["precision_at_threshold"],
            "recall_at_threshold": cal["recall_at_threshold"],
        },
    }


def _final_cost_entry(
    packaged_at: str, training_summary: dict[str, Any], calibration_summary: dict[str, Any]
) -> dict[str, Any]:
    champion_family = training_summary["tasks"]["final_cost"]["champion"]
    cal = calibration_summary["tasks"]["final_cost"]
    return {
        "model_name": "buildguard-final-cost",
        "semantic_version": buildguard.__version__,
        "family": champion_family,
        "training_date": packaged_at,
        "data_version": training_summary["git_sha"],
        "git_sha": calibration_summary["git_sha"],
        "calibration_method": "n/a (formula baseline, ADR-0006)",
        "metrics": {
            "calibration_mae": training_summary["tasks"]["final_cost"]["champion_score"],
            "target_coverage": cal["target_coverage"],
            "conformal_quantile": cal["conformal_quantile"],
        },
    }


def _build_manifest(experiments_dir: Path) -> dict[str, Any]:
    training_summary = _load_json(experiments_dir / "training_summary.json")
    calibration_summary = _load_json(experiments_dir / "calibration_summary.json")
    test_metrics_path = experiments_dir / "test_set_metrics.json"
    test_metrics = _load_json(test_metrics_path) if test_metrics_path.exists() else None

    packaged_at = datetime.now(UTC).isoformat()
    models: dict[str, Any] = {
        task: _classification_entry(task, packaged_at, training_summary, calibration_summary)
        for task in CLASSIFICATION_TASKS
    }
    models["final_cost"] = _final_cost_entry(packaged_at, training_summary, calibration_summary)

    if test_metrics is not None:
        for task_name, entry in models.items():
            entry["held_out_test_metrics"] = test_metrics["tasks"][task_name]["test_metrics"]

    return {
        "package_version": buildguard.__version__,
        "packaged_at": packaged_at,
        "data_version": get_git_sha(),
        "models": models,
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_base_config()
    models_dir = PROJECT_ROOT / cfg.paths.models_dir
    experiments_dir = PROJECT_ROOT / cfg.paths.reports_dir / "experiments"
    dist_dir = PROJECT_ROOT / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)

    manifest = _build_manifest(experiments_dir)
    manifest_path = dist_dir / "MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    logger.info("Wrote %s", manifest_path)

    archive_path = dist_dir / f"buildguard-models-v{buildguard.__version__}.tar.gz"
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(manifest_path, arcname="MANIFEST.json")
        for joblib_file in sorted(models_dir.glob("*.joblib")):
            tar.add(joblib_file, arcname=f"models/{joblib_file.name}")

    size_mb = archive_path.stat().st_size / (1024 * 1024)
    logger.info("Packaged %s (%.1f MB)", archive_path, size_mb)
    if size_mb > 100:
        logger.warning(
            "Package size %.1fMB exceeds Section 49's <100MB target -- "
            "consider excluding a model or compressing further.",
            size_mb,
        )


if __name__ == "__main__":
    main()
