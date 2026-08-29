"""FastAPI inference service (Section 28/29).

Single-project, single-prediction endpoints. Every endpoint rebuilds the
requested project's feature row through the exact same
`buildguard.features.pipeline.build_feature_table` function training uses
(Section 28: train/serve consistency) -- there is no second, "online"
feature implementation to drift out of sync with the offline one.

**Decision support, not an autonomous decision-maker** (Section 22/53):
every response is a probability/estimate plus its calibration and
uncertainty context, never a bare "will overrun" verdict.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from fastapi import Depends, FastAPI, HTTPException

import buildguard
from buildguard.api.dependencies import ServiceState, get_service_state
from buildguard.api.schemas import (
    CostRiskResponse,
    FinalCostResponse,
    HealthResponse,
    PredictionRequest,
    ScheduleRiskResponse,
    VersionResponse,
)
from buildguard.data import contracts
from buildguard.data.contracts import DataContractError
from buildguard.features.pipeline import build_feature_table
from buildguard.models.thresholds import risk_band
from buildguard.models.uncertainty import ConformalInterval, predict_interval

logger = logging.getLogger(__name__)

app = FastAPI(
    title="BuildGuard AI Inference Service",
    version=buildguard.__version__,
    description=(
        "Decision-support risk predictions for construction cost overrun, "
        "schedule delay, and final cost -- not an autonomous decision-maker. "
        "Feature attribution (where exposed) explains the model prediction; "
        "it does not establish causality."
    ),
)

_CHANGE_ORDER_COLUMNS = [
    "change_order_id",
    "project_id",
    "date",
    "category",
    "approved_amount",
    "status",
]


def _positive_class_proba(model: object, features: pd.DataFrame) -> float:
    raw = model.predict_proba(features)  # type: ignore[attr-defined]
    return float(raw[:, 1][0] if raw.ndim == 2 else raw[0])


def _get_service_state() -> ServiceState:
    try:
        return get_service_state()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _build_feature_row(request: PredictionRequest, state: ServiceState) -> pd.DataFrame:
    project_id = request.project.project_id

    projects = pd.DataFrame([request.project.model_dump(mode="json")])
    for col in ("planned_start_date", "planned_completion_date"):
        projects[col] = pd.to_datetime(projects[col])

    snapshots = pd.DataFrame([s.model_dump(mode="json") for s in request.snapshots])
    snapshots.insert(0, "project_id", project_id)
    snapshots["snapshot_date"] = pd.to_datetime(snapshots["snapshot_date"])

    if request.change_orders:
        change_orders = pd.DataFrame([c.model_dump(mode="json") for c in request.change_orders])
        change_orders.insert(0, "project_id", project_id)
        change_orders["date"] = pd.to_datetime(change_orders["date"])
    else:
        change_orders = pd.DataFrame(columns=_CHANGE_ORDER_COLUMNS)

    try:
        contracts.validate_projects(projects)
        contracts.validate_project_snapshots(snapshots)
        if not change_orders.empty:
            contracts.validate_change_orders(change_orders)
    except DataContractError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    features = build_feature_table(
        projects, snapshots, change_orders, state.index_provider, state.cfg.features
    )
    return features.iloc[[-1]]


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/version", response_model=VersionResponse)
def version(state: ServiceState = Depends(_get_service_state)) -> VersionResponse:
    return VersionResponse(
        app_version=state.model_version,
        data_version=state.data_version,
        cost_overrun_calibration=state.cost_overrun.calibration_method,
        schedule_delay_calibration=state.schedule_delay.calibration_method,
    )


@app.post("/predict/cost-risk", response_model=CostRiskResponse)
def predict_cost_risk(
    request: PredictionRequest, state: ServiceState = Depends(_get_service_state)
) -> CostRiskResponse:
    row = _build_feature_row(request, state)
    proba = _positive_class_proba(state.cost_overrun.model, row)
    band = risk_band(np.array([proba]), state.cost_overrun.threshold)[0]
    return CostRiskResponse(
        project_id=request.project.project_id,
        snapshot_date=row["snapshot_date"].iloc[0].date(),
        cost_overrun_probability=proba,
        risk_band=band,
        threshold=state.cost_overrun.threshold,
        calibration_method=state.cost_overrun.calibration_method,
        model_version=state.model_version,
        data_version=state.data_version,
    )


@app.post("/predict/schedule-risk", response_model=ScheduleRiskResponse)
def predict_schedule_risk(
    request: PredictionRequest, state: ServiceState = Depends(_get_service_state)
) -> ScheduleRiskResponse:
    row = _build_feature_row(request, state)
    proba = _positive_class_proba(state.schedule_delay.model, row)
    band = risk_band(np.array([proba]), state.schedule_delay.threshold)[0]
    return ScheduleRiskResponse(
        project_id=request.project.project_id,
        snapshot_date=row["snapshot_date"].iloc[0].date(),
        schedule_delay_probability=proba,
        risk_band=band,
        threshold=state.schedule_delay.threshold,
        calibration_method=state.schedule_delay.calibration_method,
        model_version=state.model_version,
        data_version=state.data_version,
    )


@app.post("/predict/final-cost", response_model=FinalCostResponse)
def predict_final_cost(
    request: PredictionRequest, state: ServiceState = Depends(_get_service_state)
) -> FinalCostResponse:
    row = _build_feature_row(request, state)
    point_prediction = state.final_cost_model.predict(row)
    interval = ConformalInterval(coverage=state.target_coverage, quantile=state.conformal_quantile)
    lower, upper = predict_interval(point_prediction, interval)
    return FinalCostResponse(
        project_id=request.project.project_id,
        snapshot_date=row["snapshot_date"].iloc[0].date(),
        expected_final_cost=float(point_prediction[0]),
        lower_bound=float(lower[0]),
        upper_bound=float(upper[0]),
        coverage=state.target_coverage,
        model_version=state.model_version,
        data_version=state.data_version,
    )
