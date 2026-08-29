"""Scenario Simulator page (Section 30) -- what-if only, explicitly not causal."""

from __future__ import annotations

import streamlit as st

import theme
from data_access import predict_all, project_ids, project_snapshots


def render() -> None:
    st.title("Scenario Simulator")
    st.markdown(
        '<div class="bg-disclaimer"><strong>What-if, not causal.</strong> This page re-runs '
        "the champion models on a hypothetical snapshot you construct by adjusting the "
        "project's most recent numbers. It shows what the model would predict *if* the "
        "project's latest snapshot looked like this -- it is not a simulation of what would "
        "actually happen, and adjusting one number in isolation does not mean that number "
        f"causes the change in risk. {theme.CAUSALITY_DISCLAIMER}</div>",
        unsafe_allow_html=True,
    )

    project_id = st.selectbox("Project", project_ids(), key="simulator_project_id")
    snapshots = project_snapshots(project_id)
    baseline_row = snapshots.iloc[-1]

    st.subheader("Baseline (most recent snapshot)")
    base_cols = st.columns(4)
    baseline_info = [
        ("Snapshot date", str(baseline_row["snapshot_date"].date())),
        ("Actual cost", f"${baseline_row['actual_cost'] / 1e6:.2f}M"),
        ("Earned value", f"${baseline_row['earned_value'] / 1e6:.2f}M"),
        ("Actual progress", f"{baseline_row['actual_progress']:.0%}"),
    ]
    for col, (label, value) in zip(base_cols, baseline_info, strict=True):
        with col:
            st.markdown(theme.kpi_card(label, value), unsafe_allow_html=True)

    st.subheader("Adjust the latest snapshot")
    cost_multiplier = st.slider(
        "Actual cost multiplier (cost efficiency: >1.0 = spending more than earned value)",
        min_value=0.7,
        max_value=1.5,
        value=1.0,
        step=0.01,
    )
    progress_delta = st.slider(
        "Actual progress vs. plan (percentage points; negative = behind schedule)",
        min_value=-0.30,
        max_value=0.10,
        value=0.0,
        step=0.01,
        format="%.2f",
    )
    extra_change_order = st.number_input(
        "Add a hypothetical change order to cumulative cost ($)",
        min_value=0.0,
        max_value=5_000_000.0,
        value=0.0,
        step=50_000.0,
    )

    scenario_snapshots = snapshots.copy()
    last = scenario_snapshots.index[-1]
    scenario_snapshots.loc[last, "actual_cost"] = (
        baseline_row["actual_cost"] * cost_multiplier + extra_change_order
    )
    scenario_snapshots.loc[last, "committed_cost"] = scenario_snapshots.loc[last, "actual_cost"]
    scenario_snapshots.loc[last, "actual_progress"] = float(
        min(max(baseline_row["actual_progress"] + progress_delta, 0.0), 1.0)
    )

    with st.spinner("Scoring baseline and scenario..."):
        baseline_predictions = predict_all(project_id)
        scenario_predictions = predict_all(project_id, override_snapshots=scenario_snapshots)

    st.subheader("Baseline vs. scenario")
    result_cols = st.columns(3)
    rows = [
        (
            "Cost-overrun risk",
            baseline_predictions["cost_risk"].cost_overrun_probability,
            scenario_predictions["cost_risk"].cost_overrun_probability,
            scenario_predictions["cost_risk"].risk_band,
        ),
        (
            "Schedule-delay risk",
            baseline_predictions["schedule_risk"].schedule_delay_probability,
            scenario_predictions["schedule_risk"].schedule_delay_probability,
            scenario_predictions["schedule_risk"].risk_band,
        ),
    ]
    for col, (label, baseline_value, scenario_value, band) in zip(
        result_cols[:2], rows, strict=True
    ):
        delta = scenario_value - baseline_value
        with col:
            st.markdown(
                theme.kpi_card(
                    label, f"{scenario_value:.1%}", f"baseline {baseline_value:.1%} ({delta:+.1%})"
                )
                + theme.risk_badge_html(band),
                unsafe_allow_html=True,
            )
    with result_cols[2]:
        baseline_cost = baseline_predictions["final_cost"].expected_final_cost
        scenario_cost = scenario_predictions["final_cost"].expected_final_cost
        st.markdown(
            theme.kpi_card(
                "Expected final cost",
                f"${scenario_cost / 1e6:.2f}M",
                f"baseline ${baseline_cost / 1e6:.2f}M ({(scenario_cost - baseline_cost) / 1e6:+.2f}M)",
            ),
            unsafe_allow_html=True,
        )
