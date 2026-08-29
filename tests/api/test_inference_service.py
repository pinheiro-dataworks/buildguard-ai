"""API contract tests for the FastAPI inference service (Section 28/29).

Runs against the real trained/calibrated champions committed under
`models/` -- the same artifacts `scripts/evaluate.py`/`scripts/monitor.py`
use -- rather than mocks, consistent with the rest of this project's test
suite (`test_shap.py`, `test_slices.py`, ...) preferring real computations
over mocked ones. Requires `make train && make calibrate` to have been run
at least once (true for this repo's committed state).
"""

from __future__ import annotations

import copy
import datetime as dt

import pytest
from fastapi.testclient import TestClient

from buildguard.api.app import app

pytestmark = pytest.mark.api

client = TestClient(app)


def _snapshot(month_offset: int, progress: float, cpi_efficiency: float = 1.0) -> dict:
    date = dt.date(2023, 1, 1) + dt.timedelta(days=30 * month_offset)
    planned_cost = 1_000_000.0 * progress
    earned_value = planned_cost
    actual_cost = earned_value / cpi_efficiency
    return {
        "snapshot_date": date.isoformat(),
        "planned_progress": progress,
        "actual_progress": progress,
        "planned_cost": planned_cost,
        "actual_cost": actual_cost,
        "committed_cost": actual_cost,
        "earned_value": earned_value,
        "forecast_cost": 10_000_000.0 / cpi_efficiency,
    }


def _healthy_request() -> dict:
    return {
        "project": {
            "project_id": "PRJ-TEST-001",
            "project_type": "residential",
            "city": "Sao Paulo",
            "state": "SP",
            "gross_floor_area_m2": 5000.0,
            "number_of_towers": 1,
            "number_of_units": 80,
            "construction_standard": "standard",
            "planned_start_date": "2023-01-01",
            "planned_completion_date": "2025-01-01",
            "approved_budget": 10_000_000.0,
        },
        "snapshots": [_snapshot(i, progress=(i + 1) / 12, cpi_efficiency=1.0) for i in range(6)],
        "change_orders": [],
    }


def _troubled_request() -> dict:
    request = _healthy_request()
    request["project"]["project_id"] = "PRJ-TEST-002"
    request["snapshots"] = [
        _snapshot(i, progress=(i + 1) / 12, cpi_efficiency=0.6) for i in range(6)
    ]
    return request


class TestHealthAndVersion:
    def test_health_returns_ok(self) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_version_reports_real_model_metadata(self) -> None:
        response = client.get("/version")
        assert response.status_code == 200
        body = response.json()
        assert body["app_version"]
        assert body["data_version"]
        assert body["cost_overrun_calibration"] in ("none", "sigmoid", "isotonic")
        assert body["schedule_delay_calibration"] in ("none", "sigmoid", "isotonic")


class TestPredictCostRisk:
    def test_returns_the_documented_response_shape(self) -> None:
        response = client.post("/predict/cost-risk", json=_healthy_request())
        assert response.status_code == 200
        body = response.json()
        assert set(body) == {
            "project_id",
            "snapshot_date",
            "cost_overrun_probability",
            "risk_band",
            "threshold",
            "calibration_method",
            "model_version",
            "data_version",
        }
        assert 0.0 <= body["cost_overrun_probability"] <= 1.0
        assert body["risk_band"] in ("low", "medium", "high")
        assert body["project_id"] == "PRJ-TEST-001"

    def test_a_project_with_poor_cost_efficiency_scores_higher_risk_than_a_healthy_one(
        self,
    ) -> None:
        healthy = client.post("/predict/cost-risk", json=_healthy_request()).json()
        troubled = client.post("/predict/cost-risk", json=_troubled_request()).json()
        assert troubled["cost_overrun_probability"] > healthy["cost_overrun_probability"]

    def test_empty_snapshots_fails_safely_with_422(self) -> None:
        request = _healthy_request()
        request["snapshots"] = []
        response = client.post("/predict/cost-risk", json=request)
        assert response.status_code == 422

    def test_unseen_category_fails_safely_with_422(self) -> None:
        request = copy.deepcopy(_healthy_request())
        request["project"]["project_type"] = "spaceport"
        response = client.post("/predict/cost-risk", json=request)
        assert response.status_code == 422

    def test_missing_required_field_fails_safely_with_422(self) -> None:
        request = copy.deepcopy(_healthy_request())
        del request["project"]["approved_budget"]
        response = client.post("/predict/cost-risk", json=request)
        assert response.status_code == 422

    def test_negative_budget_fails_safely_with_422(self) -> None:
        request = copy.deepcopy(_healthy_request())
        request["project"]["approved_budget"] = -1.0
        response = client.post("/predict/cost-risk", json=request)
        assert response.status_code == 422

    def test_completion_before_start_fails_safely_with_422(self) -> None:
        # Individually valid dates, but violating the contract's
        # dataframe-level completion_after_start check -- Pydantic alone
        # can't catch this (Section 48: schema/contract violations must
        # fail safely, not crash).
        request = copy.deepcopy(_healthy_request())
        request["project"]["planned_completion_date"] = "2022-01-01"
        response = client.post("/predict/cost-risk", json=request)
        assert response.status_code == 422

    def test_accepts_a_project_with_change_orders(self) -> None:
        request = copy.deepcopy(_healthy_request())
        request["change_orders"] = [
            {
                "change_order_id": "CO-TEST-001",
                "date": "2023-03-01",
                "category": "scope_change",
                "approved_amount": 50_000.0,
                "status": "approved",
            }
        ]
        response = client.post("/predict/cost-risk", json=request)
        assert response.status_code == 200


class TestPredictScheduleRisk:
    def test_returns_the_documented_response_shape(self) -> None:
        response = client.post("/predict/schedule-risk", json=_healthy_request())
        assert response.status_code == 200
        body = response.json()
        assert "schedule_delay_probability" in body
        assert 0.0 <= body["schedule_delay_probability"] <= 1.0
        assert body["risk_band"] in ("low", "medium", "high")


class TestPredictFinalCost:
    def test_returns_the_documented_response_shape_with_a_valid_interval(self) -> None:
        response = client.post("/predict/final-cost", json=_healthy_request())
        assert response.status_code == 200
        body = response.json()
        assert body["lower_bound"] <= body["expected_final_cost"] <= body["upper_bound"]
        assert body["coverage"] == pytest.approx(0.80)

    def test_a_single_snapshot_is_enough_to_predict(self) -> None:
        request = _healthy_request()
        request["snapshots"] = request["snapshots"][:1]
        response = client.post("/predict/final-cost", json=request)
        assert response.status_code == 200


class TestOpenApiDocs:
    def test_openapi_schema_is_served(self) -> None:
        response = client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        assert "/predict/cost-risk" in schema["paths"]
        assert "/predict/schedule-risk" in schema["paths"]
        assert "/predict/final-cost" in schema["paths"]

    def test_interactive_docs_are_served(self) -> None:
        response = client.get("/docs")
        assert response.status_code == 200
