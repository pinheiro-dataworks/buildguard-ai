"""Leakage-safe feature assembly (Section 11 / 28).

The single function that turns raw tables into the model-ready feature
table, shared verbatim by training, batch scoring, and (Phase 8) the
FastAPI inference service, so features are never computed a second,
slightly different way at serving time (Section 28).

**Leakage rule (Section 11):** for the output row whose prediction
timestamp is `snapshot_date`, every input to that row's features must have
its own timestamp `<= snapshot_date`. Concretely:

- EVM ratios (`cpi`, `spi`, ...) and inflation features are computed from
  that row's own `earned_value` / `actual_cost` / `planned_cost` --
  already point-in-time by construction (a snapshot only ever reflects
  cumulative-to-date reality; see
  `docs/adr/0004-synthetic-data-design.md`).
- Temporal trend/streak features look backward within a project's own
  chronological history up to and including the current row (never ahead).
- Change-order features are joined with `pandas.merge_asof(...,
  direction="backward")`, an as-of join that structurally cannot see a
  change order dated after the snapshot -- this is exercised directly by
  `tests/leakage/test_pipeline_leakage.py`.

**Known limitation:** Work Packages and Suppliers are *not* included here.
Both tables represent status "as of the project's last snapshot" (Section
8.4/`DATA_DICTIONARY.md`), not a per-date time series -- including them
naively would leak each project's final-snapshot state into every earlier
prediction point. They are excluded rather than included unsafely; wiring
them in would require giving those tables real per-row dates first (a
schema change, not attempted here).

Labels are deliberately never joined into this table -- see
`src/buildguard/data/labels.py`, which callers join separately, keeping it
structurally impossible for a target-derived value to end up in `features`.
"""

from __future__ import annotations

import pandas as pd

from buildguard.config import FeaturesConfig
from buildguard.data.economic_index import EconomicIndexProvider
from buildguard.features import evm, inflation, temporal

_STATIC_PROJECT_COLUMNS = [
    "project_id",
    "project_type",
    "city",
    "state",
    "gross_floor_area_m2",
    "number_of_towers",
    "number_of_units",
    "construction_standard",
    "planned_start_date",
    "planned_completion_date",
    "approved_budget",
]

_CHANGE_ORDER_FEATURE_COLUMNS = [
    "project_id",
    "date",
    "change_order_count_to_date",
    "change_order_amount_to_date",
]


def _change_order_cumulative_features(change_orders: pd.DataFrame) -> pd.DataFrame:
    """One row per change order: leakage-safe cumulative count/amount as of that date.

    Meant for `pandas.merge_asof(..., direction="backward")` against
    snapshots, so a given snapshot only ever picks up the most recent row
    dated on or before it.
    """
    if change_orders.empty:
        return pd.DataFrame(columns=_CHANGE_ORDER_FEATURE_COLUMNS)
    ordered = change_orders.sort_values(["project_id", "date"]).copy()
    ordered["change_order_count_to_date"] = ordered.groupby("project_id").cumcount() + 1
    ordered["change_order_amount_to_date"] = ordered.groupby("project_id")[
        "approved_amount"
    ].cumsum()
    return ordered[_CHANGE_ORDER_FEATURE_COLUMNS]


def build_feature_table(
    projects: pd.DataFrame,
    snapshots: pd.DataFrame,
    change_orders: pd.DataFrame,
    index_provider: EconomicIndexProvider,
    features_config: FeaturesConfig,
) -> pd.DataFrame:
    """Assemble the leakage-safe, point-in-time feature table.

    One output row per input `snapshots` row. See the module docstring for
    the leakage guarantee and the Work Packages/Suppliers limitation.
    """
    df = snapshots.merge(projects[_STATIC_PROJECT_COLUMNS], on="project_id", how="left")

    df["cpi"] = evm.cost_performance_index(df["earned_value"], df["actual_cost"])
    df["spi"] = evm.schedule_performance_index(df["earned_value"], df["planned_cost"])
    df["cost_variance"] = evm.cost_variance(df["earned_value"], df["actual_cost"])
    df["schedule_variance"] = evm.schedule_variance(df["earned_value"], df["planned_cost"])

    multiplier = inflation.inflation_multiplier(
        df["snapshot_date"], df["planned_start_date"], index_provider
    )
    real_actual_cost = inflation.real_actual_cost(df["actual_cost"], multiplier)
    df["inflation_multiplier"] = multiplier
    df["operational_variance"] = inflation.operational_variance(
        df["earned_value"], real_actual_cost
    )
    df["inflation_component"] = inflation.inflation_component(df["actual_cost"], real_actual_cost)

    df["months_since_start"] = temporal.months_since_start(
        df["snapshot_date"], df["planned_start_date"]
    )
    df["months_to_planned_completion"] = temporal.months_to_planned_completion(
        df["snapshot_date"], df["planned_completion_date"]
    )
    fraction = temporal.lifecycle_fraction(
        df["snapshot_date"], df["planned_start_date"], df["planned_completion_date"]
    )
    df["lifecycle_fraction"] = fraction
    df["lifecycle_stage"] = temporal.lifecycle_stage(
        fraction,
        features_config.lifecycle_early_threshold,
        features_config.lifecycle_late_threshold,
    )
    window = features_config.trend_window_months
    df["cpi_trend"] = temporal.trailing_change(df, "cpi", periods=window)
    df["spi_trend"] = temporal.trailing_change(df, "spi", periods=window)
    df["cpi_decline_streak"] = temporal.consecutive_decline_streak(df, "cpi")
    df["spi_decline_streak"] = temporal.consecutive_decline_streak(df, "spi")

    co_features = _change_order_cumulative_features(change_orders)
    if co_features.empty:
        df["change_order_count_to_date"] = 0
        df["change_order_amount_to_date"] = 0.0
    else:
        df = pd.merge_asof(
            df.sort_values("snapshot_date"),
            co_features.sort_values("date"),
            left_on="snapshot_date",
            right_on="date",
            by="project_id",
            direction="backward",
        ).drop(columns=["date"])
        df["change_order_count_to_date"] = df["change_order_count_to_date"].fillna(0).astype(int)
        df["change_order_amount_to_date"] = df["change_order_amount_to_date"].fillna(0.0)
    df["change_order_amount_ratio_to_date"] = (
        df["change_order_amount_to_date"] / df["approved_budget"]
    )

    return df.sort_values(["project_id", "snapshot_date"]).reset_index(drop=True)
