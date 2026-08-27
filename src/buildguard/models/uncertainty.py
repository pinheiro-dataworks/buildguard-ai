"""Prediction uncertainty for the final-cost estimate (Section 19).

Split conformal prediction -- model-agnostic, so it works identically
whether the point predictor is a fitted regressor or (as it actually is
for `final_cost`; see `docs/adr/0006-model-selection.md`) a deterministic
formula baseline with no learned notion of its own uncertainty. The
conformal quantile is computed from residuals on the **calibration**
split only, never train, never test (Section 12), giving a symmetric
interval with a marginal coverage guarantee under the standard conformal
exchangeability assumption -- empirically checked, not just asserted, by
`empirical_coverage`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt


@dataclass(frozen=True)
class ConformalInterval:
    coverage: float
    quantile: float


def fit_conformal_quantile(
    y_true: npt.NDArray[np.float64], y_pred: npt.NDArray[np.float64], coverage: float
) -> ConformalInterval:
    """Split-conformal quantile of absolute residuals for a target `coverage` (e.g. 0.80).

    Uses the standard finite-sample conformal correction
    (`ceil((n + 1) * coverage) / n`, capped at 1.0) rather than the naive
    empirical quantile, so the resulting interval's coverage guarantee
    holds even at small calibration-set sizes.
    """
    if not 0 < coverage < 1:
        raise ValueError(f"coverage must be in (0, 1), got {coverage}")
    residuals = np.abs(y_true - y_pred)
    n = len(residuals)
    if n == 0:
        raise ValueError("Cannot fit a conformal quantile on zero residuals")
    rank = min(math.ceil((n + 1) * coverage) / n, 1.0)
    quantile = float(np.quantile(residuals, rank, method="higher"))
    return ConformalInterval(coverage=coverage, quantile=quantile)


def predict_interval(
    point_prediction: npt.NDArray[np.float64], interval: ConformalInterval
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """`(lower, upper)` bounds, `interval.quantile` wide on each side of `point_prediction`."""
    lower = point_prediction - interval.quantile
    upper = point_prediction + interval.quantile
    return lower, upper


def empirical_coverage(
    y_true: npt.NDArray[np.float64],
    lower: npt.NDArray[np.float64],
    upper: npt.NDArray[np.float64],
) -> float:
    """Fraction of `y_true` values actually falling within `[lower, upper]`."""
    within = (y_true >= lower) & (y_true <= upper)
    return float(np.mean(within))
