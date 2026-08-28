"""Unit tests for data/prediction drift detection (Section 23)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from buildguard.monitoring.drift import (
    categorical_drift,
    drift_report,
    numeric_drift,
    population_stability_index_categorical,
    population_stability_index_numeric,
)

pytestmark = pytest.mark.monitoring

WARNING = 0.10
CRITICAL = 0.25


class TestPopulationStabilityIndexNumeric:
    def test_identical_distributions_have_near_zero_psi(self) -> None:
        rng = np.random.default_rng(0)
        reference = pd.Series(rng.normal(0, 1, 2000))
        current = pd.Series(rng.normal(0, 1, 2000))
        psi = population_stability_index_numeric(reference, current)
        assert psi < WARNING

    def test_a_clearly_shifted_distribution_has_high_psi(self) -> None:
        rng = np.random.default_rng(0)
        reference = pd.Series(rng.normal(0, 1, 2000))
        current = pd.Series(rng.normal(5, 1, 2000))  # 5-sigma shift
        psi = population_stability_index_numeric(reference, current)
        assert psi > CRITICAL

    def test_a_constant_reference_column_does_not_crash(self) -> None:
        reference = pd.Series([1.0] * 100)
        current = pd.Series([1.0] * 100)
        assert population_stability_index_numeric(reference, current) == pytest.approx(0.0)


class TestPopulationStabilityIndexCategorical:
    def test_identical_proportions_have_zero_psi(self) -> None:
        reference = pd.Series(["a"] * 50 + ["b"] * 50)
        current = pd.Series(["a"] * 50 + ["b"] * 50)
        assert population_stability_index_categorical(reference, current) == pytest.approx(
            0.0, abs=1e-9
        )

    def test_a_flipped_proportion_has_high_psi(self) -> None:
        reference = pd.Series(["a"] * 90 + ["b"] * 10)
        current = pd.Series(["a"] * 10 + ["b"] * 90)
        psi = population_stability_index_categorical(reference, current)
        assert psi > CRITICAL

    def test_a_brand_new_category_is_detected(self) -> None:
        reference = pd.Series(["a"] * 100)
        current = pd.Series(["a"] * 50 + ["c"] * 50)
        psi = population_stability_index_categorical(reference, current)
        assert psi > CRITICAL


class TestNumericDrift:
    def test_identical_distributions_are_not_flagged_and_ks_pvalue_is_high(self) -> None:
        rng = np.random.default_rng(1)
        reference = pd.Series(rng.normal(0, 1, 1000))
        current = pd.Series(rng.normal(0, 1, 1000))
        result = numeric_drift("cpi", reference, current, WARNING, CRITICAL)
        assert result.psi_severity == "none"
        assert result.ks_p_value is not None and result.ks_p_value > 0.01
        assert result.wasserstein_distance is not None and result.wasserstein_distance < 0.5

    def test_shifted_distribution_is_flagged_significant(self) -> None:
        rng = np.random.default_rng(1)
        reference = pd.Series(rng.normal(0, 1, 1000))
        current = pd.Series(rng.normal(4, 1, 1000))
        result = numeric_drift("cpi", reference, current, WARNING, CRITICAL)
        assert result.psi_severity == "significant"
        assert result.ks_p_value is not None and result.ks_p_value < 0.01
        assert result.wasserstein_distance is not None and result.wasserstein_distance > 3.0


class TestCategoricalDrift:
    def test_ks_and_wasserstein_are_not_computed_for_categoricals(self) -> None:
        reference = pd.Series(["a"] * 100)
        current = pd.Series(["a"] * 100)
        result = categorical_drift("project_type", reference, current, WARNING, CRITICAL)
        assert result.ks_statistic is None
        assert result.ks_p_value is None
        assert result.wasserstein_distance is None
        assert result.variable_type == "categorical"


class TestDriftReport:
    def test_covers_every_named_column_with_the_right_method(self) -> None:
        rng = np.random.default_rng(2)
        reference = pd.DataFrame(
            {
                "cpi": rng.normal(1.0, 0.1, 500),
                "project_type": rng.choice(["residential", "commercial"], 500),
            }
        )
        current = reference.copy()
        results = drift_report(reference, current, ["cpi"], ["project_type"], WARNING, CRITICAL)
        by_column = {r.column: r for r in results}
        assert by_column["cpi"].variable_type == "numeric"
        assert by_column["project_type"].variable_type == "categorical"
        assert len(results) == 2
