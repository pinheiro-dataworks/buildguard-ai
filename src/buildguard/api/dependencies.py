"""Loads models and configuration once, shared across requests (Section 28/29).

`get_service_state()` is `lru_cache`d so the three champion artifacts and
the calibration decisions (threshold, calibration method, conformal
quantile) are read from disk exactly once per process, not once per
request -- reading a joblib-pickled sklearn pipeline on every call would
blow through Section 49's p95 < 500ms budget on its own. A cached function
that raises does *not* poison the cache in Python (the exception
propagates without being stored), so a request made before `make train` /
`make calibrate` have ever run fails cleanly and a later retry -- after
those complete -- succeeds without restarting the process.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib

import buildguard
from buildguard.config import PROJECT_ROOT, BaseAppConfig, load_base_config
from buildguard.data.economic_index import DemoIndexProvider, EconomicIndexProvider
from buildguard.models.tracking import get_git_sha


@dataclass(frozen=True)
class TaskArtifact:
    model: Any
    threshold: float
    calibration_method: str


@dataclass(frozen=True)
class ServiceState:
    cfg: BaseAppConfig
    index_provider: EconomicIndexProvider
    cost_overrun: TaskArtifact
    schedule_delay: TaskArtifact
    final_cost_model: Any
    conformal_quantile: float
    target_coverage: float
    model_version: str
    data_version: str


def _load_task_artifact(
    models_dir: Path, calibration_summary: dict[str, Any], task_name: str
) -> TaskArtifact:
    model = joblib.load(models_dir / f"{task_name}_champion.joblib")
    task_summary = calibration_summary["tasks"][task_name]
    return TaskArtifact(
        model=model,
        threshold=float(task_summary["threshold"]),
        calibration_method=str(task_summary["calibration_method"]),
    )


@lru_cache(maxsize=1)
def get_service_state() -> ServiceState:
    cfg = load_base_config()
    models_dir = PROJECT_ROOT / cfg.paths.models_dir
    experiments_dir = PROJECT_ROOT / cfg.paths.reports_dir / "experiments"

    if not (experiments_dir / "calibration_summary.json").exists():
        raise FileNotFoundError(
            "reports/experiments/calibration_summary.json not found -- run "
            "`make train && make calibrate` before starting the API."
        )
    calibration_summary = json.loads(
        (experiments_dir / "calibration_summary.json").read_text(encoding="utf-8")
    )

    index_provider = DemoIndexProvider(
        reference_date=cfg.synthetic_data.reference_date,
        history_years=cfg.synthetic_data.history_years,
    )

    final_cost_summary = calibration_summary["tasks"]["final_cost"]

    return ServiceState(
        cfg=cfg,
        index_provider=index_provider,
        cost_overrun=_load_task_artifact(models_dir, calibration_summary, "cost_overrun"),
        schedule_delay=_load_task_artifact(models_dir, calibration_summary, "schedule_delay"),
        final_cost_model=joblib.load(models_dir / "final_cost_champion.joblib"),
        conformal_quantile=float(final_cost_summary["conformal_quantile"]),
        target_coverage=float(final_cost_summary["target_coverage"]),
        model_version=buildguard.__version__,
        data_version=get_git_sha(),
    )
