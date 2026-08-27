"""Unit tests for slice evaluation (Section 18)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import mean_absolute_error, roc_auc_score

from buildguard.evaluation.slices import bucket_by_quantile, evaluate_by_slice

pytestmark = pytest.mark.unit


class TestEvaluateBySliceClassification:
    def test_matches_hand_calculated_auc_per_slice(self) -> None:
        df = pd.DataFrame({"project_type": ["residential"] * 25 + ["commercial"] * 25})
        # Residential: perfectly separable (AUC 1.0). Commercial: inverted (AUC 0.0).
        y_true = np.array([0] * 12 + [1] * 13 + [0] * 12 + [1] * 13)
        y_pred = np.array(
            list(np.linspace(0, 0.4, 12))
            + list(np.linspace(0.6, 1.0, 13))  # residential: separable
            + list(np.linspace(0.6, 1.0, 12))
            + list(np.linspace(0, 0.4, 13))  # commercial: inverted
        )
        results = evaluate_by_slice(
            df, "project_type", y_true, y_pred, roc_auc_score, min_slice_size=5
        )
        by_value = {r.slice_value: r.metric_value for r in results}
        assert by_value["residential"] == pytest.approx(1.0)
        assert by_value["commercial"] == pytest.approx(0.0)

    def test_small_slices_get_none_not_a_misleading_number(self) -> None:
        df = pd.DataFrame({"segment": ["big"] * 30 + ["tiny"] * 5})
        y_true = np.random.default_rng(0).integers(0, 2, 35)
        y_pred = np.random.default_rng(1).uniform(0, 1, 35)
        results = evaluate_by_slice(df, "segment", y_true, y_pred, roc_auc_score, min_slice_size=20)
        by_value = {r.slice_value: r for r in results}
        assert by_value["tiny"].metric_value is None
        assert by_value["tiny"].n_rows == 5
        assert by_value["big"].metric_value is not None

    def test_single_class_slice_returns_none_instead_of_raising(self) -> None:
        df = pd.DataFrame({"segment": ["mixed"] * 25 + ["all_zero"] * 25})
        y_true = np.array([0, 1] * 12 + [0] + [0] * 25)
        y_pred = np.random.default_rng(0).uniform(0, 1, 50)
        results = evaluate_by_slice(df, "segment", y_true, y_pred, roc_auc_score, min_slice_size=20)
        by_value = {r.slice_value: r for r in results}
        assert by_value["all_zero"].metric_value is None
        assert by_value["all_zero"].n_rows == 25

    def test_n_rows_sums_to_total(self) -> None:
        df = pd.DataFrame({"stage": ["early"] * 30 + ["mid"] * 40 + ["late"] * 30})
        y_true = np.random.default_rng(0).integers(0, 2, 100)
        y_pred = np.random.default_rng(1).uniform(0, 1, 100)
        results = evaluate_by_slice(df, "stage", y_true, y_pred, roc_auc_score, min_slice_size=1)
        assert sum(r.n_rows for r in results) == 100


class TestEvaluateBySliceRegression:
    def test_works_with_a_regression_metric(self) -> None:
        df = pd.DataFrame({"size": ["small"] * 25 + ["large"] * 25})
        y_true = np.array([100.0] * 25 + [1000.0] * 25)
        y_pred = np.array([110.0] * 25 + [800.0] * 25)  # small: off by 10, large: off by 200
        results = evaluate_by_slice(
            df, "size", y_true, y_pred, mean_absolute_error, min_slice_size=5
        )
        by_value = {r.slice_value: r.metric_value for r in results}
        assert by_value["small"] == pytest.approx(10.0)
        assert by_value["large"] == pytest.approx(200.0)


class TestBucketByQuantile:
    def test_produces_the_requested_number_of_buckets(self) -> None:
        series = pd.Series(np.arange(300))
        buckets = bucket_by_quantile(series, n_buckets=3)
        assert buckets.nunique() == 3

    def test_smallest_values_land_in_the_first_bucket(self) -> None:
        series = pd.Series(np.arange(100))
        buckets = bucket_by_quantile(series, n_buckets=4, labels=["q1", "q2", "q3", "q4"])
        assert buckets.iloc[0] == "q1"
        assert buckets.iloc[-1] == "q4"

    def test_default_labels_are_ordinal(self) -> None:
        series = pd.Series(np.arange(60))
        buckets = bucket_by_quantile(series, n_buckets=3)
        assert set(buckets.unique()) == {"q1_of_3", "q2_of_3", "q3_of_3"}
