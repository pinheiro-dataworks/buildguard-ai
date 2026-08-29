"""Project Diagnostic page (Section 30): timeline, CPI/SPI, predictions, uncertainty, SHAP drivers."""

from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
import streamlit as st

import theme
from data_access import full_feature_table, local_explanation, predict_all, project_ids, project_row


def render() -> None:
    st.title("Project Diagnostic")

    ids = project_ids()
    project_id = st.selectbox("Project", ids, key="diagnostic_project_id")
    proj = project_row(project_id)

    info_cols = st.columns(4)
    info = [
        ("Type", str(proj["project_type"]).replace("_", " ").title()),
        ("Location", f"{proj['city']}, {proj['state']}"),
        ("Approved budget", f"${proj['approved_budget'] / 1e6:.2f}M"),
        ("Standard", str(proj["construction_standard"]).replace("_", " ").title()),
    ]
    for col, (label, value) in zip(info_cols, info, strict=True):
        with col:
            st.markdown(theme.kpi_card(label, value), unsafe_allow_html=True)

    history = full_feature_table()
    history = history.loc[history["project_id"] == project_id].sort_values("snapshot_date")

    st.subheader("CPI / SPI trend")
    fig = go.Figure()
    fig.add_hline(y=1.0, line_dash="dot", line_color="#8A8676", annotation_text="On plan")
    fig.add_trace(
        go.Scatter(
            x=history["snapshot_date"],
            y=history["cpi"],
            name="CPI",
            line={"color": theme.ACCENT_WARM},
        )
    )
    fig.add_trace(
        go.Scatter(
            x=history["snapshot_date"],
            y=history["spi"],
            name="SPI",
            line={"color": theme.ACCENT_COOL},
        )
    )
    fig.update_layout(
        plot_bgcolor=theme.SURFACE,
        paper_bgcolor=theme.SURFACE,
        legend={"orientation": "h"},
        margin={"t": 10},
    )
    # CPI/SPI are ratios meant to hover near 1.0; a near-zero planned/actual
    # cost at a project's very first snapshot can produce an extreme early
    # spike that would otherwise dominate the axis and hide the real trend.
    fig.update_yaxes(range=[0, 2.5])
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Current predictions")
    with st.spinner("Scoring the latest snapshot..."):
        predictions = predict_all(project_id)
    cost_risk = predictions["cost_risk"]
    schedule_risk = predictions["schedule_risk"]
    final_cost = predictions["final_cost"]

    pred_cols = st.columns(3)
    with pred_cols[0]:
        st.markdown(
            theme.kpi_card("Cost-overrun risk", f"{cost_risk.cost_overrun_probability:.1%}")
            + theme.risk_badge_html(cost_risk.risk_band),
            unsafe_allow_html=True,
        )
    with pred_cols[1]:
        st.markdown(
            theme.kpi_card("Schedule-delay risk", f"{schedule_risk.schedule_delay_probability:.1%}")
            + theme.risk_badge_html(schedule_risk.risk_band),
            unsafe_allow_html=True,
        )
    with pred_cols[2]:
        st.markdown(
            theme.kpi_card(
                "Expected final cost",
                f"${final_cost.expected_final_cost / 1e6:.2f}M",
                f"{final_cost.coverage:.0%} interval: "
                f"${final_cost.lower_bound / 1e6:.2f}M - ${final_cost.upper_bound / 1e6:.2f}M",
            ),
            unsafe_allow_html=True,
        )

    st.subheader("What is driving the cost-overrun prediction")
    st.markdown(
        f'<div class="bg-disclaimer">{theme.CAUSALITY_DISCLAIMER}</div>', unsafe_allow_html=True
    )
    explanation = local_explanation("cost_overrun", project_id)
    order = np.argsort(np.abs(explanation.shap_values))[::-1][:8]
    # Display-only cleanup of the ColumnTransformer's "numeric__"/
    # "categorical__" prefixes -- explain_local()'s own feature_names stay
    # exactly as SHAP produced them; only the chart label is prettified.
    display_names = [explanation.feature_names[i].split("__", 1)[-1] for i in order]
    fig = go.Figure(
        go.Bar(
            x=[explanation.shap_values[i] for i in order],
            y=display_names,
            orientation="h",
            marker_color=[
                theme.ACCENT_WARM if explanation.shap_values[i] > 0 else theme.ACCENT_COOL
                for i in order
            ],
        )
    )
    fig.update_layout(
        plot_bgcolor=theme.SURFACE,
        paper_bgcolor=theme.SURFACE,
        yaxis={"autorange": "reversed"},
        xaxis_title="SHAP value (impact on cost-overrun probability)",
        margin={"t": 10},
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        f"Base rate {explanation.base_value:.1%} -> predicted {explanation.predicted_value:.1%} "
        "for this project's latest snapshot."
    )
