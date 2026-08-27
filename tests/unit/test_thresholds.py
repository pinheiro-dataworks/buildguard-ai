"""Unit tests for business-cost threshold optimization (Section 17)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from buildguard.models.thresholds import optimize_threshold

pytestmark = pytest.mark.unit


def _perfectly_separable_data() -> tuple[pd.Series, np.ndarray]:
    labels = pd.Series([0, 0, 0, 0, 0, 1, 1, 1, 1, 1])
    proba = np.array([0.05, 0.1, 0.15, 0.2, 0.25, 0.75, 0.8, 0.85, 0.9, 0.95])
    return labels, proba


class TestOptimizeThreshold:
    def test_perfectly_separable_data_finds_a_threshold_with_zero_cost(self) -> None:
        labels, proba = _perfectly_separable_data()
        result = optimize_threshold(
            labels, proba, false_negative_cost=10.0, false_positive_cost=2.0
        )
        assert result.expected_cost == pytest.approx(0.0)
        assert result.precision == pytest.approx(1.0)
        assert result.recall == pytest.approx(1.0)
        assert 0.25 < result.threshold < 0.75

    def test_confusion_counts_sum_to_total_rows(self) -> None:
        labels, proba = _perfectly_separable_data()
        result = optimize_threshold(
            labels, proba, false_negative_cost=10.0, false_positive_cost=2.0
        )
        total = (
            result.true_positives
            + result.false_positives
            + result.true_negatives
            + result.false_negatives
        )
        assert total == len(labels)

    def test_high_false_negative_cost_biases_threshold_lower(self) -> None:
        # Ambiguous data: overlapping distributions.
        rng = np.random.default_rng(0)
        n = 200
        labels = pd.Series(rng.integers(0, 2, n))
        proba = np.clip(labels * 0.3 + rng.normal(0.4, 0.25, n), 0, 1)

        expensive_fn = optimize_threshold(
            labels, proba, false_negative_cost=50.0, false_positive_cost=1.0
        )
        expensive_fp = optimize_threshold(
            labels, proba, false_negative_cost=1.0, false_positive_cost=50.0
        )
        # Penalizing missed positives heavily should push the threshold
        # down (catch more, tolerate more false alarms) relative to
        # penalizing false alarms heavily.
        assert expensive_fn.threshold < expensive_fp.threshold
        assert expensive_fn.recall >= expensive_fp.recall

    def test_never_defaults_to_a_fixed_threshold_regardless_of_cost_matrix(self) -> None:
        rng = np.random.default_rng(1)
        n = 200
        labels = pd.Series(rng.integers(0, 2, n))
        proba = np.clip(labels * 0.3 + rng.normal(0.4, 0.25, n), 0, 1)

        result_a = optimize_threshold(
            labels, proba, false_negative_cost=10.0, false_positive_cost=2.0
        )
        result_b = optimize_threshold(
            labels, proba, false_negative_cost=2.0, false_positive_cost=10.0
        )
        assert result_a.threshold != result_b.threshold

    def test_zero_expected_cost_is_never_negative(self) -> None:
        labels, proba = _perfectly_separable_data()
        result = optimize_threshold(
            labels, proba, false_negative_cost=10.0, false_positive_cost=2.0
        )
        assert result.expected_cost >= 0.0
