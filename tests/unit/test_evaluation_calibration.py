"""Unit tests for the held-out calibration check (Section 18)."""

from __future__ import annotations

import numpy as np
import pytest
from sklearn.metrics import brier_score_loss

from buildguard.evaluation.calibration import evaluate_calibration_on_holdout

pytestmark = pytest.mark.unit


def test_brier_score_matches_sklearn() -> None:
    rng = np.random.default_rng(0)
    y_true = rng.integers(0, 2, 100).astype(bool)
    y_proba = rng.uniform(0, 1, 100)

    curve = evaluate_calibration_on_holdout(y_true, y_proba, method="isotonic")

    assert curve.brier_score == pytest.approx(brier_score_loss(y_true, y_proba))
    assert curve.method == "isotonic"


def test_perfectly_calibrated_probabilities_yield_zero_brier() -> None:
    y_true = np.array([False] * 10 + [True] * 10)
    y_proba = np.array([0.0] * 10 + [1.0] * 10)
    curve = evaluate_calibration_on_holdout(y_true, y_proba, method="none")
    assert curve.brier_score == pytest.approx(0.0)


def test_curve_arrays_have_matching_length() -> None:
    rng = np.random.default_rng(1)
    y_true = rng.integers(0, 2, 200).astype(bool)
    y_proba = rng.uniform(0, 1, 200)
    curve = evaluate_calibration_on_holdout(y_true, y_proba, method="sigmoid", n_bins=5)
    assert len(curve.mean_predicted_value) == len(curve.fraction_of_positives)
    assert len(curve.mean_predicted_value) <= 5
