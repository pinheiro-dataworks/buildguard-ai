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
