# Architecture

Living document -- expanded as each phase of `BUILDGUARD_AI_PROJECT_SCOPE.md`
lands. This version covers the data, domain-analytics, and anti-leakage
layers (Phases 0-3); modeling, API, UI, and monitoring sections are added
as those phases are built (see
[`BUILDGUARD_AI_COMMIT_PLAN.md`](../BUILDGUARD_AI_COMMIT_PLAN.md) for
what's done vs. planned).

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
        +--------------------------+
        v                          v
src/buildguard/features/       src/buildguard/data/split.py
  pipeline.py (+ evm,           (chronological, project-grouped
  inflation, temporal)           train/calibration/test)
  --leakage-safe-->
  feature table                 src/buildguard/data/labels.py
                                 --derives-->  cost_overrun /
                                               schedule_delay
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
| `src/buildguard/data/labels.py` | Ground-truth `cost_overrun`/`schedule_delay` derivation (Section 6/11) |
| `src/buildguard/data/split.py` | Chronological, project-grouped train/calibration/test split (Section 12) |
| `src/buildguard/features/evm.py` | Earned Value Management formulas (Section 9) |
| `src/buildguard/features/inflation.py` | Nominal/real cost decomposition (Section 10) |
| `src/buildguard/features/temporal.py` | Lifecycle position and trend/persistence features |
| `src/buildguard/features/pipeline.py` | Leakage-safe feature table assembly (Section 11/28) |
| `src/buildguard/models/baselines.py` | Mandatory pre-modeling baselines (Section 13) |
| `src/buildguard/models/preprocessing.py` | Shared numeric/categorical preprocessing for every model |
| `src/buildguard/models/classification.py` | Candidate classifiers + Optuna tuning (Section 14/15) |
| `src/buildguard/models/regression.py` | Candidate regressors + Optuna tuning (Section 14/15) |
| `src/buildguard/models/tracking.py` | MLflow experiment tracking helpers (Section 25) |
| `src/buildguard/models/calibration.py` | Probability calibration comparison (Section 16) |
| `src/buildguard/models/thresholds.py` | Business-cost threshold optimization (Section 17) |
| `src/buildguard/models/uncertainty.py` | Split-conformal prediction intervals (Section 19) |

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

## 7. Leakage-safe feature pipeline and temporal split (Section 11 / 12)

`src/buildguard/features/pipeline.py: build_feature_table()` is the single
function that assembles EVM, inflation, and temporal features into one
model-ready table -- shared by training, batch scoring, and (Phase 8) the
FastAPI service, so features are computed identically everywhere (Section
28). Full leakage guarantees and the forbidden-feature list are in
[`LEAKAGE_POLICY.md`](LEAKAGE_POLICY.md); in short, every feature's
availability timestamp is enforced `<= snapshot_date` (that row's
prediction timestamp), change orders are joined with a `merge_asof`
as-of join that cannot see future rows, and Work Packages/Suppliers are
excluded entirely rather than included unsafely (both tables only carry
"as of latest snapshot" status, not per-date history).

`src/buildguard/data/labels.py: resolve_outcomes()` derives
`cost_overrun`/`schedule_delay` ground truth from the snapshot history --
against the **inflation-adjusted (real)** final cost, not raw nominal
`actual_cost` (see [ADR-0004](adr/0004-synthetic-data-design.md)'s
nominal-vs-real overrun-rate finding for why). In-flight projects get no
resolved label (`pd.NA`), never a coerced negative.

`src/buildguard/data/split.py: chronological_project_split()` assigns
whole projects (never individual snapshot rows) to train (60%, oldest) /
calibration (20%) / test (20%, newest), preventing the project-level
contamination Section 12 warns about. Rationale for chronological +
grouped over the alternatives (random split, K-fold, walk-forward) is in
[ADR-0003](adr/0003-temporal-validation.md).

## 8. Baselines (Section 13)

`src/buildguard/models/baselines.py` -- mandatory floors every model
trained later (Session H) must beat, not just a naive statistical one:

| Task | Baseline | Nature |
|---|---|---|
| Classification | `DummyClassifierBaseline` | Uninformative: training class prior, ignores features |
| Classification | `LogisticRegressionBaseline` | Real, simple statistical model |
| Classification | `CpiRuleBaseline` | Domain rule (Section 13's own example: `CPI < 0.90 -> High Cost Risk`) |
| Regression | `MeanRegressionBaseline` / `MedianRegressionBaseline` | Uninformative: training constant, ignores features |
| Regression | `DeterministicEacBaseline` | Domain formula: the EVM CPI-based EAC already on each row, zero-parameter |
| Regression | `LinearRegressionBaseline` | Real, simple statistical model |

All six share the feature table from `build_feature_table` -- a
baseline-vs-model comparison is never confounded by different inputs.

**A validated finding, not a guess:** evaluated end-to-end on the full
synthetic portfolio (chronological test split), `DeterministicEacBaseline`
reaches ~1.6M MAE on final cost, while `LinearRegressionBaseline` -- a real
fitted statistical model -- only reaches ~3.8M MAE (both far ahead of
`MeanRegressionBaseline`'s ~11.1M). On the classification side,
`CpiRuleBaseline` alone reaches ~0.83 AUC against `LogisticRegressionBaseline`'s
~0.93 (`DummyClassifierBaseline` sits at exactly 0.5, as it must). This is
exactly the point of Section 13's "beat a meaningful construction-management
baseline, not only a naive statistical one" requirement: on this data, a
domain-informed formula is a genuinely strong baseline, and Session H's
advanced models have real work to do to clear it, not just an easy
strawman.

## 9. Advanced modeling (Section 14/15/25)

`scripts/train.py` (`make train`) trains and selects the champion for each
of the three core tasks: `RandomForestClassifier`/`RandomForestRegressor`
and LightGBM (`src/buildguard/models/classification.py`, `regression.py`),
tuned with Optuna (`GroupKFold` on `project_id`, train split only), then
compared against the Section 13 baselines on the **calibration** split
(test stays untouched). Every candidate is logged as one MLflow run
(`src/buildguard/models/tracking.py`, SQLite-backed local tracking,
`sqlite:///mlruns/mlflow.db`); the champion's fitted pipeline is attached
as a run artifact and saved to `models/*_champion.joblib`.

**Results at full scale** (400 projects, calibration split):

| Task | Metric | Champion | Score | Best baseline |
|---|---|---|---|---|
| `cost_overrun` | ROC-AUC | Random Forest | 0.898 | 0.888 (logistic regression) |
| `schedule_delay` | ROC-AUC | LightGBM | 0.974 | 0.816 (logistic regression) |
| `final_cost` | MAE ($) | **Deterministic EAC (baseline)** | 1.96M | 4.11M (tuned LightGBM) |

Two tasks are won by real, tuned ML models. The third is won decisively by
the same deterministic EVM formula baseline from Section 8 -- not a bug,
a reproducible finding confirmed at both baseline-validation scale
(Session G) and here at full scale with proper hyperparameter tuning.
`final_cost`'s shipped "champion" is honestly a formula, not a fitted
model, and every downstream document (model card, UI copy) must say so.
Full trade-off discussion (interpretability, latency, why LightGBM over
XGBoost/CatBoost) in [ADR-0006](adr/0006-model-selection.md).

## 10. Calibration, threshold, and uncertainty (Section 16/17/19)

`scripts/calibrate.py` (`make calibrate`) is the post-training pass: it
loads the champions saved by `scripts/train.py`, and on the
**calibration** split only (test stays untouched):

- **Calibration** (`src/buildguard/models/calibration.py`): compares raw
  vs. sigmoid vs. isotonic calibration by Brier score. Isotonic won both
  classification tasks -- `cost_overrun` 0.133 -> 0.122, `schedule_delay`
  0.072 -> 0.059 -- and the calibrated model replaces the raw champion as
  the saved artifact. Fit directly on `(raw_probability, label)` pairs
  (Platt scaling via a one-feature `LogisticRegression`, isotonic via
  `IsotonicRegression`) rather than through
  `CalibratedClassifierCV`/`FrozenEstimator`, which requires a full
  sklearn estimator interface that BuildGuard's own baselines don't
  implement -- the same class of problem hit with MLflow's model logging
  in Session H. Full rationale: [ADR-0007](adr/0007-calibration-strategy.md).
- **Threshold optimization** (`src/buildguard/models/thresholds.py`):
  sweeps 199 candidate thresholds against `configs/business.yaml`'s
  asymmetric cost matrix (a missed real overrun/delay costs 10x/8x a
  false alarm). Both tasks land well below the forbidden 0.50 default --
  `cost_overrun` at 0.080 (98% recall, 68% precision), `schedule_delay`
  at 0.140 (98% recall, 86% precision). Full rationale:
  [ADR-0008](adr/0008-threshold-policy.md).
- **Uncertainty** (`src/buildguard/models/uncertainty.py`): split
  conformal prediction around `final_cost`'s point forecast -- model-
  agnostic, so it works around a formula baseline exactly as it would
  around a fitted regressor. At 80% target coverage: quantile
  $3.09M (interval width $6.17M), empirical coverage 0.801 -- confirms
  the implementation is statistically correct. Full rationale:
  [ADR-0009](adr/0009-uncertainty-method.md).

**Known limitation, stated plainly:** all of the above is measured
in-sample, on the same calibration-split rows used to fit the mapping
(Section 12's CALIBRATION block is exactly where this fitting happens).
Genuinely held-out performance is confirmed only at the one final test
evaluation, a later phase.

## 11. What's not built yet

Explainability, monitoring, the FastAPI service, and the Streamlit app are
all still pending -- see
[`BUILDGUARD_AI_COMMIT_PLAN.md`](../BUILDGUARD_AI_COMMIT_PLAN.md) for the
session-by-session plan and [`BUILDGUARD_AI_PROJECT_SCOPE.md`](../BUILDGUARD_AI_PROJECT_SCOPE.md)
Section 45 for the full roadmap. This document will grow a section for
each as it lands.
