"""Unit tests for the business impact scenario formula (Section 21)."""

from __future__ import annotations

import pandas as pd
import pytest

from buildguard.evaluation.business_impact import compute_business_impact

pytestmark = pytest.mark.unit


def test_matches_hand_calculated_scenario_value() -> None:
    projects = pd.DataFrame(
        {
            "project_id": ["P1", "P2", "P3", "P4"],
            "approved_budget": [1_000_000.0, 2_000_000.0, 3_000_000.0, 4_000_000.0],
        }
    )
    # P1/P2 unresolved (active, avg exposure (1M + 2M) / 2 = 1.5M);
    # P3/P4 resolved, one overrun -> 50% prevalence.
    outcomes = pd.DataFrame(
        {
            "project_id": ["P1", "P2", "P3", "P4"],
            "is_resolved": [False, False, True, True],
            "cost_overrun": [pd.NA, pd.NA, True, False],
        }
    )

    result = compute_business_impact(
        projects=projects,
        outcomes=outcomes,
        model_recall=0.8,
        avoidable_impact_assumption=0.3,
    )

    assert result.active_projects == 2
    assert result.avg_financial_exposure == pytest.approx(1_500_000.0)
    assert result.overrun_prevalence == pytest.approx(0.5)
    # 2 * 1.5M * 0.5 * 0.8 * 0.3 = 360,000
    assert result.estimated_decision_support_value == pytest.approx(360_000.0)
    assert result.label == "Scenario-based estimated impact"


def test_no_active_projects_gives_zero_value_not_a_crash() -> None:
    projects = pd.DataFrame({"project_id": ["P1"], "approved_budget": [1_000_000.0]})
    outcomes = pd.DataFrame({"project_id": ["P1"], "is_resolved": [True], "cost_overrun": [False]})

    result = compute_business_impact(
        projects=projects,
        outcomes=outcomes,
        model_recall=0.9,
        avoidable_impact_assumption=0.3,
    )

    assert result.active_projects == 0
    assert result.estimated_decision_support_value == pytest.approx(0.0)
