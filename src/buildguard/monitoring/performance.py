"""Performance and operational monitoring (Section 23/24).

**Performance monitoring** deliberately reuses `buildguard.evaluation`'s
metric dataclasses rather than recomputing ROC-AUC/PR-AUC/Brier/MAE/RMSE a
second way (Section 27: no duplicated logic) -- this module only adds what
`evaluation/` doesn't have: comparing a `current` metric value against a
`baseline` one and flagging a degradation past a configured threshold,
which is the actual "performance drop > X%" retraining trigger Section 24
names.

**Operational monitoring** (inference latency, prediction count, errors)
has no live traffic to measure yet -- there is no deployed API until Phase
8. `measure_inference_latency` closes that gap honestly: it times real
(not simulated) repeated calls into an already-fitted model's own
`predict`/`predict_proba`, which is the same code path Phase 8's FastAPI
service will call per request, so the latency figures it reports now are
genuine local numbers against Section 49's "p95 < 500ms local CPU"
target -- not a placeholder. `PredictionLogEntry`/`summarize_operational_log`
are the aggregation half of the same story, ready for the API to append
real request-level entries to once it exists.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class PerformanceDrift:
    metric_name: str
    baseline_value: float
    current_value: float
    higher_is_better: bool
    relative_change: float
    is_degraded: bool


def compare_metric(
    metric_name: str,
    baseline_value: float,
    current_value: float,
    higher_is_better: bool,
    drop_threshold: float,
) -> PerformanceDrift:
    """Flag `current_value` as degraded if it moved against `baseline_value` by more than `drop_threshold` (relative).

    `drop_threshold` is a positive fraction (e.g. `0.05` for "more than 5%
    worse"), applied in whichever direction actually means "worse" for
    this metric -- a drop for ROC-AUC/PR-AUC/recall, a rise for
    Brier/MAE/RMSE.
    """
    if baseline_value == 0:
        relative_change = 0.0 if current_value == 0 else float("inf")
    else:
        relative_change = (current_value - baseline_value) / abs(baseline_value)
    degraded = (
        relative_change < -drop_threshold if higher_is_better else relative_change > drop_threshold
    )
    return PerformanceDrift(
        metric_name=metric_name,
        baseline_value=baseline_value,
        current_value=current_value,
        higher_is_better=higher_is_better,
        relative_change=relative_change,
        is_degraded=degraded,
    )


_CLASSIFICATION_METRIC_DIRECTIONS: dict[str, bool] = {
    "roc_auc": True,
    "pr_auc": True,
    "recall": True,
    "brier_score": False,
}
_REGRESSION_METRIC_DIRECTIONS: dict[str, bool] = {
    "mae": False,
    "rmse": False,
}


def compare_classification_metrics(
    baseline: dict[str, float], current: dict[str, float], drop_threshold: float
) -> list[PerformanceDrift]:
    return [
        compare_metric(name, baseline[name], current[name], higher_is_better, drop_threshold)
        for name, higher_is_better in _CLASSIFICATION_METRIC_DIRECTIONS.items()
        if name in baseline and name in current
    ]


def compare_regression_metrics(
    baseline: dict[str, float], current: dict[str, float], drop_threshold: float
) -> list[PerformanceDrift]:
    return [
        compare_metric(name, baseline[name], current[name], higher_is_better, drop_threshold)
        for name, higher_is_better in _REGRESSION_METRIC_DIRECTIONS.items()
        if name in baseline and name in current
    ]


@dataclass(frozen=True)
class PredictionLogEntry:
    model_name: str
    model_version: str
    data_version: str
    latency_ms: float
    error: str | None = None


@dataclass(frozen=True)
class OperationalSummary:
    n_predictions: int
    n_errors: int
    error_rate: float
    latency_p50_ms: float
    latency_p95_ms: float
    latency_p99_ms: float


def summarize_operational_log(entries: list[PredictionLogEntry]) -> OperationalSummary:
    if not entries:
        return OperationalSummary(0, 0, 0.0, 0.0, 0.0, 0.0)
    latencies = np.array([e.latency_ms for e in entries])
    n_errors = sum(1 for e in entries if e.error is not None)
    return OperationalSummary(
        n_predictions=len(entries),
        n_errors=n_errors,
        error_rate=n_errors / len(entries),
        latency_p50_ms=float(np.percentile(latencies, 50)),
        latency_p95_ms=float(np.percentile(latencies, 95)),
        latency_p99_ms=float(np.percentile(latencies, 99)),
    )


def measure_inference_latency(
    predict_fn: Callable[[pd.DataFrame], Any],
    sample_rows: pd.DataFrame,
    model_name: str,
    model_version: str,
    data_version: str,
    n_calls: int = 100,
) -> OperationalSummary:
    """Time `n_calls` real single-row `predict_fn` calls, cycling through `sample_rows`."""
    entries: list[PredictionLogEntry] = []
    n = len(sample_rows)
    for i in range(n_calls):
        row = sample_rows.iloc[[i % n]]
        start = time.perf_counter()
        error: str | None = None
        try:
            predict_fn(row)
        except Exception as exc:
            error = str(exc)
        latency_ms = (time.perf_counter() - start) * 1000
        entries.append(
            PredictionLogEntry(model_name, model_version, data_version, latency_ms, error)
        )
    return summarize_operational_log(entries)
