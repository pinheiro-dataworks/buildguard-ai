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

**Progress:** 9 / ~50 planned commits done · 0 / 12 PRs opened · Phase 0 complete, Phase 1 ~30% complete.

---

## How this maps to the roadmap

Each session below corresponds to one or more phases from Section 45 and one
suggested PR from Section 43. Sessions are ordered — later ones depend on
earlier ones (e.g. no modeling before the temporal split exists).

| Session | Phase(s) | Suggested PR | Status |
|---|---|---|---|
| A — Repository foundation | 0 | #1 Project foundation | ✅ Done (uncommitted, ready to commit) |
| B — Data foundation core | 1 | #1 / #2 | ✅ Done (uncommitted, ready to commit) |
| C — Synthetic portfolio generator | 1 | #2 Synthetic portfolio generator | ⬜ Not started |
| D — EDA & data understanding | 1–2 | #2 (docs) | ⬜ Not started |
| E — Inflation & temporal features | 2 | #3 EVM feature engine (cont'd) | ⬜ Not started |
| F — Anti-leakage & split | 3 | #4 Temporal anti-leakage split | ⬜ Not started |
| G — Baselines | 3 | #5 Baseline models | ⬜ Not started |
| H — Advanced modeling | 4 | #6/#7/#8 Cost/schedule/final-cost models | ⬜ Not started |
| I — Calibration, threshold, uncertainty | 5 | #9 Calibration & threshold optimization | ⬜ Not started |
| J — Explainability & error analysis | 6 | #9 (cont'd) | ⬜ Not started |
| K — Monitoring & MLflow | 7 | #10 Monitoring | ⬜ Not started |
| L — API & Streamlit app | 8 | #11 Public app | ⬜ Not started |
| M — Testing hardening & CI/CD | 9 | #12 Release hardening (cont'd) | ⬜ Not started |
| N — Documentation completion | 9 | #12 (cont'd) | ⬜ Not started |
| O — Deployment & v1.0.0 release | 10–11 | #12 Release hardening | ⬜ Not started |

---

## Session A — Repository Foundation (Phase 0)

Already done in the working tree; ready to commit as-is.

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

Already done in the working tree; ready to commit as-is.

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

- [ ] **C09** `feat: add synthetic project portfolio generator (core project table)`
- [ ] **C10** `feat: extend synthetic generator with monthly project snapshots`
- [ ] **C11** `feat: extend synthetic generator with work packages and change orders`
- [ ] **C12** `feat: extend synthetic generator with suppliers and demo economic index`
- [ ] **C13** `test: add synthetic data contract-compliance and reproducibility tests`
- [ ] **C14** `feat: add generate_data.py CLI entry point and commit data/sample output`
- [ ] **C15** `docs: add data dictionary`

**→ PR #2 "Synthetic portfolio generator"**

## Session D — EDA & Data Understanding (Phase 1–2)

- [ ] **C16** `docs: add 01_data_understanding notebook`
- [ ] **C17** `docs: add 02_eda notebook with synthetic portfolio analysis`
- [ ] **C18** `docs: add EDA written conclusions and key figures to reports/figures`

**→ folds into PR #2 as documentation, or its own small PR**

## Session E — Inflation & Temporal Features (Phase 2)

- [ ] **C19** `feat: add inflation-adjusted cost normalization layer`
- [ ] **C20** `feat: add temporal snapshot feature pipeline`
- [ ] **C21** `test: add inflation and temporal feature edge-case tests`
- [ ] **C22** `docs: add EVM and inflation methodology notes to ARCHITECTURE.md`

**→ PR #3 "EVM & feature engine" (extends C08)**

## Session F — Anti-Leakage & Temporal Split (Phase 3)

- [ ] **C23** `docs: add leakage policy document`
- [ ] **C24** `feat: add chronological train/calibration/test split with project grouping`
- [ ] **C25** `test: add automated leakage detection tests (feature vs. prediction timestamp)`

**→ PR #4 "Temporal anti-leakage split"**

## Session G — Baselines (Phase 3)

- [ ] **C26** `feat: add classification baselines (dummy, logistic regression, CPI rule)`
- [ ] **C27** `feat: add regression baselines (mean/median, deterministic EAC, linear regression)`

**→ PR #5 "Baseline models"**

## Session H — Advanced Modeling (Phase 4)

- [ ] **C28** `feat: add MLflow experiment tracking scaffolding`
- [ ] **C29** `feat: train and tune cost-overrun risk model`
- [ ] **C30** `feat: train and tune schedule-delay risk model`
- [ ] **C31** `feat: train and tune final-cost regression model`
- [ ] **C32** `docs: add model-selection ADR (families considered, trade-offs)`

**→ PR #6 / #7 / #8 (one per model, or combined — your call at the time)**

## Session I — Calibration, Threshold, Uncertainty (Phase 5)

- [ ] **C33** `feat: add probability calibration (Platt/isotonic comparison, Brier score)`
- [ ] **C34** `feat: add business-cost threshold optimization`
- [ ] **C35** `feat: add prediction uncertainty (conformal or quantile intervals)`
- [ ] **C36** `docs: add calibration, threshold-policy, and uncertainty-method ADRs`

**→ PR #9 "Calibration & threshold optimization"**

## Session J — Explainability & Error Analysis (Phase 6)

- [ ] **C37** `feat: add global and local SHAP explainability`
- [ ] **C38** `feat: add slice evaluation across project type/size/geography/lifecycle`
- [ ] **C39** `docs: add senior-level failure analysis report`

**→ folds into PR #9 or its own small PR**

## Session K — Monitoring & Retraining Policy (Phase 7)

- [ ] **C40** `feat: add data quality and drift monitoring`
- [ ] **C41** `feat: add prediction and performance monitoring`
- [ ] **C42** `docs: add monitoring documentation, retraining policy, and monitoring ADR`

**→ PR #10 "Monitoring"**

## Session L — API & Streamlit App (Phase 8)

This is where [`docs/design/UI_DESIGN_SPEC.md`](docs/design/UI_DESIGN_SPEC.md)
(the renan-standard sidebar/branding direction) finally gets implemented.

- [ ] **C43** `feat: add FastAPI inference service and Pydantic schemas`
- [ ] **C44** `test: add API contract tests`
- [ ] **C45** `feat: add Streamlit app shell (sidebar, branding, navigation)`
- [ ] **C46** `feat: add Executive Overview and Project Diagnostic pages`
- [ ] **C47** `feat: add Scenario Simulator, Model Performance, and Model Health pages`
- [ ] **C48** `docs: add streamlit-fastapi-boundary ADR`

**→ PR #11 "Public app"**

## Session M — Testing Hardening & CI/CD (Phase 9)

- [ ] **C49** `test: add integration tests (raw → validation → features → prediction)`
- [ ] **C50** `ci: add GitHub Actions pipeline (lint, format, type-check, test, coverage gate)`
- [ ] **C51** `security: add dependency and secret scanning (pip-audit, Bandit)`

**→ PR #12 "Release hardening" (part 1)**

## Session N — Documentation Completion (Phase 9)

- [ ] **C52** `docs: add architecture, monitoring, and limitations docs`
- [ ] **C53** `docs: complete model card and runbook`
- [ ] **C54** `docs: add interview guide and remaining ADRs`

**→ folds into PR #12**

## Session O — Deployment & v1.0.0 Release (Phase 10–11)

- [ ] **C55** `chore: add Dockerfile and package_model.py`
- [ ] **C56** `chore: deploy to Streamlit Community Cloud and add smoke tests`
- [ ] **C57** `chore: cut v1.0.0 release, update CHANGELOG and README with final results`

**→ PR #12 "Release hardening" (part 2), tag `v1.0.0`**

---

## Running totals

- **Commits:** 57 planned across 15 sessions — inside the 30 (minimum) to
  85 (stretch) range from Section 43, biased toward the upper-middle
  because the foundation phase legitimately needed more setup than the
  minimum plan assumed (governance files, ADRs, brand/UI spec captured
  early). Expect the real number to drift ±10 as sessions actually happen —
  that's fine; this is a guide, not a quota.
- **PRs:** 12, matching Section 43's suggested list almost exactly (the
  cost/schedule/final-cost models can be one PR or three, decide at
  Session H time based on how independent they end up being).

## Next action

Commit **C01–C08** now (Sessions A + B), open PR #1, then start Session C
(synthetic portfolio generator) — the next substantial piece of Phase 1.
