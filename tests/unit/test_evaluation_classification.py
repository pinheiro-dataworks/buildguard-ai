"""Unit tests for classification evaluation metrics (Section 18)."""

from __future__ import annotations

import numpy as np
import pytest
from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score

from buildguard.evaluation.classification import compute_classification_metrics

pytestmark = pytest.mark.unit


def test_matches_hand_calculated_sklearn_metrics_at_a_fixed_threshold() -> None:
    rng = np.random.default_rng(0)
    y_true = rng.integers(0, 2, 200).astype(bool)
    y_proba = np.clip(y_true * 0.6 + rng.normal(0, 0.25, 200), 0, 1)
    threshold = 0.4

    metrics = compute_classification_metrics(y_true, y_proba, threshold)

    y_pred = y_proba >= threshold
    assert metrics.roc_auc == pytest.approx(roc_auc_score(y_true, y_proba))
    assert metrics.precision == pytest.approx(precision_score(y_true, y_pred))
    assert metrics.recall == pytest.approx(recall_score(y_true, y_pred))
    assert metrics.f1 == pytest.approx(f1_score(y_true, y_pred))


def test_confusion_counts_sum_to_total_rows() -> None:
    y_true = np.array([True, True, False, False, True])
    y_proba = np.array([0.9, 0.1, 0.2, 0.8, 0.6])
    metrics = compute_classification_metrics(y_true, y_proba, threshold=0.5)

    c = metrics.confusion
    assert c.true_positives + c.false_positives + c.true_negatives + c.false_negatives == 5
    assert metrics.n_rows == 5


def test_perfect_separation_gives_auc_one_and_zero_brier_at_the_right_threshold() -> None:
    y_true = np.array([False] * 10 + [True] * 10)
    y_proba = np.array([0.0] * 10 + [1.0] * 10)
    metrics = compute_classification_metrics(y_true, y_proba, threshold=0.5)

    assert metrics.roc_auc == pytest.approx(1.0)
    assert metrics.brier_score == pytest.approx(0.0)
    assert metrics.precision == pytest.approx(1.0)
    assert metrics.recall == pytest.approx(1.0)


def test_threshold_shifts_recall_and_precision_tradeoff() -> None:
    y_true = np.array([True, True, True, False, False])
    y_proba = np.array([0.9, 0.6, 0.3, 0.2, 0.1])

    lenient = compute_classification_metrics(y_true, y_proba, threshold=0.2)
    strict = compute_classification_metrics(y_true, y_proba, threshold=0.8)

    assert lenient.recall >= strict.recall
    assert lenient.confusion.true_positives >= strict.confusion.true_positives


def test_positive_rate_reflects_class_balance() -> None:
    y_true = np.array([True, True, True, False])
    y_proba = np.array([0.9, 0.8, 0.7, 0.1])
    metrics = compute_classification_metrics(y_true, y_proba, threshold=0.5)
    assert metrics.positive_rate == pytest.approx(0.75)
