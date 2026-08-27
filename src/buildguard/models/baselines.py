"""Baseline models (Section 13) -- mandatory before any advanced model.

Every candidate model trained later (Session H / Section 14) must beat
these, not just a naive statistical baseline: "the ML model must beat a
meaningful construction-management baseline, not only a naive statistical
one." Classification and regression baselines share a minimal
``fit``/``predict[_proba]`` interface (`ClassificationBaseline`,
`RegressionBaseline` protocols) so evaluation code added in a later phase
never needs to special-case "is this a baseline or a real model."

All baselines consume the output of
`buildguard.features.pipeline.build_feature_table` directly -- the same
feature table real models will use, so a baseline-vs-model comparison is
never confounded by different inputs.
"""

from __future__ import annotations

from typing import Protocol

import numpy as np
import numpy.typing as npt
import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.pipeline import Pipeline

from buildguard.models.preprocessing import build_preprocessor


class ClassificationBaseline(Protocol):
    def fit(self, features: pd.DataFrame, labels: pd.Series) -> ClassificationBaseline: ...
    def predict_proba(self, features: pd.DataFrame) -> npt.NDArray[np.float64]: ...


class RegressionBaseline(Protocol):
    def fit(self, features: pd.DataFrame, labels: pd.Series) -> RegressionBaseline: ...
    def predict(self, features: pd.DataFrame) -> npt.NDArray[np.float64]: ...


class DummyClassifierBaseline:
    """Predicts the training class prior for every row, ignoring features.

    The uninformative floor: any model failing to beat this has learned
    nothing from the features at all.
    """

    def __init__(self) -> None:
        self._model = DummyClassifier(strategy="prior")

    def fit(self, features: pd.DataFrame, labels: pd.Series) -> DummyClassifierBaseline:
        self._model.fit(np.zeros((len(labels), 1)), labels)
        return self

    def predict_proba(self, features: pd.DataFrame) -> npt.NDArray[np.float64]:
        proba: npt.NDArray[np.float64] = self._model.predict_proba(np.zeros((len(features), 1)))[
            :, 1
        ]
        return proba


class LogisticRegressionBaseline:
    """A real, simple statistical baseline: standardized/encoded features + logistic regression."""

    def __init__(self) -> None:
        self._pipeline = Pipeline(
            steps=[
                ("preprocess", build_preprocessor()),
                ("model", LogisticRegression(max_iter=1000)),
            ]
        )

    def fit(self, features: pd.DataFrame, labels: pd.Series) -> LogisticRegressionBaseline:
        self._pipeline.fit(features, labels)
        return self

    def predict_proba(self, features: pd.DataFrame) -> npt.NDArray[np.float64]:
        proba: npt.NDArray[np.float64] = self._pipeline.predict_proba(features)[:, 1]
        return proba


class CpiRuleBaseline:
    """Domain rule baseline (Section 13's own example): ``CPI < threshold -> High Cost Risk``.

    No fitting happens -- a hand-written rule has nothing to learn from
    data, and is kept in the same interface as the learned baselines only
    so evaluation code can compare them uniformly. A row with an undefined
    (``NaN``) CPI -- e.g. the very first snapshot, before any cost has been
    incurred -- is not flagged: there is no evidence of a problem yet, and
    flagging it would just be guessing.
    """

    def __init__(self, threshold: float) -> None:
        self.threshold = threshold

    def fit(self, features: pd.DataFrame, labels: pd.Series) -> CpiRuleBaseline:
        return self

    def predict_proba(self, features: pd.DataFrame) -> npt.NDArray[np.float64]:
        cpi = features["cpi"].to_numpy()
        flagged = np.where(np.isnan(cpi), False, cpi < self.threshold)
        return flagged.astype(np.float64)


class MeanRegressionBaseline:
    """Predicts the training-set mean label for every row, ignoring features."""

    def __init__(self) -> None:
        self._value = 0.0

    def fit(self, features: pd.DataFrame, labels: pd.Series) -> MeanRegressionBaseline:
        self._value = float(labels.mean())
        return self

    def predict(self, features: pd.DataFrame) -> npt.NDArray[np.float64]:
        return np.full(len(features), self._value, dtype=np.float64)


class MedianRegressionBaseline:
    """Predicts the training-set median label for every row, ignoring features."""

    def __init__(self) -> None:
        self._value = 0.0

    def fit(self, features: pd.DataFrame, labels: pd.Series) -> MedianRegressionBaseline:
        self._value = float(labels.median())
        return self

    def predict(self, features: pd.DataFrame) -> npt.NDArray[np.float64]:
        return np.full(len(features), self._value, dtype=np.float64)


class DeterministicEacBaseline:
    """Uses the EVM CPI-based Estimate at Completion already on each row.

    Zero-parameter and deterministic -- `forecast_cost` (`evm.estimate_at_completion_cpi`,
    Section 9) is computed once at data-generation/serving time from that
    row's own CPI, not learned from a training set. `fit` is a no-op kept
    only for interface uniformity with the learned baselines.
    """

    def fit(self, features: pd.DataFrame, labels: pd.Series) -> DeterministicEacBaseline:
        return self

    def predict(self, features: pd.DataFrame) -> npt.NDArray[np.float64]:
        forecast: npt.NDArray[np.float64] = features["forecast_cost"].to_numpy()
        return forecast


class LinearRegressionBaseline:
    """A real, simple statistical baseline: standardized/encoded features + linear regression."""

    def __init__(self) -> None:
        self._pipeline = Pipeline(
            steps=[
                ("preprocess", build_preprocessor()),
                ("model", LinearRegression()),
            ]
        )

    def fit(self, features: pd.DataFrame, labels: pd.Series) -> LinearRegressionBaseline:
        self._pipeline.fit(features, labels)
        return self

    def predict(self, features: pd.DataFrame) -> npt.NDArray[np.float64]:
        prediction: npt.NDArray[np.float64] = self._pipeline.predict(features)
        return prediction
