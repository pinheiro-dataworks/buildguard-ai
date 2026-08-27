"""Probability calibration (Section 16).

Compares raw (uncalibrated) probabilities from an already-fitted
classifier against Platt/sigmoid and isotonic calibration, fit on the
**calibration** split only (never train, never test -- Section 12). This
answers the question Section 16 poses directly: "when BuildGuard says 70%
risk, is that probability approximately trustworthy?"

Calibrators are fit directly on `(raw_probability, label)` pairs -- Platt
scaling via a one-feature `LogisticRegression` (a public, stable API
equivalent to sklearn's internal, private `_SigmoidCalibration`), isotonic
via `IsotonicRegression` -- rather than through
`CalibratedClassifierCV`/`FrozenEstimator` wrapping the original model.
That wrapping route was tried first and rejected: it requires the wrapped
object to be a full sklearn estimator (`fit` *and* `predict`), which
BuildGuard's own baselines (`buildguard.models.baselines`) don't implement
-- they only expose `predict_proba` (the same class of problem hit with
MLflow's skops serialization in Session H). Calibrating directly on the
probability output works uniformly for baselines and real sklearn
pipelines alike, with no assumptions about the underlying model's API.

**Known limitation:** Brier score and the calibration curve here are
measured on the same calibration-split rows used to fit the calibration
mapping (in-sample for that split). This is standard for the
train/calibration/test design (Section 12's CALIBRATION block is exactly
where this fitting happens), but it is optimistic relative to genuinely
held-out data -- true out-of-sample calibration quality is only confirmed
at the one final test evaluation (a later phase), never here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol

import numpy as np
import numpy.typing as npt
import pandas as pd
from sklearn.calibration import calibration_curve
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss

CalibrationMethod = Literal["none", "sigmoid", "isotonic"]


class _ProbaModel(Protocol):
    def predict_proba(self, features: pd.DataFrame) -> npt.NDArray[np.float64]: ...


@dataclass(frozen=True)
class CalibrationCurve:
    method: CalibrationMethod
    brier_score: float
    mean_predicted_value: npt.NDArray[np.float64]
    fraction_of_positives: npt.NDArray[np.float64]


class CalibratedModel:
    """Wraps a fitted model's `predict_proba` with a fitted calibration mapping."""

    def __init__(self, base_model: _ProbaModel, calibrator: Any) -> None:
        self._base_model = base_model
        self._calibrator = calibrator

    def predict_proba(self, features: pd.DataFrame) -> npt.NDArray[np.float64]:
        raw = _positive_class_proba(self._base_model.predict_proba(features))
        calibrated: npt.NDArray[np.float64] = self._calibrator.predict(raw.reshape(-1, 1)).ravel()
        return np.column_stack([1 - calibrated, calibrated])


@dataclass(frozen=True)
class CalibrationComparison:
    curves: dict[CalibrationMethod, CalibrationCurve]
    best_method: CalibrationMethod
    calibrated_model: Any
    """The object to call `.predict_proba` on going forward: the original
    `fitted_model` (method == "none") or a `CalibratedModel`
    (method == "sigmoid"/"isotonic")."""


def _positive_class_proba(proba: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    return proba[:, 1] if proba.ndim == 2 else proba


def _brier_and_curve(
    method: CalibrationMethod, labels: pd.Series, proba: npt.NDArray[np.float64], n_bins: int
) -> CalibrationCurve:
    fraction_of_positives, mean_predicted_value = calibration_curve(labels, proba, n_bins=n_bins)
    return CalibrationCurve(
        method=method,
        brier_score=float(brier_score_loss(labels, proba)),
        mean_predicted_value=mean_predicted_value,
        fraction_of_positives=fraction_of_positives,
    )


def evaluate_calibration_methods(
    fitted_model: _ProbaModel,
    calibration_features: pd.DataFrame,
    calibration_labels: pd.Series,
    n_bins: int = 10,
) -> CalibrationComparison:
    """Compare raw / sigmoid / isotonic calibration for an already-fitted classifier.

    `fitted_model` must already implement `predict_proba` (a fitted
    baseline from `buildguard.models.baselines` or a
    `classification.fit_classifier(...)` pipeline) and must already be fit
    on the **train** split -- this function only ever fits the calibration
    mapping, on `calibration_features`/`calibration_labels`.

    Selects `best_method` by lowest Brier score among the three; "none"
    wins whenever calibration doesn't actually improve on the raw
    probabilities, since forcing calibration that makes things worse would
    defeat the point of comparing in the first place.
    """
    curves: dict[CalibrationMethod, CalibrationCurve] = {}

    raw_proba = _positive_class_proba(fitted_model.predict_proba(calibration_features))
    curves["none"] = _brier_and_curve("none", calibration_labels, raw_proba, n_bins)

    labels_array = calibration_labels.to_numpy()
    calibrated_candidates: dict[CalibrationMethod, CalibratedModel] = {}

    sigmoid = LogisticRegression().fit(raw_proba.reshape(-1, 1), labels_array)
    sigmoid_proba = sigmoid.predict_proba(raw_proba.reshape(-1, 1))[:, 1]
    curves["sigmoid"] = _brier_and_curve("sigmoid", calibration_labels, sigmoid_proba, n_bins)
    calibrated_candidates["sigmoid"] = CalibratedModel(fitted_model, sigmoid)

    isotonic = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(
        raw_proba, labels_array
    )
    isotonic_proba = isotonic.predict(raw_proba)
    curves["isotonic"] = _brier_and_curve("isotonic", calibration_labels, isotonic_proba, n_bins)
    calibrated_candidates["isotonic"] = CalibratedModel(fitted_model, isotonic)

    best_method = min(curves, key=lambda m: curves[m].brier_score)
    calibrated_model: Any = (
        fitted_model if best_method == "none" else calibrated_candidates[best_method]
    )

    return CalibrationComparison(
        curves=curves, best_method=best_method, calibrated_model=calibrated_model
    )
