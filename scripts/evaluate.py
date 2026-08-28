#!/usr/bin/env python
"""Final held-out evaluation, explainability, and failure analysis (Section 18/20/47).

Usage::

    uv run python scripts/evaluate.py
    make evaluate

Loads the calibrated champions (``models/*_champion.joblib``, produced by
``scripts/train.py`` + ``scripts/calibrate.py``) and the decisions already
made on the calibration split (``reports/experiments/calibration_summary.json``:
threshold, calibration method, conformal quantile) and applies them,
unchanged, to the **test** split -- the one split reserved for exactly one
final evaluation (Section 12, ``docs/adr/0003-temporal-validation.md``).
Nothing here selects a threshold, a calibration method, or a champion; it
only measures what was already decided, on data none of those decisions
ever saw.

For ``cost_overrun`` / ``schedule_delay``: the full Section 18
classification battery, an out-of-sample calibration check, slice
evaluation across the mandatory dimensions (project type, size,
construction standard, lifecycle stage, geography, budget segment) plus an
inflation-regime dimension answering Section 47's "does inflation regime
change performance" question, global SHAP/permutation explanations, and a
Section 47 failure analysis written to ``reports/error_analysis/``.

For ``final_cost``: the Section 18 regression battery, the conformal
interval's true out-of-sample coverage, the same slice dimensions scored
by both MAE and mean signed error (bias direction), and a failure analysis
of the largest errors. ``final_cost``'s champion (``DeterministicEacBaseline``,
ADR-0006) is a formula, not a fitted model -- no SHAP/permutation
explanation applies to it.

Every task's test-set metrics are logged as one MLflow run
(tag ``stage=test_evaluation``) and written to
``reports/experiments/test_set_metrics.json``.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import numpy.typing as npt
import pandas as pd
from sklearn.metrics import mean_absolute_error, roc_auc_score

from _common import (
    assemble_task_dataset,
    feature_columns,
    filter_by_split,
    load_training_dataset,
    positive_class_proba,
)
from buildguard.config import PROJECT_ROOT, load_base_config
from buildguard.evaluation.calibration import evaluate_calibration_on_holdout
from buildguard.evaluation.classification import compute_classification_metrics
from buildguard.evaluation.regression import compute_regression_metrics
from buildguard.evaluation.slices import bucket_by_quantile, evaluate_by_slice
from buildguard.explainability.shap import (
    GlobalExplanation,
    LocalExplanation,
    explain_global,
    explain_local,
)
from buildguard.models.preprocessing import NUMERIC_FEATURE_COLUMNS
from buildguard.models.tracking import configure_tracking, get_git_sha, log_model_run
from buildguard.models.uncertainty import ConformalInterval, empirical_coverage, predict_interval
from buildguard.monitoring.data_quality import range_violation_mask, reference_ranges

logger = logging.getLogger(__name__)

MIN_SLICE_SIZE = 15
NEAR_THRESHOLD_BAND = 0.05
TOP_N_EXAMPLES = 5


def _slice_dimensions(df: pd.DataFrame) -> dict[str, pd.Series]:
    return {
        "project_type": df["project_type"],
        "construction_standard": df["construction_standard"],
        "lifecycle_stage": df["lifecycle_stage"],
        "geography_state": df["state"],
        "project_size": bucket_by_quantile(
            df["gross_floor_area_m2"], 3, ["small", "medium", "large"]
        ),
        "budget_segment": bucket_by_quantile(
            df["approved_budget"], 3, ["low_budget", "mid_budget", "high_budget"]
        ),
        "inflation_regime": bucket_by_quantile(
            df["inflation_multiplier"], 3, ["low_inflation", "mid_inflation", "high_inflation"]
        ),
    }


def _slice_report(
    df: pd.DataFrame,
    y_true: npt.NDArray[np.float64],
    y_score: npt.NDArray[np.float64],
    metric_fn: Any,
    metric_name: str,
) -> dict[str, list[dict[str, Any]]]:
    report: dict[str, list[dict[str, Any]]] = {}
    for dim_name, dim_series in _slice_dimensions(df).items():
        working = df.assign(_dim=dim_series)
        results = evaluate_by_slice(
            working, "_dim", y_true, y_score, metric_fn, min_slice_size=MIN_SLICE_SIZE
        )
        report[dim_name] = [
            {"slice_value": r.slice_value, "n_rows": r.n_rows, metric_name: r.metric_value}
            for r in results
        ]
    return report


def _top_shap_features(explanation: GlobalExplanation, n: int = 5) -> list[tuple[str, float]]:
    order = np.argsort(explanation.mean_abs_shap)[::-1][:n]
    return [(explanation.shap_feature_names[i], float(explanation.mean_abs_shap[i])) for i in order]


def _top_permutation_features(
    explanation: GlobalExplanation, n: int = 5
) -> list[tuple[str, float]]:
    order = np.argsort(explanation.permutation_importance_mean)[::-1][:n]
    return [
        (
            explanation.permutation_feature_names[i],
            float(explanation.permutation_importance_mean[i]),
        )
        for i in order
    ]


def _local_explanation_lines(explanation: LocalExplanation, n: int = 5) -> list[str]:
    order = np.argsort(np.abs(explanation.shap_values))[::-1][:n]
    return [
        f"  - `{explanation.feature_names[i]}`: SHAP={explanation.shap_values[i]:+.4f}"
        for i in order
    ]


def _row_label(row: pd.Series) -> str:
    return f"{row['project_id']} @ {pd.Timestamp(row['snapshot_date']).date()}"


def _classification_failure_report(
    *,
    task_name: str,
    threshold: float,
    test: pd.DataFrame,
    y_true: npt.NDArray[np.bool_],
    y_proba: npt.NDArray[np.float64],
    feature_cols: list[str],
    ood_mask: pd.Series,
    slices: dict[str, list[dict[str, Any]]],
    global_explanation: GlobalExplanation,
    worst_fn_explanation: LocalExplanation | None,
    worst_fn_row: pd.Series | None,
    worst_fp_explanation: LocalExplanation | None,
    worst_fp_row: pd.Series | None,
) -> str:
    working = test.assign(_y_true=y_true, _y_proba=y_proba, _ood=ood_mask.to_numpy())
    pred = working["_y_proba"] >= threshold

    fn = working.loc[working["_y_true"] & ~pred].sort_values("_y_proba")
    fp = working.loc[~working["_y_true"] & pred].sort_values("_y_proba", ascending=False)
    near_threshold = working.loc[(working["_y_proba"] - threshold).abs() <= NEAR_THRESHOLD_BAND]
    ood_rows = working.loc[working["_ood"]]

    def _worst_slices(dim: str, metric_key: str, n: int = 3) -> list[str]:
        rows = [r for r in slices[dim] if r[metric_key] is not None]
        rows.sort(key=lambda r: r[metric_key])
        return [
            f"  - {r['slice_value']} (n={r['n_rows']}): AUC={r[metric_key]:.3f}" for r in rows[:n]
        ]

    lines = [
        f"# Failure Analysis -- {task_name} (Section 47)",
        "",
        f"Held-out **test split** ({len(test)} rows across "
        f"{test['project_id'].nunique()} projects). Threshold={threshold:.3f} "
        "(Section 17, optimized on the calibration split, never on test).",
        "",
        "## Where the model fails",
        "",
        f"- False negatives (missed a real overrun/delay): {len(fn)} of "
        f"{int(working['_y_true'].sum())} actual positives ({len(fn) / max(int(working['_y_true'].sum()), 1):.1%}).",
        f"- False positives (false alarm): {len(fp)} of "
        f"{int((~working['_y_true']).sum())} actual negatives ({len(fp) / max(int((~working['_y_true']).sum()), 1):.1%}).",
        f"- Near-threshold predictions (within +-{NEAR_THRESHOLD_BAND:.2f} of the decision "
        f"boundary): {len(near_threshold)} rows -- these are the cases most sensitive to model "
        "noise and the ones a human reviewer gains the most from double-checking.",
        f"- Out-of-distribution rows (at least one numeric feature outside the train split's "
        f"observed range): {len(ood_rows)} of {len(working)} ({len(ood_rows) / len(working):.1%}). "
        "The model extrapolates for these; treat its probability as less trustworthy.",
        "",
        "## Worst false negatives (model most confident, and most wrong)",
        "",
    ]
    if fn.empty:
        lines.append("None on this test split.")
    else:
        for _, row in fn.head(TOP_N_EXAMPLES).iterrows():
            lines.append(
                f"- {_row_label(row)}: predicted {row['_y_proba']:.3f}, actual positive "
                f"(cpi={row.get('cpi', float('nan')):.3f}, lifecycle={row.get('lifecycle_stage', 'n/a')})"
            )
    if worst_fn_row is not None and worst_fn_explanation is not None:
        lines += [
            "",
            f"Top SHAP drivers for the single worst false negative ({_row_label(worst_fn_row)}):",
            *_local_explanation_lines(worst_fn_explanation),
        ]

    lines += ["", "## Worst false positives (model most confident, and most wrong)", ""]
    if fp.empty:
        lines.append("None on this test split.")
    else:
        for _, row in fp.head(TOP_N_EXAMPLES).iterrows():
            lines.append(
                f"- {_row_label(row)}: predicted {row['_y_proba']:.3f}, actual negative "
                f"(cpi={row.get('cpi', float('nan')):.3f}, lifecycle={row.get('lifecycle_stage', 'n/a')})"
            )
    if worst_fp_row is not None and worst_fp_explanation is not None:
        lines += [
            "",
            f"Top SHAP drivers for the single worst false positive ({_row_label(worst_fp_row)}):",
            *_local_explanation_lines(worst_fp_explanation),
        ]

    lines += [
        "",
        "## Hardest subgroups (lowest AUC per dimension)",
        "",
        "**Project type:**",
        *(_worst_slices("project_type", "auc") or ["  - (all slices below the minimum size)"]),
        "",
        "**Lifecycle stage:**",
        *(_worst_slices("lifecycle_stage", "auc") or ["  - (all slices below the minimum size)"]),
        "",
        "**Geography (state):**",
        *(_worst_slices("geography_state", "auc") or ["  - (all slices below the minimum size)"]),
        "",
        "**Inflation regime:**",
        *(_worst_slices("inflation_regime", "auc") or ["  - (all slices below the minimum size)"]),
        "",
        "## Global drivers",
        "",
        "Top 5 features by mean |SHAP value| (encoded feature space):",
        *[f"  - `{name}`: {value:.4f}" for name, value in _top_shap_features(global_explanation)],
        "",
        "Top 5 features by permutation importance (original feature space, ROC-AUC drop):",
        *[
            f"  - `{name}`: {value:.4f}"
            for name, value in _top_permutation_features(global_explanation)
        ],
        "",
        "## What a human reviewer should check",
        "",
        f"- Any prediction within +-{NEAR_THRESHOLD_BAND:.2f} of the {threshold:.3f} threshold --"
        " the model's decision there is close to a coin flip between the two sides of the boundary.",
        "- Any prediction flagged out-of-distribution above -- the model is extrapolating, not"
        " interpolating within data it was trained on.",
        '- Predictions for the subgroups listed under "Hardest subgroups" above, where the model\'s'
        " discriminative power is weakest even though the global metric looks strong.",
        f"- False negatives specifically: at this threshold the model trades a higher false-positive"
        f" rate for a lower false-negative rate (Section 17's cost matrix makes a missed overrun far"
        f" more expensive than a false alarm) -- but the {len(fn)} false negatives above are the"
        f" cases that slipped through anyway and deserve manual follow-up.",
    ]
    return "\n".join(lines)


def _regression_failure_report(
    *,
    test: pd.DataFrame,
    y_true: npt.NDArray[np.float64],
    y_pred: npt.NDArray[np.float64],
    lower: npt.NDArray[np.float64],
    upper: npt.NDArray[np.float64],
    ood_mask: pd.Series,
    slices: dict[str, list[dict[str, Any]]],
) -> str:
    working = test.assign(
        _y_true=y_true,
        _y_pred=y_pred,
        _abs_error=np.abs(y_true - y_pred),
        _signed_error=y_pred - y_true,
        _lower=lower,
        _upper=upper,
        _ood=ood_mask.to_numpy(),
    )
    worst = working.sort_values("_abs_error", ascending=False)
    ood_rows = working.loc[working["_ood"]]
    outside_interval = working.loc[
        (working["_y_true"] < working["_lower"]) | (working["_y_true"] > working["_upper"])
    ]

    def _worst_slices(dim: str, n: int = 3) -> list[str]:
        rows = [r for r in slices[dim] if r["mae"] is not None]
        rows.sort(key=lambda r: -r["mae"])
        return [
            f"  - {r['slice_value']} (n={r['n_rows']}): MAE=${r['mae']:,.0f}, bias={r['bias']:+,.0f}"
            for r in rows[:n]
        ]

    lines = [
        "# Failure Analysis -- final_cost (Section 47)",
        "",
        f"Held-out **test split** ({len(test)} rows across "
        f"{test['project_id'].nunique()} projects). Champion is "
        "`DeterministicEacBaseline` (`BAC / CPI`, ADR-0006), so there is no SHAP/permutation "
        "explanation to attach here -- the formula itself is the explanation.",
        "",
        "## Largest errors",
        "",
    ]
    for _, row in worst.head(TOP_N_EXAMPLES).iterrows():
        lines.append(
            f"- {_row_label(row)}: actual ${row['_y_true']:,.0f}, predicted ${row['_y_pred']:,.0f} "
            f"(error ${row['_signed_error']:+,.0f}, lifecycle={row.get('lifecycle_stage', 'n/a')}, "
            f"project_type={row.get('project_type', 'n/a')})"
        )

    lines += [
        "",
        "## Systematic bias by subgroup (positive bias = model overpredicts final cost)",
        "",
        "**Project size:**",
        *(_worst_slices("project_size") or ["  - (all slices below the minimum size)"]),
        "",
        "**Lifecycle stage:**",
        *(_worst_slices("lifecycle_stage") or ["  - (all slices below the minimum size)"]),
        "",
        "**Inflation regime:**",
        *(_worst_slices("inflation_regime") or ["  - (all slices below the minimum size)"]),
        "",
        "## Uncertainty interval",
        "",
        f"- {len(outside_interval)} of {len(working)} test rows ({len(outside_interval) / len(working):.1%}) "
        "fall outside their own conformal prediction interval.",
        f"- Out-of-distribution rows (at least one numeric feature outside the train split's "
        f"range): {len(ood_rows)} of {len(working)} ({len(ood_rows) / len(working):.1%}).",
        "",
        "## What a human reviewer should check",
        "",
        "- The largest-error projects listed above, especially any where the actual cost fell"
        " outside the reported prediction interval.",
        "- Subgroups with the largest MAE/bias above -- a consistent sign on `bias` means the"
        " model is systematically over- or under-predicting for that subgroup, not just noisy.",
        "- Out-of-distribution rows, where `BAC / CPI` is being applied to a CPI value the model's"
        " calibration split never observed.",
    ]
    return "\n".join(lines)


def _evaluate_classification_task(
    *,
    task_name: str,
    label_column: str,
    models_dir: Path,
    reports_dir: Path,
    error_dir: Path,
    train: pd.DataFrame,
    test: pd.DataFrame,
    calibration_summary: dict[str, Any],
    data_version: str,
) -> dict[str, Any]:
    feature_cols = feature_columns(test, label_column)
    x_test = test[feature_cols]
    y_test = test[label_column].astype(bool).to_numpy()

    champion = joblib.load(models_dir / f"{task_name}_champion.joblib")
    proba = positive_class_proba(champion, x_test)
    task_summary = calibration_summary["tasks"][task_name]
    threshold = float(task_summary["threshold"])
    method = task_summary["calibration_method"]

    metrics = compute_classification_metrics(y_test, proba, threshold)
    holdout_calibration = evaluate_calibration_on_holdout(y_test, proba, method=method)

    slices = _slice_report(test, y_test, proba, roc_auc_score, "auc")

    ranges = reference_ranges(train, list(NUMERIC_FEATURE_COLUMNS))
    ood_mask = range_violation_mask(test, ranges)

    global_explanation = explain_global(champion, x_test, test[label_column].astype(bool))

    working = test.assign(_y_true=y_test, _y_proba=proba)
    pred = working["_y_proba"] >= threshold
    fn = working.loc[working["_y_true"] & ~pred].sort_values("_y_proba")
    fp = working.loc[~working["_y_true"] & pred].sort_values("_y_proba", ascending=False)

    worst_fn_row = fn.iloc[0] if not fn.empty else None
    worst_fp_row = fp.iloc[0] if not fp.empty else None
    worst_fn_explanation = (
        explain_local(champion, x_test.loc[[worst_fn_row.name]], background=x_test)
        if worst_fn_row is not None
        else None
    )
    worst_fp_explanation = (
        explain_local(champion, x_test.loc[[worst_fp_row.name]], background=x_test)
        if worst_fp_row is not None
        else None
    )

    logger.info(
        "%s test set: AUC=%.4f, PR-AUC=%.4f, precision=%.3f, recall=%.3f, brier=%.4f "
        "(threshold=%.3f, calibration=%s)",
        task_name,
        metrics.roc_auc,
        metrics.pr_auc,
        metrics.precision,
        metrics.recall,
        metrics.brier_score,
        threshold,
        method,
    )

    log_model_run(
        run_name=f"{task_name}-test-evaluation",
        params={"threshold": threshold, "calibration_method": method, "data_version": data_version},
        metrics={
            "test_roc_auc": metrics.roc_auc,
            "test_pr_auc": metrics.pr_auc,
            "test_precision": metrics.precision,
            "test_recall": metrics.recall,
            "test_f1": metrics.f1,
            "test_brier_score": metrics.brier_score,
            "holdout_calibration_brier": holdout_calibration.brier_score,
        },
        tags={"task": task_name, "stage": "test_evaluation"},
    )

    report_text = _classification_failure_report(
        task_name=task_name,
        threshold=threshold,
        test=test,
        y_true=y_test,
        y_proba=proba,
        feature_cols=feature_cols,
        ood_mask=ood_mask,
        slices=slices,
        global_explanation=global_explanation,
        worst_fn_explanation=worst_fn_explanation,
        worst_fn_row=worst_fn_row,
        worst_fp_explanation=worst_fp_explanation,
        worst_fp_row=worst_fp_row,
    )
    (error_dir / f"{task_name}_failure_analysis.md").write_text(report_text, encoding="utf-8")

    return {
        "task": task_name,
        "threshold": threshold,
        "calibration_method": method,
        "test_metrics": asdict(metrics),
        "holdout_calibration": {
            "brier_score": holdout_calibration.brier_score,
            "mean_predicted_value": holdout_calibration.mean_predicted_value.tolist(),
            "fraction_of_positives": holdout_calibration.fraction_of_positives.tolist(),
        },
        "slices": slices,
        "out_of_distribution_rows": int(ood_mask.sum()),
        "top_shap_features": _top_shap_features(global_explanation),
        "top_permutation_features": _top_permutation_features(global_explanation),
    }


def _evaluate_final_cost_task(
    *,
    models_dir: Path,
    error_dir: Path,
    train: pd.DataFrame,
    test: pd.DataFrame,
    calibration_summary: dict[str, Any],
    data_version: str,
) -> dict[str, Any]:
    label_column = "final_cost_real"
    feature_cols = feature_columns(test, label_column)
    x_test = test[feature_cols]
    y_test = test[label_column].to_numpy()

    champion = joblib.load(models_dir / "final_cost_champion.joblib")
    point_prediction = champion.predict(x_test)

    metrics = compute_regression_metrics(y_test, point_prediction)

    task_summary = calibration_summary["tasks"]["final_cost"]
    interval = ConformalInterval(
        coverage=float(task_summary["target_coverage"]),
        quantile=float(task_summary["conformal_quantile"]),
    )
    lower, upper = predict_interval(point_prediction, interval)
    test_coverage = empirical_coverage(y_test, lower, upper)

    slices = _slice_report(test, y_test, point_prediction, mean_absolute_error, "mae")
    bias_slices = _slice_report(
        test, y_test, point_prediction, lambda yt, yp: float(np.mean(yp - yt)), "bias"
    )
    for dim_name, dim_results in slices.items():
        bias_by_value = {r["slice_value"]: r["bias"] for r in bias_slices[dim_name]}
        for entry in dim_results:
            entry["bias"] = bias_by_value.get(entry["slice_value"])

    ranges = reference_ranges(train, list(NUMERIC_FEATURE_COLUMNS))
    ood_mask = range_violation_mask(test, ranges)

    logger.info(
        "final_cost test set: MAE=$%.0f, RMSE=$%.0f, R2=%.3f, MAPE=%.3f, coverage=%.3f "
        "(target=%.2f)",
        metrics.mae,
        metrics.rmse,
        metrics.r2,
        metrics.mape,
        test_coverage,
        interval.coverage,
    )

    log_model_run(
        run_name="final_cost-test-evaluation",
        params={"target_coverage": interval.coverage, "data_version": data_version},
        metrics={
            "test_mae": metrics.mae,
            "test_rmse": metrics.rmse,
            "test_r2": metrics.r2,
            "test_mape": metrics.mape,
            "test_smape": metrics.smape,
            "test_empirical_coverage": test_coverage,
        },
        tags={"task": "final_cost", "stage": "test_evaluation"},
    )

    report_text = _regression_failure_report(
        test=test,
        y_true=y_test,
        y_pred=point_prediction,
        lower=lower,
        upper=upper,
        ood_mask=ood_mask,
        slices=slices,
    )
    (error_dir / "final_cost_failure_analysis.md").write_text(report_text, encoding="utf-8")

    return {
        "task": "final_cost",
        "test_metrics": asdict(metrics),
        "conformal": {
            "target_coverage": interval.coverage,
            "quantile": interval.quantile,
            "test_empirical_coverage": test_coverage,
        },
        "slices": slices,
        "out_of_distribution_rows": int(ood_mask.sum()),
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_base_config()
    data_version = get_git_sha()

    logger.info("Generating synthetic portfolio and feature table (seed=%s)...", cfg.seed)
    training_dataset = load_training_dataset(cfg)
    features, outcomes, assignment = (
        training_dataset.features,
        training_dataset.outcomes,
        training_dataset.assignment,
    )

    configure_tracking(cfg.paths.mlflow_tracking_uri, cfg.training.mlflow_experiment_name)
    models_dir = PROJECT_ROOT / cfg.paths.models_dir
    reports_dir = PROJECT_ROOT / cfg.paths.reports_dir
    experiments_dir = reports_dir / "experiments"
    error_dir = reports_dir / "error_analysis"
    experiments_dir.mkdir(parents=True, exist_ok=True)
    error_dir.mkdir(parents=True, exist_ok=True)

    calibration_summary = json.loads(
        (reports_dir / "experiments" / "calibration_summary.json").read_text(encoding="utf-8")
    )

    summary: dict[str, Any] = {"git_sha": data_version, "tasks": {}}

    for task_name, label_column in (
        ("cost_overrun", "cost_overrun"),
        ("schedule_delay", "schedule_delay"),
    ):
        task_data = assemble_task_dataset(features, outcomes, label_column)
        train = filter_by_split(task_data, assignment.train_project_ids)
        test = filter_by_split(task_data, assignment.test_project_ids)
        summary["tasks"][task_name] = _evaluate_classification_task(
            task_name=task_name,
            label_column=label_column,
            models_dir=models_dir,
            reports_dir=reports_dir,
            error_dir=error_dir,
            train=train,
            test=test,
            calibration_summary=calibration_summary,
            data_version=data_version,
        )

    final_cost_data = assemble_task_dataset(features, outcomes, "final_cost_real")
    final_cost_train = filter_by_split(final_cost_data, assignment.train_project_ids)
    final_cost_test = filter_by_split(final_cost_data, assignment.test_project_ids)
    summary["tasks"]["final_cost"] = _evaluate_final_cost_task(
        models_dir=models_dir,
        error_dir=error_dir,
        train=final_cost_train,
        test=final_cost_test,
        calibration_summary=calibration_summary,
        data_version=data_version,
    )

    summary_path = experiments_dir / "test_set_metrics.json"
    summary_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    logger.info("Test-set metrics written to %s", summary_path)
    logger.info("Failure analysis reports written to %s", error_dir)


if __name__ == "__main__":
    main()
