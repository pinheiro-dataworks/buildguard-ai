"""Unit tests for ground-truth label derivation (Section 6 / 11)."""

from __future__ import annotations

import pandas as pd
import pytest

from buildguard.data.economic_index import EconomicIndexProvider
from buildguard.data.labels import resolve_outcomes

pytestmark = pytest.mark.unit


class _FlatIndexProvider(EconomicIndexProvider):
    """No inflation at all -- nominal and real costs coincide."""

    def get_series(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "reference_month": pd.to_datetime(["2020-01-31", "2026-01-31"]),
                "index_name": "FLAT",
                "index_value": [100.0, 100.0],
            }
        )


def _projects() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "project_id": ["PRJ-A", "PRJ-B", "PRJ-C"],
            "planned_start_date": pd.to_datetime(["2022-01-01", "2022-01-01", "2022-01-01"]),
            "planned_completion_date": pd.to_datetime(["2023-01-01", "2023-01-01", "2023-01-01"]),
            "approved_budget": [1_000_000.0, 1_000_000.0, 1_000_000.0],
        }
    )


class TestResolvedProjects:
    def test_completed_on_budget_and_on_time_is_not_flagged(self) -> None:
        snapshots = pd.DataFrame(
            {
                "project_id": ["PRJ-A"],
                "snapshot_date": pd.to_datetime(["2023-01-01"]),
                "actual_progress": [1.0],
                "actual_cost": [1_000_000.0],
            }
        )
        outcomes = resolve_outcomes(_projects(), snapshots, _FlatIndexProvider(), 0.10, 14)
        row = outcomes.set_index("project_id").loc["PRJ-A"]
        assert row["is_resolved"]
        assert not row["cost_overrun"]
        assert not row["schedule_delay"]
        assert row["final_cost_real"] == pytest.approx(1_000_000.0)

    def test_completed_over_budget_and_late_is_flagged(self) -> None:
        snapshots = pd.DataFrame(
            {
                "project_id": ["PRJ-A"],
                "snapshot_date": pd.to_datetime(["2023-03-01"]),
                "actual_progress": [1.0],
                "actual_cost": [1_300_000.0],
            }
        )
        outcomes = resolve_outcomes(_projects(), snapshots, _FlatIndexProvider(), 0.10, 14)
        row = outcomes.set_index("project_id").loc["PRJ-A"]
        assert row["cost_overrun"]
        assert row["schedule_delay"]
        assert row["delay_days"] == pytest.approx(59.0)

    def test_overrun_uses_tolerance_band_not_zero(self) -> None:
        # 5% over budget, but tolerance is 10% -> not flagged.
        snapshots = pd.DataFrame(
            {
                "project_id": ["PRJ-A"],
                "snapshot_date": pd.to_datetime(["2023-01-01"]),
                "actual_progress": [1.0],
                "actual_cost": [1_050_000.0],
            }
        )
        outcomes = resolve_outcomes(_projects(), snapshots, _FlatIndexProvider(), 0.10, 14)
        row = outcomes.set_index("project_id").loc["PRJ-A"]
        assert not row["cost_overrun"]

    def test_delay_at_exactly_tolerance_is_not_flagged(self) -> None:
        # 14 days late, tolerance is 14 days -> strictly greater required.
        snapshots = pd.DataFrame(
            {
                "project_id": ["PRJ-A"],
                "snapshot_date": pd.to_datetime(["2023-01-15"]),
                "actual_progress": [1.0],
                "actual_cost": [1_000_000.0],
            }
        )
        outcomes = resolve_outcomes(_projects(), snapshots, _FlatIndexProvider(), 0.10, 14)
        row = outcomes.set_index("project_id").loc["PRJ-A"]
        assert not row["schedule_delay"]

    def test_early_completion_gives_negative_delay_days(self) -> None:
        snapshots = pd.DataFrame(
            {
                "project_id": ["PRJ-A"],
                "snapshot_date": pd.to_datetime(["2022-11-01"]),
                "actual_progress": [1.0],
                "actual_cost": [900_000.0],
            }
        )
        outcomes = resolve_outcomes(_projects(), snapshots, _FlatIndexProvider(), 0.10, 14)
        row = outcomes.set_index("project_id").loc["PRJ-A"]
        assert row["delay_days"] < 0
        assert not row["schedule_delay"]


class TestUnresolvedProjects:
    def test_in_flight_project_has_no_resolved_outcome(self) -> None:
        snapshots = pd.DataFrame(
            {
                "project_id": ["PRJ-A"],
                "snapshot_date": pd.to_datetime(["2022-06-30"]),
                "actual_progress": [0.4],
                "actual_cost": [300_000.0],
            }
        )
        outcomes = resolve_outcomes(_projects(), snapshots, _FlatIndexProvider(), 0.10, 14)
        row = outcomes.set_index("project_id").loc["PRJ-A"]
        assert not row["is_resolved"]
        assert pd.isna(row["actual_completion_date"])
        assert pd.isna(row["final_cost_real"])
        assert pd.isna(row["cost_overrun"])
        assert pd.isna(row["schedule_delay"])


class TestMultipleProjects:
    def test_only_the_last_snapshot_per_project_is_used(self) -> None:
        snapshots = pd.DataFrame(
            {
                "project_id": ["PRJ-A", "PRJ-A", "PRJ-A"],
                "snapshot_date": pd.to_datetime(["2022-06-30", "2022-12-31", "2023-01-01"]),
                "actual_progress": [0.5, 0.95, 1.0],
                "actual_cost": [500_000.0, 950_000.0, 1_000_000.0],
            }
        )
        outcomes = resolve_outcomes(_projects(), snapshots, _FlatIndexProvider(), 0.10, 14)
        row = outcomes.set_index("project_id").loc["PRJ-A"]
        assert row["is_resolved"]
        assert row["final_cost_real"] == pytest.approx(1_000_000.0)

    def test_resolves_each_project_independently(self) -> None:
        snapshots = pd.DataFrame(
            {
                "project_id": ["PRJ-A", "PRJ-B", "PRJ-C"],
                "snapshot_date": pd.to_datetime(["2023-01-01", "2022-06-30", "2023-06-01"]),
                "actual_progress": [1.0, 0.5, 1.0],
                "actual_cost": [1_000_000.0, 500_000.0, 1_400_000.0],
            }
        )
        outcomes = resolve_outcomes(_projects(), snapshots, _FlatIndexProvider(), 0.10, 14)
        by_project = outcomes.set_index("project_id")
        assert by_project.loc["PRJ-A", "is_resolved"]
        assert not by_project.loc["PRJ-B", "is_resolved"]
        assert by_project.loc["PRJ-C", "cost_overrun"]
