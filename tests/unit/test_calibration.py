"""Unit tests for probability calibration (Section 16)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from sklearn.ensemble import RandomForestClassifier

from buildguard.models.calibration import evaluate_calibration_methods

pytestmark = pytest.mark.unit


class _RawProbaModel:
    """A hand-built "model" with deliberately overconfident, poorly
    calibrated probabilities -- always predicts near 0 or 1 regardless of
    how ambiguous the row actually is -- so there is real room for
    sigmoid/isotonic calibration to improve on it.
    """

    def fit(self, features: pd.DataFrame, labels: pd.Series) -> _RawProbaModel:
        return self

    def predict_proba(self, features: pd.DataFrame) -> np.ndarray:
        raw = features["signal"].to_numpy()
        overconfident = np.where(raw > 0, 0.98, 0.02)
        return np.column_stack([1 - overconfident, overconfident])


def _classification_data(n: int = 400, seed: int = 0) -> tuple[pd.DataFrame, pd.Series]:
    rng = np.random.default_rng(seed)
    signal = rng.normal(0, 1, n)
    # True probability is a smooth sigmoid of `signal`, not the
    # overconfident step function _RawProbaModel predicts.
    true_prob = 1.0 / (1.0 + np.exp(-signal))
    labels = pd.Series(rng.binomial(1, true_prob))
    features = pd.DataFrame({"signal": signal})
    return features, labels


class TestEvaluateCalibrationMethods:
    def test_all_three_methods_are_reported(self) -> None:
        features, labels = _classification_data()
        model = _RawProbaModel().fit(features, labels)
        comparison = evaluate_calibration_methods(model, features, labels)
        assert set(comparison.curves.keys()) == {"none", "sigmoid", "isotonic"}

    def test_calibration_improves_on_an_overconfident_model(self) -> None:
        features, labels = _classification_data()
        model = _RawProbaModel().fit(features, labels)
        comparison = evaluate_calibration_methods(model, features, labels)

        raw_brier = comparison.curves["none"].brier_score
        best_brier = comparison.curves[comparison.best_method].brier_score
        assert best_brier <= raw_brier
        # The deliberately overconfident model should not be the winner.
        assert comparison.best_method != "none"

    def test_best_method_is_the_lowest_brier_score_by_construction(self) -> None:
        features, labels = _classification_data()
        model = _RawProbaModel().fit(features, labels)
        comparison = evaluate_calibration_methods(model, features, labels)

        best_brier = min(c.brier_score for c in comparison.curves.values())
        assert comparison.curves[comparison.best_method].brier_score == pytest.approx(best_brier)

    def test_calibrated_model_produces_valid_probabilities(self) -> None:
        features, labels = _classification_data()
        model = _RawProbaModel().fit(features, labels)
        comparison = evaluate_calibration_methods(model, features, labels)

        proba = comparison.calibrated_model.predict_proba(features)
        proba = proba[:, 1] if proba.ndim == 2 else proba
        assert ((proba >= 0) & (proba <= 1)).all()

    def test_calibration_curve_arrays_are_valid_probabilities(self) -> None:
        features, labels = _classification_data()
        model = _RawProbaModel().fit(features, labels)
        comparison = evaluate_calibration_methods(model, features, labels, n_bins=5)

        for curve in comparison.curves.values():
            assert ((curve.mean_predicted_value >= 0) & (curve.mean_predicted_value <= 1)).all()
            assert ((curve.fraction_of_positives >= 0) & (curve.fraction_of_positives <= 1)).all()

    def test_works_with_a_real_sklearn_pipeline_champion(self) -> None:
        rng = np.random.default_rng(1)
        n = 300
        features = pd.DataFrame({"a": rng.normal(size=n), "b": rng.normal(size=n)})
        labels = pd.Series((features["a"] + rng.normal(0, 0.5, n) > 0).astype(int))
        model = RandomForestClassifier(n_estimators=30, random_state=0).fit(features, labels)

        comparison = evaluate_calibration_methods(model, features, labels)
        assert comparison.best_method in {"none", "sigmoid", "isotonic"}
        assert comparison.curves["none"].brier_score >= 0
