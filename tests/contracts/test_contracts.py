"""Data contract tests (Section 8.5 / 35): required columns, ranges,
uniqueness, categorical domains, and chronological consistency.
"""

from __future__ import annotations

import pandas as pd
import pytest

from buildguard.data.contracts import (
    DataContractError,
    check_snapshots_within_project_lifecycle,
    validate_change_orders,
    validate_economic_index,
    validate_project_snapshots,
    validate_projects,
    validate_suppliers,
    validate_work_packages,
)

pytestmark = pytest.mark.contracts


def _valid_projects() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "project_id": ["PRJ-001", "PRJ-002"],
            "project_type": ["residential", "commercial"],
            "city": ["Sao Paulo", "Rio de Janeiro"],
            "state": ["SP", "RJ"],
            "gross_floor_area_m2": [12000.0, 8000.0],
            "number_of_towers": [2, 1],
            "number_of_units": [150, 60],
            "construction_standard": ["standard", "high_standard"],
            "planned_start_date": pd.to_datetime(["2022-01-01", "2022-06-01"]),
            "planned_completion_date": pd.to_datetime(["2024-01-01", "2024-06-01"]),
            "approved_budget": [15_000_000.0, 9_000_000.0],
        }
    )


def _valid_snapshots() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "project_id": ["PRJ-001", "PRJ-001"],
            "snapshot_date": pd.to_datetime(["2022-02-01", "2022-03-01"]),
            "planned_progress": [0.05, 0.10],
            "actual_progress": [0.04, 0.09],
            "planned_cost": [700_000.0, 1_400_000.0],
            "actual_cost": [650_000.0, 1_350_000.0],
            "committed_cost": [800_000.0, 1_500_000.0],
            "earned_value": [600_000.0, 1_200_000.0],
            "forecast_cost": [15_200_000.0, 15_300_000.0],
        }
    )


class TestProjectSchema:
    def test_valid_projects_pass(self) -> None:
        result = validate_projects(_valid_projects())
        assert len(result) == 2

    def test_non_positive_budget_rejected(self) -> None:
        df = _valid_projects()
        df.loc[0, "approved_budget"] = 0.0
        with pytest.raises(DataContractError):
            validate_projects(df)

    def test_completion_before_start_rejected(self) -> None:
        df = _valid_projects()
        df.loc[0, "planned_completion_date"] = pd.Timestamp("2020-01-01")
        with pytest.raises(DataContractError):
            validate_projects(df)

    def test_unknown_project_type_rejected(self) -> None:
        df = _valid_projects()
        df.loc[0, "project_type"] = "spaceship"
        with pytest.raises(DataContractError):
            validate_projects(df)

    def test_duplicate_project_id_rejected(self) -> None:
        df = _valid_projects()
        df.loc[1, "project_id"] = "PRJ-001"
        with pytest.raises(DataContractError):
            validate_projects(df)


class TestProjectSnapshotSchema:
    def test_valid_snapshots_pass(self) -> None:
        result = validate_project_snapshots(_valid_snapshots())
        assert len(result) == 2

    def test_progress_out_of_range_rejected(self) -> None:
        df = _valid_snapshots()
        df.loc[0, "actual_progress"] = 1.2
        with pytest.raises(DataContractError):
            validate_project_snapshots(df)

    def test_negative_earned_value_rejected(self) -> None:
        df = _valid_snapshots()
        df.loc[0, "earned_value"] = -1.0
        with pytest.raises(DataContractError):
            validate_project_snapshots(df)

    def test_duplicate_project_snapshot_date_rejected(self) -> None:
        df = _valid_snapshots()
        df.loc[1, "snapshot_date"] = df.loc[0, "snapshot_date"]
        with pytest.raises(DataContractError):
            validate_project_snapshots(df)


class TestCrossTableChronology:
    def test_snapshot_before_project_start_rejected(self) -> None:
        projects = _valid_projects()
        snapshots = _valid_snapshots()
        snapshots.loc[0, "snapshot_date"] = pd.Timestamp("2021-01-01")  # before PRJ-001 start
        with pytest.raises(DataContractError):
            check_snapshots_within_project_lifecycle(projects, snapshots)

    def test_snapshot_within_lifecycle_passes(self) -> None:
        check_snapshots_within_project_lifecycle(_valid_projects(), _valid_snapshots())

    def test_snapshot_referencing_unknown_project_rejected(self) -> None:
        projects = _valid_projects()
        snapshots = _valid_snapshots()
        snapshots.loc[0, "project_id"] = "PRJ-999"
        with pytest.raises(DataContractError):
            check_snapshots_within_project_lifecycle(projects, snapshots)


class TestWorkPackageSchema:
    def test_valid_work_packages_pass(self) -> None:
        df = pd.DataFrame(
            {
                "project_id": ["PRJ-001", "PRJ-001"],
                "work_package_id": ["WP-01", "WP-02"],
                "work_package_name": ["Foundations", "Structure"],
                "budget": [500_000.0, 1_200_000.0],
                "actual_cost": [480_000.0, 1_150_000.0],
                "planned_progress": [1.0, 0.6],
                "actual_progress": [1.0, 0.55],
            }
        )
        result = validate_work_packages(df)
        assert len(result) == 2

    def test_duplicate_work_package_in_project_rejected(self) -> None:
        df = pd.DataFrame(
            {
                "project_id": ["PRJ-001", "PRJ-001"],
                "work_package_id": ["WP-01", "WP-01"],
                "work_package_name": ["Foundations", "Foundations"],
                "budget": [500_000.0, 500_000.0],
                "actual_cost": [480_000.0, 480_000.0],
                "planned_progress": [1.0, 1.0],
                "actual_progress": [1.0, 1.0],
            }
        )
        with pytest.raises(DataContractError):
            validate_work_packages(df)


class TestChangeOrderSchema:
    def test_valid_change_orders_pass(self) -> None:
        df = pd.DataFrame(
            {
                "change_order_id": ["CO-001"],
                "project_id": ["PRJ-001"],
                "date": pd.to_datetime(["2022-05-01"]),
                "category": ["scope_change"],
                "approved_amount": [50_000.0],
                "status": ["approved"],
            }
        )
        result = validate_change_orders(df)
        assert len(result) == 1

    def test_invalid_status_rejected(self) -> None:
        df = pd.DataFrame(
            {
                "change_order_id": ["CO-001"],
                "project_id": ["PRJ-001"],
                "date": pd.to_datetime(["2022-05-01"]),
                "category": ["scope_change"],
                "approved_amount": [50_000.0],
                "status": ["maybe"],
            }
        )
        with pytest.raises(DataContractError):
            validate_change_orders(df)


class TestSupplierSchema:
    def test_valid_suppliers_pass(self) -> None:
        df = pd.DataFrame(
            {
                "supplier_id": ["SUP-001"],
                "supplier_category": ["structural"],
                "project_id": ["PRJ-001"],
                "contract_value": [2_000_000.0],
                "delivery_delay_days": [5],
                "quality_score": [8.5],
                "rework_cost": [10_000.0],
            }
        )
        result = validate_suppliers(df)
        assert len(result) == 1

    def test_quality_score_out_of_range_rejected(self) -> None:
        df = pd.DataFrame(
            {
                "supplier_id": ["SUP-001"],
                "supplier_category": ["structural"],
                "project_id": ["PRJ-001"],
                "contract_value": [2_000_000.0],
                "delivery_delay_days": [5],
                "quality_score": [11.0],
                "rework_cost": [10_000.0],
            }
        )
        with pytest.raises(DataContractError):
            validate_suppliers(df)


class TestEconomicIndexSchema:
    def test_valid_index_passes(self) -> None:
        df = pd.DataFrame(
            {
                "reference_month": pd.to_datetime(["2022-01-01", "2022-02-01"]),
                "index_name": ["INCC", "INCC"],
                "index_value": [100.0, 100.8],
            }
        )
        result = validate_economic_index(df)
        assert len(result) == 2

    def test_non_positive_index_value_rejected(self) -> None:
        df = pd.DataFrame(
            {
                "reference_month": pd.to_datetime(["2022-01-01"]),
                "index_name": ["INCC"],
                "index_value": [0.0],
            }
        )
        with pytest.raises(DataContractError):
            validate_economic_index(df)
