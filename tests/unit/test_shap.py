"""Unit tests for SHAP/permutation-importance explainability (Section 20)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from buildguard.explainability.shap import (
    CAUSALITY_DISCLAIMER,
    UnsupportedModelError,
    explain_global,
    explain_local,
)
from buildguard.models.baselines import CpiRuleBaseline, DeterministicEacBaseline
from buildguard.models.calibration import evaluate_calibration_methods
from buildguard.models.classification import fit_classifier

pytestmark = pytest.mark.unit


def _classification_data(n: int = 300, seed: int = 0) -> tuple[pd.DataFrame, pd.Series]:
    rng = np.random.default_rng(seed)
    cpi = rng.normal(1.0, 0.15, n)
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
    # Strong, unambiguous signal: low CPI -> positive label. Every other
    # column is pure noise, so both importance measures should single it out.
    labels = pd.Series((cpi < 0.95).astype(int))
    return features, labels


@pytest.fixture(scope="module", params=["random_forest", "lightgbm"])
def fitted_model(request: pytest.FixtureRequest) -> tuple[str, pd.DataFrame, pd.Series, object]:
    features, labels = _classification_data()
    model = fit_classifier(request.param, {"n_estimators": 30}, features, labels, seed=0)
    return request.param, features, labels, model


class TestExplainGlobal:
    def test_shap_and_permutation_both_identify_cpi_as_top_driver(self, fitted_model) -> None:
        _family, features, labels, model = fitted_model
        result = explain_global(model, features, labels, sample_size=150)

        top_shap = result.shap_feature_names[int(np.argmax(result.mean_abs_shap))]
        assert "cpi" in top_shap and "cpi_trend" not in top_shap and "cpi_decline" not in top_shap

        top_perm = result.permutation_feature_names[
            int(np.argmax(result.permutation_importance_mean))
        ]
        assert top_perm == "cpi"

    def test_shap_and_permutation_feature_spaces_have_expected_lengths(self, fitted_model) -> None:
        _family, features, labels, model = fitted_model
        result = explain_global(model, features, labels, sample_size=100)

        # Permutation importance stays in original-column space.
        assert len(result.permutation_feature_names) == features.shape[1]
        assert len(result.permutation_importance_mean) == features.shape[1]
        # SHAP operates on the one-hot-expanded, preprocessed space, so it
        # has at least as many columns as the original (categoricals expand).
        assert len(result.shap_feature_names) >= features.shape[1]
        assert len(result.mean_abs_shap) == len(result.shap_feature_names)

    def test_rejects_a_non_tree_model(self) -> None:
        features, labels = _classification_data(n=50)
        model = CpiRuleBaseline(threshold=0.9).fit(features, labels)
        with pytest.raises(UnsupportedModelError):
            explain_global(model, features, labels)

    def test_rejects_the_deterministic_formula_baseline(self) -> None:
        features, labels = _classification_data(n=50)
        model = DeterministicEacBaseline()
        with pytest.raises(UnsupportedModelError):
            explain_global(model, features, labels)


class TestExplainLocal:
    def test_requires_exactly_one_row(self, fitted_model) -> None:
        _family, features, _labels, model = fitted_model
        with pytest.raises(ValueError, match="exactly one row"):
            explain_local(model, features.iloc[:2], background=features)

    def test_base_value_plus_shap_sum_equals_predicted_probability(self, fitted_model) -> None:
        _family, features, _labels, model = fitted_model
        row = features.iloc[[0]]
        result = explain_local(model, row, background=features)

        reconstructed = result.base_value + result.shap_values.sum()
        assert reconstructed == pytest.approx(result.predicted_value, abs=1e-6)

    def test_predicted_value_is_a_valid_probability(self, fitted_model) -> None:
        _family, features, _labels, model = fitted_model
        result = explain_local(model, features.iloc[[0]], background=features)
        assert 0.0 <= result.predicted_value <= 1.0

    def test_works_through_a_calibrated_model_wrapper(self, fitted_model) -> None:
        _family, features, labels, model = fitted_model
        comparison = evaluate_calibration_methods(model, features, labels)
        result = explain_local(comparison.calibrated_model, features.iloc[[0]], background=features)
        assert 0.0 <= result.predicted_value <= 1.0
        assert len(result.shap_values) == len(result.feature_names)

    def test_rejects_the_deterministic_formula_baseline(self) -> None:
        features, _ = _classification_data(n=50)
        model = DeterministicEacBaseline()
        with pytest.raises(UnsupportedModelError):
            explain_local(model, features.iloc[[0]], background=features)


class TestCausalityDisclaimer:
    def test_disclaimer_text_matches_section_20_verbatim(self) -> None:
        assert CAUSALITY_DISCLAIMER == (
            "Feature attribution explains the model prediction; it does not establish causality."
        )
