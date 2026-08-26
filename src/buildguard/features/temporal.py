"""Temporal / lifecycle features (Section 8.2: risk evolving over the lifecycle).

Complements `evm.py` (point-in-time EVM ratios) and `inflation.py`
(point-in-time real-terms restatement) with features about *where a
project sits in its lifecycle* and *how a metric has been trending* --
needed to capture signals like "persistent SPI deterioration" that a
single snapshot's CPI/SPI value alone cannot express.

Every function here takes plain `pandas.Series`/`DataFrame` inputs and
returns a `pandas.Series` aligned to the input's index, so these compose
the same way `evm.py` and `inflation.py` do. Trend/streak functions need
each project's snapshots ordered chronologically internally, but always
return a result reindexed back to the caller's original row order.
"""

from __future__ import annotations

import pandas as pd


def months_since_start(snapshot_date: pd.Series, project_start_date: pd.Series) -> pd.Series:
    """Whole months elapsed since the project's planned start."""
    snapshot_month = snapshot_date.dt.to_period("M").astype(int)
    start_month = project_start_date.dt.to_period("M").astype(int)
    delta: pd.Series = snapshot_month - start_month
    return delta


def months_to_planned_completion(
    snapshot_date: pd.Series, planned_completion_date: pd.Series
) -> pd.Series:
    """Whole months remaining to the planned finish (negative once past it)."""
    completion_month = planned_completion_date.dt.to_period("M").astype(int)
    snapshot_month = snapshot_date.dt.to_period("M").astype(int)
    delta: pd.Series = completion_month - snapshot_month
    return delta


def lifecycle_fraction(
    snapshot_date: pd.Series,
    project_start_date: pd.Series,
    planned_completion_date: pd.Series,
) -> pd.Series:
    """Elapsed time / planned duration. 0 at start, 1 at planned finish, >1 if running late."""
    elapsed = months_since_start(snapshot_date, project_start_date)
    planned_duration = months_since_start(planned_completion_date, project_start_date)
    return elapsed / planned_duration


def lifecycle_stage(
    fraction: pd.Series,
    early_threshold: float,
    late_threshold: float,
) -> pd.Series:
    """Bucket a `lifecycle_fraction` into "early" / "mid" / "late".

    Thresholds come from `configs/base.yaml: features.lifecycle_*` (Section
    18 requires lifecycle stage as a slice-analysis dimension; the
    boundaries must be configurable, not hard-coded).
    """
    return pd.cut(
        fraction,
        bins=[-float("inf"), early_threshold, late_threshold, float("inf")],
        labels=["early", "mid", "late"],
    ).astype(str)


def trailing_change(
    df: pd.DataFrame,
    value_col: str,
    periods: int,
    group_col: str = "project_id",
    date_col: str = "snapshot_date",
) -> pd.Series:
    """`value[t] - value[t - periods]` within each project, ordered by date.

    NaN for the first `periods` snapshots of each project (no history yet
    to compare against) -- a real absence of information, not coerced to 0.
    """
    ordered = df.sort_values([group_col, date_col])
    diff = ordered.groupby(group_col)[value_col].diff(periods=periods)
    return diff.reindex(df.index)


def consecutive_decline_streak(
    df: pd.DataFrame,
    value_col: str,
    group_col: str = "project_id",
    date_col: str = "snapshot_date",
) -> pd.Series:
    """Consecutive prior snapshots (within a project) where `value_col` strictly decreased.

    0 at a project's first snapshot and at any snapshot that did not
    decrease from the previous one; increments by 1 for each additional
    consecutive month of decline. This is the "persistence" signal Section
    8.2 asks for (e.g. persistent SPI deterioration), which a single
    period-over-period diff cannot express on its own. `NaN` values in
    `value_col` are treated as "not a decline" (comparisons against NaN are
    always false), resetting the streak rather than raising.
    """
    ordered = df.sort_values([group_col, date_col])
    streak = pd.Series(0, index=ordered.index, dtype=int)
    for _, group in ordered.groupby(group_col):
        values = group[value_col].to_numpy()
        current_streak = 0
        result = []
        previous = None
        for value in values:
            if previous is not None and value < previous:
                current_streak += 1
            else:
                current_streak = 0
            result.append(current_streak)
            previous = value
        streak.loc[group.index] = pd.Series(result, index=group.index)
    return streak.reindex(df.index)
