"""Unit tests for candidate classification models (Section 14/15)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import roc_auc_score

from buildguard.models.classification import (
    build_classifier_pipeline,
    fit_classifier,
    tune_classifier,
)

pytestmark = pytest.mark.unit


def _classification_data(
    n_groups: int = 40, rows_per_group: int = 5, seed: int = 0
) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    rng = np.random.default_rng(seed)
    n = n_groups * rows_per_group
    groups = np.repeat(np.arange(n_groups), rows_per_group)
    cpi = rng.normal(1.0, 0.15, n)
    prob_overrun = 1.0 / (1.0 + np.exp((cpi - 0.95) * 12))
    labels = rng.binomial(1, prob_overrun)

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


class TestBuildClassifierPipeline:
    def test_unknown_family_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown classifier family"):
            build_classifier_pipeline("not_a_family", {}, seed=0)  # type: ignore[arg-type]

    @pytest.mark.parametrize("family", ["random_forest", "lightgbm"])
    def test_known_families_build_a_working_pipeline(self, family: str) -> None:
        features, labels, _ = _classification_data(n_groups=10, rows_per_group=5)
        pipeline = build_classifier_pipeline(family, {"n_estimators": 20}, seed=0)  # type: ignore[arg-type]
        pipeline.fit(features, labels)
        proba = pipeline.predict_proba(features)[:, 1]
        assert proba.shape == (len(features),)
        assert ((proba >= 0) & (proba <= 1)).all()


class TestTuneClassifier:
    @pytest.mark.parametrize("family", ["random_forest", "lightgbm"])
    def test_finds_a_reasonably_good_config_on_signal_data(self, family: str) -> None:
        features, labels, groups = _classification_data()
        result = tune_classifier(
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
        assert result.best_cv_auc > 0.6  # there is a strong real signal in the fixture

    def test_unknown_family_raises(self) -> None:
        features, labels, groups = _classification_data(n_groups=10, rows_per_group=5)
        with pytest.raises(ValueError, match="Unknown classifier family"):
            tune_classifier(
                "not_a_family",
                features,
                labels,
                groups,
                n_trials=1,
                n_splits=2,
                seed=0,  # type: ignore[arg-type]
            )


class TestFitClassifier:
    def test_fitted_model_beats_random_on_held_out_data(self) -> None:
        features, labels, groups = _classification_data()
        train_mask = groups < 30
        model = fit_classifier(
            "random_forest",
            {"n_estimators": 50, "max_depth": 5},
            features[train_mask],
            labels[train_mask],
            seed=0,
        )
        proba = model.predict_proba(features[~train_mask])[:, 1]
        auc = roc_auc_score(labels[~train_mask], proba)
        assert auc > 0.6
