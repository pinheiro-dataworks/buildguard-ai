"""Candidate regression models (Section 14) for the final-cost task (Section 6.3).

Mirrors `classification.py`: `RandomForestRegressor` and LightGBM compared
against the mandatory baselines (Section 13,
`buildguard.models.baselines`), tuned with Optuna (Section 15) scored by
grouped-CV MAE (`GroupKFold` on `project_id`, Section 12) so a project's
own rows never appear on both sides of a fold.

The regression target is `final_cost_real` (inflation-adjusted, currency
units) -- not a normalized ratio. Section 6.3 allows either and says
normalization "must be justified experimentally"; that comparison is left
as a documented follow-up (`docs/adr/0006-model-selection.md`) rather than
explored unboundedly here.

Tuning and fitting here only ever touch the **train** split; candidate
selection happens on **calibration** (`scripts/train.py`), never test.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import lightgbm as lgb
import numpy as np
import numpy.typing as npt
import optuna
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline

from buildguard.models.preprocessing import build_preprocessor

optuna.logging.set_verbosity(optuna.logging.WARNING)

RegressorFamily = Literal["random_forest", "lightgbm"]


def _random_forest_search_space(trial: optuna.Trial) -> dict[str, Any]:
    return {
        "n_estimators": trial.suggest_int("n_estimators", 100, 400),
        "max_depth": trial.suggest_int("max_depth", 3, 14),
        "min_samples_leaf": trial.suggest_int("min_samples_leaf", 1, 20),
    }


def _lightgbm_search_space(trial: optuna.Trial) -> dict[str, Any]:
    return {
        "n_estimators": trial.suggest_int("n_estimators", 100, 400),
        "num_leaves": trial.suggest_int("num_leaves", 8, 64),
        "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
        "min_child_samples": trial.suggest_int("min_child_samples", 5, 50),
    }


_SEARCH_SPACES = {
    "random_forest": _random_forest_search_space,
    "lightgbm": _lightgbm_search_space,
}


def _build_estimator(family: RegressorFamily, params: dict[str, Any], seed: int) -> Any:
    if family == "random_forest":
        return RandomForestRegressor(random_state=seed, **params)
    if family == "lightgbm":
        return lgb.LGBMRegressor(random_state=seed, verbose=-1, **params)
    raise ValueError(f"Unknown regressor family: {family!r}")


def build_regressor_pipeline(
    family: RegressorFamily, params: dict[str, Any], seed: int
) -> Pipeline:
    """A fresh, unfitted preprocessing + estimator pipeline for `family`."""
    return Pipeline(
        steps=[
            ("preprocess", build_preprocessor()),
            ("model", _build_estimator(family, params, seed)),
        ]
    )


@dataclass(frozen=True)
class RegressorTuningResult:
    family: RegressorFamily
    best_params: dict[str, Any]
    best_cv_mae: float
    n_trials: int


def _cross_val_mae(
    family: RegressorFamily,
    params: dict[str, Any],
    features: pd.DataFrame,
    labels: pd.Series,
    groups: pd.Series,
    n_splits: int,
    seed: int,
) -> float:
    gkf = GroupKFold(n_splits=n_splits)
    scores: list[float] = []
    for train_idx, val_idx in gkf.split(features, labels, groups=groups):
        pipeline = build_regressor_pipeline(family, params, seed)
        pipeline.fit(features.iloc[train_idx], labels.iloc[train_idx])
        prediction: npt.NDArray[np.float64] = pipeline.predict(features.iloc[val_idx])
        scores.append(mean_absolute_error(labels.iloc[val_idx], prediction))
    return float(np.mean(scores))


def tune_regressor(
    family: RegressorFamily,
    features: pd.DataFrame,
    labels: pd.Series,
    groups: pd.Series,
    n_trials: int,
    n_splits: int,
    seed: int,
) -> RegressorTuningResult:
    """Optuna TPE search over `family`'s space, scored by grouped-CV MAE (lower is better).

    `features`/`labels`/`groups` must already be restricted to the train
    split -- this function has no knowledge of splits.
    """
    if family not in _SEARCH_SPACES:
        raise ValueError(f"Unknown regressor family: {family!r}")
    search_space = _SEARCH_SPACES[family]

    def objective(trial: optuna.Trial) -> float:
        params = search_space(trial)
        return _cross_val_mae(family, params, features, labels, groups, n_splits, seed)

    study = optuna.create_study(direction="minimize", sampler=optuna.samplers.TPESampler(seed=seed))
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

    return RegressorTuningResult(
        family=family,
        best_params=study.best_params,
        best_cv_mae=study.best_value,
        n_trials=n_trials,
    )


def fit_regressor(
    family: RegressorFamily,
    params: dict[str, Any],
    features: pd.DataFrame,
    labels: pd.Series,
    seed: int,
) -> Pipeline:
    """Fit one final pipeline on the full `features`/`labels` given (train split)."""
    pipeline = build_regressor_pipeline(family, params, seed)
    pipeline.fit(features, labels)
    return pipeline
