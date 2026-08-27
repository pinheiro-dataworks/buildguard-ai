"""Candidate classification models (Section 14) for `cost_overrun` and
`schedule_delay` -- the same binary-classification machinery serves both
tasks (Section 6.1/6.2); only the label column supplied to `fit` differs.

Two advanced families are compared here against the mandatory baselines
(Section 13, `buildguard.models.baselines`): `RandomForestClassifier` and
LightGBM. Deliberately not also XGBoost/CatBoost -- Section 14 lists them
as an either/or gradient-boosted-tree option, and adding a second one
alongside LightGBM would pad the dependency stack for no comparative
benefit a reviewer could act on (Section 61).

Hyperparameter search uses Optuna (Section 15: "Randomized Search / Optuna
/ Bayesian optimization only -- avoid unjustified exhaustive grids"),
scored with `GroupKFold` on `project_id` (Section 12's cross-validation
policy: "Group K-Fold -- multiple rows per project, prevents project
leakage across folds"). Every snapshot row of a project carries that
project's single final outcome label, so an ungrouped split would let
near-duplicate rows of the same project sit on both sides of a fold.

Tuning and fitting here only ever touch the **train** split. Selecting
among tuned candidates happens on the **calibration** split
(`scripts/train.py`) -- never on test (Section 12).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import lightgbm as lgb
import numpy as np
import numpy.typing as npt
import optuna
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline

from buildguard.models.preprocessing import build_preprocessor

optuna.logging.set_verbosity(optuna.logging.WARNING)

ClassifierFamily = Literal["random_forest", "lightgbm"]


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


def _build_estimator(family: ClassifierFamily, params: dict[str, Any], seed: int) -> Any:
    if family == "random_forest":
        return RandomForestClassifier(random_state=seed, **params)
    if family == "lightgbm":
        return lgb.LGBMClassifier(random_state=seed, verbose=-1, **params)
    raise ValueError(f"Unknown classifier family: {family!r}")


def build_classifier_pipeline(
    family: ClassifierFamily, params: dict[str, Any], seed: int
) -> Pipeline:
    """A fresh, unfitted preprocessing + estimator pipeline for `family`."""
    return Pipeline(
        steps=[
            ("preprocess", build_preprocessor()),
            ("model", _build_estimator(family, params, seed)),
        ]
    )


@dataclass(frozen=True)
class ClassifierTuningResult:
    family: ClassifierFamily
    best_params: dict[str, Any]
    best_cv_auc: float
    n_trials: int


def _cross_val_auc(
    family: ClassifierFamily,
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
        pipeline = build_classifier_pipeline(family, params, seed)
        pipeline.fit(features.iloc[train_idx], labels.iloc[train_idx])
        proba: npt.NDArray[np.float64] = pipeline.predict_proba(features.iloc[val_idx])[:, 1]
        scores.append(roc_auc_score(labels.iloc[val_idx], proba))
    return float(np.mean(scores))


def tune_classifier(
    family: ClassifierFamily,
    features: pd.DataFrame,
    labels: pd.Series,
    groups: pd.Series,
    n_trials: int,
    n_splits: int,
    seed: int,
) -> ClassifierTuningResult:
    """Optuna TPE search over `family`'s space, scored by grouped-CV ROC-AUC.

    `features`/`labels`/`groups` must already be restricted to the train
    split -- this function has no knowledge of splits and will happily
    overfit to whatever it's handed.
    """
    if family not in _SEARCH_SPACES:
        raise ValueError(f"Unknown classifier family: {family!r}")
    search_space = _SEARCH_SPACES[family]

    def objective(trial: optuna.Trial) -> float:
        params = search_space(trial)
        return _cross_val_auc(family, params, features, labels, groups, n_splits, seed)

    study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=seed))
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

    return ClassifierTuningResult(
        family=family,
        best_params=study.best_params,
        best_cv_auc=study.best_value,
        n_trials=n_trials,
    )


def fit_classifier(
    family: ClassifierFamily,
    params: dict[str, Any],
    features: pd.DataFrame,
    labels: pd.Series,
    seed: int,
) -> Pipeline:
    """Fit one final pipeline on the full `features`/`labels` given (train split)."""
    pipeline = build_classifier_pipeline(family, params, seed)
    pipeline.fit(features, labels)
    return pipeline
