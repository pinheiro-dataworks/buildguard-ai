"""Chronological, project-grouped train/calibration/test split (Section 12).

Splits at the **project** level, never at the snapshot-row level: every
snapshot, change order, work package, and supplier row for a given project
goes to exactly one of train/calibration/test, so no project's history can
"contaminate" more than one split the way a naive random row split would
(Section 12's `GroupKFold`-style requirement -- see
`docs/adr/0003-temporal-validation.md` for why this method was chosen).

Projects are ordered chronologically by `planned_start_date` (ties broken
by `project_id` for determinism) -- oldest projects in TRAIN, newest in
TEST, per `configs/base.yaml: split` fractions. The test split is meant to
be used for exactly one final evaluation (Section 12): nothing in this
module or its callers may use test-split data for feature selection,
tuning, calibration, or threshold selection.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from buildguard.config import SplitConfig


@dataclass(frozen=True)
class SplitAssignment:
    """Project-ID membership for each split. A project belongs to exactly one."""

    train_project_ids: frozenset[str]
    calibration_project_ids: frozenset[str]
    test_project_ids: frozenset[str]

    def split_of(self, project_id: str) -> str:
        """Which split a project belongs to: "train", "calibration", or "test"."""
        if project_id in self.train_project_ids:
            return "train"
        if project_id in self.calibration_project_ids:
            return "calibration"
        if project_id in self.test_project_ids:
            return "test"
        raise KeyError(f"Unknown project_id (not part of this split): {project_id!r}")


def chronological_project_split(
    projects: pd.DataFrame, split_config: SplitConfig
) -> SplitAssignment:
    """Assign every project in `projects` to train/calibration/test.

    Requires a `project_id` and `planned_start_date` column. Raises
    `ValueError` if `projects` is empty or contains duplicate `project_id`s
    -- a split over ambiguous or missing project identity would silently
    produce a meaningless assignment.
    """
    if projects.empty:
        raise ValueError("Cannot split an empty projects table")
    if projects["project_id"].duplicated().any():
        raise ValueError("projects table has duplicate project_id values")

    ordered = projects.sort_values(["planned_start_date", "project_id"])
    n = len(ordered)
    train_end = round(n * split_config.train_fraction)
    calibration_end = train_end + round(n * split_config.calibration_fraction)

    ids = ordered["project_id"].tolist()
    train_ids = frozenset(ids[:train_end])
    calibration_ids = frozenset(ids[train_end:calibration_end])
    test_ids = frozenset(ids[calibration_end:])

    return SplitAssignment(
        train_project_ids=train_ids,
        calibration_project_ids=calibration_ids,
        test_project_ids=test_ids,
    )


def filter_by_split(df: pd.DataFrame, project_ids: frozenset[str]) -> pd.DataFrame:
    """Restrict any table with a `project_id` column to one split's projects."""
    return df.loc[df["project_id"].isin(project_ids)].reset_index(drop=True)
