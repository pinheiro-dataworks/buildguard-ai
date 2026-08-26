"""Unit tests for the economic index provider interface (Section 8.3)."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from buildguard.data.economic_index import (
    DemoIndexProvider,
    ExternalLicensedProvider,
)

pytestmark = pytest.mark.unit


def _provider(reference_date: str = "2026-01-01", history_years: int = 5) -> DemoIndexProvider:
    return DemoIndexProvider(
        reference_date=dt.date.fromisoformat(reference_date), history_years=history_years
    )


class TestDemoIndexProvider:
    def test_series_is_monotonically_non_decreasing(self) -> None:
        series = _provider().get_series()
        values = series.sort_values("reference_month")["index_value"].to_numpy()
        assert np.all(np.diff(values) >= 0)

    def test_series_starts_at_base_100(self) -> None:
        series = _provider().get_series()
        assert series.sort_values("reference_month")["index_value"].iloc[0] == pytest.approx(100.0)

    def test_series_covers_the_configured_history_window(self) -> None:
        provider = _provider(reference_date="2026-01-01", history_years=5)
        series = provider.get_series()
        assert series["reference_month"].min() <= pd.Timestamp("2021-01-31")
        assert series["reference_month"].max() <= pd.Timestamp("2026-01-01")

    def test_get_series_is_cached_and_stable_across_calls(self) -> None:
        provider = _provider()
        first = provider.get_series()
        second = provider.get_series()
        assert first.equals(second)

    def test_same_parameters_produce_identical_series(self) -> None:
        a = _provider().get_series()
        b = _provider().get_series()
        assert a.equals(b)

    def test_different_reference_date_changes_the_series(self) -> None:
        a = _provider(reference_date="2026-01-01").get_series()
        b = _provider(reference_date="2024-01-01").get_series()
        assert not a.equals(b)

    def test_value_at_exact_month_end(self) -> None:
        provider = _provider()
        series = provider.get_series()
        some_month = series["reference_month"].iloc[10]
        expected = series.loc[series["reference_month"] == some_month, "index_value"].iloc[0]
        assert provider.value_at(some_month) == pytest.approx(expected)

    def test_value_at_mid_month_falls_back_to_month_end(self) -> None:
        provider = _provider()
        series = provider.get_series()
        some_month_end = series["reference_month"].iloc[10]
        mid_month = some_month_end - pd.Timedelta(days=10)
        expected = series.loc[series["reference_month"] == some_month_end, "index_value"].iloc[0]
        assert provider.value_at(mid_month) == pytest.approx(expected)

    def test_value_at_grows_over_time(self) -> None:
        provider = _provider()
        early = provider.value_at(dt.date(2021, 6, 1))
        late = provider.value_at(dt.date(2025, 12, 1))
        assert late > early


class TestExternalLicensedProvider:
    def test_instantiation_raises_not_implemented(self) -> None:
        with pytest.raises(NotImplementedError, match="no verified licensed data source"):
            ExternalLicensedProvider()
