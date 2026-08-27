"""Held-out calibration check (Section 18).

`buildguard.models.calibration.evaluate_calibration_methods` *fits* the
calibration mapping and reports its Brier score on the same calibration
split it was fit on -- optimistic, by that module's own documented
limitation. This function applies an already-chosen, already-fitted
probability column to a split the calibrator never saw (the test split),
closing the loop that limitation leaves open: is the calibration mapping
still trustworthy out-of-sample, or did it just memorize the calibration
split's quirks?
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt
from sklearn.calibration import calibration_curve
from sklearn.metrics import brier_score_loss

from buildguard.models.calibration import CalibrationCurve, CalibrationMethod


def evaluate_calibration_on_holdout(
    y_true: npt.NDArray[np.bool_],
    y_proba: npt.NDArray[np.float64],
    method: CalibrationMethod,
    n_bins: int = 10,
) -> CalibrationCurve:
    """`y_proba` is the already-applied `method`'s output (Section 16's
    winning calibrator, e.g. "isotonic"), scored here on a split that
    calibrator was never fit or selected on.
    """
    fraction_of_positives, mean_predicted_value = calibration_curve(y_true, y_proba, n_bins=n_bins)
    return CalibrationCurve(
        method=method,
        brier_score=float(brier_score_loss(y_true, y_proba)),
        mean_predicted_value=mean_predicted_value,
        fraction_of_positives=fraction_of_positives,
    )
