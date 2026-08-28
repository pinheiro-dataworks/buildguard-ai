"""Data and prediction drift detection (Section 23).

Method chosen per variable type, not one-size-fits-all: **PSI** (Population
Stability Index) applies to both numeric and categorical columns alike (it
only needs a way to bin a distribution into buckets and compare bucket
proportions), while the **KS test** and **Wasserstein distance** are
defined for continuous distributions specifically, so they run on numeric
columns only. All three take a `reference` distribution (the trusted prior
batch -- in practice the **train** split, the only split every downstream
decision is ultimately anchored to) and a `current` distribution (the
batch being monitored -- in practice the **test** split, standing in for
"the next batch of production data" in the absence of real production
history yet). Prediction drift (risk-probability distribution, predicted-
cost distribution, risk-band proportions) reuses these exact same
functions on model *outputs* rather than input features -- there is
nothing structurally different about drift in a prediction column versus
a feature column.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
import numpy.typing as npt
import pandas as pd
from scipy.stats import ks_2samp, wasserstein_distance

Severity = Literal["none", "moderate", "significant"]

_PSI_EPSILON = 1e-4


def _psi_severity(psi: float, warning_threshold: float, critical_threshold: float) -> Severity:
    if psi >= critical_threshold:
        return "significant"
    if psi >= warning_threshold:
        return "moderate"
    return "none"


def population_stability_index_numeric(
    reference: pd.Series, current: pd.Series, n_bins: int = 10
) -> float:
    """PSI for a numeric column, binned into `n_bins` quantile buckets of `reference`."""
    edges = np.unique(np.quantile(reference.dropna(), np.linspace(0, 1, n_bins + 1)))
    edges[0], edges[-1] = -np.inf, np.inf
    if len(edges) < 3:
        return 0.0  # reference has no meaningful spread to bin against
    ref_counts, _ = np.histogram(reference.dropna(), bins=edges)
    cur_counts, _ = np.histogram(current.dropna(), bins=edges)
    return _psi_from_counts(ref_counts, cur_counts)


def population_stability_index_categorical(reference: pd.Series, current: pd.Series) -> float:
    """PSI for a categorical column, bucketed by the union of categories observed in either split."""
    categories = sorted(set(reference.dropna().unique()) | set(current.dropna().unique()))
    ref_counts = reference.value_counts().reindex(categories, fill_value=0).to_numpy()
    cur_counts = current.value_counts().reindex(categories, fill_value=0).to_numpy()
    return _psi_from_counts(ref_counts, cur_counts)


def _psi_from_counts(
    ref_counts: npt.NDArray[np.integer[Any]], cur_counts: npt.NDArray[np.integer[Any]]
) -> float:
    ref_pct = ref_counts / max(ref_counts.sum(), 1)
    cur_pct = cur_counts / max(cur_counts.sum(), 1)
    ref_pct = np.clip(ref_pct, _PSI_EPSILON, None)
    cur_pct = np.clip(cur_pct, _PSI_EPSILON, None)
    return float(np.sum((cur_pct - ref_pct) * np.log(cur_pct / ref_pct)))


@dataclass(frozen=True)
class DriftResult:
    column: str
    variable_type: Literal["numeric", "categorical"]
    psi: float
    psi_severity: Severity
    ks_statistic: float | None
    ks_p_value: float | None
    wasserstein_distance: float | None


def numeric_drift(
    column: str,
    reference: pd.Series,
    current: pd.Series,
    psi_warning_threshold: float,
    psi_critical_threshold: float,
    n_bins: int = 10,
) -> DriftResult:
    psi = population_stability_index_numeric(reference, current, n_bins)
    ks = ks_2samp(reference.dropna(), current.dropna())
    return DriftResult(
        column=column,
        variable_type="numeric",
        psi=psi,
        psi_severity=_psi_severity(psi, psi_warning_threshold, psi_critical_threshold),
        ks_statistic=float(ks.statistic),
        ks_p_value=float(ks.pvalue),
        wasserstein_distance=float(wasserstein_distance(reference.dropna(), current.dropna())),
    )


def categorical_drift(
    column: str,
    reference: pd.Series,
    current: pd.Series,
    psi_warning_threshold: float,
    psi_critical_threshold: float,
) -> DriftResult:
    psi = population_stability_index_categorical(reference, current)
    return DriftResult(
        column=column,
        variable_type="categorical",
        psi=psi,
        psi_severity=_psi_severity(psi, psi_warning_threshold, psi_critical_threshold),
        ks_statistic=None,
        ks_p_value=None,
        wasserstein_distance=None,
    )


def drift_report(
    reference_df: pd.DataFrame,
    current_df: pd.DataFrame,
    numeric_columns: list[str],
    categorical_columns: list[str],
    psi_warning_threshold: float,
    psi_critical_threshold: float,
) -> list[DriftResult]:
    """Drift for every named column, numeric and categorical methods applied per type."""
    results = [
        numeric_drift(
            col, reference_df[col], current_df[col], psi_warning_threshold, psi_critical_threshold
        )
        for col in numeric_columns
        if col in reference_df.columns and col in current_df.columns
    ]
    results += [
        categorical_drift(
            col, reference_df[col], current_df[col], psi_warning_threshold, psi_critical_threshold
        )
        for col in categorical_columns
        if col in reference_df.columns and col in current_df.columns
    ]
    return results
