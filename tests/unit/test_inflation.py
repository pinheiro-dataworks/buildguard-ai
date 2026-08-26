"""Unit tests for inflation-adjusted cost normalization (Section 10)."""

from __future__ import annotations

import pandas as pd
import pytest

from buildguard.data.economic_index import EconomicIndexProvider
from buildguard.features import evm
from buildguard.features.inflation import (
    inflation_component,
    inflation_multiplier,
    operational_variance,
    real_actual_cost,
    real_budget,
)

pytestmark = pytest.mark.unit


class _FakeIndexProvider(EconomicIndexProvider):
    """A tiny, hand-controlled index: 100 at baseline, 120 one year later."""

    def __init__(self) -> None:
        self._series = pd.DataFrame(
            {
                "reference_month": pd.to_datetime(["2022-01-31", "2023-01-31"]),
                "index_name": "FAKE",
                "index_value": [100.0, 120.0],
            }
        )

    def get_series(self) -> pd.DataFrame:
        return self._series


@pytest.fixture
def provider() -> _FakeIndexProvider:
    return _FakeIndexProvider()


class TestInflationMultiplier:
    def test_multiplier_matches_hand_calculation(self, provider: _FakeIndexProvider) -> None:
        snapshot_date = pd.Series([pd.Timestamp("2023-01-31")])
        baseline_date = pd.Series([pd.Timestamp("2022-01-31")])
        multiplier = inflation_multiplier(snapshot_date, baseline_date, provider)
        assert multiplier.iloc[0] == pytest.approx(1.2)

    def test_multiplier_is_one_when_dates_match(self, provider: _FakeIndexProvider) -> None:
        date = pd.Series([pd.Timestamp("2022-01-31")])
        multiplier = inflation_multiplier(date, date, provider)
        assert multiplier.iloc[0] == pytest.approx(1.0)


class TestRealActualCost:
    def test_deflates_by_the_multiplier(self) -> None:
        nominal = pd.Series([120_000.0])
        multiplier = pd.Series([1.2])
        real = real_actual_cost(nominal, multiplier)
        assert real.iloc[0] == pytest.approx(100_000.0)

    def test_no_inflation_leaves_cost_unchanged(self) -> None:
        nominal = pd.Series([100_000.0])
        multiplier = pd.Series([1.0])
        assert real_actual_cost(nominal, multiplier).iloc[0] == pytest.approx(100_000.0)


class TestRealBudget:
    def test_is_identity(self) -> None:
        budget = pd.Series([1_000_000.0, 2_500_000.0])
        assert real_budget(budget).equals(budget)


class TestDecomposition:
    """nominal_cost_variance == operational_variance + inflation_component."""

    def test_decomposition_identity_holds(self) -> None:
        earned_value = pd.Series([900_000.0])
        actual_cost_nominal = pd.Series([1_200_000.0])
        multiplier = pd.Series([1.2])  # 20% cumulative inflation

        real_ac = real_actual_cost(actual_cost_nominal, multiplier)
        nominal_cv = evm.cost_variance(earned_value, actual_cost_nominal)
        op_var = operational_variance(earned_value, real_ac)
        infl_component = inflation_component(actual_cost_nominal, real_ac)

        assert (op_var + infl_component).iloc[0] == pytest.approx(nominal_cv.iloc[0])

    def test_inflation_component_is_non_positive_when_prices_rose(self) -> None:
        actual_cost_nominal = pd.Series([1_200_000.0])
        multiplier = pd.Series([1.2])
        real_ac = real_actual_cost(actual_cost_nominal, multiplier)
        infl_component = inflation_component(actual_cost_nominal, real_ac)
        assert infl_component.iloc[0] <= 0

    def test_operational_variance_more_favorable_than_nominal_when_prices_rose(self) -> None:
        earned_value = pd.Series([900_000.0])
        actual_cost_nominal = pd.Series([1_200_000.0])
        multiplier = pd.Series([1.2])
        real_ac = real_actual_cost(actual_cost_nominal, multiplier)

        nominal_cv = evm.cost_variance(earned_value, actual_cost_nominal)
        op_var = operational_variance(earned_value, real_ac)
        # Stripping out inflation should make the variance look less bad
        # (less negative / more positive), never worse.
        assert op_var.iloc[0] >= nominal_cv.iloc[0]

    def test_no_inflation_makes_all_three_variances_equal(self) -> None:
        earned_value = pd.Series([900_000.0])
        actual_cost_nominal = pd.Series([1_200_000.0])
        multiplier = pd.Series([1.0])  # no inflation since baseline
        real_ac = real_actual_cost(actual_cost_nominal, multiplier)

        nominal_cv = evm.cost_variance(earned_value, actual_cost_nominal)
        op_var = operational_variance(earned_value, real_ac)
        infl_component = inflation_component(actual_cost_nominal, real_ac)

        assert op_var.iloc[0] == pytest.approx(nominal_cv.iloc[0])
        assert infl_component.iloc[0] == pytest.approx(0.0)
