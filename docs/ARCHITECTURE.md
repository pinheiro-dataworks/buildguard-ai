# Architecture

How BuildGuard AI is put together, from synthetic data generation to the
deployed app. What the system is required to do is in
[`REQUIREMENTS.md`](REQUIREMENTS.md); why each major choice was made is in
the [ADRs](adr/).

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
| `src/buildguard/data/contracts.py` | Pandera schemas for all six core tables |
| `src/buildguard/data/enums.py` | Controlled vocabularies shared by contracts and the generator |
| `src/buildguard/data/economic_index.py` | `EconomicIndexProvider` interface |
| `src/buildguard/data/synthetic.py` | Deterministic synthetic portfolio generator |
| `src/buildguard/data/labels.py` | Ground-truth `cost_overrun`/`schedule_delay` derivation |
| `src/buildguard/data/split.py` | Chronological, project-grouped train/calibration/test split |
| `src/buildguard/features/evm.py` | Earned Value Management formulas |
| `src/buildguard/features/inflation.py` | Nominal/real cost decomposition |
| `src/buildguard/features/temporal.py` | Lifecycle position and trend/persistence features |
| `src/buildguard/features/pipeline.py` | Leakage-safe feature table assembly |
| `src/buildguard/models/baselines.py` | Mandatory pre-modeling baselines |
| `src/buildguard/models/preprocessing.py` | Shared numeric/categorical preprocessing for every model |
| `src/buildguard/models/classification.py` | Candidate classifiers + Optuna tuning |
| `src/buildguard/models/regression.py` | Candidate regressors + Optuna tuning |
| `src/buildguard/models/tracking.py` | MLflow experiment tracking helpers |
| `src/buildguard/models/calibration.py` | Probability calibration comparison |
| `src/buildguard/models/thresholds.py` | Business-cost threshold optimization + risk bands |
| `src/buildguard/models/uncertainty.py` | Split-conformal prediction intervals |
| `src/buildguard/evaluation/classification.py` | Held-out classification metrics: ROC-AUC, PR-AUC, precision/recall/F1, Brier, confusion matrix |
| `src/buildguard/evaluation/regression.py` | Held-out regression metrics: MAE, RMSE, R2, MAPE/SMAPE, business-terms error |
| `src/buildguard/evaluation/calibration.py` | Out-of-sample calibration check, reusing `models/calibration.py`'s `CalibrationCurve` |
| `src/buildguard/evaluation/slices.py` | Per-subgroup metric evaluation and quantile bucketing |
| `src/buildguard/explainability/shap.py` | Global (SHAP + permutation) and local (SHAP) explanations for the tree-based classifiers |
| `src/buildguard/monitoring/data_quality.py` | Missing values, schema violations, unexpected categories, range violations, duplicate keys |
| `src/buildguard/monitoring/drift.py` | PSI/KS/Wasserstein data and prediction drift detection |
| `src/buildguard/monitoring/performance.py` | Performance-drop comparison (reusing `evaluation`'s metrics) and real inference-latency measurement |
| `src/buildguard/api/app.py` | FastAPI routes: health/version/predict-cost-risk/predict-schedule-risk/predict-final-cost |
| `src/buildguard/api/dependencies.py` | Loads champion models + calibration decisions once, shared across requests |
| `src/buildguard/api/schemas.py` | Pydantic request/response schemas mirroring the raw table shapes |
| `app/theme.py` | Renan-standard color tokens and CSS injection ([`design/UI_DESIGN.md`](design/UI_DESIGN.md)) |
| `app/data_access.py` | Report loading + in-process prediction calls shared by every Streamlit page |
| `app/page_modules/*.py` | One `render()` function per page |

See [ADR-0001](adr/0001-project-architecture.md) for why this layout was
chosen over alternatives.

## 3. Data model

Full column-level reference: [`DATA_DICTIONARY.md`](DATA_DICTIONARY.md).
Every table is validated by `buildguard.data.contracts` before any
downstream code sees it -- a contract violation fails loudly (raises
`DataContractError`), never silently coerces.

## 4. EVM methodology

`src/buildguard/features/evm.py` implements the standard Earned Value
Management formulas as pure, vectorized functions over `pandas.Series`:

| Metric | Formula | Business meaning |
|---|---|---|
| Cost Variance (CV) | `EV - AC` | Favorable (positive) or unfavorable (negative) cost performance to date |
| Schedule Variance (SV) | `EV - PV` | Ahead of / behind schedule, in cost-equivalent terms |
| Cost Performance Index (CPI) | `EV / AC` | Cost efficiency; `< 1` signals an overrun trend |
| Schedule Performance Index (SPI) | `EV / PV` | Schedule efficiency; `< 1` signals a delay trend |
| Estimate at Completion, CPI-based | `BAC / CPI` | Assumes current cost efficiency holds for remaining work |
| Estimate at Completion, composite | `AC + (BAC - EV) / (CPI * SPI)` | A second, more conservative baseline weighing schedule too, so no single formula is over-trusted |
| Estimate to Complete (ETC) | `EAC - AC` | Remaining expected spend |
| Variance at Completion (VAC) | `BAC - EAC` | Expected over/under-run at completion |

Every ratio guards against division by zero: a zero denominator produces
`NaN` (the metric is genuinely undefined, e.g. before any cost has been
incurred), never a silently coerced `0` or `inf`.

## 5. Inflation normalization methodology

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

`inflation_multiplier` is read from an `EconomicIndexProvider`: `DemoIndexProvider` (the only one the public app and generator ever
use) or the unimplemented `ExternalLicensedProvider` placeholder.

**Language rule:** every figure here is an *estimated* inflation-adjusted
value, derived from one illustrative demo index -- reports and UI copy must
say "estimated inflation-adjusted variance," never claim an exact causal
decomposition of why a project's cost moved.

A validated finding from generating the demo portfolio at full scale: the
*nominal* cost-overrun rate among completed projects is ~79%, but the
*inflation-adjusted* rate is ~47% -- confirming this decomposition is not
optional plumbing but a real, material effect on how the primary
classification target should be defined. See
[ADR-0004](adr/0004-synthetic-data-design.md).

## 6. Temporal / lifecycle features

`src/buildguard/features/temporal.py` adds two kinds of signal that a
single snapshot's EVM ratios cannot express on their own:

- **Lifecycle position**: `months_since_start`, `months_to_planned_completion`,
  `lifecycle_fraction` (elapsed / planned duration), and a configurable
  `lifecycle_stage` bucketing (`early` / `mid` / `late`, thresholds in
  `configs/base.yaml: features.lifecycle_*`), which is also one of the
  slice-analysis dimensions.
- **Trend / persistence**: `trailing_change` (period-over-period change
  within a project) and `consecutive_decline_streak` (how many consecutive
  prior months a metric has been getting worse) -- these capture "persistent
  SPI deterioration", which a single point-in-time SPI value
  cannot distinguish from one noisy bad month.

## 7. Leakage-safe feature pipeline and temporal split

`src/buildguard/features/pipeline.py: build_feature_table()` is the single
function that assembles EVM, inflation, and temporal features into one
model-ready table -- shared by training, batch scoring, and the FastAPI service, so features
are computed identically everywhere. Full leakage guarantees and the forbidden-feature list are in
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
calibration (20%) / test (20%, newest), preventing project-level
contamination across splits. Rationale for chronological +
grouped over the alternatives (random split, K-fold, walk-forward) is in
[ADR-0003](adr/0003-temporal-validation.md).

## 8. Baselines

`src/buildguard/models/baselines.py` -- mandatory floors every candidate
model must beat -- and not just the naive statistical one:

| Task | Baseline | Nature |
|---|---|---|
| Classification | `DummyClassifierBaseline` | Uninformative: training class prior, ignores features |
| Classification | `LogisticRegressionBaseline` | Real, simple statistical model |
| Classification | `CpiRuleBaseline` | Domain rule: `CPI < 0.90 -> High Cost Risk` |
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
exactly why the bar is a meaningful construction-management baseline, not
only a naive statistical one: on this data, a domain-informed formula is a
genuinely strong baseline, and the advanced models have real work to do to
clear it, not just an easy strawman. (These first baseline numbers were
scored on the test split; see
[`LIMITATIONS.md`](LIMITATIONS.md#11-the-test-split-was-seen-once-before-the-final-evaluation).)

## 9. Advanced modeling

`scripts/train.py` (`make train`) trains and selects the champion for each
of the three core tasks: `RandomForestClassifier`/`RandomForestRegressor`
and LightGBM (`src/buildguard/models/classification.py`, `regression.py`),
tuned with Optuna (`GroupKFold` on `project_id`, train split only), then
compared against the baselines on the **calibration** split
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
the same deterministic EVM formula baseline from the section above -- not
a bug, a reproducible finding confirmed at both baseline-validation scale
and at full scale with proper hyperparameter tuning.
`final_cost`'s shipped "champion" is honestly a formula, not a fitted
model, and every downstream document (model card, UI copy) must say so.
Full trade-off discussion (interpretability, latency, why LightGBM over
XGBoost/CatBoost) in [ADR-0006](adr/0006-model-selection.md).

## 10. Calibration, threshold, and uncertainty

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
  implement -- the same class of problem hit earlier with MLflow's model
  logging. Full rationale: [ADR-0007](adr/0007-calibration-strategy.md).
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
(the calibration split exists for exactly this fitting). Genuinely
held-out performance is confirmed at the one final test evaluation --
see the next section.

## 11. Explainability, held-out evaluation, and failure analysis

`scripts/evaluate.py` (`make evaluate`) is the one moment the **test**
split gets used, applying every decision already frozen on the
calibration split (threshold, calibration method, conformal quantile)
unchanged, to data none of them ever saw:

- **Explainability** (`src/buildguard/explainability/shap.py`): SHAP
  `TreeExplainer` with `model_output="probability"` and an explicit
  background sample, unifying `RandomForestClassifier` (natively
  probability-space SHAP) and LightGBM (natively log-odds-space) into the
  same additive identity `base_value + shap_values.sum() == predicted_probability`
  for both model families. Global explanations report both mean |SHAP
  value| and permutation importance (they are computed over different
  feature spaces -- encoded vs. original -- and can disagree, so both are
  kept rather than forced into one number). `final_cost`'s champion is a
  formula (`BAC / CPI`, ADR-0006), not a fitted model -- explanations
  don't apply; the formula is the explanation. Every explanation-bearing
  surface carries the mandatory disclaimer: *"Feature attribution explains
  the model prediction; it does not establish causality."*
- **Held-out metrics** (`src/buildguard/evaluation/classification.py`,
  `regression.py`, `calibration.py`): the full metric battery, scored on
  test. **Real results:** `cost_overrun` ROC-AUC 0.9495 / PR-AUC
  0.9008 / recall 97.4% at the frozen 0.080 threshold; `schedule_delay`
  ROC-AUC 0.9002 / recall 92.9% at 0.140; `final_cost` MAE $1.61M / RMSE
  $3.03M / R2 0.959 / MAPE 7.0%, conformal coverage 0.899 against an 0.80
  target (conservative -- wider than strictly required).
- **Slice evaluation** (`src/buildguard/evaluation/slices.py`): the six
  required dimensions plus an inflation-regime dimension answering "does
  the inflation regime change performance?" directly. **Real finding:**
  `cost_overrun`'s global AUC (0.9495) hides a materially weaker subgroup
  -- the `ES` state slice scores AUC 0.597 (n=76), close to random. This
  is exactly the "high global metric, poor subgroup behavior" case that
  has to be surfaced rather than hidden.
- **Failure analysis** (`reports/error_analysis/*.md`): generated
  directly from the same computed arrays as
  `reports/experiments/test_set_metrics.json` -- worst
  false negatives/positives with their top SHAP drivers, near-threshold
  and out-of-distribution rows, hardest subgroups, and (for `final_cost`)
  largest errors and systematic bias by subgroup. **Real finding:**
  `schedule_delay`'s isotonic calibration, which won in-sample (Brier
  0.059, ADR-0007), degrades to 0.145 out-of-sample -- a genuine
  generalization gap, not a bug.

Full design rationale, both findings above, and every alternative
considered: [ADR-0010](adr/0010-evaluation-explainability-design.md).

## 12. Monitoring and retraining policy

`scripts/monitor.py` (`make monitor`) is the second and last script to run
after training/calibration/evaluation -- it implements every monitoring
signal against the real portfolio and real champions rather than just
documenting a plan:

- **Data quality** (`src/buildguard/monitoring/data_quality.py`): missing
  values, schema violations (reusing `buildguard.data.contracts`, never
  re-implemented), unexpected categories, range violations, duplicate
  keys. **Real result:** 0 violations across Projects/Snapshots/Change
  Orders (400/11,953/897 rows).
- **Data & prediction drift** (`src/buildguard/monitoring/drift.py`): PSI
  for every variable type, KS test + Wasserstein distance for numeric
  only. Feature drift compares the **train** vs. **test** split;
  prediction drift compares the **calibration** vs. **test** split.
  **Real result:** 10 of 23 features significantly drifted (dominated by
  `inflation_multiplier` and `months_since_start`) -- the expected
  signature of the chronological split itself, not a data defect (see
  ADR-0011 for why); prediction-drift and risk-band proportions stayed
  stable for both classifiers even where performance did not (below).
- **Performance monitoring** (`src/buildguard/monitoring/performance.py`):
  reuses `buildguard.evaluation`'s metrics, comparing each task's
  calibration-split baseline against its held-out test-split result. **Real result:** `schedule_delay` degraded on all three tracked
  metrics (ROC-AUC 0.974 -> 0.900, recall 0.984 -> 0.929, Brier 0.059 ->
  0.145) despite negligible prediction drift -- caught only because
  performance monitoring is label-dependent and drift detection is not.
- **Operational monitoring**: real (not simulated) inference latency,
  timing actual `predict`/`predict_proba` calls. **Real result:** p95
  37.2ms / 11.3ms / 0.06ms for cost-overrun / schedule-delay / final-cost,
  all comfortably under the 500ms target (wall-clock figures, so they vary
  with the machine that runs `make monitor`). Request volume/error rate stay
  inert: the app predicts in-process and the API keeps no request log.
- **Risk bands** (`models/thresholds.risk_band()`): "low" below the
  optimized decision threshold, the flagged zone above it split at its
  own midpoint into "medium"/"high" -- a reporting convenience, not a
  second business-cost decision.
- **Retraining triggers**: PSI-above-critical,
  performance-drop, calibration-deterioration, and schema-changes are
  computed for real against this run's signals; new-labeled-data-volume
  and scheduled-quarterly-evaluation are calendar/volume-driven policy,
  documented rather than computed. **The script only flags -- it never
  retrains**; enforced structurally, not just by convention.

Full rationale, every alternative considered, and the complete real-results
snapshot: [ADR-0011](adr/0011-monitoring-drift-detection.md) and
[`docs/MONITORING.md`](MONITORING.md).

## 13. API and Streamlit app

**FastAPI service** (`src/buildguard/api/`): `GET /health`, `GET /version`,
`POST /predict/{cost-risk,schedule-risk,final-cost}`. Every prediction
endpoint is a plain, dependency-injected function
(`app.py`) -- `dependencies.py`'s `get_service_state()` loads the three
champion artifacts and calibration decisions once (`lru_cache`d, not
per-request); `schemas.py`'s `PredictionRequest` mirrors the raw
Project/Snapshot/Change-Order table shapes rather than a bespoke shape, so
a caller sends a project's real snapshot history and the endpoint rebuilds
its feature row through the exact same `build_feature_table` training
uses. Validated twice -- Pydantic (types/ranges/enums) then
`buildguard.data.contracts` (cross-field checks Pydantic can't express) --
both failing safely as a 422, never a crash. 15 contract
tests (`tests/api/test_inference_service.py`) run against the real
trained/calibrated champions, not mocks.

**Streamlit app** (`app/`): six pages (Executive Overview, Project
Diagnostic, Scenario Simulator, Model Performance, Model Health, About/
Governance) under `app/page_modules/` (not the conventional
`pages/` -- see ADR-0012 for why that name conflicts with Streamlit's own
auto-discovery). Predictions are made **in-process** by calling the
FastAPI endpoint functions directly -- one prediction code
path, called two ways, never two implementations. The sidebar (logo,
project name, bordered nav buttons, version/GitHub footer) is a custom
`st.session_state` router styled to [`design/UI_DESIGN.md`](design/UI_DESIGN.md)'s
renan-standard tokens (`app/theme.py`), chosen over `st.navigation()`
after empirically hitting a fixed-position constraint that would have put
the nav above the logo. The Executive Overview page batch-scores the
whole portfolio in one vectorized pass (same feature pipeline, same
champions) rather than 400 individual single-prediction calls. Verified
with a real headless-browser pass (Playwright) across all six pages, not
just import-level smoke tests -- caught two real bugs `ruff`/`mypy`
couldn't (see ADR-0012).

Full rationale and every alternative considered:
[ADR-0012](adr/0012-streamlit-fastapi-boundary.md).

## 14. Testing, CI/CD, and documentation

**Integration tests** (`tests/integration/test_pipeline_integration.py`):
the real pipeline end to end -- raw `data/sample/` CSVs -> contract
validation -> `build_feature_table` -> the actual trained champions --
rather than each stage tested only in isolation.

**CI** (`.github/workflows/ci.yml`): two parallel jobs, `quality`
(`ruff check`, `ruff format --check`, `mypy src`) and `test` (`make
train && make calibrate`, then the full suite with an 85% coverage gate). **Security**
(`security.yml`): `pip-audit` and `bandit`, weekly plus every push/PR,
with no ignored vulnerabilities. New advisories against locked
dependencies are fixed by upgrading them in `uv.lock`.

**Documentation set:** [`REQUIREMENTS.md`](REQUIREMENTS.md),
[`DATA_DICTIONARY.md`](DATA_DICTIONARY.md), [`DATA_PRIVACY.md`](DATA_PRIVACY.md),
[`LEAKAGE_POLICY.md`](LEAKAGE_POLICY.md), [`MODEL_CARD.md`](MODEL_CARD.md),
[`MONITORING.md`](MONITORING.md), [`LIMITATIONS.md`](LIMITATIONS.md),
[`RUNBOOK.md`](RUNBOOK.md), [`design/UI_DESIGN.md`](design/UI_DESIGN.md),
and thirteen ADRs under [`adr/`](adr/).

## 15. Deployment

**Public app:** Streamlit Community Cloud, deployed straight from `main`
with the committed champion artifacts, at
<https://buildguard-ai-renands.streamlit.app/>
([ADR-0013](adr/0013-zero-cost-deployment.md); deployment steps and the
live smoke test are in [`RUNBOOK.md`](RUNBOOK.md#3-deployment-streamlit-community-cloud)).

**Container image:** the `Dockerfile` (`make docker-build`,
`make docker-run`) installs from `uv.lock`, trains and calibrates the
champions inside the build, and runs the Streamlit app as a non-root user
with a health check. It is an optional, portable path, not part of the
public deployment, and has not yet been validated with a real
`docker build`.
