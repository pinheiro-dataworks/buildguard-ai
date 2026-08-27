"""Unit tests for candidate regression models (Section 14/15)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import mean_absolute_error

from buildguard.models.baselines import MeanRegressionBaseline
from buildguard.models.regression import (
    build_regressor_pipeline,
    fit_regressor,
    tune_regressor,
)

pytestmark = pytest.mark.unit


def _regression_data(
    n_groups: int = 40, rows_per_group: int = 5, seed: int = 1
) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    rng = np.random.default_rng(seed)
    n = n_groups * rows_per_group
    groups = np.repeat(np.arange(n_groups), rows_per_group)
    cpi = rng.normal(1.0, 0.15, n)
    labels = 1_000_000.0 / cpi + rng.normal(0, 20_000, n)

    features = pd.DataFrame(
        {
            "gross_floor_area_m2": rng.uniform(500, 20_000, n),
            "number_of_towers": rng.integers(1, 3, n),
            "number_of_units": rng.integers(0, 200, n),
            "cpi": cpi,
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
            "project_type": rng.choice(["residential", "commercial"], n),
            "construction_standard": rng.choice(["economy", "standard"], n),
            "lifecycle_stage": rng.choice(["early", "mid", "late"], n),
        }
    )
    return features, pd.Series(labels), pd.Series(groups)


class TestBuildRegressorPipeline:
    def test_unknown_family_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown regressor family"):
            build_regressor_pipeline("not_a_family", {}, seed=0)  # type: ignore[arg-type]

    @pytest.mark.parametrize("family", ["random_forest", "lightgbm"])
    def test_known_families_build_a_working_pipeline(self, family: str) -> None:
        features, labels, _ = _regression_data(n_groups=10, rows_per_group=5)
        pipeline = build_regressor_pipeline(family, {"n_estimators": 20}, seed=0)  # type: ignore[arg-type]
        pipeline.fit(features, labels)
        prediction = pipeline.predict(features)
        assert prediction.shape == (len(features),)


class TestTuneRegressor:
    @pytest.mark.parametrize("family", ["random_forest", "lightgbm"])
    def test_finds_a_reasonably_good_config_on_signal_data(self, family: str) -> None:
        features, labels, groups = _regression_data()
        result = tune_regressor(
            family,
            features,
            labels,
            groups,
            n_trials=3,
            n_splits=2,
            seed=0,  # type: ignore[arg-type]
        )
        assert result.family == family
        assert result.n_trials == 3
        # Mean baseline on this fixture is far worse than a model using CPI.
        naive_mae = float(np.abs(labels - labels.mean()).mean())
        assert result.best_cv_mae < naive_mae

    def test_unknown_family_raises(self) -> None:
        features, labels, groups = _regression_data(n_groups=10, rows_per_group=5)
        with pytest.raises(ValueError, match="Unknown regressor family"):
            tune_regressor(
                "not_a_family",
                features,
                labels,
                groups,
                n_trials=1,
                n_splits=2,
                seed=0,  # type: ignore[arg-type]
            )


class TestFitRegressor:
    def test_fitted_model_beats_mean_baseline_on_held_out_data(self) -> None:
        features, labels, groups = _regression_data()
        train_mask = groups < 30

        mean_model = MeanRegressionBaseline().fit(features[train_mask], labels[train_mask])
        mean_mae = mean_absolute_error(
            labels[~train_mask], mean_model.predict(features[~train_mask])
        )

        model = fit_regressor(
            "random_forest",
            {"n_estimators": 50, "max_depth": 5},
            features[train_mask],
            labels[train_mask],
            seed=0,
        )
        model_mae = mean_absolute_error(labels[~train_mask], model.predict(features[~train_mask]))

        assert model_mae < mean_mae
