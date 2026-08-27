"""Unit tests for split-conformal prediction intervals (Section 19)."""

from __future__ import annotations

import numpy as np
import pytest

from buildguard.models.uncertainty import (
    empirical_coverage,
    fit_conformal_quantile,
    predict_interval,
)

pytestmark = pytest.mark.unit


class TestFitConformalQuantile:
    def test_rejects_coverage_outside_open_unit_interval(self) -> None:
        residuals_true = np.array([1.0, 2.0, 3.0])
        residuals_pred = np.array([1.1, 2.1, 3.1])
        with pytest.raises(ValueError, match="coverage must be in"):
            fit_conformal_quantile(residuals_true, residuals_pred, coverage=1.0)
        with pytest.raises(ValueError, match="coverage must be in"):
            fit_conformal_quantile(residuals_true, residuals_pred, coverage=0.0)

    def test_rejects_empty_residuals(self) -> None:
        empty = np.array([])
        with pytest.raises(ValueError, match="zero residuals"):
            fit_conformal_quantile(empty, empty, coverage=0.8)

    def test_quantile_is_non_negative(self) -> None:
        y_true = np.array([10.0, 20.0, 30.0, 40.0])
        y_pred = np.array([12.0, 18.0, 33.0, 37.0])
        interval = fit_conformal_quantile(y_true, y_pred, coverage=0.8)
        assert interval.quantile >= 0.0

    def test_higher_coverage_requires_a_wider_quantile(self) -> None:
        rng = np.random.default_rng(0)
        y_true = rng.normal(100, 10, 200)
        y_pred = y_true + rng.normal(0, 5, 200)
        low_coverage = fit_conformal_quantile(y_true, y_pred, coverage=0.5)
        high_coverage = fit_conformal_quantile(y_true, y_pred, coverage=0.95)
        assert high_coverage.quantile > low_coverage.quantile


class TestPredictInterval:
    def test_interval_is_symmetric_around_point_prediction(self) -> None:
        from buildguard.models.uncertainty import ConformalInterval

        interval = ConformalInterval(coverage=0.8, quantile=5.0)
        point = np.array([100.0, 200.0])
        lower, upper = predict_interval(point, interval)
        assert lower.tolist() == [95.0, 195.0]
        assert upper.tolist() == [105.0, 205.0]


class TestEmpiricalCoverage:
    def test_all_within_bounds_gives_full_coverage(self) -> None:
        y_true = np.array([1.0, 2.0, 3.0])
        lower = np.array([0.0, 1.0, 2.0])
        upper = np.array([2.0, 3.0, 4.0])
        assert empirical_coverage(y_true, lower, upper) == pytest.approx(1.0)

    def test_none_within_bounds_gives_zero_coverage(self) -> None:
        y_true = np.array([10.0, 20.0, 30.0])
        lower = np.array([0.0, 1.0, 2.0])
        upper = np.array([2.0, 3.0, 4.0])
        assert empirical_coverage(y_true, lower, upper) == pytest.approx(0.0)

    def test_conformal_interval_achieves_approximately_its_target_coverage(self) -> None:
        """The actual statistical guarantee, checked empirically on
        genuinely held-out data (not the data the quantile was fit on).
        """
        rng = np.random.default_rng(42)
        y_true_all = rng.normal(1000, 100, 4000)
        y_pred_all = y_true_all + rng.normal(0, 50, 4000)

        cal_true, cal_pred = y_true_all[:2000], y_pred_all[:2000]
        holdout_true, holdout_pred = y_true_all[2000:], y_pred_all[2000:]

        interval = fit_conformal_quantile(cal_true, cal_pred, coverage=0.80)
        lower, upper = predict_interval(holdout_pred, interval)
        coverage = empirical_coverage(holdout_true, lower, upper)

        assert coverage == pytest.approx(0.80, abs=0.03)
