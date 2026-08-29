"""Shared data loading and in-process prediction calls for the Streamlit app.

Reuses the same report JSON files (`reports/experiments/`,
`reports/monitoring/`, `reports/error_analysis/`) every other phase of
this project already produces and commits -- the dashboard never
recomputes a metric a script already computed. Predictions are made
in-process by calling the FastAPI endpoint functions directly (Section 29:
"Streamlit app may call it in-process (zero cost)"), so there is exactly
one prediction code path shared by the API and the UI.
"""

from __future__ import annotations

import json
from typing import Any

import pandas as pd
import streamlit as st

from buildguard.api import app as api_app
from buildguard.api.dependencies import ServiceState, get_service_state
from buildguard.api.schemas import (
    ChangeOrderInput,
    PredictionRequest,
    ProjectInput,
    SnapshotInput,
)
from buildguard.config import PROJECT_ROOT, load_base_config
from buildguard.data.economic_index import DemoIndexProvider
from buildguard.data.synthetic import PortfolioDataset, generate_portfolio
from buildguard.features.pipeline import build_feature_table
from buildguard.models.thresholds import risk_band

REPORTS_DIR = PROJECT_ROOT / "reports"


@st.cache_data(show_spinner=False)
def load_json_report(relative_path: str) -> dict[str, Any] | None:
    path = REPORTS_DIR / relative_path
    if not path.exists():
        return None
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


@st.cache_data(show_spinner=False)
def load_text_report(relative_path: str) -> str | None:
    path = REPORTS_DIR / relative_path
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


@st.cache_resource(show_spinner="Loading champion models...")
def get_state() -> ServiceState:
    return get_service_state()


@st.cache_data(show_spinner="Generating the demo portfolio...")
def get_portfolio() -> PortfolioDataset:
    cfg = load_base_config()
    return generate_portfolio(cfg)


@st.cache_data(show_spinner="Building the portfolio feature table...")
def full_feature_table() -> pd.DataFrame:
    """Every snapshot's leakage-safe feature row, for every project -- the
    same table `scripts/train.py`/`evaluate.py`/`monitor.py` build. Used
    both for portfolio-wide batch scoring and as a SHAP background sample."""
    cfg = load_base_config()
    portfolio = get_portfolio()
    provider = DemoIndexProvider(
        reference_date=cfg.synthetic_data.reference_date,
        history_years=cfg.synthetic_data.history_years,
    )
    return build_feature_table(
        portfolio.projects, portfolio.snapshots, portfolio.change_orders, provider, cfg.features
    )


def project_ids() -> list[str]:
    return sorted(get_portfolio().projects["project_id"].tolist())


def project_row(project_id: str) -> pd.Series:
    portfolio = get_portfolio()
    return portfolio.projects.loc[portfolio.projects["project_id"] == project_id].iloc[0]


def project_snapshots(project_id: str) -> pd.DataFrame:
    portfolio = get_portfolio()
    return (
        portfolio.snapshots.loc[portfolio.snapshots["project_id"] == project_id]
        .sort_values("snapshot_date")
        .reset_index(drop=True)
    )


def project_change_orders(project_id: str) -> pd.DataFrame:
    portfolio = get_portfolio()
    return portfolio.change_orders.loc[
        portfolio.change_orders["project_id"] == project_id
    ].sort_values("date")


def _build_request(
    project_id: str,
    as_of_snapshot_index: int | None = None,
    override_snapshots: pd.DataFrame | None = None,
) -> PredictionRequest:
    """The project + its snapshot history up to `as_of_snapshot_index`
    (default: full history), formatted as the same request shape the API
    validates. `override_snapshots` lets the Scenario Simulator substitute
    a what-if version of the history without touching the cached portfolio.
    """
    proj = project_row(project_id)
    snaps = override_snapshots if override_snapshots is not None else project_snapshots(project_id)
    if as_of_snapshot_index is not None:
        snaps = snaps.iloc[: as_of_snapshot_index + 1]

    cos = project_change_orders(project_id)
    if not cos.empty:
        cutoff = pd.Timestamp(snaps["snapshot_date"].max())
        cos = cos.loc[cos["date"] <= cutoff]

    project_input = ProjectInput(
        project_id=str(proj["project_id"]),
        project_type=proj["project_type"],
        city=str(proj["city"]),
        state=str(proj["state"]),
        gross_floor_area_m2=float(proj["gross_floor_area_m2"]),
        number_of_towers=int(proj["number_of_towers"]),
        number_of_units=int(proj["number_of_units"]),
        construction_standard=proj["construction_standard"],
        planned_start_date=pd.Timestamp(proj["planned_start_date"]).date(),
        planned_completion_date=pd.Timestamp(proj["planned_completion_date"]).date(),
        approved_budget=float(proj["approved_budget"]),
    )
    snapshot_inputs = [
        SnapshotInput(
            snapshot_date=pd.Timestamp(row["snapshot_date"]).date(),
            planned_progress=float(row["planned_progress"]),
            actual_progress=float(row["actual_progress"]),
            planned_cost=float(row["planned_cost"]),
            actual_cost=float(row["actual_cost"]),
            committed_cost=float(row["committed_cost"]),
            earned_value=float(row["earned_value"]),
            forecast_cost=float(row["forecast_cost"]),
        )
        for _, row in snaps.iterrows()
    ]
    change_order_inputs = [
        ChangeOrderInput(
            change_order_id=str(row["change_order_id"]),
            date=pd.Timestamp(row["date"]).date(),
            category=row["category"],
            approved_amount=float(row["approved_amount"]),
            status=row["status"],
        )
        for _, row in cos.iterrows()
    ]
    return PredictionRequest(
        project=project_input, snapshots=snapshot_inputs, change_orders=change_order_inputs
    )


@st.cache_data(show_spinner="Scoring the current portfolio...")
def portfolio_latest_scores() -> pd.DataFrame:
    """One row per project, scored at its own most recent snapshot.

    Batch-scores the whole portfolio through the same
    `build_feature_table` training/evaluation already use, rather than 400
    individual single-project API calls -- a legitimate different access
    pattern (batch vs. single-prediction) sharing the same feature
    pipeline and champion artifacts (Section 28).
    """
    features = full_feature_table()
    # approved_budget is already carried through from build_feature_table's
    # own static-project-column merge -- no second merge needed here.
    latest = features.sort_values("snapshot_date").groupby("project_id", as_index=False).tail(1)

    state = get_state()
    cost_proba = state.cost_overrun.model.predict_proba(latest)[:, 1]
    schedule_proba = state.schedule_delay.model.predict_proba(latest)[:, 1]
    final_cost = state.final_cost_model.predict(latest)

    latest = latest.assign(
        cost_overrun_probability=cost_proba,
        cost_overrun_band=risk_band(cost_proba, state.cost_overrun.threshold),
        schedule_delay_probability=schedule_proba,
        schedule_delay_band=risk_band(schedule_proba, state.schedule_delay.threshold),
        expected_final_cost=final_cost,
    )
    return latest[
        [
            "project_id",
            "project_type",
            "state",
            "snapshot_date",
            "lifecycle_stage",
            "approved_budget",
            "cost_overrun_probability",
            "cost_overrun_band",
            "schedule_delay_probability",
            "schedule_delay_band",
            "expected_final_cost",
        ]
    ].reset_index(drop=True)


def predict_all(
    project_id: str,
    as_of_snapshot_index: int | None = None,
    override_snapshots: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Cost-risk, schedule-risk, and final-cost predictions for one project,
    calling the exact same FastAPI endpoint functions the live API serves
    -- in-process, no HTTP round trip (Section 29)."""
    state = get_state()
    request = _build_request(project_id, as_of_snapshot_index, override_snapshots)
    return {
        "cost_risk": api_app.predict_cost_risk(request, state),
        "schedule_risk": api_app.predict_schedule_risk(request, state),
        "final_cost": api_app.predict_final_cost(request, state),
    }


@st.cache_data(show_spinner="Computing SHAP drivers...")
def local_explanation(task_name: str, project_id: str) -> Any:
    """Per-prediction SHAP drivers (Section 20) for `project_id`'s latest
    snapshot, using a portfolio-wide sample as the SHAP background."""
    from buildguard.explainability.shap import explain_local

    state = get_state()
    model = state.cost_overrun.model if task_name == "cost_overrun" else state.schedule_delay.model
    features = full_feature_table()
    row = features.loc[features["project_id"] == project_id].sort_values("snapshot_date").iloc[[-1]]
    background = features.sample(min(200, len(features)), random_state=42)
    return explain_local(model, row, background=background)
