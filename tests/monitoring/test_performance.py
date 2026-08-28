"""Unit tests for performance and operational monitoring (Section 23/24)."""

from __future__ import annotations

import time

import pandas as pd
import pytest

from buildguard.monitoring.performance import (
    PredictionLogEntry,
    compare_classification_metrics,
    compare_metric,
    compare_regression_metrics,
    measure_inference_latency,
    summarize_operational_log,
)

pytestmark = pytest.mark.monitoring


class TestCompareMetric:
    def test_unchanged_metric_is_not_degraded(self) -> None:
        result = compare_metric("roc_auc", 0.90, 0.90, higher_is_better=True, drop_threshold=0.05)
        assert not result.is_degraded
        assert result.relative_change == pytest.approx(0.0)

    def test_a_higher_is_better_metric_dropping_beyond_threshold_is_degraded(self) -> None:
        result = compare_metric("roc_auc", 0.90, 0.80, higher_is_better=True, drop_threshold=0.05)
        assert result.is_degraded

    def test_a_higher_is_better_metric_improving_is_never_degraded(self) -> None:
        result = compare_metric("roc_auc", 0.80, 0.95, higher_is_better=True, drop_threshold=0.05)
        assert not result.is_degraded

    def test_a_lower_is_better_metric_rising_beyond_threshold_is_degraded(self) -> None:
        result = compare_metric(
            "brier_score", 0.10, 0.20, higher_is_better=False, drop_threshold=0.05
        )
        assert result.is_degraded

    def test_a_lower_is_better_metric_falling_is_never_degraded(self) -> None:
        result = compare_metric(
            "mae", 100_000.0, 80_000.0, higher_is_better=False, drop_threshold=0.05
        )
        assert not result.is_degraded

    def test_small_movement_within_threshold_is_not_degraded(self) -> None:
        result = compare_metric("roc_auc", 0.90, 0.88, higher_is_better=True, drop_threshold=0.05)
        assert not result.is_degraded

    def test_zero_baseline_does_not_raise(self) -> None:
        result = compare_metric("mae", 0.0, 0.0, higher_is_better=False, drop_threshold=0.05)
        assert result.relative_change == 0.0


class TestCompareClassificationMetrics:
    def test_matches_the_real_session_j_finding_schedule_delay_calibration_degrades(self) -> None:
        # Real numbers from ADR-0010: schedule_delay's Brier goes from
        # 0.0592 (in-sample, calibration split) to 0.1452 (test split).
        baseline = {"roc_auc": 0.90, "pr_auc": 0.88, "recall": 0.98, "brier_score": 0.0592}
        current = {"roc_auc": 0.9002, "pr_auc": 0.8949, "recall": 0.929, "brier_score": 0.1452}
        results = compare_classification_metrics(baseline, current, drop_threshold=0.05)
        by_name = {r.metric_name: r for r in results}
        assert by_name["brier_score"].is_degraded
        assert not by_name["roc_auc"].is_degraded

    def test_missing_metrics_are_skipped_not_raised(self) -> None:
        results = compare_classification_metrics({"roc_auc": 0.9}, {"roc_auc": 0.9}, 0.05)
        assert len(results) == 1


class TestCompareRegressionMetrics:
    def test_mae_increase_is_flagged(self) -> None:
        results = compare_regression_metrics(
            {"mae": 1_000_000.0, "rmse": 2_000_000.0},
            {"mae": 1_500_000.0, "rmse": 2_000_000.0},
            drop_threshold=0.05,
        )
        by_name = {r.metric_name: r for r in results}
        assert by_name["mae"].is_degraded
        assert not by_name["rmse"].is_degraded


class TestSummarizeOperationalLog:
    def test_empty_log_does_not_raise(self) -> None:
        summary = summarize_operational_log([])
        assert summary.n_predictions == 0
        assert summary.error_rate == 0.0

    def test_error_rate_matches_hand_count(self) -> None:
        entries = [
            PredictionLogEntry("m", "1.0.0", "abc", 10.0, error=None),
            PredictionLogEntry("m", "1.0.0", "abc", 12.0, error="boom"),
        ]
        summary = summarize_operational_log(entries)
        assert summary.n_predictions == 2
        assert summary.n_errors == 1
        assert summary.error_rate == pytest.approx(0.5)

    def test_p95_is_never_below_p50(self) -> None:
        entries = [PredictionLogEntry("m", "1.0.0", "abc", float(i), None) for i in range(100)]
        summary = summarize_operational_log(entries)
        assert summary.latency_p95_ms >= summary.latency_p50_ms


class TestMeasureInferenceLatency:
    def test_times_real_calls_and_reports_positive_latency(self) -> None:
        sample = pd.DataFrame({"x": [1, 2, 3]})

        def _predict(row: pd.DataFrame) -> float:
            time.sleep(0.001)
            return float(row["x"].iloc[0])

        summary = measure_inference_latency(
            _predict, sample, "test-model", "1.0.0", "abc", n_calls=5
        )
        assert summary.n_predictions == 5
        assert summary.n_errors == 0
        assert summary.latency_p50_ms > 0

    def test_a_predict_function_that_always_raises_is_captured_as_errors(self) -> None:
        sample = pd.DataFrame({"x": [1]})

        def _always_fails(row: pd.DataFrame) -> None:
            raise RuntimeError("simulated inference failure")

        summary = measure_inference_latency(
            _always_fails, sample, "test-model", "1.0.0", "abc", n_calls=3
        )
        assert summary.n_errors == 3
        assert summary.error_rate == pytest.approx(1.0)
