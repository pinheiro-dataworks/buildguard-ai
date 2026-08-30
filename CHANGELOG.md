# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Repository foundation: full project layout, `pyproject.toml` (uv-managed,
  Ruff + Mypy strict + Pytest configured), `Makefile`, governance files
  (`LICENSE`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`),
  GitHub issue/PR templates, `.pre-commit-config.yaml`.
- Project scope and engineering charter
  (`BUILDGUARD_AI_PROJECT_SCOPE.md`).
- Data privacy policy (`docs/DATA_PRIVACY.md`) and the first two ADRs
  (`docs/adr/0001-project-architecture.md`,
  `docs/adr/0002-data-privacy-strategy.md`).
- UI design spec capturing the sidebar/branding direction for Phase 8
  (`docs/design/UI_DESIGN_SPEC.md`), without implementing any UI yet.
- Typed configuration loading (`src/buildguard/config.py`) over
  `configs/base.yaml` and `configs/business.yaml`.
- Core data contracts (`src/buildguard/data/contracts.py`,
  `src/buildguard/data/enums.py`): Pandera schemas for Projects, Project
  Snapshots, Work Packages, Change Orders, Suppliers, and the Economic
  Index, enforcing the Section 8.5 minimum checks plus a cross-table
  chronological-consistency check.
- Earned Value Management formula engine (`src/buildguard/features/evm.py`):
  CV, SV, CPI, SPI, two independent EAC baselines (CPI-based and
  schedule-adjusted composite), ETC, VAC — each documented with its
  business interpretation and safe division-by-zero handling (Section 9).
- Deterministic synthetic portfolio generator
  (`src/buildguard/data/synthetic.py`): all six core tables (Projects,
  Project Snapshots, Work Packages, Change Orders, Suppliers, Economic
  Index) generated from one seeded RNG, correlated through a per-project
  latent risk profile so the required realism relationships (Section 8.2)
  hold by construction. Design rationale, a caught progress-accumulation
  bug, and the validated nominal-vs-inflation-adjusted overrun-rate finding
  are recorded in `docs/adr/0004-synthetic-data-design.md`.
- `scripts/generate_data.py` (`make data`): writes the full dataset to
  `data/processed/` (gitignored) and a small 20-project sample to
  `data/sample/` (committed) from the same run.
- `docs/DATA_DICTIONARY.md`: column-level reference for all six tables.
- `EconomicIndexProvider` interface (`src/buildguard/data/economic_index.py`,
  Section 8.3): `DemoIndexProvider` (deterministic illustrative index, used
  by the generator and, by default, everywhere else) and an intentionally
  unimplemented `ExternalLicensedProvider` placeholder. The synthetic
  generator was refactored to consume this instead of its own private copy
  of the same logic.
- Inflation-adjusted cost normalization
  (`src/buildguard/features/inflation.py`, Section 10): decomposes nominal
  cost variance into an operational (execution) component and an inflation
  component, with the identity `nominal = operational + inflation` tested
  directly against `evm.cost_variance` and validated against real generated
  data (exact decomposition, zero error).
- Temporal / lifecycle features (`src/buildguard/features/temporal.py`):
  lifecycle position/stage and trend/persistence signals (e.g. consecutive
  months of SPI decline) — captures "persistent deterioration" (Section
  8.2) that a single snapshot's ratios can't express alone.
- `docs/ARCHITECTURE.md`: system overview, package layout, EVM and
  inflation-normalization methodology.
- Ground-truth label derivation (`src/buildguard/data/labels.py`, Section
  6/11): `cost_overrun`/`schedule_delay` resolved from the snapshot
  history against the **inflation-adjusted (real)** final cost, per the
  open question recorded in ADR-0004. In-flight projects get `pd.NA`, never
  a coerced negative.
- Chronological, project-grouped train/calibration/test split
  (`src/buildguard/data/split.py`, Section 12): whole projects, ordered by
  `planned_start_date`, assigned to exactly one split — no project's
  history can appear in more than one. Rationale in
  `docs/adr/0003-temporal-validation.md`.
- Leakage-safe feature pipeline (`src/buildguard/features/pipeline.py`,
  Section 11/28): the single function assembling EVM, inflation, temporal,
  and leakage-safe cumulative change-order features (via
  `pandas.merge_asof(..., direction="backward")`) into one model-ready
  table. Work Packages and Suppliers are deliberately excluded (documented
  limitation: neither table carries a per-row date).
- `docs/LEAKAGE_POLICY.md`: prediction timestamp, feature-availability
  timestamps, label creation, forbidden features, and the automated tests
  that enforce them.
- `tests/leakage/test_pipeline_leakage.py`: the Section 11-mandated
  automated leakage tests — a future-dated change order injected into the
  test fixtures never contributes to an earlier snapshot's features,
  verified directly rather than assumed.
- Baseline models (`src/buildguard/models/baselines.py`, Section 13):
  `DummyClassifierBaseline` / `LogisticRegressionBaseline` / `CpiRuleBaseline`
  for classification, `MeanRegressionBaseline` / `MedianRegressionBaseline`
  / `DeterministicEacBaseline` / `LinearRegressionBaseline` for regression
  — the mandatory floors every model trained later (Session H) must beat.
  Validated end-to-end on the full synthetic portfolio: the deterministic
  EVM EAC baseline (~1.6M MAE) beats even a real fitted linear regression
  (~3.8M MAE), and the domain-rule `CPI < 0.90` classifier alone reaches
  ~0.83 AUC — confirming Section 13's "beat a meaningful
  construction-management baseline" bar is a real one on this data, not a
  trivial strawman. Details in `docs/ARCHITECTURE.md` Section 8.
- Shared model preprocessing (`src/buildguard/models/preprocessing.py`),
  promoted out of `baselines.py` once `classification.py`/`regression.py`
  needed the identical numeric/categorical handling.
- Candidate classification and regression models
  (`src/buildguard/models/classification.py`, `regression.py`, Section
  14/15): Random Forest and LightGBM, tuned with Optuna (`GroupKFold` on
  `project_id`, train split only). Deliberately not also XGBoost/CatBoost
  — see `docs/adr/0006-model-selection.md`.
- MLflow experiment tracking (`src/buildguard/models/tracking.py`, Section
  25): SQLite-backed local tracking, not MLflow's raw filesystem store
  (now in maintenance mode — discovered while building this). Every run
  tagged with `git_sha`; champion artifacts logged via `mlflow.log_artifact`
  rather than `mlflow.sklearn.log_model`, since BuildGuard's own baseline
  wrapper classes trip skops' `UntrustedTypesFoundException` and a baseline
  can legitimately be the champion (it was, for `final_cost`).
- `scripts/train.py` (`make train`): trains and selects the champion for
  all three core tasks, evaluated on the calibration split (test
  untouched), with results written to `reports/experiments/training_summary.json`.
  **Real results at full scale (400 projects):** cost-overrun risk →
  Random Forest, 0.898 AUC (vs. 0.888 best baseline); schedule-delay risk
  → LightGBM, 0.974 AUC (vs. 0.816); final-cost estimate → the
  **deterministic EAC baseline**, 1.96M MAE, beating tuned LightGBM's
  4.11M by more than 2x. Two tasks won by real models, one won decisively
  by a formula — reported honestly rather than forced. Full rationale in
  `docs/adr/0006-model-selection.md`.
- Probability calibration (`src/buildguard/models/calibration.py`, Section
  16): compares raw vs. sigmoid vs. isotonic by Brier score, fit directly
  on `(raw_probability, label)` pairs rather than through
  `CalibratedClassifierCV`/`FrozenEstimator` (which requires a full
  sklearn estimator interface BuildGuard's baselines don't implement — see
  `docs/adr/0007-calibration-strategy.md`). **Real results:** isotonic won
  both classification tasks (cost-overrun Brier 0.133 → 0.122;
  schedule-delay 0.072 → 0.059) and now ships as the production artifact.
- Business-cost threshold optimization (`src/buildguard/models/thresholds.py`,
  Section 17): never a silent 0.50 default — sweeps 199 candidates against
  `configs/business.yaml`'s asymmetric cost matrix. **Real results:**
  cost-overrun risk at 0.080 (98% recall / 68% precision), schedule-delay
  risk at 0.140 (98% recall / 86% precision). Rationale in
  `docs/adr/0008-threshold-policy.md`.
- Split-conformal prediction intervals
  (`src/buildguard/models/uncertainty.py`, Section 19): model-agnostic, so
  it works around the `final_cost` champion (a deterministic formula, not
  a fitted regressor) exactly as it would around a real model. **Real
  result:** 80% target coverage → ±$3.09M interval, 0.801 empirical
  coverage. Rationale in `docs/adr/0009-uncertainty-method.md`.
- `scripts/calibrate.py` (`make calibrate`): the post-training pass —
  loads the champions from `scripts/train.py`, applies calibration/
  threshold/uncertainty on the calibration split (test untouched), updates
  the saved champion artifacts, and writes
  `reports/experiments/calibration_summary.json`.
- `scripts/_common.py`: dataset-assembly helper shared by `train.py` and
  `calibrate.py` (generate portfolio → build features → resolve labels →
  split), extracted once it was needed identically in both scripts.
- `docs/adr/0005-feature-pipeline.md`: retroactive ADR documenting the
  Session F leakage-safe pipeline design, completing the Section 39
  minimum ADR set alongside 0007-0009.
- 99% test coverage on everything shipped so far (`tests/unit/`,
  `tests/contracts/`, `tests/leakage/`); Ruff, Ruff format, and Mypy
  (`--strict`) all clean.
- SHAP/permutation explainability (`src/buildguard/explainability/shap.py`,
  Section 20): global (mean |SHAP value| + permutation importance) and
  local (per-prediction SHAP) explanations for the tree-based classifiers.
  `TreeExplainer` built with `model_output="probability"` and an explicit
  background sample so RandomForest (natively probability-space) and
  LightGBM (natively log-odds-space) land in the same additive identity
  `base_value + shap_values.sum() == predicted_probability` for both
  families. `final_cost`'s formula champion (ADR-0006) has no learned
  explanation to attach. Mandatory disclaimer exported as
  `CAUSALITY_DISCLAIMER`.
- Slice evaluation (`src/buildguard/evaluation/slices.py`, Section 18):
  per-subgroup metric evaluation with a `None` (not a misleading number)
  result for slices below a minimum size or with an undefined metric (e.g.
  a single-class ROC-AUC slice), and `bucket_by_quantile` for continuous
  dimensions (size, budget, inflation exposure).
- Held-out evaluation metrics (`src/buildguard/evaluation/classification.py`,
  `regression.py`, `calibration.py`, Section 18): the full classification
  (ROC-AUC, PR-AUC, precision/recall/F1, Brier, confusion matrix) and
  regression (MAE, RMSE, R², MAPE/SMAPE, business-terms error) batteries,
  plus an out-of-sample calibration check — deliberately separate from
  `models/calibration.py`/`thresholds.py`, which *fit*/*select* on the
  calibration split; these modules only *measure*, on whatever split the
  caller passes in.
- `scripts/evaluate.py` (`make evaluate`): the one script that touches the
  **test** split — applies the frozen champion, threshold, calibration
  method, and conformal quantile unchanged, computes held-out metrics
  across all three tasks, runs slice evaluation across seven dimensions
  (six mandatory + inflation regime), and generates
  `reports/error_analysis/*_failure_analysis.md` (Section 47) directly
  from the computed numbers — false negatives/positives with their top
  SHAP drivers, near-threshold and out-of-distribution rows, hardest
  subgroups, and (for `final_cost`) largest errors and systematic bias by
  subgroup. **Real results:** cost-overrun risk ROC-AUC 0.9495 (recall
  97.4% @ 0.080); schedule-delay risk ROC-AUC 0.9002 (recall 92.9% @
  0.140); final-cost MAE $1.61M / R² 0.959, 89.9% empirical interval
  coverage against an 80% target. **Two genuine findings:**
  schedule-delay's isotonic calibration, which won in-sample (Brier
  0.059), degrades to 0.145 out-of-sample; cost-overrun's global AUC
  (0.9495) hides a materially weaker `ES`-state subgroup (AUC 0.597,
  n=76). Both documented, not hidden, per Section 18. Full rationale:
  `docs/adr/0010-evaluation-explainability-design.md`.
- Data quality monitoring (`src/buildguard/monitoring/data_quality.py`,
  Section 23): missing values, schema violations (reusing
  `buildguard.data.contracts`, never re-implemented), unexpected
  categories, range violations, and duplicate keys. **Real result:** 0
  violations across Projects/Snapshots/Change Orders (400/11,953/897
  rows).
- Drift detection (`src/buildguard/monitoring/drift.py`, Section 23): PSI
  for every variable type (numeric quantile-binned, categorical
  proportion-based), KS test and Wasserstein distance for numeric columns
  specifically. **Real result:** 10 of 23 features significantly
  drifted between the train and test splits — dominated by
  `inflation_multiplier` and `months_since_start`, the expected signature
  of the chronological split itself (older/train projects have had more
  calendar time to accrue inflation and lifecycle progress), not a data
  defect.
- Performance and operational monitoring
  (`src/buildguard/monitoring/performance.py`, Section 23/24): compares
  each task's calibration-split baseline against its genuinely held-out
  test-split result (reusing `buildguard.evaluation`'s metrics rather than
  recomputing them), and measures real (not simulated) inference latency
  by timing actual `predict`/`predict_proba` calls. **Real results:**
  `schedule_delay` degraded on ROC-AUC (0.974 → 0.900), recall (0.984 →
  0.929), and Brier score (0.059 → 0.145) despite negligible prediction
  drift — caught only because performance monitoring is label-dependent
  and drift detection is not; `cost_overrun`/`final_cost` both held or
  improved. Inference latency p95: 20.8ms / 5.6ms / 0.03ms for
  cost-overrun/schedule-delay/final-cost, all well under Section 49's
  500ms target.
- Risk bands (`models/thresholds.risk_band()`, Section 23/28): "low"
  below the optimized decision threshold, the flagged zone above it split
  at its own midpoint into "medium"/"high".
- `scripts/monitor.py` (`make monitor`): the monitoring orchestration
  script — data quality on the raw tables, feature drift (train vs.
  test), prediction drift (calibration vs. test, including risk-band
  proportions), performance comparison, real inference-latency
  measurement, and Section 24 retraining-trigger evaluation, all written
  to `reports/monitoring/monitoring_report.json`. **Never auto-retrains**
  — the script has no code path that calls `scripts/train.py`; it only
  flags. Of the six Section 24 triggers, four are computed for real
  (PSI, performance drop, calibration deterioration, schema changes); two
  (new labeled-data volume, scheduled quarterly evaluation) are
  calendar/volume-driven policy, documented rather than computed.
- `docs/MONITORING.md`: the Section 23/24 reference — what is monitored,
  why these particular reference/current split pairings, how to read a
  drift alert without misreading expected chronological-split drift as a
  problem, and the full retraining-trigger table.
- `docs/adr/0011-monitoring-drift-detection.md`: design rationale for
  every monitoring decision above, the complete real-results snapshot,
  and the alternatives considered (including why a synthetic drift demo
  was rejected in favor of the real train/calibration/test splits).
- FastAPI inference service (`src/buildguard/api/`, Section 28/29):
  `GET /health`, `GET /version`, `POST /predict/{cost-risk,schedule-risk,
  final-cost}`. Every endpoint rebuilds the caller's project through the
  same `build_feature_table` training uses (a project's real snapshot
  history, not just its latest state, since trend/streak features need
  it), validated twice — Pydantic (types/ranges/enum membership, so an
  unseen category fails safely as a 422) then `buildguard.data.contracts`
  (cross-field checks Pydantic alone can't express, e.g.
  `completion_after_start`). Champion models and calibration decisions
  load once (`lru_cache`d), not per request.
- API contract tests (`tests/api/test_inference_service.py`, 15 tests):
  run against the real trained/calibrated champions rather than mocks,
  including a genuine model-behavior check (a project with worse cost
  efficiency scores strictly higher cost-overrun risk than an identical
  healthy one) alongside the schema/error-handling checks.
- Streamlit public app (`app/`, Section 30): six pages — Executive
  Overview, Project Diagnostic, Scenario Simulator, Model Performance,
  Model Health, About/Governance — following the renan-standard sidebar
  direction from `docs/design/UI_DESIGN_SPEC.md` (logo, project name,
  bordered nav buttons, version/GitHub footer). Predictions are made
  in-process by calling the FastAPI endpoint functions directly (Section
  29) — one prediction code path, never two. The Executive Overview page
  batch-scores the whole portfolio in one vectorized pass (same pipeline,
  same champions) rather than 400 individual calls. Verified with a real
  headless-browser pass (Playwright) across every page — caught two real
  bugs neither `ruff` nor `mypy` could (a computed dataclass property
  read as a JSON key, a duplicate-column merge), fixed before commit.
- `docs/adr/0012-streamlit-fastapi-boundary.md`: why `st.navigation()` was
  tried and rejected (its sidebar nav renders at a fixed position,
  incompatible with the logo-above-nav spec) in favor of a custom
  `st.session_state` router; why page files live in `app/page_modules/`
  rather than Section 33's suggested `pages/` (that literal name
  triggers Streamlit's own auto-discovery regardless of navigation
  approach — confirmed empirically, not assumed); and every other
  API/UI boundary decision, with real findings from the verification
  pass.
- Integration tests (`tests/integration/test_pipeline_integration.py`):
  raw `data/sample/` CSVs → contracts → `build_feature_table` → real
  trained champions, end to end. 10 tests, all passing against the
  actual committed sample data.
- CI (`.github/workflows/ci.yml`): lint, format check, and mypy in one
  job; train + calibrate + full test suite with an 85% coverage gate in
  another. Real run: 293 tests, 98% coverage.
- Security scanning (`.github/workflows/security.yml`): `pip-audit` and
  `bandit`, weekly plus on every push/PR. One known CVE
  (`cryptography` < 50, pinned by `mlflow` itself) is explicitly ignored
  with a documented reason — BuildGuard never touches the vulnerable
  code path (MLflow's Databricks integration).
