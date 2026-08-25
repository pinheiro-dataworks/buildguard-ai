"""Data contracts for the core BuildGuard AI data model (Section 8.4/8.5).

Each table in the data model gets a declarative `pandera` schema enforcing,
at minimum: non-null keys, valid value ranges, categorical domains, and
uniqueness constraints. Validation always runs with ``lazy=True`` so every
violation in a batch is collected before raising, and always with
``coerce=False`` so a malformed value fails loudly instead of being
silently cast into range — see Section 8.5.
"""

from __future__ import annotations

import pandas as pd
import pandera.pandas as pa
from pandera.typing import Series

from buildguard.data.enums import (
    ChangeOrderCategory,
    ChangeOrderStatus,
    ConstructionStandard,
    ProjectType,
    SupplierCategory,
    values,
)


class DataContractError(ValueError):
    """Raised when a dataframe violates a BuildGuard data contract.

    Wraps pandera's lazy-validation failure cases into one readable message
    instead of leaking the raw pandera exception type to callers.
    """

    def __init__(self, schema_name: str, failure_cases: pd.DataFrame) -> None:
        self.schema_name = schema_name
        self.failure_cases = failure_cases
        summary = failure_cases.loc[:, ["column", "check", "failure_case"]].to_string(index=False)
        super().__init__(f"{schema_name}: {len(failure_cases)} contract violation(s):\n{summary}")


class ProjectSchema(pa.DataFrameModel):
    project_id: Series[str] = pa.Field(nullable=False, unique=True)
    project_type: Series[str] = pa.Field(isin=values(ProjectType))
    city: Series[str] = pa.Field(nullable=False)
    state: Series[str] = pa.Field(nullable=False)
    gross_floor_area_m2: Series[float] = pa.Field(gt=0)
    number_of_towers: Series[int] = pa.Field(ge=1)
    number_of_units: Series[int] = pa.Field(ge=0)
    construction_standard: Series[str] = pa.Field(isin=values(ConstructionStandard))
    planned_start_date: Series[pd.Timestamp] = pa.Field(nullable=False)
    planned_completion_date: Series[pd.Timestamp] = pa.Field(nullable=False)
    approved_budget: Series[float] = pa.Field(gt=0)

    class Config:
        strict = True
        coerce = False

    @pa.dataframe_check
    def completion_after_start(cls, df: pd.DataFrame) -> pd.Series[bool]:  # type: ignore[misc]  # noqa: N805
        return df["planned_completion_date"] > df["planned_start_date"]


class ProjectSnapshotSchema(pa.DataFrameModel):
    project_id: Series[str] = pa.Field(nullable=False)
    snapshot_date: Series[pd.Timestamp] = pa.Field(nullable=False)
    planned_progress: Series[float] = pa.Field(ge=0, le=1)
    actual_progress: Series[float] = pa.Field(ge=0, le=1)
    planned_cost: Series[float] = pa.Field(ge=0)
    actual_cost: Series[float] = pa.Field(ge=0)
    committed_cost: Series[float] = pa.Field(ge=0)
    earned_value: Series[float] = pa.Field(ge=0)
    forecast_cost: Series[float] = pa.Field(ge=0)

    class Config:
        strict = True
        coerce = False
        unique = ("project_id", "snapshot_date")


class WorkPackageSchema(pa.DataFrameModel):
    project_id: Series[str] = pa.Field(nullable=False)
    work_package_id: Series[str] = pa.Field(nullable=False)
    work_package_name: Series[str] = pa.Field(nullable=False)
    budget: Series[float] = pa.Field(gt=0)
    actual_cost: Series[float] = pa.Field(ge=0)
    planned_progress: Series[float] = pa.Field(ge=0, le=1)
    actual_progress: Series[float] = pa.Field(ge=0, le=1)

    class Config:
        strict = True
        coerce = False
        unique = ("project_id", "work_package_id")


class ChangeOrderSchema(pa.DataFrameModel):
    change_order_id: Series[str] = pa.Field(nullable=False, unique=True)
    project_id: Series[str] = pa.Field(nullable=False)
    date: Series[pd.Timestamp] = pa.Field(nullable=False)
    category: Series[str] = pa.Field(isin=values(ChangeOrderCategory))
    # May be negative (scope-reduction change orders); never coerced.
    approved_amount: Series[float] = pa.Field(nullable=False)
    status: Series[str] = pa.Field(isin=values(ChangeOrderStatus))

    class Config:
        strict = True
        coerce = False


class SupplierSchema(pa.DataFrameModel):
    supplier_id: Series[str] = pa.Field(nullable=False)
    supplier_category: Series[str] = pa.Field(isin=values(SupplierCategory))
    project_id: Series[str] = pa.Field(nullable=False)
    contract_value: Series[float] = pa.Field(ge=0)
    # Negative values mean early delivery; kept unbounded above.
    delivery_delay_days: Series[int] = pa.Field(nullable=False)
    quality_score: Series[float] = pa.Field(ge=0, le=10)
    rework_cost: Series[float] = pa.Field(ge=0)

    class Config:
        strict = True
        coerce = False
        unique = ("supplier_id", "project_id")


class EconomicIndexSchema(pa.DataFrameModel):
    reference_month: Series[pd.Timestamp] = pa.Field(nullable=False)
    index_name: Series[str] = pa.Field(nullable=False)
    index_value: Series[float] = pa.Field(gt=0)

    class Config:
        strict = True
        coerce = False
        unique = ("reference_month", "index_name")


def _validate(schema: type[pa.DataFrameModel], df: pd.DataFrame, name: str) -> pd.DataFrame:
    try:
        return schema.validate(df, lazy=True)
    except pa.errors.SchemaErrors as exc:
        raise DataContractError(name, exc.failure_cases) from exc


def validate_projects(df: pd.DataFrame) -> pd.DataFrame:
    return _validate(ProjectSchema, df, "ProjectSchema")


def validate_project_snapshots(df: pd.DataFrame) -> pd.DataFrame:
    return _validate(ProjectSnapshotSchema, df, "ProjectSnapshotSchema")


def validate_work_packages(df: pd.DataFrame) -> pd.DataFrame:
    return _validate(WorkPackageSchema, df, "WorkPackageSchema")


def validate_change_orders(df: pd.DataFrame) -> pd.DataFrame:
    return _validate(ChangeOrderSchema, df, "ChangeOrderSchema")


def validate_suppliers(df: pd.DataFrame) -> pd.DataFrame:
    return _validate(SupplierSchema, df, "SupplierSchema")


def validate_economic_index(df: pd.DataFrame) -> pd.DataFrame:
    return _validate(EconomicIndexSchema, df, "EconomicIndexSchema")


def check_snapshots_within_project_lifecycle(
    projects: pd.DataFrame, snapshots: pd.DataFrame
) -> None:
    """Cross-table chronological consistency check (Section 8.5).

    Every snapshot's ``snapshot_date`` must fall on or after its project's
    ``planned_start_date``. Snapshots may extend past ``planned_completion_date``
    (that lag is itself a delay signal, not a contract violation). Raises
    ``DataContractError`` with the offending rows if the check fails.
    """
    merged = snapshots.merge(
        projects[["project_id", "planned_start_date"]], on="project_id", how="left"
    )
    if merged["planned_start_date"].isna().any():
        orphaned = merged.loc[merged["planned_start_date"].isna(), "project_id"].unique()
        raise DataContractError(
            "ProjectSnapshotSchema",
            pd.DataFrame(
                {
                    "column": "project_id",
                    "check": "snapshot_references_known_project",
                    "failure_case": orphaned,
                }
            ),
        )
    violations = merged.loc[merged["snapshot_date"] < merged["planned_start_date"]]
    if not violations.empty:
        raise DataContractError(
            "ProjectSnapshotSchema",
            pd.DataFrame(
                {
                    "column": "snapshot_date",
                    "check": "snapshot_date_on_or_after_project_start",
                    "failure_case": violations["snapshot_date"].astype(str).to_numpy(),
                }
            ),
        )
