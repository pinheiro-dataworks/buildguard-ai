"""Slice evaluation (Section 18).

A strong global metric can hide poor subgroup behavior -- Section 18 is
explicit that this must be *documented, not hidden*. `evaluate_by_slice()`
computes the same metric BuildGuard already reports globally (ROC-AUC for
the classifiers, MAE for `final_cost`) independently within each subgroup
of a slicing dimension: project type, construction standard, geography
(`city`/`state`, already in the feature table), lifecycle stage, and the
two derived dimensions this module adds -- project size and budget
segment (`bucket_by_quantile` on `gross_floor_area_m2` / `approved_budget`)
-- so a champion that looks strong in aggregate but fails on, say,
luxury-standard or small-budget projects is visible rather than averaged
away.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
import pandas as pd


@dataclass(frozen=True)
class SliceResult:
    slice_column: str
    slice_value: str
    n_rows: int
    metric_value: float | None
    """`None` when the slice has too few rows, or too little label
    variation (e.g. every row in the slice shares one class, which makes
    ROC-AUC undefined), to compute the metric meaningfully -- never a
    silently misleading number."""


def evaluate_by_slice(
    df: pd.DataFrame,
    slice_column: str,
    y_true: npt.NDArray[np.float64] | pd.Series,
    y_pred: npt.NDArray[np.float64] | pd.Series,
    metric_fn: Callable[[npt.NDArray[np.float64], npt.NDArray[np.float64]], float],
    min_slice_size: int = 20,
) -> list[SliceResult]:
    """Compute `metric_fn(y_true, y_pred)` independently within each value of `slice_column`.

    `y_true`/`y_pred` must be row-aligned with `df` (same length and
    order) -- typically the task's label column and the model's
    predict_proba/predict output on those same rows. Slices with fewer
    than `min_slice_size` rows, or on which `metric_fn` raises (e.g.
    `roc_auc_score` with only one class present), get `metric_value=None`.
    """
    working = df.copy()
    working["_slice_y_true"] = np.asarray(y_true)
    working["_slice_y_pred"] = np.asarray(y_pred)

    results: list[SliceResult] = []
    for value, group in working.groupby(slice_column, observed=True):
        n = len(group)
        if n < min_slice_size:
            results.append(SliceResult(slice_column, str(value), n, None))
            continue
        try:
            metric_value: float | None = float(
                metric_fn(
                    group["_slice_y_true"].to_numpy(),
                    group["_slice_y_pred"].to_numpy(),
                )
            )
        except ValueError:
            metric_value = None
        if metric_value is not None and np.isnan(metric_value):
            # Some metrics (e.g. roc_auc_score on a single-class slice) warn
            # and return NaN instead of raising -- normalize both failure
            # modes to the same "undefined for this slice" signal.
            metric_value = None
        results.append(SliceResult(slice_column, str(value), n, metric_value))
    return results


def bucket_by_quantile(
    series: pd.Series, n_buckets: int = 3, labels: list[str] | None = None
) -> pd.Series:
    """Quantile-based bucketing (default: tertiles) for a continuous slice dimension.

    Used for slice dimensions with no natural categories -- project size
    (`gross_floor_area_m2`) and budget segment (`approved_budget`),
    Section 18's two dimensions that aren't already columns.
    """
    bucket_labels = labels or [f"q{i + 1}_of_{n_buckets}" for i in range(n_buckets)]
    return pd.qcut(series, q=n_buckets, labels=bucket_labels, duplicates="drop")
