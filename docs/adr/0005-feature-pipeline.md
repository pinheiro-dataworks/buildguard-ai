# ADR-0005: Leakage-Safe Feature Pipeline Design

**Status:** Accepted

## Context

Section 11 requires that a model predicting risk at month `t` may only use
information available on or before `t`, and requires an automated test
proving it. Section 28 requires the *same* feature logic for training and
inference (no train/serve skew). `src/buildguard/features/pipeline.py`
(built in Session F, alongside the temporal split and labels) is the one
function meeting both requirements at once -- this ADR was not written at
the time and is added retroactively now, during Session I, to complete the
minimum ADR set (Section 39).

## Decision

`build_feature_table(projects, snapshots, change_orders, index_provider,
features_config)` produces one output row per input snapshot row, where
that row's `snapshot_date` **is** its prediction timestamp:

- **EVM ratios and inflation features** (`evm.py`, `inflation.py`) are
  computed from that row's own `earned_value`/`actual_cost`/`planned_cost`
  -- already point-in-time by construction, since a snapshot only ever
  reflects cumulative-to-date reality (ADR-0004).
- **Temporal trend/streak features** (`temporal.py`) look backward within
  a project's own chronological history up to and including the current
  row, never ahead.
- **Change-order cumulative features** are joined with
  `pandas.merge_asof(..., direction="backward")` -- an as-of join that
  structurally cannot see a change order dated after the snapshot, rather
  than a filter that could be gotten wrong by a future edit.
- **Work Packages and Suppliers are excluded entirely.** Both tables
  represent status "as of the project's last snapshot"
  (`DATA_DICTIONARY.md`), not a genuine per-date time series -- joining
  them naively would leak each project's final-snapshot state into every
  earlier prediction point. Excluding them outright (rather than including
  them and hoping no one trains on the leaky columns) was chosen over the
  alternative of giving those tables real per-row dates, which would be a
  schema change out of scope for this phase.
- **Labels are never joined into this table.** `buildguard.data.labels` is
  a separate module that nothing under `features/` imports from -- this
  makes "a target-derived value ends up in the features" structurally
  impossible, not just discouraged by convention.

Full column-by-column availability-timestamp reasoning, the forbidden
feature list, and the automated leakage tests that enforce all of this are
in [`docs/LEAKAGE_POLICY.md`](../LEAKAGE_POLICY.md) and
`tests/leakage/test_pipeline_leakage.py`.

## Alternatives Considered

- **A per-task feature function** (one for `cost_overrun`, one for
  `schedule_delay`, one for `final_cost`) -- rejected: all three tasks
  need the same point-in-time features; the only difference is which
  label gets joined afterward by the caller. A single shared function is
  both less code and removes any chance of the three tasks silently
  drifting apart in what "as of `t`" means.
- **Filtering change orders with a plain boolean mask
  (`date <= snapshot_date`) inside a per-row loop** instead of
  `merge_asof` -- rejected: `merge_asof` is the standard, well-tested
  pandas primitive for exactly this "as-of" join pattern, is vectorized
  (fast at portfolio scale), and its `direction="backward"` semantics
  make the leakage guarantee a property of the join itself rather than of
  correctly writing a comparison in a loop body every time.
- **Include Work Packages/Suppliers with a caveat comment** -- rejected
  outright per Section 56 ("never ... use future data in features"); a
  comment is not a control, and the leakage would be real regardless of
  how well it was documented.

## Consequences

- Any new time-varying feature added later must go through this same
  function (or an equally leakage-safe successor), not be joined ad hoc in
  a training script -- `scripts/train.py` and `scripts/calibrate.py`
  already both depend on this as the single source of features.
- The Work Packages/Suppliers exclusion is a real, acknowledged capability
  gap (e.g. no supplier-concentration risk signal reaches the models yet),
  tracked as a documented limitation rather than a silent omission.
- `tests/leakage/test_pipeline_leakage.py` is the concrete enforcement
  mechanism for this ADR -- if it ever needs updating to make a new
  feature pass, that is itself a signal the new feature needs scrutiny.
