"""About / Governance page (Section 22/30/53)."""

from __future__ import annotations

import streamlit as st

import theme
from data_access import get_state, load_json_report


def render() -> None:
    st.title("About / Governance")

    st.markdown(
        f'<div class="bg-disclaimer">{theme.DECISION_SUPPORT_DISCLAIMER}</div>',
        unsafe_allow_html=True,
    )

    st.subheader("What BuildGuard AI is")
    st.markdown(
        "BuildGuard AI is a decision-support tool for construction portfolio risk: "
        "cost-overrun probability, schedule-delay probability, and a final-cost estimate "
        "with an explicit uncertainty interval, built on Earned Value Management analytics. "
        "It is trained and evaluated entirely on a deterministic **synthetic** portfolio "
        "(Section 8.2/ADR-0004) -- no real client or project data is used."
    )

    st.subheader("What it is not")
    st.markdown(
        "- Not an autonomous decision-maker. Every prediction is a probability or a point "
        "forecast with an interval, for a human reviewer to weigh alongside context the model "
        "does not have.\n"
        "- Not causal. Feature attribution (SHAP, permutation importance) explains what drove "
        "a *prediction*, never what would change the *outcome* if intervened on -- see the "
        "Scenario Simulator page's own explicit what-if disclaimer.\n"
        "- Not validated on real-world data. Every metric on the Model Performance page is "
        "measured on the synthetic portfolio's held-out test split, not a real deployment."
    )

    st.subheader("Model versions in this deployment")
    state = get_state()
    st.dataframe(
        [
            {
                "task": "cost_overrun",
                "family": "RandomForest",
                "calibration": state.cost_overrun.calibration_method,
                "threshold": state.cost_overrun.threshold,
            },
            {
                "task": "schedule_delay",
                "family": "LightGBM",
                "calibration": state.schedule_delay.calibration_method,
                "threshold": state.schedule_delay.threshold,
            },
            {
                "task": "final_cost",
                "family": "Deterministic EAC (BAC / CPI)",
                "calibration": "n/a (formula baseline, ADR-0006)",
                "threshold": None,
            },
        ],
        hide_index=True,
        use_container_width=True,
    )
    st.caption(f"App version `{state.model_version}` · data/code version `{state.data_version}`.")

    st.subheader("Human oversight")
    st.markdown(
        "- Every risk prediction ships with its calibration method and decision threshold "
        "(Section 16/17), never a bare score.\n"
        "- Retraining is never automatic (Section 24): the monitoring pipeline "
        "(`scripts/monitor.py`) only flags triggers -- Detect -> **Investigate** -> Validate "
        "data -> Retrain candidate -> Compare vs. champion -> Approve -> Release is always a "
        "human-run workflow. See the Model Health page for what is currently flagged.\n"
        "- Known limitations (weak subgroups, out-of-sample calibration gaps) are documented, "
        "not hidden -- see ADR-0010 and ADR-0011, and the Model Performance page's per-task "
        "failure analysis."
    )

    st.subheader("Zero-cost architecture (Section 31)")
    st.markdown(
        "GitHub (public repo) -> GitHub Actions (lint/test/type-check) -> Streamlit Community "
        "Cloud, serving this UI, the packaged models, and an in-process prediction service "
        "against the synthetic demo dataset. No paid database, model endpoint, LLM, or "
        "monitoring SaaS."
    )

    calibration_summary = load_json_report("experiments/calibration_summary.json")
    if calibration_summary:
        st.caption(f"Last calibration run: git SHA `{calibration_summary['git_sha']}`.")

    st.subheader("Project links")
    st.markdown(
        f"- [Project scope & specification](https://github.com/pinheiro-dataworks/buildguard-ai/blob/main/BUILDGUARD_AI_PROJECT_SCOPE.md)\n"
        f"- [Architecture Decision Records](https://github.com/pinheiro-dataworks/buildguard-ai/tree/main/docs/adr)\n"
        f"- [Full source on GitHub]({theme.GITHUB_URL})"
    )
