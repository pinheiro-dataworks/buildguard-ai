"""Unit tests for the EVM formula engine (Section 9 / 35)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from buildguard.features.evm import (
    cost_performance_index,
    cost_variance,
    estimate_at_completion_composite,
    estimate_at_completion_cpi,
    estimate_to_complete,
    schedule_performance_index,
    schedule_variance,
    variance_at_completion,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def snapshot() -> dict[str, pd.Series]:
    # A single, hand-checkable snapshot: behind schedule and over budget.
    return {
        "bac": pd.Series([1_000_000.0]),
        "pv": pd.Series([400_000.0]),
        "ev": pd.Series([350_000.0]),
        "ac": pd.Series([380_000.0]),
    }


class TestVariances:
    def test_cost_variance_unfavorable_when_overspent(self, snapshot: dict[str, pd.Series]) -> None:
        cv = cost_variance(snapshot["ev"], snapshot["ac"])
        assert cv.iloc[0] == pytest.approx(350_000.0 - 380_000.0)
        assert cv.iloc[0] < 0

    def test_schedule_variance_unfavorable_when_behind(self, snapshot: dict[str, pd.Series]) -> None:
        sv = schedule_variance(snapshot["ev"], snapshot["pv"])
        assert sv.iloc[0] == pytest.approx(350_000.0 - 400_000.0)
        assert sv.iloc[0] < 0


class TestPerformanceIndices:
    def test_cpi_matches_hand_calculation(self, snapshot: dict[str, pd.Series]) -> None:
        cpi = cost_performance_index(snapshot["ev"], snapshot["ac"])
        assert cpi.iloc[0] == pytest.approx(350_000.0 / 380_000.0)
        assert cpi.iloc[0] < 1  # over budget

    def test_spi_matches_hand_calculation(self, snapshot: dict[str, pd.Series]) -> None:
        spi = schedule_performance_index(snapshot["ev"], snapshot["pv"])
        assert spi.iloc[0] == pytest.approx(350_000.0 / 400_000.0)
        assert spi.iloc[0] < 1  # behind schedule

    def test_cpi_undefined_when_actual_cost_zero(self) -> None:
        cpi = cost_performance_index(pd.Series([0.0]), pd.Series([0.0]))
        assert np.isnan(cpi.iloc[0])

    def test_spi_undefined_when_planned_value_zero(self) -> None:
        spi = schedule_performance_index(pd.Series([0.0]), pd.Series([0.0]))
        assert np.isnan(spi.iloc[0])

    def test_no_inf_produced_for_nonzero_numerator_zero_denominator(self) -> None:
        # EV > 0 but AC == 0 must still be NaN, never +inf.
        cpi = cost_performance_index(pd.Series([100.0]), pd.Series([0.0]))
        assert np.isnan(cpi.iloc[0])
        assert not np.isinf(cpi.iloc[0])


class TestEstimateAtCompletion:
    def test_eac_cpi_matches_hand_calculation(self, snapshot: dict[str, pd.Series]) -> None:
        cpi = cost_performance_index(snapshot["ev"], snapshot["ac"])
        eac = estimate_at_completion_cpi(snapshot["bac"], cpi)
        expected = 1_000_000.0 / (350_000.0 / 380_000.0)
        assert eac.iloc[0] == pytest.approx(expected)

    def test_eac_composite_matches_hand_calculation(self, snapshot: dict[str, pd.Series]) -> None:
        cpi = cost_performance_index(snapshot["ev"], snapshot["ac"])
        spi = schedule_performance_index(snapshot["ev"], snapshot["pv"])
        eac = estimate_at_completion_composite(
            snapshot["bac"], snapshot["ac"], snapshot["ev"], cpi, spi
        )
        expected = 380_000.0 + (1_000_000.0 - 350_000.0) / (
            (350_000.0 / 380_000.0) * (350_000.0 / 400_000.0)
        )
        assert eac.iloc[0] == pytest.approx(expected)

    def test_composite_eac_more_conservative_when_over_budget_and_behind(
        self, snapshot: dict[str, pd.Series]
    ) -> None:
        # Both efficiency factors < 1 here, so the composite baseline should
        # forecast a higher final cost than the CPI-only baseline.
        cpi = cost_performance_index(snapshot["ev"], snapshot["ac"])
        spi = schedule_performance_index(snapshot["ev"], snapshot["pv"])
        eac_cpi = estimate_at_completion_cpi(snapshot["bac"], cpi)
        eac_composite = estimate_at_completion_composite(
            snapshot["bac"], snapshot["ac"], snapshot["ev"], cpi, spi
        )
        assert eac_composite.iloc[0] > eac_cpi.iloc[0]

    def test_etc_and_vac_are_consistent_with_eac(self, snapshot: dict[str, pd.Series]) -> None:
        cpi = cost_performance_index(snapshot["ev"], snapshot["ac"])
        eac = estimate_at_completion_cpi(snapshot["bac"], cpi)
        etc = estimate_to_complete(eac, snapshot["ac"])
        vac = variance_at_completion(snapshot["bac"], eac)
        assert etc.iloc[0] == pytest.approx(eac.iloc[0] - 380_000.0)
        assert vac.iloc[0] == pytest.approx(1_000_000.0 - eac.iloc[0])
        assert vac.iloc[0] < 0  # forecast overrun, consistent with CPI < 1


class TestVectorizedBehavior:
    def test_operates_elementwise_over_multiple_projects(self) -> None:
        ev = pd.Series([100.0, 200.0, 0.0])
        ac = pd.Series([80.0, 250.0, 0.0])
        cpi = cost_performance_index(ev, ac)
        assert cpi.iloc[0] == pytest.approx(100.0 / 80.0)
        assert cpi.iloc[1] == pytest.approx(200.0 / 250.0)
        assert np.isnan(cpi.iloc[2])
