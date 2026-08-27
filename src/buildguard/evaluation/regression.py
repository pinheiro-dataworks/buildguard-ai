"""Regression evaluation metrics (Section 18).

MAE/RMSE/R² are the standard error-magnitude battery; MAPE and SMAPE
express that same error as a percentage (SMAPE is reported alongside MAPE
because `final_cost_real` values are strictly positive but can still be
small for short/cheap projects, where MAPE alone can blow up); the two
business-terms figures (median dollar error, median percent error) are
what Section 18 asks for so a non-technical reader can answer "how far off
is this, in money, for a typical project" without decoding RMSE.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error, r2_score


@dataclass(frozen=True)
class RegressionMetrics:
    mae: float
    rmse: float
    r2: float
    mape: float
    smape: float
    median_dollar_error: float
    median_percent_error: float
    n_rows: int


def compute_regression_metrics(
    y_true: npt.NDArray[np.float64], y_pred: npt.NDArray[np.float64]
) -> RegressionMetrics:
    y_true_arr = np.asarray(y_true, dtype=float)
    y_pred_arr = np.asarray(y_pred, dtype=float)
    abs_error = np.abs(y_true_arr - y_pred_arr)

    smape = float(
        np.mean(2 * abs_error / (np.abs(y_true_arr) + np.abs(y_pred_arr) + np.finfo(float).eps))
    )

    return RegressionMetrics(
        mae=float(mean_absolute_error(y_true_arr, y_pred_arr)),
        rmse=float(np.sqrt(np.mean((y_true_arr - y_pred_arr) ** 2))),
        r2=float(r2_score(y_true_arr, y_pred_arr)),
        mape=float(mean_absolute_percentage_error(y_true_arr, y_pred_arr)),
        smape=smape,
        median_dollar_error=float(np.median(abs_error)),
        median_percent_error=float(np.median(abs_error / y_true_arr)),
        n_rows=len(y_true_arr),
    )
