"""Explainability for the tree-based classifiers (Section 20).

SHAP `TreeExplainer` computes attributions on the underlying model's raw
(pre-calibration) score -- `cost_overrun`'s Random Forest,
`schedule_delay`'s LightGBM. The calibration mapping (Section 16,
`buildguard.models.calibration.CalibratedModel`) is a monotonic 1-D
transform of that score, so it changes the probability *scale* but never
*which* features drove the prediction -- explaining the pre-calibration
score is both correct and simpler than trying to differentiate through the
calibrator.

Global explanations report **both** mean absolute SHAP value and
permutation importance (Section 20 lists them as two separate outputs, not
one) -- deliberately, since they can disagree (most often under correlated
features) and reporting only one would hide that disagreement. They are
computed over different feature spaces by construction: SHAP explains the
model's *encoded* inputs (after the pipeline's one-hot expansion of
categoricals), permutation importance explains its *original* inputs
(it permutes whole columns of the pipeline's own input, before
preprocessing runs) -- both are returned, not forced into a shared shape.

`final_cost`'s champion (`DeterministicEacBaseline`, ADR-0006) is a
formula, not a fitted model -- nothing here applies to it; the formula
itself (`BAC / CPI`) already is the explanation.

**Mandatory disclaimer (Section 20)**, exported as `CAUSALITY_DISCLAIMER`
so every explanation-bearing UI surface displays the identical wording:
"Feature attribution explains the model prediction; it does not establish
causality."
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd
import shap
from sklearn.inspection import permutation_importance
from sklearn.pipeline import Pipeline

CAUSALITY_DISCLAIMER = (
    "Feature attribution explains the model prediction; it does not establish causality."
)


class UnsupportedModelError(TypeError):
    """Raised when asked to explain a model this module has no SHAP support for."""


def _unwrap_pipeline(model: Any) -> Pipeline:
    """Reach through a `CalibratedModel` wrapper (if present) to the underlying sklearn `Pipeline`."""
    base = getattr(model, "_base_model", model)
    if not isinstance(base, Pipeline):
        raise UnsupportedModelError(
            "Expected a sklearn Pipeline (optionally wrapped in "
            f"buildguard.models.calibration.CalibratedModel), got {type(base)!r}. "
            "SHAP/permutation-importance explanations are only implemented for the "
            "tree-based classifiers (cost_overrun, schedule_delay) -- not the "
            "final_cost formula baseline."
        )
    return base


def _positive_class_shap_values(raw: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    """Normalize `TreeExplainer.shap_values` output to `(n_rows, n_features)` for the positive class.

    Different model/SHAP combinations return different shapes for binary
    classification: `RandomForestClassifier` gives
    `(n_rows, n_features, n_classes)`; LightGBM's binary classifier gives
    `(n_rows, n_features)` directly (its single raw-margin output already
    corresponds to the positive class). Both are handled here so callers
    never need to know which model produced the values.
    """
    if raw.ndim == 3:
        return raw[:, :, 1]
    return raw


def _positive_class_expected_value(expected_value: Any) -> float:
    if isinstance(expected_value, list | np.ndarray):
        arr = np.asarray(expected_value)
        return float(arr[1]) if arr.ndim >= 1 and arr.shape[0] > 1 else float(arr.reshape(-1)[0])
    return float(expected_value)


def _build_explainer(estimator: Any, background: npt.NDArray[np.float64]) -> Any:
    """A `TreeExplainer` in **probability** space for either model family.

    Without ``model_output="probability"``, LightGBM's binary classifier
    yields SHAP values in raw log-odds/margin space while
    `RandomForestClassifier`'s yield probability-space values directly --
    forcing both into probability space (which needs a `background`
    sample to estimate) is what makes ``base_value + shap_values.sum() ==
    predicted_probability`` hold for *both* families, not just one.
    """
    return shap.TreeExplainer(estimator, data=background, model_output="probability")


@dataclass(frozen=True)
class GlobalExplanation:
    shap_feature_names: list[str]
    mean_abs_shap: npt.NDArray[np.float64]
    permutation_feature_names: list[str]
    permutation_importance_mean: npt.NDArray[np.float64]
    permutation_importance_std: npt.NDArray[np.float64]


@dataclass(frozen=True)
class LocalExplanation:
    feature_names: list[str]
    shap_values: npt.NDArray[np.float64]
    base_value: float
    predicted_value: float


def explain_global(
    model: Any,
    features: pd.DataFrame,
    labels: pd.Series,
    sample_size: int | None = 500,
    background_size: int = 100,
    n_permutation_repeats: int = 10,
    seed: int = 42,
) -> GlobalExplanation:
    """Global feature importance: mean |SHAP value| and permutation importance.

    `model` may be a fitted sklearn `Pipeline` or a `CalibratedModel`
    wrapping one (`classification.fit_classifier(...)` output, calibrated
    or not). `sample_size` subsamples `features`/`labels` for the (more
    expensive) SHAP computation -- `None` uses every row. `background_size`
    controls how many (transformed) rows anchor the probability-space
    SHAP baseline (see `_build_explainer`).
    """
    pipeline = _unwrap_pipeline(model)
    preprocess = pipeline.named_steps["preprocess"]
    estimator = pipeline.named_steps["model"]

    shap_features = features
    shap_labels = labels
    if sample_size is not None and len(features) > sample_size:
        shap_features = features.sample(sample_size, random_state=seed)
        shap_labels = labels.loc[shap_features.index]

    transformed = preprocess.transform(shap_features)
    shap_feature_names = list(preprocess.get_feature_names_out())

    rng = np.random.default_rng(seed)
    background_idx = rng.choice(
        len(transformed), size=min(background_size, len(transformed)), replace=False
    )
    explainer = _build_explainer(estimator, transformed[background_idx])
    raw_shap_values = np.asarray(explainer.shap_values(transformed))
    positive_shap = _positive_class_shap_values(raw_shap_values)
    mean_abs_shap = np.abs(positive_shap).mean(axis=0)

    permutation_feature_names = list(features.columns)
    perm_result = permutation_importance(
        pipeline,
        shap_features,
        shap_labels,
        n_repeats=n_permutation_repeats,
        random_state=seed,
        scoring="roc_auc",
    )

    return GlobalExplanation(
        shap_feature_names=shap_feature_names,
        mean_abs_shap=mean_abs_shap,
        permutation_feature_names=permutation_feature_names,
        permutation_importance_mean=perm_result.importances_mean,
        permutation_importance_std=perm_result.importances_std,
    )


def explain_local(
    model: Any,
    feature_row: pd.DataFrame,
    background: pd.DataFrame,
    background_size: int = 100,
    seed: int = 42,
) -> LocalExplanation:
    """SHAP values for a single prediction (`feature_row` must have exactly one row).

    `background` -- a representative sample (e.g. the calibration split)
    -- anchors the probability-space SHAP baseline; it is not the row
    being explained.
    """
    if len(feature_row) != 1:
        raise ValueError(f"explain_local expects exactly one row, got {len(feature_row)}")

    pipeline = _unwrap_pipeline(model)
    preprocess = pipeline.named_steps["preprocess"]
    estimator = pipeline.named_steps["model"]

    transformed = preprocess.transform(feature_row)
    feature_names = list(preprocess.get_feature_names_out())

    transformed_background = preprocess.transform(background)
    rng = np.random.default_rng(seed)
    background_idx = rng.choice(
        len(transformed_background),
        size=min(background_size, len(transformed_background)),
        replace=False,
    )
    explainer = _build_explainer(estimator, transformed_background[background_idx])

    raw_shap_values = np.asarray(explainer.shap_values(transformed))
    positive_shap = _positive_class_shap_values(raw_shap_values)[0]
    base_value = _positive_class_expected_value(explainer.expected_value)

    predicted_value: float = float(np.asarray(model.predict_proba(feature_row))[:, 1][0])

    return LocalExplanation(
        feature_names=feature_names,
        shap_values=positive_shap,
        base_value=base_value,
        predicted_value=predicted_value,
    )
