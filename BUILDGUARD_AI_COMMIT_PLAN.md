# BuildGuard AI — Commit & Session Plan

Companion tracking document to [`BUILDGUARD_AI_PROJECT_SCOPE.md`](BUILDGUARD_AI_PROJECT_SCOPE.md)
Sections 43 (Commit & PR Plan) and 45 (Roadmap). This file turns that
workstream table into a concrete, ordered, checkable list of commits, so
progress toward the **≥30 commit (target 60–85), ≥12 PR** goal stays
traceable across sessions instead of being re-derived each time.

**Rule (unchanged from Section 43):** do not manufacture commits to hit a
number. Every item below is a real, independently meaningful unit of work.
If a real session naturally merges or splits an item, update this file to
match reality — this document follows the work, not the other way around.

Check off an item (`- [x]`) once it is actually committed. Update the
**Progress** line at the top after every session.

**Progress:** 32 / 59 planned commits actually committed (C33–C38 code is
written, tested, and actually calibrated end-to-end, ready to commit) · 0 /
14 PRs opened · Phase 0-4 complete, Phase 5 (calibration/threshold/
uncertainty) complete.

---

## How this maps to the roadmap

Each session below corresponds to one or more phases from Section 45 and one
suggested PR from Section 43. Sessions are ordered — later ones depend on
earlier ones (e.g. no modeling before the temporal split exists).

| Session | Phase(s) | Suggested PR | Status |
|---|---|---|---|
| A — Repository foundation | 0 | #1 Project foundation | ✅ Committed (C01–C05) |
| B — Data foundation core | 1 | #1 / #2 | ✅ Committed (C06–C08) |
| C — Synthetic portfolio generator | 1 | #2 Synthetic portfolio generator | ✅ Committed (C09–C13) |
| D — EDA & data understanding | 1–2 | #2 (docs) | ⬜ Not started (skipped ahead to E; notebooks are documentation-only and don't block anything) |
| E — Inflation & temporal features | 2 | #3 EVM feature engine (cont'd) | ✅ Committed (C17–C20) |
| F — Anti-leakage & split | 3 | #4 Temporal anti-leakage split | ✅ Committed (C21–C25) |
| G — Baselines | 3 | #5 Baseline models | ✅ Committed (C26–C27) |
| H — Advanced modeling | 4 | #6 Advanced modeling (bundled) | ✅ Committed (C28–C32) |
| I — Calibration, threshold, uncertainty | 5 | #9 Calibration & threshold optimization | ✅ Done (uncommitted, ready to commit) |
| J — Explainability & error analysis | 6 | #10 Explainability & error analysis | ⬜ Not started |
| K — Monitoring & MLflow | 7 | #11 Monitoring | ⬜ Not started |
| L — API & Streamlit app | 8 | #7 FastAPI service + #8 Streamlit UI | ⬜ Not started |
| M — Testing hardening & CI/CD | 9 | #12 Testing hardening & CI/CD | ⬜ Not started |
| N — Documentation completion | 9 | #13 Documentation completion | ⬜ Not started |
| O — Deployment & v1.0.0 release | 10–11 | #14 Deployment & v1.0.0 release | ⬜ Not started |

---

## Session A — Repository Foundation (Phase 0)

Committed.

- [x] **C01** `chore: bootstrap project tooling and environment`
  `pyproject.toml`, `uv.lock`, `.python-version`, `Makefile`, `.gitignore`, `.pre-commit-config.yaml`, `.env.example`
- [x] **C02** `docs: add project scope charter, README, and repository governance`
  `BUILDGUARD_AI_PROJECT_SCOPE.md`, `README.md`, `LICENSE`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `CHANGELOG.md`
- [x] **C03** `chore: add GitHub issue and pull request templates`
  `.github/ISSUE_TEMPLATE/*`, `.github/pull_request_template.md`
- [x] **C04** `docs: add data privacy policy and foundational ADRs`
  `docs/DATA_PRIVACY.md`, `docs/adr/0001-project-architecture.md`, `docs/adr/0002-data-privacy-strategy.md`, `docs/adr/template.md`
- [x] **C05** `chore: add brand assets, UI design spec, and folder placeholders`
  `assets/brand/logo_renan_ds.png`, `docs/design/*`, `app/README.md`, `models/README.md`, `notebooks/README.md`, `data/sample/README.md`, `data/external/README.md`

## Session B — Data Foundation Core (Phase 1, part 1)

Committed.

- [x] **C06** `feat: add typed configuration loading over YAML configs`
  `src/buildguard/__init__.py`, `src/buildguard/config.py`, `configs/base.yaml`, `configs/business.yaml`, `tests/unit/test_config.py`
- [x] **C07** `feat: add core data contracts for the project data model`
  `src/buildguard/data/__init__.py`, `src/buildguard/data/enums.py`, `src/buildguard/data/contracts.py`, `tests/contracts/test_contracts.py`
- [x] **C08** `feat: add Earned Value Management formula engine`
  `src/buildguard/features/__init__.py`, `src/buildguard/features/evm.py`, `tests/unit/test_evm.py`

**→ PR #1 "Project foundation" opens here**, bundling C01–C05 (or C01–C08 if
you prefer one larger foundational PR — your call; either is defensible).

---

## Session C — Synthetic Portfolio Generator (Phase 1, part 2)

Done (uncommitted, ready to commit). Revised from the original C09-C15 split: the generator was
designed and smoke-tested as one cohesive module (all six tables share one
per-project risk-profile mechanism, so splitting it table-by-table would
have meant committing intermediate states that didn't actually work yet --
a real bug, permanently-stalled delayed projects, was only caught by
testing the whole thing together). Reflecting reality per this file's own
rule: "if a real session naturally merges or splits an item, update this
file to match."

- [x] **C09** `style: apply ruff formatting to EVM module and tests`
  `src/buildguard/features/evm.py`, `tests/unit/test_evm.py` (cosmetic only, line-wrap width)
- [x] **C10** `feat: add deterministic synthetic portfolio generator`
  `src/buildguard/data/synthetic.py` -- Projects, Snapshots, Work Packages, Change Orders, Suppliers, Economic Index, all six tables, correlated via a shared per-project latent risk profile (see ADR-0004)
- [x] **C11** `test: add synthetic generator test suite`
  `tests/unit/test_synthetic.py` -- determinism, contract compliance, scale, realism, economic-index tests
- [x] **C12** `feat: add generate_data CLI and data-output config`
  `scripts/generate_data.py`, `configs/base.yaml` (+`data_processed` path, new `synthetic_data` fields), `src/buildguard/config.py`, `tests/unit/test_config.py`, `data/sample/*.csv` (small committed sample)
- [x] **C13** `docs: add synthetic-data-design ADR and data dictionary`
  `docs/adr/0004-synthetic-data-design.md`, `docs/DATA_DICTIONARY.md`

## Session D — EDA & Data Understanding (Phase 1–2)

- [ ] **C14** `docs: add 01_data_understanding notebook`
- [ ] **C15** `docs: add 02_eda notebook with synthetic portfolio analysis`
- [ ] **C16** `docs: add EDA written conclusions and key figures to reports/figures`

**→ folds into PR #2 as documentation, or its own small PR**

## Session E — Inflation & Temporal Features (Phase 2)

Done (uncommitted, ready to commit). Revised from the original C17-C20:
building `inflation.py` surfaced that the economic-index generation logic
living privately inside `synthetic.py` needed to become the real
`EconomicIndexProvider` interface (Section 8.3) first, since `inflation.py`
needs the same index both for historical (generator) and future
(inference-time) dates -- so that refactor became its own commit ahead of
the feature work it unblocks.

- [x] **C17** `refactor: extract EconomicIndexProvider from the synthetic generator`
  `src/buildguard/data/economic_index.py` (new: `EconomicIndexProvider`, `DemoIndexProvider`, `ExternalLicensedProvider` placeholder), `src/buildguard/data/synthetic.py` (now consumes the provider instead of a private duplicate), `tests/unit/test_synthetic.py`, `tests/unit/test_economic_index.py`
- [x] **C18** `feat: add inflation-adjusted cost normalization layer`
  `src/buildguard/features/inflation.py`, `tests/unit/test_inflation.py` -- `real_actual_cost`, `real_budget`, `operational_variance`, `inflation_component`; decomposition identity tested against `evm.cost_variance`
- [x] **C19** `feat: add temporal lifecycle and trend features`
  `src/buildguard/features/temporal.py`, `tests/unit/test_temporal.py`, `configs/base.yaml` (+`features:` section), `src/buildguard/config.py` (+`FeaturesConfig`), `tests/unit/test_config.py`
- [x] **C20** `docs: add architecture doc and update README for data/feature layers`
  `docs/ARCHITECTURE.md` (new), `README.md`, `CHANGELOG.md`, `BUILDGUARD_AI_COMMIT_PLAN.md`

**→ PR #3 "EVM & feature engine" (extends C08)**

## Session F — Anti-Leakage & Temporal Split (Phase 3)

Done (uncommitted, ready to commit). Revised from the original C21-C23:
building the leakage-safe pipeline surfaced that ground-truth label
derivation (`labels.py`) had to exist first and separately (nothing under
`features/` may import it -- that's the actual enforcement mechanism for
"no target-derived features"), and the pipeline itself
(`pipeline.py` -- EVM + inflation + temporal + leakage-safe change-order
joins) was substantial enough to warrant its own commit apart from its
tests and the leakage-specific test suite.

- [x] **C21** `feat: add ground-truth label derivation`
  `src/buildguard/data/labels.py`, `tests/unit/test_labels.py` -- `cost_overrun`/`schedule_delay` resolved from the snapshot history against the inflation-adjusted (real) final cost, per the open question in ADR-0004; in-flight projects get `pd.NA`
- [x] **C22** `feat: add chronological project-grouped train/calibration/test split`
  `src/buildguard/data/split.py`, `tests/unit/test_split.py`
- [x] **C23** `feat: add leakage-safe feature pipeline`
  `src/buildguard/features/pipeline.py`, `tests/unit/test_pipeline.py` -- assembles EVM/inflation/temporal features plus a `merge_asof`-based leakage-safe change-order join; Work Packages/Suppliers deliberately excluded (no per-row date)
- [x] **C24** `test: add automated leakage detection tests`
  `tests/leakage/test_pipeline_leakage.py` -- the Section 11-mandated test: a future-dated change order injected into fixtures never contributes to an earlier snapshot's features
- [x] **C25** `docs: add leakage policy and temporal-validation ADR`
  `docs/LEAKAGE_POLICY.md`, `docs/adr/0003-temporal-validation.md`, `docs/ARCHITECTURE.md`, `README.md`, `CHANGELOG.md`, `BUILDGUARD_AI_COMMIT_PLAN.md`

**→ PR #4 "Temporal anti-leakage split"**

## Session G — Baselines (Phase 3)

Done (uncommitted, ready to commit). Revised from the original C26/C27
split: classification and regression baselines share one preprocessing
helper and one fit/predict interface convention, so they were built and
tested as a single cohesive module rather than two.

- [x] **C26** `feat: add baseline models for classification and regression`
  `src/buildguard/models/__init__.py`, `src/buildguard/models/baselines.py`, `tests/unit/test_baselines.py`, `configs/base.yaml` (+`baselines:` section), `src/buildguard/config.py` (+`BaselinesConfig`), `tests/unit/test_config.py`, `pyproject.toml` (mypy `sklearn.*` override) -- `DummyClassifierBaseline`/`LogisticRegressionBaseline`/`CpiRuleBaseline`, `MeanRegressionBaseline`/`MedianRegressionBaseline`/`DeterministicEacBaseline`/`LinearRegressionBaseline`
- [x] **C27** `docs: document baseline validation results`
  `docs/ARCHITECTURE.md`, `README.md`, `CHANGELOG.md`, `BUILDGUARD_AI_COMMIT_PLAN.md` -- records the validated end-to-end finding: deterministic EAC (~1.6M MAE) beats fitted linear regression (~3.8M MAE); CPI rule alone reaches ~0.83 AUC

**→ PR #5 "Baseline models"**

## Session H — Advanced Modeling (Phase 4)

Done (uncommitted, ready to commit). Revised from the original C28-C32: the
three tasks share one training script rather than three separate ones
(`_run_classification_task`/`_run_regression_task` are the same machinery
with a different label column and metric), so "train cost-overrun" /
"train schedule-delay" / "train final-cost" became one combined commit;
the shared preprocessing extraction (needed once `classification.py`
existed alongside `baselines.py`) became its own commit instead.

- [x] **C28** `refactor: extract shared model preprocessing`
  `src/buildguard/models/preprocessing.py` (new), `src/buildguard/models/baselines.py`, `tests/unit/test_baselines.py` -- promoted out of `baselines.py` once a second real consumer needed it (Section 27)
- [x] **C29** `feat: add candidate classification and regression models`
  `src/buildguard/models/classification.py`, `src/buildguard/models/regression.py`, `tests/unit/test_classification.py`, `tests/unit/test_regression.py` -- Random Forest + LightGBM, Optuna-tuned with grouped (`project_id`) CV
- [x] **C30** `feat: add MLflow experiment tracking`
  `src/buildguard/models/tracking.py`, `tests/unit/test_tracking.py` -- SQLite-backed local tracking (MLflow's raw filesystem store is now in maintenance mode); champion artifacts logged via `mlflow.log_artifact`, not `mlflow.sklearn.log_model` (skops rejects BuildGuard's custom baseline classes)
- [x] **C31** `feat: add training orchestration script and train the three core models`
  `scripts/train.py`, `configs/base.yaml` (+`training:` section, `mlflow_tracking_uri` → sqlite), `src/buildguard/config.py` (+`TrainingConfig`), `tests/unit/test_config.py`, `reports/experiments/training_summary.json` -- **real results, full scale**: cost-overrun → Random Forest (0.898 AUC); schedule-delay → LightGBM (0.974 AUC); final-cost → deterministic EAC baseline (1.96M MAE, beating tuned LightGBM's 4.11M)
- [x] **C32** `docs: add model-selection ADR with real training results`
  `docs/adr/0006-model-selection.md`, `docs/ARCHITECTURE.md`, `README.md`, `CHANGELOG.md`, `BUILDGUARD_AI_COMMIT_PLAN.md`

**→ PR #6 "Advanced modeling" (one bundled PR covering all three tasks, since they share one training script -- not split into #6/#7/#8)**

## Session I — Calibration, Threshold, Uncertainty (Phase 5)

Done (uncommitted, ready to commit). Revised from the original C33-C36:
`train.py` and the new `calibrate.py` both needed identical dataset
assembly, so that got extracted as its own commit; the orchestration
script itself (wiring calibration+threshold+uncertainty together and
actually running it against the real trained champions) became a fifth
commit distinct from the three underlying modules.

- [x] **C33** `feat: add probability calibration`
  `src/buildguard/models/calibration.py`, `tests/unit/test_calibration.py` -- raw vs. sigmoid vs. isotonic by Brier score, fit directly on `(raw_probability, label)` pairs (not via `CalibratedClassifierCV`, which rejects BuildGuard's own baseline classes)
- [x] **C34** `feat: add business-cost threshold optimization`
  `src/buildguard/models/thresholds.py`, `tests/unit/test_thresholds.py` -- never a silent 0.50 default, optimized against `configs/business.yaml`'s cost matrix
- [x] **C35** `feat: add split-conformal prediction uncertainty`
  `src/buildguard/models/uncertainty.py`, `tests/unit/test_uncertainty.py` -- model-agnostic, works around the `final_cost` formula baseline
- [x] **C36** `refactor: extract shared dataset assembly for training scripts`
  `scripts/_common.py` (new), `scripts/train.py` (now consumes it instead of its own copy)
- [x] **C37** `feat: add calibration orchestration script and run it end-to-end`
  `scripts/calibrate.py`, `configs/base.yaml` (+`uncertainty:` section), `src/buildguard/config.py` (+`UncertaintyConfig`), `tests/unit/test_config.py`, `Makefile` (+`calibrate` target), `reports/experiments/calibration_summary.json` -- **real results**: isotonic calibration wins both classifiers; thresholds land at 0.080/0.140 (~98% recall each); final-cost 80% interval achieves 0.801 empirical coverage
- [x] **C38** `docs: add feature-pipeline, calibration, threshold-policy, and uncertainty-method ADRs`
  `docs/adr/0005-feature-pipeline.md` (retroactive, completes the Section 39 minimum set), `docs/adr/0007-calibration-strategy.md`, `docs/adr/0008-threshold-policy.md`, `docs/adr/0009-uncertainty-method.md`, `docs/ARCHITECTURE.md`, `README.md`, `CHANGELOG.md`, `BUILDGUARD_AI_COMMIT_PLAN.md`

**→ PR #9 "Calibration & threshold optimization"**

## Session J — Explainability & Error Analysis (Phase 6)

- [ ] **C39** `feat: add global and local SHAP explainability`
- [ ] **C40** `feat: add slice evaluation across project type/size/geography/lifecycle`
- [ ] **C41** `docs: add senior-level failure analysis report`

**→ PR #10 "Explainability & error analysis"**

## Session K — Monitoring & Retraining Policy (Phase 7)

- [ ] **C42** `feat: add data quality and drift monitoring`
- [ ] **C43** `feat: add prediction and performance monitoring`
- [ ] **C44** `docs: add monitoring documentation, retraining policy, and monitoring ADR`

**→ PR #11 "Monitoring"**

## Session L — API & Streamlit App (Phase 8)

This is where [`docs/design/UI_DESIGN_SPEC.md`](docs/design/UI_DESIGN_SPEC.md)
(the renan-standard sidebar/branding direction) finally gets implemented.
This session is also where the PR #7/#8 numbering gap (left by Session H
bundling three models into one PR) gets closed: API service and Streamlit
UI are genuinely independent halves, so this splits into two PRs (#7, #8)
rather than one #11.

- [ ] **C45** `feat: add FastAPI inference service and Pydantic schemas`
- [ ] **C46** `test: add API contract tests`
- [ ] **C47** `feat: add Streamlit app shell (sidebar, branding, navigation)`
- [ ] **C48** `feat: add Executive Overview and Project Diagnostic pages`
- [ ] **C49** `feat: add Scenario Simulator, Model Performance, and Model Health pages`
- [ ] **C50** `docs: add streamlit-fastapi-boundary ADR`

**→ PR #7 "FastAPI inference service"** (C45-C46) **+ PR #8 "Streamlit public app"** (C47-C50)

## Session M — Testing Hardening & CI/CD (Phase 9)

- [ ] **C51** `test: add integration tests (raw → validation → features → prediction)`
- [ ] **C52** `ci: add GitHub Actions pipeline (lint, format, type-check, test, coverage gate)`
- [ ] **C53** `security: add dependency and secret scanning (pip-audit, Bandit)`

**→ PR #12 "Testing hardening & CI/CD"**

## Session N — Documentation Completion (Phase 9)

- [ ] **C54** `docs: add architecture, monitoring, and limitations docs`
- [ ] **C55** `docs: complete model card and runbook`
- [ ] **C56** `docs: add interview guide and remaining ADRs`

**→ PR #13 "Documentation completion"**

## Session O — Deployment & v1.0.0 Release (Phase 10–11)

- [ ] **C57** `chore: add Dockerfile and package_model.py`
- [ ] **C58** `chore: deploy to Streamlit Community Cloud and add smoke tests`
- [ ] **C59** `chore: cut v1.0.0 release, update CHANGELOG and README with final results`

**→ PR #14 "Deployment & v1.0.0 release", tag `v1.0.0`**

---

## Running totals

- **Commits:** 59 planned across 15 sessions — inside the 30 (minimum) to
  85 (stretch) range from Section 43, biased toward the upper-middle
  because the foundation, anti-leakage, and calibration phases
  legitimately needed more granularity than the minimum plan assumed.
  Expect the real number to drift ±10 as sessions actually happen —
  that's fine; this is a guide, not a quota.
- **PRs:** 14 planned, clearing Section 43's minimum of 12 (recommended
  15-20) with room to spare. Session H merged the originally-planned
  #6/#7/#8 (one PR per model) into a single PR #6, since all three tasks
  ended up sharing one training script rather than three independent ones
  -- splitting the PR three ways would have meant three PRs touching the
  same commits, not three independent units of review. That gap is closed
  by Session L splitting into two real, independent PRs (#7 FastAPI
  service, #8 Streamlit UI) and Session J/M/N/O each getting their own PR
  (#10, #12, #13, #14) rather than folding into a neighbor -- every PR
  boundary here reflects an actual independently-reviewable unit of work,
  not a number manufactured to hit a target (Section 43: "do not
  manufacture commits [or PRs] to hit a number").

## Next action

Commit **C33–C38** now (Session I), open PR #9, then start Session J
(explainability & error analysis) -- the next piece that depends on the
calibrated champions existing (`models/*_champion.joblib`, now
calibration-wrapped where it helped).
