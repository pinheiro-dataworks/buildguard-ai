"""Inflation-adjusted cost normalization (Section 10).

Preserves the legacy GETEC separation of *nominal* cost growth (what was
actually spent, in the currency units of each month) from *operational*
performance (how efficiently the project executed, independent of
market/inflation effects). `actual_cost` on Project Snapshots is nominal by
construction (see `docs/adr/0004-synthetic-data-design.md`); `approved_budget`
and `planned_cost` are expressed in original-approval terms and need no
adjustment.

**Language rule (Section 10):** every output here is an *estimated*
inflation-adjusted figure, derived from one demo/illustrative index. Never
describe it as an exact or causal decomposition of why a project's cost
moved -- say "estimated inflation-adjusted variance", not "the inflation
caused $X of the overrun."

Decomposition identity (tested in `tests/unit/test_inflation.py`):

    nominal_cost_variance == operational_variance + inflation_component

where `nominal_cost_variance = evm.cost_variance(earned_value, actual_cost)`.
"""

from __future__ import annotations

import pandas as pd

from buildguard.data.economic_index import EconomicIndexProvider
from buildguard.features import evm


def inflation_multiplier(
    snapshot_date: pd.Series,
    baseline_date: pd.Series,
    provider: EconomicIndexProvider,
) -> pd.Series:
    """Cumulative inflation since `baseline_date`, as of each `snapshot_date`.

    `index_value(snapshot_date) / index_value(baseline_date)`, elementwise.
    Typically `baseline_date` is the project's `planned_start_date` -- the
    point at which `approved_budget` was set.
    """
    numerator = snapshot_date.map(provider.value_at)
    denominator = baseline_date.map(provider.value_at)
    return numerator / denominator


def real_actual_cost(actual_cost: pd.Series, multiplier: pd.Series) -> pd.Series:
    """Deflate nominal `actual_cost` back to baseline-date purchasing power.

    `real_actual_cost = actual_cost / multiplier`. This is the "what would
    this spend be worth in the project's original-approval money" figure --
    the fair basis for comparing against `approved_budget`.
    """
    return actual_cost / multiplier


def real_budget(approved_budget: pd.Series) -> pd.Series:
    """Budget at Completion, restated for pipeline symmetry with `real_actual_cost`.

    Identity function in this data model: `approved_budget` (and
    `planned_cost`, which is derived from it) are already expressed in
    original-approval-time terms -- see
    `docs/adr/0004-synthetic-data-design.md`. This function exists so
    feature-building code can treat "budget" and "actual cost" uniformly
    (`inflation.real_budget(...)`, `inflation.real_actual_cost(...)`)
    without needing to know which side of the comparison happens to need
    deflating in the current data model.
    """
    return approved_budget


def operational_variance(earned_value: pd.Series, real_actual_cost: pd.Series) -> pd.Series:
    """Cost variance with inflation removed -- the execution-only component.

    `operational_variance = EV - real_actual_cost`, i.e.
    `evm.cost_variance(earned_value, real_actual_cost)`. This is what
    Section 10 calls both "real_cost_variance" and "operational_variance" --
    the same figure under two names emphasizing different readings: an
    accounting restatement (real terms) and a business one (performance net
    of market effects).
    """
    return evm.cost_variance(earned_value, real_actual_cost)


def inflation_component(actual_cost: pd.Series, real_actual_cost: pd.Series) -> pd.Series:
    """The portion of nominal cost variance attributable to price growth.

    `inflation_component = real_actual_cost - actual_cost`. Non-positive
    whenever prices have risen since the baseline date (the usual case),
    since nominal `actual_cost` then exceeds its deflated equivalent --
    meaning inflation alone drags nominal variance below the operational
    (execution-only) variance. Together with `operational_variance`:

        nominal_cost_variance = operational_variance + inflation_component
    """
    return real_actual_cost - actual_cost
