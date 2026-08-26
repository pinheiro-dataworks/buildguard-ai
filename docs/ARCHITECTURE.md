# Architecture

Living document -- expanded as each phase of `BUILDGUARD_AI_PROJECT_SCOPE.md`
lands. This version covers the data and domain-analytics layers (Phases
0-2); modeling, API, UI, and monitoring sections are added as those phases
are built (see [`BUILDGUARD_AI_COMMIT_PLAN.md`](../BUILDGUARD_AI_COMMIT_PLAN.md)
for what's done vs. planned).

## 1. System overview

```
configs/*.yaml (typed via src/buildguard/config.py)
        |
        v
src/buildguard/data/synthetic.py  --generates-->  six core tables
        |  (uses)                                  (Projects, Snapshots,
        v                                           Work Packages, Change
src/buildguard/data/economic_index.py              Orders, Suppliers,
  (EconomicIndexProvider / DemoIndexProvider)       Economic Index)
        |
        v
src/buildguard/data/contracts.py  --validates-->  every table, every time
        |
        v
src/buildguard/features/{evm,inflation,temporal}.py  --derive-->  features
```

`scripts/generate_data.py` (`make data`) is the only entry point that
writes files to disk (`data/processed/` full, `data/sample/` committed
subset) -- everything upstream of it is pure, seeded, in-memory
computation, so the whole chain is independently unit-testable without I/O.

## 2. Package layout

| Path | Responsibility |
|---|---|
| `src/buildguard/config.py` | Typed loading/validation of `configs/*.yaml` (Pydantic) |
| `src/buildguard/data/contracts.py` | Pandera schemas for all six core tables (Section 8.4/8.5) |
| `src/buildguard/data/enums.py` | Controlled vocabularies shared by contracts and the generator |
| `src/buildguard/data/economic_index.py` | `EconomicIndexProvider` interface (Section 8.3) |
| `src/buildguard/data/synthetic.py` | Deterministic synthetic portfolio generator (Section 8.2) |
| `src/buildguard/features/evm.py` | Earned Value Management formulas (Section 9) |
| `src/buildguard/features/inflation.py` | Nominal/real cost decomposition (Section 10) |
| `src/buildguard/features/temporal.py` | Lifecycle position and trend/persistence features |

See [ADR-0001](adr/0001-project-architecture.md) for why this layout was
chosen over alternatives.

## 3. Data model

Full column-level reference: [`DATA_DICTIONARY.md`](DATA_DICTIONARY.md).
Every table is validated by `buildguard.data.contracts` before any
downstream code sees it -- a contract violation fails loudly (raises
`DataContractError`), never silently coerces.

## 4. EVM methodology (Section 9)

`src/buildguard/features/evm.py` implements the standard Earned Value
Management formulas as pure, vectorized functions over `pandas.Series`:

| Metric | Formula | Business meaning |
|---|---|---|
| Cost Variance (CV) | `EV - AC` | Favorable (positive) or unfavorable (negative) cost performance to date |
| Schedule Variance (SV) | `EV - PV` | Ahead of / behind schedule, in cost-equivalent terms |
| Cost Performance Index (CPI) | `EV / AC` | Cost efficiency; `< 1` signals an overrun trend |
| Schedule Performance Index (SPI) | `EV / PV` | Schedule efficiency; `< 1` signals a delay trend |
| Estimate at Completion, CPI-based | `BAC / CPI` | Assumes current cost efficiency holds for remaining work |
| Estimate at Completion, composite | `AC + (BAC - EV) / (CPI * SPI)` | A second, more conservative baseline weighing schedule too (Section 9 requires >= 2 baselines) |
| Estimate to Complete (ETC) | `EAC - AC` | Remaining expected spend |
| Variance at Completion (VAC) | `BAC - EAC` | Expected over/under-run at completion |

Every ratio guards against division by zero: a zero denominator produces
`NaN` (the metric is genuinely undefined, e.g. before any cost has been
incurred), never a silently coerced `0` or `inf`.

## 5. Inflation normalization methodology (Section 10)

`actual_cost` on Project Snapshots is **nominal** by construction (it
compounds with a demo construction-cost index over the project's life);
`approved_budget` and `planned_cost` are expressed in original-approval
("real") terms. Comparing them directly conflates market/inflation effects
with execution performance -- `src/buildguard/features/inflation.py`
decomposes the gap:

```
nominal_cost_variance = operational_variance + inflation_component

  nominal_cost_variance = EV - actual_cost                (evm.cost_variance)
  real_actual_cost       = actual_cost / inflation_multiplier
  operational_variance   = EV - real_actual_cost           (execution-only)
  inflation_component    = real_actual_cost - actual_cost  (price-growth drag)
```

`inflation_multiplier` is read from an `EconomicIndexProvider` (Section
8.3): `DemoIndexProvider` (the only one the public app and generator ever
use) or the unimplemented `ExternalLicensedProvider` placeholder.

**Language rule:** every figure here is an *estimated* inflation-adjusted
value, derived from one illustrative demo index -- reports and UI copy must
say "estimated inflation-adjusted variance," never claim an exact causal
decomposition of why a project's cost moved.

A validated finding from generating the demo portfolio at full scale: the
*nominal* cost-overrun rate among completed projects is ~79%, but the
*inflation-adjusted* rate is ~47% -- confirming this decomposition is not
optional plumbing but a real, material effect on how the primary
classification target (Section 6.1) should be defined. See
[ADR-0004](adr/0004-synthetic-data-design.md).

## 6. Temporal / lifecycle features

`src/buildguard/features/temporal.py` adds two kinds of signal that a
single snapshot's EVM ratios cannot express on their own:

- **Lifecycle position**: `months_since_start`, `months_to_planned_completion`,
  `lifecycle_fraction` (elapsed / planned duration), and a configurable
  `lifecycle_stage` bucketing (`early` / `mid` / `late`, thresholds in
  `configs/base.yaml: features.lifecycle_*`) -- Section 18 requires
  lifecycle stage as a slice-analysis dimension.
- **Trend / persistence**: `trailing_change` (period-over-period change
  within a project) and `consecutive_decline_streak` (how many consecutive
  prior months a metric has been getting worse) -- these capture "persistent
  SPI deterioration" (Section 8.2), which a single point-in-time SPI value
  cannot distinguish from one noisy bad month.

## 7. What's not built yet

Anti-leakage temporal split, baselines, the three core ML models,
calibration/threshold/uncertainty, explainability, monitoring, the FastAPI
service, and the Streamlit app are all still pending -- see
[`BUILDGUARD_AI_COMMIT_PLAN.md`](../BUILDGUARD_AI_COMMIT_PLAN.md) for the
session-by-session plan and [`BUILDGUARD_AI_PROJECT_SCOPE.md`](../BUILDGUARD_AI_PROJECT_SCOPE.md)
Section 45 for the full roadmap. This document will grow a section for
each as it lands.
