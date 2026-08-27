"""Unit tests for regression evaluation metrics (Section 18)."""

from __future__ import annotations

import numpy as np
import pytest

from buildguard.evaluation.regression import compute_regression_metrics

pytestmark = pytest.mark.unit


def test_matches_hand_calculated_mae_and_median_dollar_error() -> None:
    y_true = np.array([100.0, 200.0, 300.0, 400.0])
    y_pred = np.array([110.0, 180.0, 330.0, 420.0])
    # abs errors: 10, 20, 30, 20 -> mean 20, median 20
    metrics = compute_regression_metrics(y_true, y_pred)

    assert metrics.mae == pytest.approx(20.0)
    assert metrics.median_dollar_error == pytest.approx(20.0)
    assert metrics.n_rows == 4


def test_perfect_predictions_give_zero_error_and_r2_one() -> None:
    y_true = np.array([1_000.0, 2_000.0, 3_000.0])
    metrics = compute_regression_metrics(y_true, y_true.copy())

    assert metrics.mae == pytest.approx(0.0)
    assert metrics.rmse == pytest.approx(0.0)
    assert metrics.r2 == pytest.approx(1.0)
    assert metrics.mape == pytest.approx(0.0)
    assert metrics.smape == pytest.approx(0.0)
    assert metrics.median_percent_error == pytest.approx(0.0)


def test_median_percent_error_matches_hand_calculation() -> None:
    y_true = np.array([100.0, 200.0])
    y_pred = np.array([110.0, 220.0])  # both off by exactly 10%
    metrics = compute_regression_metrics(y_true, y_pred)
    assert metrics.median_percent_error == pytest.approx(0.10)


def test_rmse_penalizes_large_errors_more_than_mae() -> None:
    y_true = np.array([100.0, 100.0, 100.0, 100.0])
    y_pred = np.array([100.0, 100.0, 100.0, 500.0])  # one huge outlier
    metrics = compute_regression_metrics(y_true, y_pred)
    assert metrics.rmse > metrics.mae


def test_smape_is_symmetric_between_over_and_under_prediction() -> None:
    over = compute_regression_metrics(np.array([100.0]), np.array([150.0]))
    under = compute_regression_metrics(np.array([150.0]), np.array([100.0]))
    assert over.smape == pytest.approx(under.smape)
