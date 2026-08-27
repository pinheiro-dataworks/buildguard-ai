"""Unit tests for the leakage-safe feature pipeline (Section 11 / 28)."""

from __future__ import annotations

import pandas as pd
import pytest

from buildguard.config import FeaturesConfig
from buildguard.data.economic_index import EconomicIndexProvider
from buildguard.features.pipeline import build_feature_table

pytestmark = pytest.mark.unit


class _FlatIndexProvider(EconomicIndexProvider):
    def get_series(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "reference_month": pd.to_datetime(["2020-01-31", "2026-01-31"]),
                "index_name": "FLAT",
                "index_value": [100.0, 100.0],
            }
        )


def _features_config() -> FeaturesConfig:
    return FeaturesConfig(
        lifecycle_early_threshold=0.33, lifecycle_late_threshold=0.66, trend_window_months=1
    )


def _projects() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "project_id": ["PRJ-A"],
            "project_type": ["residential"],
            "city": ["Sao Paulo"],
            "state": ["SP"],
            "gross_floor_area_m2": [5000.0],
            "number_of_towers": [1],
            "number_of_units": [80],
            "construction_standard": ["standard"],
            "planned_start_date": pd.to_datetime(["2022-01-01"]),
            "planned_completion_date": pd.to_datetime(["2023-01-01"]),
            "approved_budget": [1_000_000.0],
        }
    )


def _snapshots() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "project_id": ["PRJ-A", "PRJ-A", "PRJ-A"],
            "snapshot_date": pd.to_datetime(["2022-01-31", "2022-02-28", "2022-03-31"]),
            "planned_progress": [0.1, 0.2, 0.3],
            "actual_progress": [0.08, 0.15, 0.20],
            "planned_cost": [100_000.0, 200_000.0, 300_000.0],
            "actual_cost": [90_000.0, 180_000.0, 260_000.0],
            "committed_cost": [95_000.0, 190_000.0, 270_000.0],
            "earned_value": [80_000.0, 150_000.0, 200_000.0],
            "forecast_cost": [1_100_000.0, 1_150_000.0, 1_200_000.0],
        }
    )


def _empty_change_orders() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["change_order_id", "project_id", "date", "category", "approved_amount", "status"]
    )


class TestOutputShape:
    def test_one_row_per_input_snapshot(self) -> None:
        result = build_feature_table(
            _projects(),
            _snapshots(),
            _empty_change_orders(),
            _FlatIndexProvider(),
            _features_config(),
        )
        assert len(result) == 3

    def test_includes_evm_inflation_and_temporal_columns(self) -> None:
        result = build_feature_table(
            _projects(),
            _snapshots(),
            _empty_change_orders(),
            _FlatIndexProvider(),
            _features_config(),
        )
        expected_columns = {
            "cpi",
            "spi",
            "cost_variance",
            "schedule_variance",
            "inflation_multiplier",
            "operational_variance",
            "inflation_component",
            "months_since_start",
            "lifecycle_fraction",
            "lifecycle_stage",
            "cpi_trend",
            "cpi_decline_streak",
            "change_order_count_to_date",
            "change_order_amount_to_date",
            "change_order_amount_ratio_to_date",
        }
        assert expected_columns <= set(result.columns)

    def test_excludes_work_packages_and_suppliers_columns(self) -> None:
        # Structural guard for the documented limitation (module docstring):
        # nothing named like a work-package/supplier field should ever
        # appear, since those tables are not point-in-time safe to join.
        result = build_feature_table(
            _projects(),
            _snapshots(),
            _empty_change_orders(),
            _FlatIndexProvider(),
            _features_config(),
        )
        forbidden = {"work_package_id", "supplier_id", "quality_score", "rework_cost"}
        assert forbidden.isdisjoint(result.columns)

    def test_no_label_columns_present(self) -> None:
        result = build_feature_table(
            _projects(),
            _snapshots(),
            _empty_change_orders(),
            _FlatIndexProvider(),
            _features_config(),
        )
        forbidden = {"cost_overrun", "schedule_delay", "final_cost_real", "final_cost_nominal"}
        assert forbidden.isdisjoint(result.columns)


class TestFeatureCorrectness:
    def test_cpi_matches_direct_evm_calculation(self) -> None:
        result = build_feature_table(
            _projects(),
            _snapshots(),
            _empty_change_orders(),
            _FlatIndexProvider(),
            _features_config(),
        )
        row = result.iloc[0]
        assert row["cpi"] == pytest.approx(80_000.0 / 90_000.0)

    def test_no_inflation_means_operational_variance_equals_cost_variance(self) -> None:
        # _FlatIndexProvider has zero inflation, so real == nominal.
        result = build_feature_table(
            _projects(),
            _snapshots(),
            _empty_change_orders(),
            _FlatIndexProvider(),
            _features_config(),
        )
        assert (
            result["operational_variance"] - result["cost_variance"]
        ).abs().max() == pytest.approx(0.0)
        assert result["inflation_component"].abs().max() == pytest.approx(0.0)

    def test_months_since_start_increases_monotonically(self) -> None:
        result = build_feature_table(
            _projects(),
            _snapshots(),
            _empty_change_orders(),
            _FlatIndexProvider(),
            _features_config(),
        )
        values = result.sort_values("snapshot_date")["months_since_start"].tolist()
        assert values == sorted(values)

    def test_empty_change_orders_gives_zero_cumulative_features(self) -> None:
        result = build_feature_table(
            _projects(),
            _snapshots(),
            _empty_change_orders(),
            _FlatIndexProvider(),
            _features_config(),
        )
        assert (result["change_order_count_to_date"] == 0).all()
        assert (result["change_order_amount_to_date"] == 0.0).all()


class TestMultipleProjects:
    def test_rows_stay_grouped_by_project_and_ordered_by_date(self) -> None:
        projects = pd.concat(
            [_projects(), _projects().assign(project_id="PRJ-B")], ignore_index=True
        )
        snapshots_a = _snapshots()
        snapshots_b = _snapshots().assign(project_id="PRJ-B")
        snapshots = pd.concat(
            [snapshots_b, snapshots_a], ignore_index=True
        )  # deliberately unsorted

        result = build_feature_table(
            projects, snapshots, _empty_change_orders(), _FlatIndexProvider(), _features_config()
        )
        assert result["project_id"].tolist() == ["PRJ-A"] * 3 + ["PRJ-B"] * 3
        for _, group in result.groupby("project_id"):
            dates = group["snapshot_date"].tolist()
            assert dates == sorted(dates)
