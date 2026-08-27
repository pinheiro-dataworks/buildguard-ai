# Anti-Leakage Policy

**Rule (Section 11):** a model predicting risk at month `t` may use only
information available on or before `t`. This document is the single
reference for what that means concretely in BuildGuard AI, and how it is
enforced in code and tests -- not just in intent.

## 1. Prediction timestamp

Every row of the feature table (`buildguard.features.pipeline.build_feature_table`)
corresponds to one project at one monthly snapshot. **The prediction
timestamp for that row is its `snapshot_date`.** This is the "as of" date a
BuildGuard risk prediction is implicitly stamped with -- "given everything
known about this project through `snapshot_date`, what is its risk?"

There is no separate, independently-configurable prediction timestamp:
using the snapshot's own date keeps the concept concrete and testable
(the alternative -- an arbitrary prediction date decoupled from any real
observation -- would require inventing what "known as of that date" even
means, with no data to back it).

## 2. Feature availability timestamp

Every feature computed by `build_feature_table` has a defined availability
timestamp, and it is enforced to be `<= snapshot_date`:

| Feature group | Availability timestamp | How enforced |
|---|---|---|
| EVM ratios (`cpi`, `spi`, `cost_variance`, `schedule_variance`) | `snapshot_date` | Computed from that row's own `earned_value`/`actual_cost`/`planned_cost` -- a snapshot only ever reflects cumulative-to-date reality by construction (`docs/adr/0004-synthetic-data-design.md`) |
| Inflation features (`inflation_multiplier`, `operational_variance`, `inflation_component`) | `snapshot_date` | Same reasoning; the economic index is looked up at `snapshot_date`, never a later date |
| Temporal/lifecycle (`months_since_start`, `lifecycle_fraction`, `lifecycle_stage`) | `snapshot_date` | Pure function of `snapshot_date` and static project dates |
| Trend/streak (`cpi_trend`, `spi_trend`, `*_decline_streak`) | `<= snapshot_date` | `buildguard.features.temporal` sorts each project's own history chronologically and only ever looks backward from the current row |
| Change-order cumulative (`change_order_count_to_date`, `change_order_amount_to_date`) | `<= snapshot_date` | `pandas.merge_asof(..., direction="backward")` -- a change order dated after `snapshot_date` is structurally excluded from the match, not merely filtered by convention |
| Static project attributes (`project_type`, `construction_standard`, `gross_floor_area_m2`, ...) | Available at `planned_start_date` | Set once at project approval, never change over the project's life |

## 3. Label creation

Labels (`buildguard.data.labels.resolve_outcomes`) are **not** part of the
feature table and are computed by a separate module that nothing under
`src/buildguard/features/` is allowed to import from. A label is only
*resolved* once a project's last available snapshot has `actual_progress
>= 1.0` (i.e. the project has actually finished):

- `cost_overrun`: real (inflation-adjusted) final cost `>` `approved_budget
  * (1 + cost_overrun_tolerance)`.
- `schedule_delay`: `actual_completion_date > planned_completion_date +
  schedule_delay_tolerance_days`.

Projects still in-flight as of the dataset's `reference_date` get `pd.NA`
for every outcome field -- never a coerced `False`, which would silently
teach a model that "not yet finished" means "did not overrun."

## 4. Forbidden features (Section 11)

Never allowed as a model input, anywhere in `src/buildguard/features/`:

- `final_cost` (nominal or real), or anything derived from a project's
  *last* snapshot when predicting from an *earlier* one.
- Future change orders (`date > snapshot_date`) -- structurally impossible
  via `merge_asof`, see Section 2.
- Future supplier delivery delays -- moot today: Work Packages and
  Suppliers are entirely excluded from the feature pipeline (see Section
  6), precisely because those tables represent "as of the project's last
  snapshot" status, not a genuine per-date time series.
- Final completion status (`actual_progress >= 1.0` as a *feature* --
  it is only ever used, appropriately, as the *resolution condition* for a
  label).
- Future inflation index values -- `EconomicIndexProvider.value_at(date)`
  is only ever called with `date <= snapshot_date` inside the pipeline.
- Whole-lifecycle aggregates computed over a project's full history when
  scoring an earlier snapshot (e.g. "average CPI over the whole project").
- Any label or label-derived value (`cost_overrun`, `schedule_delay`,
  `final_cost_real`) appearing as a feature -- see Section 3.

## 5. Temporal validation strategy

Chronological, **project-grouped** split
(`buildguard.data.split.chronological_project_split`, Section 12):
projects are sorted by `planned_start_date` and assigned wholesale to
train (60%, oldest) / calibration (20%) / test (20%, newest) -- never split
at the snapshot-row level, so no project's history can appear in more than
one split. Rationale for this method over alternatives (e.g. plain
`GroupKFold` without chronological ordering) is recorded in
[ADR-0003](adr/0003-temporal-validation.md).

The test split is reserved for exactly one final, unbiased evaluation
(Section 12) -- it must never be touched for feature selection,
hyperparameter tuning, calibration, or threshold selection. This is a
process discipline this document records but code cannot fully enforce;
future model-training scripts must respect it explicitly.

## 6. Known limitation: Work Packages and Suppliers

Neither table carries a per-row date (`DATA_DICTIONARY.md`) -- both reflect
status "as of the project's most recent snapshot." Including them in the
feature pipeline as-is would leak each project's *final* state into every
*earlier* prediction point. They are excluded entirely from
`build_feature_table` rather than included unsafely (see the module
docstring in `src/buildguard/features/pipeline.py`). Wiring them in
correctly would require giving both tables real per-row dates -- a schema
change, not attempted in this phase.

## 7. Automated leakage tests

`tests/leakage/test_pipeline_leakage.py` -- the Section 11-mandated
automated check, run on every CI build:

- A change order dated after a project's snapshots must never contribute
  to any row's cumulative change-order features (`max(feature_timestamp)
  <= prediction_timestamp`, checked directly against an injected
  far-future change order).
- Same-day change orders are correctly *included* (the boundary is
  inclusive: `<=`, not `<`).
- Cross-project isolation: one project's change orders never leak into
  another project's rows.
- The first snapshot of any project has no trailing trend (`NaN`, not a
  value borrowed from a later row).
- Feature output is invariant to the input row order (a pipeline that
  depended on input ordering for its as-of logic would be a latent leakage
  risk even if today's tests happened to pass).

`tests/unit/test_pipeline.py` additionally asserts, as a standing
regression guard, that no Work Package/Supplier column and no label column
ever appears in `build_feature_table`'s output.
