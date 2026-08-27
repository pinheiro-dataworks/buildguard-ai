"""Unit tests for baseline models (Section 13).

Beyond "does it run," these tests check the actual point of a baseline
suite: the informative baselines (logistic/linear regression, the CPI
rule) must be demonstrably better than the uninformative ones (dummy,
mean/median) on data with a real, known signal -- otherwise the "beat the
baseline" bar (Section 13) would be trivially easy to clear for nothing.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import mean_absolute_error, roc_auc_score

from buildguard.models.baselines import (
    CATEGORICAL_FEATURE_COLUMNS,
    NUMERIC_FEATURE_COLUMNS,
    CpiRuleBaseline,
    DeterministicEacBaseline,
    DummyClassifierBaseline,
    LinearRegressionBaseline,
    LogisticRegressionBaseline,
    MeanRegressionBaseline,
    MedianRegressionBaseline,
)

pytestmark = pytest.mark.unit


def _base_features(n: int, rng: np.random.Generator) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "spi": rng.normal(1.0, 0.15, n),
            "cost_variance": rng.normal(0, 10_000, n),
            "schedule_variance": rng.normal(0, 10_000, n),
            "inflation_multiplier": rng.uniform(1.0, 1.3, n),
            "operational_variance": rng.normal(0, 10_000, n),
            "inflation_component": rng.normal(-5_000, 2_000, n),
            "months_since_start": rng.integers(1, 36, n),
            "months_to_planned_completion": rng.integers(-5, 24, n),
            "lifecycle_fraction": rng.uniform(0, 1.3, n),
            "cpi_trend": rng.normal(0, 0.05, n),
            "spi_trend": rng.normal(0, 0.05, n),
            "cpi_decline_streak": rng.integers(0, 5, n),
            "spi_decline_streak": rng.integers(0, 5, n),
            "change_order_count_to_date": rng.integers(0, 5, n),
            "change_order_amount_to_date": rng.uniform(0, 50_000, n),
            "change_order_amount_ratio_to_date": rng.uniform(0, 0.1, n),
            "gross_floor_area_m2": rng.uniform(500, 20_000, n),
            "number_of_towers": rng.integers(1, 3, n),
            "number_of_units": rng.integers(0, 200, n),
            "project_type": rng.choice(["residential", "commercial"], n),
            "construction_standard": rng.choice(["economy", "standard"], n),
            "lifecycle_stage": rng.choice(["early", "mid", "late"], n),
        }
    )


def _classification_data(n: int = 400, seed: int = 0) -> tuple[pd.DataFrame, pd.Series]:
    rng = np.random.default_rng(seed)
    cpi = rng.normal(1.0, 0.15, n)
    features = _base_features(n, rng)
    features["cpi"] = cpi
    # Real signal: lower CPI -> higher probability of eventual overrun.
    prob_overrun = 1.0 / (1.0 + np.exp((cpi - 0.95) * 12))
    labels = pd.Series(rng.binomial(1, prob_overrun))
    return features, labels


def _regression_data(n: int = 400, seed: int = 1) -> tuple[pd.DataFrame, pd.Series]:
    rng = np.random.default_rng(seed)
    cpi = rng.normal(1.0, 0.15, n)
    features = _base_features(n, rng)
    features["cpi"] = cpi
    features["forecast_cost"] = 1_000_000.0 / cpi
    # Real signal: final cost driven by CPI, plus noise.
    labels = pd.Series(1_000_000.0 / cpi + rng.normal(0, 20_000, n))
    return features, labels


def _train_test_split(
    features: pd.DataFrame, labels: pd.Series, train_fraction: float = 0.7
) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series]:
    cutoff = int(len(features) * train_fraction)
    return (
        features.iloc[:cutoff],
        labels.iloc[:cutoff],
        features.iloc[cutoff:],
        labels.iloc[cutoff:],
    )


class TestDummyClassifierBaseline:
    def test_predicts_constant_training_prior(self) -> None:
        features, labels = _classification_data()
        model = DummyClassifierBaseline().fit(features, labels)
        proba = model.predict_proba(features)
        assert np.allclose(proba, proba[0])
        assert proba[0] == pytest.approx(labels.mean(), abs=1e-6)

    def test_ignores_feature_content(self) -> None:
        features, labels = _classification_data()
        model = DummyClassifierBaseline().fit(features, labels)
        garbage = features.copy()
        garbage["cpi"] = 0.0
        assert np.allclose(model.predict_proba(features), model.predict_proba(garbage))


class TestLogisticRegressionBaseline:
    def test_beats_dummy_baseline_on_data_with_real_signal(self) -> None:
        features, labels = _classification_data()
        train_x, train_y, test_x, test_y = _train_test_split(features, labels)

        dummy_auc = roc_auc_score(
            test_y, DummyClassifierBaseline().fit(train_x, train_y).predict_proba(test_x)
        )
        logistic_auc = roc_auc_score(
            test_y, LogisticRegressionBaseline().fit(train_x, train_y).predict_proba(test_x)
        )
        assert logistic_auc > dummy_auc
        assert logistic_auc > 0.7  # there is a strong real signal in the fixture

    def test_uses_declared_feature_columns(self) -> None:
        assert "cpi" in NUMERIC_FEATURE_COLUMNS
        assert "project_type" in CATEGORICAL_FEATURE_COLUMNS


class TestCpiRuleBaseline:
    def test_flags_rows_below_threshold(self) -> None:
        features = pd.DataFrame({"cpi": [0.80, 0.95, 1.10]})
        model = CpiRuleBaseline(threshold=0.90)
        proba = model.predict_proba(features)
        assert proba.tolist() == [1.0, 0.0, 0.0]

    def test_nan_cpi_is_not_flagged(self) -> None:
        features = pd.DataFrame({"cpi": [np.nan]})
        model = CpiRuleBaseline(threshold=0.90)
        assert model.predict_proba(features).tolist() == [0.0]

    def test_fit_is_a_no_op(self) -> None:
        model = CpiRuleBaseline(threshold=0.90)
        fitted = model.fit(pd.DataFrame({"cpi": [1.0]}), pd.Series([0]))
        assert fitted is model

    def test_has_some_discriminative_power_on_correlated_data(self) -> None:
        features, labels = _classification_data()
        auc = roc_auc_score(labels, CpiRuleBaseline(threshold=0.95).predict_proba(features))
        assert auc > 0.5


class TestMeanMedianRegressionBaselines:
    def test_mean_baseline_predicts_training_mean(self) -> None:
        features, labels = _regression_data()
        model = MeanRegressionBaseline().fit(features, labels)
        predictions = model.predict(features)
        assert np.allclose(predictions, labels.mean())

    def test_median_baseline_predicts_training_median(self) -> None:
        features, labels = _regression_data()
        model = MedianRegressionBaseline().fit(features, labels)
        predictions = model.predict(features)
        assert np.allclose(predictions, labels.median())

    def test_ignores_feature_content(self) -> None:
        features, labels = _regression_data()
        model = MeanRegressionBaseline().fit(features, labels)
        garbage = features.copy()
        garbage["cpi"] = 999.0
        assert np.allclose(model.predict(features), model.predict(garbage))


class TestDeterministicEacBaseline:
    def test_predicts_forecast_cost_column_verbatim(self) -> None:
        features = pd.DataFrame({"forecast_cost": [1.0, 2.0, 3.0]})
        model = DeterministicEacBaseline()
        assert model.predict(features).tolist() == [1.0, 2.0, 3.0]

    def test_requires_no_fitting(self) -> None:
        features = pd.DataFrame({"forecast_cost": [5.0]})
        model = DeterministicEacBaseline()  # fit() never called
        assert model.predict(features).tolist() == [5.0]

    def test_fit_is_a_no_op_kept_for_interface_uniformity(self) -> None:
        model = DeterministicEacBaseline()
        fitted = model.fit(pd.DataFrame({"forecast_cost": [1.0]}), pd.Series([1.0]))
        assert fitted is model


class TestLinearRegressionBaseline:
    def test_beats_mean_baseline_on_data_with_real_signal(self) -> None:
        features, labels = _regression_data()
        train_x, train_y, test_x, test_y = _train_test_split(features, labels)

        mean_mae = mean_absolute_error(
            test_y, MeanRegressionBaseline().fit(train_x, train_y).predict(test_x)
        )
        linear_mae = mean_absolute_error(
            test_y, LinearRegressionBaseline().fit(train_x, train_y).predict(test_x)
        )
        assert linear_mae < mean_mae
