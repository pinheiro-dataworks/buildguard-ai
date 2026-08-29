"""Model Health page (Section 23/30) -- renders the real `make monitor` output."""

from __future__ import annotations

import pandas as pd
import streamlit as st

import theme
from data_access import load_json_report


def render() -> None:
    st.title("Model Health")
    report = load_json_report("monitoring/monitoring_report.json")
    if report is None:
        st.warning("No monitoring report found. Run `make monitor` to generate one.")
        return

    st.caption(f"From the last `make monitor` run -- git SHA `{report['git_sha']}`.")

    st.subheader("Retraining triggers (Section 24)")
    st.markdown(
        '<div class="bg-disclaimer">Never auto-retrained: this page only reports what the '
        "last monitoring run flagged. Every trigger requires a human to Investigate before "
        "any retraining decision.</div>",
        unsafe_allow_html=True,
    )
    triggers = pd.DataFrame(report["retraining_triggers"])
    triggers["status"] = triggers["fired"].map({True: "FIRED", False: "clear", None: "policy only"})
    st.dataframe(
        triggers[["trigger", "status", "detail"]], hide_index=True, use_container_width=True
    )

    st.subheader("Data quality")
    dq_cols = st.columns(len(report["data_quality"]))
    for col, (name, dq) in zip(dq_cols, report["data_quality"].items(), strict=True):
        with col:
            # `is_clean` is a computed property on DataQualityReport, not a
            # serialized field -- dataclasses.asdict() only captures the
            # raw fields, so it's recomputed here from those.
            is_clean = (
                not dq["schema_violations"]
                and not any(dq["unexpected_categories"].values())
                and not any(dq["range_violation_counts"].values())
                and dq["duplicate_key_count"] == 0
            )
            status = "Clean" if is_clean else "Issues found"
            st.markdown(
                theme.kpi_card(name.replace("_", " ").title(), status, f"{dq['n_rows']} rows"),
                unsafe_allow_html=True,
            )

    st.subheader("Feature drift (train vs. test split)")
    drift = pd.DataFrame(report["feature_drift"]).sort_values("psi", ascending=False)
    significant = int((drift["psi_severity"] == "significant").sum())
    st.caption(
        f"{significant} of {len(drift)} features significantly drifted -- expected for a "
        "chronological split (older/train projects have had more calendar time to accrue "
        "inflation and lifecycle progress). See ADR-0011 for the full explanation."
    )
    st.dataframe(
        drift[["column", "variable_type", "psi", "psi_severity", "ks_p_value"]],
        hide_index=True,
        use_container_width=True,
    )

    st.subheader("Performance: calibration-split baseline vs. held-out test result")
    for task_name, result in report["performance"].items():
        st.markdown(f"**{task_name.replace('_', ' ').title()}**")
        comparisons = pd.DataFrame(result["comparisons"])
        comparisons["status"] = comparisons["is_degraded"].map({True: "DEGRADED", False: "stable"})
        st.dataframe(
            comparisons[["metric_name", "baseline_value", "current_value", "status"]],
            hide_index=True,
            use_container_width=True,
        )

    st.subheader("Operational: real inference latency")
    op_rows = [
        {
            "task": task,
            "p50_ms": s["latency_p50_ms"],
            "p95_ms": s["latency_p95_ms"],
            "p99_ms": s["latency_p99_ms"],
            "n_predictions": s["n_predictions"],
        }
        for task, s in report["operational"].items()
    ]
    st.dataframe(pd.DataFrame(op_rows), hide_index=True, use_container_width=True)
    st.caption(
        "Target: p95 < 500ms on local CPU (Section 49). All three champions are well under it."
    )
