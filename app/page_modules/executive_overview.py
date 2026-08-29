"""Executive Overview page (Section 30)."""

from __future__ import annotations

import plotly.express as px
import streamlit as st

import theme
from data_access import portfolio_latest_scores


def render() -> None:
    st.title("Executive Overview")
    st.markdown(
        f'<div class="bg-disclaimer">{theme.DECISION_SUPPORT_DISCLAIMER}</div>',
        unsafe_allow_html=True,
    )

    scores = portfolio_latest_scores()

    total_projects = len(scores)
    total_exposure = scores["approved_budget"].sum()
    high_cost_risk = int((scores["cost_overrun_band"] == "high").sum())
    high_schedule_risk = int((scores["schedule_delay_band"] == "high").sum())
    avg_cost_risk = scores["cost_overrun_probability"].mean()

    cols = st.columns(4)
    for col, html in zip(
        cols,
        [
            theme.kpi_card("Projects tracked", f"{total_projects}", "Latest snapshot per project"),
            theme.kpi_card(
                "Portfolio exposure", f"${total_exposure / 1e6:,.1f}M", "Sum of approved budgets"
            ),
            theme.kpi_card(
                "High cost-overrun risk", f"{high_cost_risk}", "Projects in the 'high' band"
            ),
            theme.kpi_card(
                "High schedule-delay risk", f"{high_schedule_risk}", "Projects in the 'high' band"
            ),
        ],
        strict=True,
    ):
        with col:
            st.markdown(html, unsafe_allow_html=True)

    st.markdown(
        theme.kpi_card(
            "Average cost-overrun probability",
            f"{avg_cost_risk:.1%}",
            "Across every tracked project's latest snapshot",
        ),
        unsafe_allow_html=True,
    )

    st.subheader("Risk-band distribution")
    band_col1, band_col2 = st.columns(2)
    band_order = ["low", "medium", "high"]
    with band_col1:
        counts = scores["cost_overrun_band"].value_counts().reindex(band_order, fill_value=0)
        fig = px.bar(
            x=counts.index,
            y=counts.values,
            labels={"x": "Risk band", "y": "Projects"},
            title="Cost-overrun risk",
            color=counts.index,
            color_discrete_map={b: theme.RISK_COLORS[b][0] for b in band_order},
        )
        fig.update_layout(showlegend=False, plot_bgcolor=theme.SURFACE, paper_bgcolor=theme.SURFACE)
        st.plotly_chart(fig, use_container_width=True)
    with band_col2:
        counts = scores["schedule_delay_band"].value_counts().reindex(band_order, fill_value=0)
        fig = px.bar(
            x=counts.index,
            y=counts.values,
            labels={"x": "Risk band", "y": "Projects"},
            title="Schedule-delay risk",
            color=counts.index,
            color_discrete_map={b: theme.RISK_COLORS[b][0] for b in band_order},
        )
        fig.update_layout(showlegend=False, plot_bgcolor=theme.SURFACE, paper_bgcolor=theme.SURFACE)
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Highest cost-overrun-risk projects")
    top = scores.sort_values("cost_overrun_probability", ascending=False).head(10).copy()
    top["cost_overrun_probability"] = top["cost_overrun_probability"] * 100
    top["schedule_delay_probability"] = top["schedule_delay_probability"] * 100
    st.dataframe(
        top[
            [
                "project_id",
                "project_type",
                "state",
                "lifecycle_stage",
                "cost_overrun_probability",
                "cost_overrun_band",
                "schedule_delay_probability",
                "expected_final_cost",
            ]
        ],
        column_config={
            "cost_overrun_probability": st.column_config.NumberColumn(
                "Cost-overrun risk", format="%.1f%%"
            ),
            "schedule_delay_probability": st.column_config.NumberColumn(
                "Schedule-delay risk", format="%.1f%%"
            ),
            "expected_final_cost": st.column_config.NumberColumn(
                "Expected final cost", format="$%.0f"
            ),
            "cost_overrun_band": "Band",
        },
        hide_index=True,
        use_container_width=True,
    )
