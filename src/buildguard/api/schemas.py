"""Pydantic request/response schemas for the inference API (Section 28/29).

Request schemas mirror the raw table shapes `buildguard.data.contracts`
already validates (Projects / Project Snapshots / Change Orders) rather
than a bespoke "prediction request" shape -- a caller sends a project's
real snapshot *history* (not just its latest state), because
`buildguard.features.pipeline.build_feature_table` -- the same function
training uses -- needs that history to compute trend/streak features
identically to how it was computed offline (Section 28's train/serve
consistency requirement). The endpoint scores the most recent snapshot.
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field

from buildguard.data.enums import (
    ChangeOrderCategory,
    ChangeOrderStatus,
    ConstructionStandard,
    ProjectType,
)


class ProjectInput(BaseModel):
    project_id: str
    project_type: ProjectType
    city: str
    state: str
    gross_floor_area_m2: float = Field(gt=0)
    number_of_towers: int = Field(ge=1)
    number_of_units: int = Field(ge=0)
    construction_standard: ConstructionStandard
    planned_start_date: dt.date
    planned_completion_date: dt.date
    approved_budget: float = Field(gt=0)


class SnapshotInput(BaseModel):
    snapshot_date: dt.date
    planned_progress: float = Field(ge=0, le=1)
    actual_progress: float = Field(ge=0, le=1)
    planned_cost: float = Field(ge=0)
    actual_cost: float = Field(ge=0)
    committed_cost: float = Field(ge=0)
    earned_value: float = Field(ge=0)
    forecast_cost: float = Field(ge=0)


class ChangeOrderInput(BaseModel):
    change_order_id: str
    date: dt.date
    category: ChangeOrderCategory
    approved_amount: float
    status: ChangeOrderStatus


class PredictionRequest(BaseModel):
    """A project plus its full snapshot history (chronological, oldest
    first) up to and including the snapshot to score. `change_orders` may
    be empty (a project with none yet is valid)."""

    project: ProjectInput
    snapshots: list[SnapshotInput] = Field(min_length=1)
    change_orders: list[ChangeOrderInput] = Field(default_factory=list)


class CostRiskResponse(BaseModel):
    project_id: str
    snapshot_date: dt.date
    cost_overrun_probability: float
    risk_band: str
    threshold: float
    calibration_method: str
    model_version: str
    data_version: str


class ScheduleRiskResponse(BaseModel):
    project_id: str
    snapshot_date: dt.date
    schedule_delay_probability: float
    risk_band: str
    threshold: float
    calibration_method: str
    model_version: str
    data_version: str


class FinalCostResponse(BaseModel):
    project_id: str
    snapshot_date: dt.date
    expected_final_cost: float
    lower_bound: float
    upper_bound: float
    coverage: float
    model_version: str
    data_version: str


class HealthResponse(BaseModel):
    status: str


class VersionResponse(BaseModel):
    app_version: str
    data_version: str
    cost_overrun_calibration: str
    schedule_delay_calibration: str
