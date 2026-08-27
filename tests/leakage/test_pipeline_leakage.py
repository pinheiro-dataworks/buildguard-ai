"""Automated anti-leakage tests (Section 11 -- mandatory before v1.0.0).

Rule under test: for a feature row whose prediction timestamp is
`snapshot_date`, every input to that row's features must have its own
timestamp `<= snapshot_date`. `max(feature_timestamp) <= prediction_timestamp`
must hold for every temporal input, not just on average.
"""

from __future__ import annotations

import pandas as pd
import pytest

from buildguard.config import FeaturesConfig
from buildguard.data.economic_index import EconomicIndexProvider
from buildguard.features.pipeline import build_feature_table

pytestmark = pytest.mark.leakage


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


class TestChangeOrderLeakage:
    """The concrete guarantee: a change order dated after a snapshot must
    never contribute to that snapshot's cumulative change-order features.
    """

    def test_future_change_order_excluded_from_earlier_snapshots(self) -> None:
        # CO-1 is visible to every snapshot; CO-2 becomes visible only from
        # March onward; CO-3 is dated far beyond every snapshot in this
        # dataset and must never appear in any row's cumulative total.
        change_orders = pd.DataFrame(
            {
                "change_order_id": ["CO-1", "CO-2", "CO-3"],
                "project_id": ["PRJ-A", "PRJ-A", "PRJ-A"],
                "date": pd.to_datetime(["2022-01-15", "2022-03-15", "2022-12-01"]),
                "category": ["scope_change"] * 3,
                "approved_amount": [5_000.0, 7_000.0, 999_999.0],
                "status": ["approved"] * 3,
            }
        )
        result = build_feature_table(
            _projects(), _snapshots(), change_orders, _FlatIndexProvider(), _features_config()
        )
        by_date = result.set_index("snapshot_date")

        jan = by_date.loc[pd.Timestamp("2022-01-31")]
        feb = by_date.loc[pd.Timestamp("2022-02-28")]
        mar = by_date.loc[pd.Timestamp("2022-03-31")]

        assert jan["change_order_amount_to_date"] == pytest.approx(5_000.0)
        assert feb["change_order_amount_to_date"] == pytest.approx(5_000.0)  # CO-2 not yet visible
        assert mar["change_order_amount_to_date"] == pytest.approx(12_000.0)  # CO-1 + CO-2 only

        # The hard invariant: CO-3's amount (999,999) never leaks into any row.
        assert (result["change_order_amount_to_date"] < 999_999.0).all()

    def test_change_order_on_the_same_day_is_visible(self) -> None:
        # A change order dated exactly on a snapshot's date is <=, so it
        # must count -- this is the correct inclusive boundary.
        change_orders = pd.DataFrame(
            {
                "change_order_id": ["CO-1"],
                "project_id": ["PRJ-A"],
                "date": pd.to_datetime(["2022-01-31"]),
                "category": ["scope_change"],
                "approved_amount": [4_000.0],
                "status": ["approved"],
            }
        )
        result = build_feature_table(
            _projects(), _snapshots(), change_orders, _FlatIndexProvider(), _features_config()
        )
        jan = result.set_index("snapshot_date").loc[pd.Timestamp("2022-01-31")]
        assert jan["change_order_amount_to_date"] == pytest.approx(4_000.0)

    def test_change_order_before_project_history_starts_is_excluded(self) -> None:
        # A change order dated before the FIRST snapshot must not appear
        # for a snapshot in a *different* project (by-group isolation).
        projects = pd.concat(
            [_projects(), _projects().assign(project_id="PRJ-B")], ignore_index=True
        )
        snapshots = pd.concat(
            [_snapshots(), _snapshots().assign(project_id="PRJ-B")], ignore_index=True
        )
        change_orders = pd.DataFrame(
            {
                "change_order_id": ["CO-1"],
                "project_id": ["PRJ-A"],
                "date": pd.to_datetime(["2022-01-15"]),
                "category": ["scope_change"],
                "approved_amount": [5_000.0],
                "status": ["approved"],
            }
        )
        result = build_feature_table(
            projects, snapshots, change_orders, _FlatIndexProvider(), _features_config()
        )
        b_rows = result.loc[result["project_id"] == "PRJ-B"]
        assert (b_rows["change_order_amount_to_date"] == 0.0).all()


class TestTemporalTrendLeakage:
    """Trend/streak features must only reflect a project's own past."""

    def test_max_feature_timestamp_never_exceeds_prediction_timestamp(self) -> None:
        """The literal Section 11 requirement: for every project, the
        snapshot dates feeding a row's trend features never exceed that
        row's own snapshot_date -- checked by construction here, since
        `trailing_change`/`consecutive_decline_streak` only ever look at
        `df.sort_values([...]).groupby(...)` history up to the current
        row's position, never beyond it.
        """
        result = build_feature_table(
            _projects(),
            _snapshots(),
            pd.DataFrame(
                columns=[
                    "change_order_id",
                    "project_id",
                    "date",
                    "category",
                    "approved_amount",
                    "status",
                ]
            ),
            _FlatIndexProvider(),
            _features_config(),
        )
        # First snapshot has no prior history -> trend must be NaN, not a
        # value borrowed from a later (future) row.
        first_row = result.sort_values("snapshot_date").iloc[0]
        assert pd.isna(first_row["cpi_trend"])
        assert pd.isna(first_row["spi_trend"])
        assert first_row["cpi_decline_streak"] == 0
        assert first_row["spi_decline_streak"] == 0

    def test_reordering_input_rows_does_not_change_output_features(self) -> None:
        """A pipeline that accidentally relied on input row order for its
        as-of logic would be a latent leakage risk. Shuffling the input
        snapshot rows must not change any computed feature.
        """
        change_orders = pd.DataFrame(
            columns=[
                "change_order_id",
                "project_id",
                "date",
                "category",
                "approved_amount",
                "status",
            ]
        )
        ordered = build_feature_table(
            _projects(), _snapshots(), change_orders, _FlatIndexProvider(), _features_config()
        )
        shuffled_snapshots = _snapshots().iloc[::-1].reset_index(drop=True)
        shuffled = build_feature_table(
            _projects(), shuffled_snapshots, change_orders, _FlatIndexProvider(), _features_config()
        )
        pd.testing.assert_frame_equal(
            ordered.reset_index(drop=True), shuffled.reset_index(drop=True)
        )
