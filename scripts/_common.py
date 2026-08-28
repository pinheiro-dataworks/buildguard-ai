"""Shared dataset assembly for training scripts (`train.py`, `calibrate.py`).

Not part of `src/buildguard/` deliberately: this is script-level
orchestration (regenerate the whole portfolio, build features, resolve
labels, compute the split) specific to batch training/calibration runs --
the FastAPI inference service (Phase 8) will build features for one
project at a time from live data, not by regenerating the full synthetic
portfolio, so this isn't reusable "serving" logic (Section 28's shared
module is `buildguard.features.pipeline`, which this calls into).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd

from buildguard.config import BaseAppConfig
from buildguard.data.economic_index import DemoIndexProvider, EconomicIndexProvider
from buildguard.data.labels import resolve_outcomes
from buildguard.data.split import SplitAssignment, chronological_project_split, filter_by_split
from buildguard.data.synthetic import PortfolioDataset, generate_portfolio
from buildguard.features.pipeline import build_feature_table

NON_FEATURE_COLUMNS = {
    "project_id",
    "snapshot_date",
    "planned_start_date",
    "planned_completion_date",
}


@dataclass(frozen=True)
class TrainingDataset:
    raw: PortfolioDataset
    features: pd.DataFrame
    outcomes: pd.DataFrame
    assignment: SplitAssignment
    index_provider: EconomicIndexProvider


def load_training_dataset(cfg: BaseAppConfig) -> TrainingDataset:
    """Regenerate the synthetic portfolio and assemble the leakage-safe
    feature table, resolved outcomes, and project split -- everything
    downstream of `generate_portfolio` that `train.py`, `calibrate.py`,
    `evaluate.py`, and `monitor.py` need identically. `raw` (the six core
    tables straight from `generate_portfolio`) is only needed by
    `monitor.py`'s data-quality checks -- everything else works off
    `features`/`outcomes`.
    """
    dataset = generate_portfolio(cfg)
    provider = DemoIndexProvider(
        reference_date=cfg.synthetic_data.reference_date,
        history_years=cfg.synthetic_data.history_years,
    )
    features = build_feature_table(
        dataset.projects, dataset.snapshots, dataset.change_orders, provider, cfg.features
    )
    outcomes = resolve_outcomes(
        dataset.projects,
        dataset.snapshots,
        provider,
        cfg.targets.cost_overrun_tolerance,
        cfg.targets.schedule_delay_tolerance_days,
    )
    assignment = chronological_project_split(dataset.projects, cfg.split)
    return TrainingDataset(
        raw=dataset,
        features=features,
        outcomes=outcomes,
        assignment=assignment,
        index_provider=provider,
    )


def assemble_task_dataset(
    features: pd.DataFrame, outcomes: pd.DataFrame, label_column: str
) -> pd.DataFrame:
    """Every feature row of a resolved project, joined to its single outcome label."""
    resolved = outcomes.loc[outcomes["is_resolved"], ["project_id", label_column]]
    return features.merge(resolved, on="project_id", how="inner")


def feature_columns(df: pd.DataFrame, label_column: str) -> list[str]:
    return [c for c in df.columns if c not in NON_FEATURE_COLUMNS | {label_column}]


def positive_class_proba(model: Any, features: pd.DataFrame) -> npt.NDArray[np.float64]:
    """The positive-class column of `model.predict_proba(features)`, handling both a
    2-column `(n, 2)` output and an already-1-D positive-class-only output."""
    raw = model.predict_proba(features)
    return raw[:, 1] if raw.ndim == 2 else raw


__all__ = [
    "NON_FEATURE_COLUMNS",
    "TrainingDataset",
    "assemble_task_dataset",
    "feature_columns",
    "filter_by_split",
    "load_training_dataset",
    "positive_class_proba",
]
