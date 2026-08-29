"""Model Performance page (Section 18/30) -- the real held-out test-set evaluation."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

import theme
from data_access import load_json_report, load_text_report


def _classification_section(task_name: str, label: str, task: dict[str, Any]) -> None:
    st.subheader(label)
    metrics = task["test_metrics"]
    cols = st.columns(5)
    values = [
        ("ROC-AUC", f"{metrics['roc_auc']:.4f}"),
        ("PR-AUC", f"{metrics['pr_auc']:.4f}"),
        ("Precision", f"{metrics['precision']:.1%}"),
        ("Recall", f"{metrics['recall']:.1%}"),
        ("Brier score", f"{metrics['brier_score']:.4f}"),
    ]
    for col, (lbl, val) in zip(cols, values, strict=True):
        with col:
            st.markdown(theme.kpi_card(lbl, val), unsafe_allow_html=True)
    st.caption(
        f"Threshold {task['threshold']:.3f} ({task['calibration_method']} calibration), "
        f"n={metrics['n_rows']} test rows, {metrics['positive_rate']:.1%} positive rate."
    )

    st.markdown("**Confusion matrix at the operating threshold**")
    confusion = metrics["confusion"]
    st.dataframe(
        pd.DataFrame(
            [
                ["Actual positive", confusion["true_positives"], confusion["false_negatives"]],
                ["Actual negative", confusion["false_positives"], confusion["true_negatives"]],
            ],
            columns=["", "Predicted positive", "Predicted negative"],
        ),
        hide_index=True,
        use_container_width=True,
    )

    st.markdown("**Slice evaluation (ROC-AUC by subgroup)**")
    slice_dim = st.selectbox("Dimension", list(task["slices"].keys()), key=f"{task_name}_slice_dim")
    slice_df = pd.DataFrame(task["slices"][slice_dim]).sort_values("auc", ascending=True)
    st.dataframe(slice_df, hide_index=True, use_container_width=True)

    with st.expander(
        "Full failure analysis (false negatives/positives, SHAP drivers, hardest subgroups)"
    ):
        text = load_text_report(f"error_analysis/{task_name}_failure_analysis.md")
        st.markdown(text or "Not available.")


def _regression_section(task: dict[str, Any]) -> None:
    st.subheader("Final-Cost Estimate")
    metrics = task["test_metrics"]
    cols = st.columns(4)
    values = [
        ("MAE", f"${metrics['mae'] / 1e6:.2f}M"),
        ("RMSE", f"${metrics['rmse'] / 1e6:.2f}M"),
        ("R²", f"{metrics['r2']:.3f}"),
        ("MAPE", f"{metrics['mape']:.1%}"),
    ]
    for col, (lbl, val) in zip(cols, values, strict=True):
        with col:
            st.markdown(theme.kpi_card(lbl, val), unsafe_allow_html=True)

    conformal = task["conformal"]
    st.markdown(
        theme.kpi_card(
            "80% interval empirical coverage",
            f"{conformal['test_empirical_coverage']:.1%}",
            f"target {conformal['target_coverage']:.0%}, quantile ${conformal['quantile'] / 1e6:.2f}M",
        ),
        unsafe_allow_html=True,
    )

    with st.expander("Full failure analysis (largest errors, systematic bias by subgroup)"):
        text = load_text_report("error_analysis/final_cost_failure_analysis.md")
        st.markdown(text or "Not available.")


def render() -> None:
    st.title("Model Performance")
    st.caption(
        "Final, one-shot evaluation on the held-out **test split** -- never touched until "
        "this evaluation (Section 12 / ADR-0003)."
    )

    metrics = load_json_report("experiments/test_set_metrics.json")
    if metrics is None:
        st.warning("No test-set metrics found. Run `make evaluate` to generate one.")
        return

    tasks = metrics["tasks"]
    _classification_section("cost_overrun", "Cost-Overrun Risk", tasks["cost_overrun"])
    st.divider()
    _classification_section("schedule_delay", "Schedule-Delay Risk", tasks["schedule_delay"])
    st.divider()
    _regression_section(tasks["final_cost"])
