"""Business-cost threshold optimization (Section 17).

Never defaults silently to 0.50: the decision threshold is chosen to
minimize *expected business cost*, using the cost matrix in
`configs/business.yaml` (a missed real overrun/delay -- a false negative --
costs more than a false alarm -- a false positive -- and the threshold
reflects that asymmetry, rather than treating both error types as equally
bad). Optimized on the **calibration** split only, never test (Section 12).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import numpy.typing as npt
import pandas as pd
from sklearn.metrics import confusion_matrix, precision_score, recall_score

RiskBand = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class ThresholdResult:
    threshold: float
    expected_cost: float
    precision: float
    recall: float
    true_positives: int
    false_positives: int
    true_negatives: int
    false_negatives: int


def _expected_cost(
    tp: int, fp: int, tn: int, fn: int, false_negative_cost: float, false_positive_cost: float
) -> float:
    return fn * false_negative_cost + fp * false_positive_cost


def optimize_threshold(
    labels: pd.Series,
    proba: npt.NDArray[np.float64],
    false_negative_cost: float,
    false_positive_cost: float,
    n_candidates: int = 199,
) -> ThresholdResult:
    """Sweep candidate thresholds in (0, 1); pick the one minimizing expected business cost.

    `n_candidates` evenly spaced thresholds strictly between 0 and 1 (the
    endpoints are excluded -- a threshold of exactly 0 or 1 always predicts
    a single class and is never a meaningful business decision point).
    """
    candidates = np.linspace(0.0, 1.0, n_candidates + 2)[1:-1]

    best_threshold = candidates[0]
    best_cost = np.inf
    best_confusion = (0, 0, 0, 0)
    for threshold in candidates:
        y_pred = (proba >= threshold).astype(int)
        tn, fp, fn, tp = confusion_matrix(labels, y_pred, labels=[0, 1]).ravel()
        cost = _expected_cost(
            int(tp), int(fp), int(tn), int(fn), false_negative_cost, false_positive_cost
        )
        if cost < best_cost:
            best_cost = cost
            best_threshold = threshold
            best_confusion = (int(tp), int(fp), int(tn), int(fn))

    tp, fp, tn, fn = best_confusion
    y_pred_best = (proba >= best_threshold).astype(int)
    precision = precision_score(labels, y_pred_best, zero_division=0)
    recall = recall_score(labels, y_pred_best, zero_division=0)

    return ThresholdResult(
        threshold=float(best_threshold),
        expected_cost=float(best_cost),
        precision=float(precision),
        recall=float(recall),
        true_positives=tp,
        false_positives=fp,
        true_negatives=tn,
        false_negatives=fn,
    )


def risk_band(proba: npt.NDArray[np.float64], threshold: float) -> npt.NDArray[np.str_]:
    """Bucket a (calibrated) probability into "low"/"medium"/"high" around the decision `threshold`.

    Below `threshold` (not flagged by the business-cost decision, Section
    17) is always "low". The flagged zone above it is split at its own
    midpoint into "medium" and "high" -- there is no further business-cost
    justification for where exactly to split it, unlike `threshold` itself,
    so this is a display/reporting convenience (Section 23's risk-band
    proportions, the API response shape in Section 28), not a second
    business decision.
    """
    midpoint = threshold + (1.0 - threshold) / 2.0
    bands = np.full(np.shape(proba), "low", dtype=object)
    proba_arr = np.asarray(proba)
    bands[proba_arr >= threshold] = "medium"
    bands[proba_arr >= midpoint] = "high"
    return bands.astype(str)
