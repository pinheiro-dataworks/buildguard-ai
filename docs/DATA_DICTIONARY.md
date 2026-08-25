# Data Dictionary

Describes the six core tables of the BuildGuard AI data model (Section 8.4
of `BUILDGUARD_AI_PROJECT_SCOPE.md`). Every column and constraint here is
enforced in code by `src/buildguard/data/contracts.py`
(`buildguard.data.contracts`) -- if this document and the code ever
disagree, the code (and its tests) is authoritative; file an issue.

All tables are produced by `src/buildguard/data/synthetic.py`
(`make data`) -- see [`docs/adr/0004-synthetic-data-design.md`](adr/0004-synthetic-data-design.md)
for how realism is encoded, and [`docs/DATA_PRIVACY.md`](DATA_PRIVACY.md)
for why the data is entirely synthetic.

## Projects

One row per project. `project_id` is the primary key.

| Column | Type | Constraint | Meaning |
|---|---|---|---|
| `project_id` | string | unique, not null | Stable project identifier, e.g. `PRJ-0001` |
| `project_type` | categorical | one of `residential, commercial, industrial, infrastructure, mixed_use` | Primary use of the built asset |
| `city` / `state` | string | not null | Project location |
| `gross_floor_area_m2` | float | `> 0` | Total constructed area |
| `number_of_towers` | int | `>= 1` | Physical building count |
| `number_of_units` | int | `>= 0` | Sellable/leasable units (0 for non-residential) |
| `construction_standard` | categorical | one of `economy, standard, high_standard, luxury` | Cost/finish tier, drives cost-per-m2 |
| `planned_start_date` | date | not null | Contractual start |
| `planned_completion_date` | date | `>` `planned_start_date` | Contractual finish |
| `approved_budget` | float | `> 0` | Budget at Completion (BAC), in original-approval (real) terms |

No `actual_completion_date` or `final_cost` column exists -- both are
*derived* from Project Snapshots (see below), never stored redundantly.

## Project Snapshots

One row per project per month observed. `(project_id, snapshot_date)` is
unique. This is the EVM time series (Section 9) that everything else
(features, labels, models) is built on.

| Column | Type | Constraint | Meaning |
|---|---|---|---|
| `project_id` | string | not null, FK -> Projects | |
| `snapshot_date` | date | not null | Month-end reporting date |
| `planned_progress` | float | `[0, 1]` | Cumulative % complete per the original plan (plateaus at 1.0 after the planned finish date) |
| `actual_progress` | float | `[0, 1]` | Cumulative % complete actually achieved |
| `planned_cost` | float | `>= 0` | Planned Value, `PV = BAC x planned_progress` |
| `actual_cost` | float | `>= 0` | Actual Cost (AC), **nominal** (includes inflation since project start) |
| `committed_cost` | float | `>= 0` | AC plus obligations issued but not yet invoiced |
| `earned_value` | float | `>= 0` | Earned Value, `EV = BAC x actual_progress` |
| `forecast_cost` | float | `>= 0` | Estimate at Completion (CPI-based baseline, `EAC = BAC / CPI`) |

A project's completion status is read off this table, not stored
separately: the last snapshot with `actual_progress == 1.0` is the
project's actual completion (that row's `snapshot_date` is the actual
completion date, its `actual_cost` is the final cost). A project whose last
available snapshot has `actual_progress < 1.0` is still in-flight as of the
dataset's reference date and has no resolved outcome label yet.

`actual_cost` is nominal, while `approved_budget` (Projects) and
`planned_cost` are expressed in original-approval terms -- comparing them
directly conflates inflation with execution performance. See
[ADR-0004](adr/0004-synthetic-data-design.md) and Section 10 (inflation
normalization) before using either as a raw model target.

## Work Packages

One row per work package per project, reflecting status as of the
project's most recent snapshot (no independent time series).
`(project_id, work_package_id)` is unique.

| Column | Type | Constraint | Meaning |
|---|---|---|---|
| `project_id` | string | not null, FK -> Projects | |
| `work_package_id` | string | not null | e.g. `WP-001` |
| `work_package_name` | string | not null | e.g. `Foundations`, `Electrical` |
| `budget` | float | `> 0` | Allocated share of `approved_budget` |
| `actual_cost` | float | `>= 0` | Cost incurred on this package |
| `planned_progress` / `actual_progress` | float | `[0, 1]` | Package-level progress, correlated with the parent project's overall progress |

## Change Orders

One row per change order. `change_order_id` is the primary key.

| Column | Type | Constraint | Meaning |
|---|---|---|---|
| `change_order_id` | string | unique, not null | e.g. `CO-00001` |
| `project_id` | string | not null, FK -> Projects | |
| `date` | date | not null | Effective month |
| `category` | categorical | one of `scope_change, design_error, site_condition, regulatory, client_request, other` | |
| `approved_amount` | float | not null (may be 0) | Additional cost; 0 unless `status == approved` |
| `status` | categorical | one of `pending, approved, rejected` | |

Approved change-order amounts are already folded into `actual_cost` on any
Project Snapshot dated on/after the change order's `date`.

## Suppliers

One row per supplier *engagement* with a project -- the same physical
supplier (`supplier_id`) can appear against multiple projects, by design
(supplier concentration is one of the required realism signals, Section
8.2). `(supplier_id, project_id)` is unique.

| Column | Type | Constraint | Meaning |
|---|---|---|---|
| `supplier_id` | string | not null | Shared across projects, e.g. `SUP-0042` |
| `supplier_category` | categorical | one of `structural, mep, finishes, earthworks, facade, general_contractor, other` | |
| `project_id` | string | not null, FK -> Projects | |
| `contract_value` | float | `>= 0` | |
| `delivery_delay_days` | int | not null (may be negative = early) | |
| `quality_score` | float | `[0, 10]` | |
| `rework_cost` | float | `>= 0` | Cost attributable to this supplier's rework |

## Economic Index

One row per `(reference_month, index_name)` -- a demo, illustrative
construction-cost inflation index (never a real published index; see
[`docs/DATA_PRIVACY.md`](DATA_PRIVACY.md) Section 6).

| Column | Type | Constraint | Meaning |
|---|---|---|---|
| `reference_month` | date | not null | Month-end |
| `index_name` | string | not null | `INCC-DEMO` (illustrative, not the real INCC) |
| `index_value` | float | `> 0` | Base 100 at the start of the generated window, non-decreasing |
