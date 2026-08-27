"""Classification evaluation metrics (Section 18).

Deliberately separate from `buildguard.models.calibration` (Section 16,
which *fits* a calibration mapping on the calibration split) and
`buildguard.models.thresholds` (Section 17, which *selects* a decision
threshold on the calibration split). This module only *measures* -- it
takes an already-decided threshold and an already-calibrated probability
column and reports the metric battery Section 18 requires, on whichever
split the caller passes in (in practice, always the held-out test split --
the one evaluation `docs/adr/0003-temporal-validation.md` reserves it for).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)


@dataclass(frozen=True)
class ConfusionCounts:
    true_positives: int
    false_positives: int
    true_negatives: int
    false_negatives: int


@dataclass(frozen=True)
class ClassificationMetrics:
    roc_auc: float
    pr_auc: float
    precision: float
    recall: float
    f1: float
    brier_score: float
    confusion: ConfusionCounts
    threshold: float
    n_rows: int
    positive_rate: float


def compute_classification_metrics(
    y_true: npt.NDArray[np.bool_],
    y_proba: npt.NDArray[np.float64],
    threshold: float,
) -> ClassificationMetrics:
    """The full Section 18 classification battery at a fixed `threshold`.

    `y_proba` is the positive-class probability (already calibrated, if a
    calibrator was selected); ROC-AUC, PR-AUC, and Brier score are
    threshold-free and score `y_proba` directly, while precision/recall/F1/
    confusion matrix apply `threshold` (never 0.50 by default -- Section
    17's optimized business-cost threshold).
    """
    y_true_arr = np.asarray(y_true, dtype=bool)
    y_pred = y_proba >= threshold

    tn, fp, fn, tp = confusion_matrix(y_true_arr, y_pred, labels=[False, True]).ravel()

    return ClassificationMetrics(
        roc_auc=float(roc_auc_score(y_true_arr, y_proba)),
        pr_auc=float(average_precision_score(y_true_arr, y_proba)),
        precision=float(precision_score(y_true_arr, y_pred, zero_division=0)),
        recall=float(recall_score(y_true_arr, y_pred, zero_division=0)),
        f1=float(f1_score(y_true_arr, y_pred, zero_division=0)),
        brier_score=float(brier_score_loss(y_true_arr, y_proba)),
        confusion=ConfusionCounts(
            true_positives=int(tp),
            false_positives=int(fp),
            true_negatives=int(tn),
            false_negatives=int(fn),
        ),
        threshold=threshold,
        n_rows=len(y_true_arr),
        positive_rate=float(y_true_arr.mean()),
    )
