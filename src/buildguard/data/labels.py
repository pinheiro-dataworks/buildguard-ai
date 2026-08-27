"""Ground-truth label derivation (Section 6 / 11).

Labels are never stored as columns on Projects (Section 8.4 has none) --
derived here, once, from the snapshot history, so training and any future
batch-scoring path resolve outcomes identically (Section 28). Nothing under
`src/buildguard/features/` may import from this module: a predictive
feature computed from the same information used to build the label it's
meant to predict is exactly the "target-derived feature" Section 11
forbids.

**Label basis (resolves the open question from ADR-0004):** `cost_overrun`
is computed against the **inflation-adjusted (real)** final cost, not the
raw nominal `actual_cost`. Section 10 documents why: nominal cost includes
years of compounding demo inflation on top of a budget fixed in
approval-time terms, which alone pushes ~79% of completed projects "over
budget" in nominal terms versus ~47% once inflation is stripped out --
using the nominal figure would make the classification target mostly a
proxy for "how old is this project," not a genuine execution-risk signal.
"""

from __future__ import annotations

import pandas as pd

from buildguard.data.economic_index import EconomicIndexProvider
from buildguard.features import inflation


def resolve_outcomes(
    projects: pd.DataFrame,
    snapshots: pd.DataFrame,
    index_provider: EconomicIndexProvider,
    cost_overrun_tolerance: float,
    schedule_delay_tolerance_days: int,
) -> pd.DataFrame:
    """One row per project: resolved outcome, or all-NaN if still in-flight.

    A project is "resolved" once its last available snapshot has
    ``actual_progress >= 1.0`` -- see
    `src/buildguard/data/synthetic.py` module docstring and
    `docs/adr/0004-synthetic-data-design.md` for why completion is read off
    the snapshot history rather than a stored column. In-flight
    (unresolved) projects get ``pd.NA`` for every outcome field: they have
    no ground truth yet, and callers must not silently treat that absence
    as "no overrun."

    Returns columns: ``project_id``, ``is_resolved``, ``actual_completion_date``,
    ``final_cost_nominal``, ``final_cost_real``, ``delay_days``,
    ``cost_overrun``, ``schedule_delay``.
    """
    last = snapshots.sort_values("snapshot_date").groupby("project_id", as_index=False).tail(1)
    merged = last.merge(
        projects[
            ["project_id", "planned_start_date", "planned_completion_date", "approved_budget"]
        ],
        on="project_id",
        how="left",
    )

    is_resolved = merged["actual_progress"] >= 1.0

    multiplier = inflation.inflation_multiplier(
        merged["snapshot_date"], merged["planned_start_date"], index_provider
    )
    final_cost_real = inflation.real_actual_cost(merged["actual_cost"], multiplier)
    delay_days = (merged["snapshot_date"] - merged["planned_completion_date"]).dt.days

    cost_overrun = (
        final_cost_real > merged["approved_budget"] * (1 + cost_overrun_tolerance)
    ).astype("boolean")
    schedule_delay = (delay_days > schedule_delay_tolerance_days).astype("boolean")

    result = pd.DataFrame(
        {
            "project_id": merged["project_id"],
            "is_resolved": is_resolved,
            "actual_completion_date": merged["snapshot_date"].where(is_resolved, pd.NaT),
            "final_cost_nominal": merged["actual_cost"].where(is_resolved),
            "final_cost_real": final_cost_real.where(is_resolved),
            "delay_days": delay_days.where(is_resolved),
            "cost_overrun": cost_overrun.where(is_resolved),
            "schedule_delay": schedule_delay.where(is_resolved),
        }
    )
    return result.reset_index(drop=True)
