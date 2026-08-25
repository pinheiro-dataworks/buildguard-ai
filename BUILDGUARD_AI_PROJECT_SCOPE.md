# BuildGuard AI — Project Scope & Engineering Charter

**Project type:** Production-oriented Machine Learning / Construction Analytics / PropTech
**Target positioning:** Senior Data Scientist / Machine Learning Engineer — International Portfolio
**Primary language:** English only (code, docs, commits, issues, PRs, UI)
**Repository visibility:** Public
**Recurring production cost:** USD 0.00
**Legacy baseline:** GETEC Analytics
**Target quality bar:** ≥ 90/100 on the internal 10/10 Portfolio Scoring Rubric (Section 19)

> This document is the single source of truth for scope, rules, structure, and definition of done for BuildGuard AI. Any ambiguity during implementation should be resolved by referring back to this file, and any deliberate deviation should be recorded as an ADR (`docs/adr/`).

---

## 1. Executive Mandate

BuildGuard AI evolves the original **GETEC Analytics** concept — descriptive construction cost monitoring — into a **complete, reproducible, testable, deployable, and monitored ML system**.

This is **not**:
- a dashboard project;
- a Kaggle-style notebook project;
- a collection of disconnected ML experiments.

It **must** behave like a small, professionally engineered ML product that demonstrates, in public and inspectable form, the full lifecycle: business framing → data design → validation → leakage-safe feature engineering → baselines → model comparison → calibration → business-cost thresholding → uncertainty → explainability → testing → packaging → deployment → monitoring → governance → communication.

**Final message the repository must send:**
> "I can design, build, evaluate, deploy, monitor, and explain a Machine Learning system — not only train a model."

---

## 2. Legacy Baseline — GETEC Analytics

### 2.1 Domain logic to preserve
Budget vs. actual cost, committed cost, physical/financial progress, planned vs. actual behavior, cost groups, suppliers, time × cost analysis, inflation-adjusted (INCC-oriented) cost, management-by-exception, early detection of unfavorable trends, executive dashboards, single source of truth for cost analysis.

### 2.2 What must be substantially improved
Formal data contracts, reproducible pipelines, modular package structure, explicit ML targets, leakage-safe feature engineering, statistical baselines, calibrated probabilistic risk scoring, prediction intervals, business-cost-aware thresholds, explainability, drift/data monitoring, automated testing, CI/CD, typing/linting, reproducible environments, versioned experiments and models, public deployment, model card, ADRs, security/privacy controls, release management, documented failure modes.

---

## 3. Product Vision

BuildGuard AI answers **five executive questions**:
1. Which projects are most likely to exceed their approved budget?
2. Which projects are most likely to miss their contractual schedule?
3. What is the expected final cost of each project?
4. What factors are currently driving the risk?
5. What should management investigate first?

**Positioning rule:** *Decision Support for Construction Cost and Schedule Risk.* Never market the model as infallible, autonomous, or a guarantee of project outcomes. The product supports decisions — it does not automate high-stakes financial decisions without human review.

---

## 4. Primary Users & Needs

| User | Core needs |
|---|---|
| Executive Leadership | Portfolio overview, overrun/delay probability, expected final cost, exposure, top drivers, ranking, confidence intervals |
| Construction / Engineering Management | Work-package performance, CPI/SPI, deviation trends, cost-group & supplier risk, productivity, actionable alerts |
| Planning & Cost Control | Detailed EVM metrics, time series, forecast accuracy, variance decomposition, model diagnostics |
| Data / ML Teams | Pipeline traceability, model version, experiment history, feature definitions, drift metrics, test coverage, reproducible training |

---

## 5. Business Objectives

**A — Cost Overrun Risk:** `P(final_cost > approved_budget)` → probability, risk band, primary SHAP drivers.
**B — Schedule Delay Risk:** `P(actual_completion_date > planned_completion_date)` → probability, risk band, expected delay range.
**C — Estimate at Completion:** point forecast of final cost + 80% prediction interval.
**D — Management Prioritization:** a transparent, documented, sensitivity-tested risk-priority score combining overrun probability, financial impact, delay probability, schedule impact, model confidence, current exposure. **No undocumented black-box score.**

---

## 6. Machine Learning Tasks (Core — mandatory for v1.0.0)

| # | Task | Target | Notes |
|---|---|---|---|
| 6.1 | Binary Classification | `cost_overrun = final_cost > approved_budget * tolerance` | Tolerance configurable (0/5/10%); README states which is primary |
| 6.2 | Binary Classification | `schedule_delay = actual_completion > planned_completion + tolerance_days` | Tolerance configurable |
| 6.3 | Regression | `final_cost` (or normalized `final_cost_ratio` / `cost_overrun_pct`) | Target normalization must be justified experimentally |

## 7. Optional Advanced Tasks (only after core is correct)
Time-to-delay / survival analysis · Supplier performance risk · Probabilistic cost forecasting (quantile regression / conformal prediction / bootstrap) · Change-order risk · Anomaly detection. **Must never compromise the three core tasks.**

---

## 8. Data Strategy

### 8.1 Confidentiality Rule (hard rule)
No confidential employer/client/contractor/supplier/employee/project data in the public repo. Use synthetic data, strongly anonymized data with explicit permission, or compatibly licensed public data. **Required:** `docs/DATA_PRIVACY.md`.

### 8.2 Synthetic Demo Dataset (target scale)
Projects 100–500 · Snapshots 10,000–100,000 · Work packages 20–80/project · Suppliers 100–1,000 · Monthly observations 12–48/project.

Must encode realistic relationships (poor CPI → cost overrun risk, persistent SPI deterioration → delay risk, high change-order ratio → higher final cost, procurement delay → schedule impact, inflation → nominal cost, low physical/high financial progress → risk, supplier concentration → exposure, risk evolving over the lifecycle). Deterministic seeds. Implementation: `src/buildguard/data/synthetic.py`.

### 8.3 Public Economic Indicators (e.g., INCC)
Verify redistribution rights; never scrape/republish restricted data; document source/license; access via adapter:
```
EconomicIndexProvider
├── DemoIndexProvider          (default — public app must run on this)
└── ExternalLicensedProvider
```

### 8.4 Core Data Model
- **Projects:** `project_id, project_type, city, state, gross_floor_area_m2, number_of_towers, number_of_units, construction_standard, planned_start_date, planned_completion_date, approved_budget`
- **Project Snapshots:** `project_id, snapshot_date, planned_progress, actual_progress, planned_cost, actual_cost, committed_cost, earned_value, forecast_cost`
- **Work Packages:** `project_id, work_package_id, work_package_name, budget, actual_cost, planned_progress, actual_progress`
- **Change Orders:** `change_order_id, project_id, date, category, approved_amount, status`
- **Suppliers:** `supplier_id, supplier_category, project_id, contract_value, delivery_delay_days, quality_score, rework_cost`
- **Economic Index:** `reference_month, index_name, index_value`

### 8.5 Data Contracts
Use Pandera / Pydantic / native typed validation. Minimum checks: non-null `project_id`, valid `snapshot_date`, `approved_budget > 0`, `actual_cost >= 0`, progress fields in `[0,1]`, `earned_value >= 0`, chronological date consistency, uniqueness of `project_id + snapshot_date`. Failures must **fail loudly**, produce useful errors, never silently coerce, and be covered by tests.

---

## 9. Earned Value Management (EVM) Layer — mandatory, formal, documented

| Metric | Formula |
|---|---|
| Planned Value | `PV` |
| Earned Value | `EV` |
| Actual Cost | `AC` |
| Cost Variance | `CV = EV - AC` |
| Schedule Variance | `SV = EV - PV` |
| Cost Performance Index | `CPI = EV / AC` |
| Schedule Performance Index | `SPI = EV / PV` |
| Budget at Completion | `BAC` |
| Estimate at Completion | ≥ 2 deterministic baselines, e.g. `EAC_CPI = BAC / CPI` + schedule-adjusted alternative |
| Estimate to Complete | `ETC = EAC - AC` |
| Variance at Completion | `VAC = BAC - EAC` |

Every formula requires edge-case handling, unit tests, documentation, and business interpretation.

## 10. Inflation / Cost Normalization
Preserve the GETEC separation of nominal cost growth vs. operational performance. Features: `real_actual_cost, real_budget, real_cost_variance, inflation_component, operational_variance`. Decomposition: `Nominal Cost Variance = Inflation/Market Component + Project Execution Component`. **Language rule:** say *"estimated inflation-adjusted variance"*, never claim exact causal decomposition.

---

## 11. Temporal Design & Anti-Leakage Policy (critical Senior-level requirement)

**Rule:** a model predicting risk at month `t` may use only information available on or before `t`.

**Forbidden:** final cost as a feature, future change orders, future supplier delays, final completion status, future inflation values, whole-lifecycle aggregates, normalization using future observations, target-derived features.

**Required document:** `docs/LEAKAGE_POLICY.md` — prediction timestamp, feature availability timestamp, label creation, forbidden features, temporal validation strategy, automated leakage tests.

**Required automated test:** `max(feature_timestamp) <= prediction_timestamp` for all temporal features.

## 12. Train / Validation / Calibration / Test Design

The final **test set is never reused** for feature selection, hyperparameter tuning, early stopping, calibration, threshold selection, model comparison, or business-rule tuning.

```
Historical Data
  ├─ TRAIN            → CV / tuning
  ├─ CALIBRATION/VAL  → probability calibration + threshold selection
  └─ TEST             → exactly one final unbiased evaluation
```

Chronological split preferred (e.g., Train 60% oldest / Val 20% / Test 20% newest). Prevent project-level contamination across time (`GroupKFold`, `StratifiedGroupKFold`, temporal group splits) — method choice must be justified in an ADR.

**Cross-validation policy:**
| Method | When to use |
|---|---|
| K-Fold | i.i.d. tabular data, no time/group dependency |
| Stratified K-Fold | classification with class imbalance |
| Time Series Split | strictly sequential, single-series forecasting |
| Group K-Fold | multiple rows per project — prevents project leakage across folds |

---

## 13. Baselines (mandatory before any advanced model)

- **Classification:** `DummyClassifier`, `LogisticRegression`, domain rule baseline (e.g., `CPI < 0.90 → High Cost Risk`).
- **Regression:** mean/median predictor, deterministic EVM `EAC`, `LinearRegression`.
- **Rule:** the ML model must beat a *meaningful construction-management baseline*, not only a naive statistical one.

## 14. Candidate Models
- **Classification:** Logistic Regression, Random Forest, LightGBM, XGBoost/CatBoost.
- **Regression:** Linear Regression, Random Forest Regressor, LightGBM/XGBoost/CatBoost Regressor, quantile models where appropriate.
- README must justify: why each family was considered, why the final model was selected, performance vs. complexity, interpretability trade-off, inference latency, operational implications. **Do not use every model just to show tools.**

## 15. Hyperparameter Optimization
Randomized Search / Optuna / Bayesian optimization only — avoid unjustified exhaustive grids. Tuning restricted to train/CV data; search spaces documented; seeds controlled; objective matches the business problem; experiment metadata recorded.

## 16. Probability Calibration
Compare raw vs. Platt/sigmoid vs. isotonic calibration on data **separate from the final test set**. Report Brier Score, calibration curve, (optionally) ECE. Must answer: *"When BuildGuard says 70% risk, is that probability approximately trustworthy?"*

## 17. Threshold Optimization
Never default silently to 0.50. Define a configurable business cost matrix:
```yaml
business:
  false_negative_cost: 10   # missed real overrun
  false_positive_cost: 2    # false alarm / investigation time
```
Optimize on validation/calibration data. Report threshold, recall, precision, expected business cost, confusion matrix.

## 18. Evaluation Requirements

**Classification:** ROC-AUC, PR-AUC (emphasized under imbalance), Precision, Recall, F1, Brier Score, Confusion Matrix, Calibration.
**Regression:** MAE, RMSE, R², MAPE/SMAPE + business-terms error (median $ error, median % error).
**Slice analysis (mandatory):** project type, project size, construction standard, lifecycle stage, geography, budget segment. A high global metric with poor subgroup behavior must be documented, not hidden.

## 19. Uncertainty Quantification
At least one valid method for final-cost forecasting: conformal prediction, quantile regression, or bootstrap interval. Empirically evaluate coverage. Example output:
```
Expected Final Cost: $27.1M
80% Prediction Interval: $25.9M – $28.7M
```

## 20. Explainability
Global feature importance, permutation importance, SHAP (final tree-based model), local explanations per prediction. **Mandatory disclaimer visible in the UI:** *"Feature attribution explains the model prediction; it does not establish causality."*

## 21. Business Impact Layer
```
Active projects × Avg financial exposure × Overrun prevalence × Model recall × Avoidable-impact assumption
= Estimated decision-support value
```
All assumptions explicitly labeled. Use *"Scenario-based estimated impact"* — never fabricate realized ROI (e.g., never claim "the model saved $5M" without real evidence).

---

## 22. Model Governance — `docs/MODEL_CARD.md`
Must include: model name, version, owner, intended use, out-of-scope use, training/evaluation data, features, metrics, calibration, known limitations, risk considerations, drift policy, retraining criteria, human-oversight requirements. App must clearly state BuildGuard AI is **decision support**, not an autonomous decision-maker.

## 23. Monitoring (implemented, not just documented)

| Category | Tracked signals |
|---|---|
| Data quality | missing values, schema violations, unexpected categories, range violations, duplicate keys |
| Data drift | PSI, KS test, Wasserstein distance, distribution plots (method chosen per variable type, not one-size-fits-all) |
| Prediction drift | risk-probability distribution, predicted-cost distribution, risk-band proportions |
| Performance (when labels available) | ROC-AUC, PR-AUC, Recall, Brier Score, MAE, RMSE |
| Operational | inference latency, prediction count, errors, model version, data version |

Dedicated **Model Health** page required in the public app.

## 24. Retraining Policy
Triggers: `PSI` above threshold, performance drop > X%, calibration deterioration, new labeled-data volume > N, scheduled quarterly evaluation, schema changes. **Never auto-retrain solely because drift exists.**
```
Detect → Investigate → Validate data → Retrain candidate → Compare vs. champion → Approve → Release
```

## 25. Experiment Tracking & Model Versioning
MLflow, zero-cost local/file-based config. Track run_id, model, params, features, data version, metrics, plots, artifacts, duration, git SHA. Export summaries to `reports/experiments/` (do not commit large MLflow dirs).

Model version metadata: `model_name, semantic_version, training_date, data_version, git_sha, metrics, threshold, calibration_method` — e.g. `cost-risk-lightgbm v1.0.0`. Prediction responses expose model metadata.

---

## 26. Reproducibility
```
git clone <repo>
cd buildguard-ai
make setup && make data && make train && make test && make app
```
Deterministic seeds, pinned core dependencies, `pyproject.toml` + lock file, explicit Python version, no machine-specific paths, no undocumented manual steps.

## 27. Python Engineering Standard
Python 3.11+. Type hints, docstrings on public APIs, small functions, explicit interfaces, dependency injection where useful, dataclasses/Pydantic models, pure transformation functions, no notebook-only business logic, no global mutable state, no duplicated feature logic.

**Forbidden:** 1,000-line `app.py`, copy-pasted preprocessing, hard-coded paths/thresholds/magic numbers, silent `except:`, wildcard imports, secrets in Git, feature logic duplicated between train and inference.

## 28. Train/Serve Consistency
Shared feature module `src/buildguard/features/` used by training, inference service, and batch prediction. Tests comparing offline vs. online feature generation to prevent train/serve skew.

## 29. API Layer — FastAPI
Endpoints: `GET /health`, `GET /version`, `POST /predict/cost-risk`, `POST /predict/schedule-risk`, `POST /predict/final-cost`.
```json
{
  "project_id": "PRJ-001",
  "cost_overrun_probability": 0.73,
  "risk_band": "high",
  "threshold": 0.61,
  "model_version": "1.0.0"
}
```
Pydantic validation, stable schemas, error handling, model version, tests, OpenAPI docs. Streamlit app may call it in-process (zero cost); FastAPI must remain independently runnable.

## 30. Public Application — Streamlit
Pages: **Executive Overview** · **Project Diagnostic** (timeline, CPI/SPI, trends, predictions, uncertainty, SHAP drivers) · **Scenario Simulator** (what-if only, explicitly not causal) · **Model Performance** · **Model Health** · **About / Governance**.

## 31. Zero-Cost Production Architecture (mandatory public path)
```
GitHub (public repo) → GitHub Actions (lint/test/type-check) → Streamlit Community Cloud
                                                                  ├─ BuildGuard UI
                                                                  ├─ packaged model
                                                                  ├─ in-process prediction service
                                                                  └─ demo dataset
```
No paid database, model endpoint, LLM, or monitoring SaaS. Optional `docs/architecture/aws-reference.md` for a non-implemented enterprise reference — never claim it's deployed unless it actually is; if ever demoed, use budget alerts and tear down immediately.

## 32. Containerization
`Dockerfile`: slim base image, non-root runtime where practical, deterministic install, `.dockerignore`, health check, no secrets, reasonable size. Optional `docker-compose.yml` for local API + app + MLflow. Docker not mandatory for Streamlit Community Cloud deployment.

---

## 33. Repository Structure
```
buildguard-ai/
├── README.md · LICENSE · CHANGELOG.md · CONTRIBUTING.md · CODE_OF_CONDUCT.md · SECURITY.md
├── Makefile · pyproject.toml · uv.lock · .python-version · .env.example · .gitignore · .pre-commit-config.yaml · Dockerfile
├── configs/            base.yaml, training.yaml, monitoring.yaml, business.yaml
├── data/               sample/, README.md
├── notebooks/          01_data_understanding, 02_eda, 03_feature_research, 04_model_research
├── src/buildguard/
│   ├── config.py
│   ├── data/            contracts.py, ingest.py, validate.py, synthetic.py
│   ├── features/         evm.py, inflation.py, temporal.py, pipeline.py
│   ├── models/           baselines.py, classification.py, regression.py, calibration.py, thresholds.py, uncertainty.py
│   ├── evaluation/        classification.py, regression.py, calibration.py, slices.py
│   ├── explainability/    shap.py
│   ├── monitoring/        data_quality.py, drift.py, performance.py
│   ├── api/               app.py, schemas.py, dependencies.py
│   └── utils/
├── app/                 Home.py, pages/
├── scripts/             generate_data.py, train.py, evaluate.py, monitor.py, package_model.py
├── tests/               unit/, integration/, contracts/, leakage/, monitoring/, api/
├── models/              README.md
├── reports/             figures/, metrics/, experiments/, monitoring/, error_analysis/
├── docs/                ARCHITECTURE.md, DATA_DICTIONARY.md, DATA_PRIVACY.md, LEAKAGE_POLICY.md,
│                        MODEL_CARD.md, MONITORING.md, RUNBOOK.md, LIMITATIONS.md, INTERVIEW_GUIDE.md, adr/
└── .github/             ISSUE_TEMPLATE/, pull_request_template.md, workflows/{ci.yml, security.yml, release.yml}
```
Every folder must exist because it has a purpose — not because a template expects it.

## 34. Notebook Policy
Notebooks are for exploration, EDA, research, communicating reasoning — **not production logic**. Once a method is accepted, move it into `src/buildguard/`. Notebooks must run top-to-bottom, use deterministic seeds, avoid hidden state, import project functions, contain written conclusions, and avoid massive raw output dumps.

---

## 35. Testing Strategy

| Layer | Covers |
|---|---|
| Unit | EVM formulas, inflation normalization, feature transforms, threshold logic, risk bands, schemas, utils |
| Data contracts | required columns, ranges, uniqueness, date consistency, missing critical fields |
| Leakage | future timestamps, target-derived columns, training pipeline contamination |
| Integration | raw sample → validation → features → prediction |
| API contracts | valid/invalid requests, missing fields, response schema, model version |
| Monitoring | known artificial drift scenarios |
| Regression | same fixture + same model version ⇒ prediction within tolerance |

**Coverage target:** ≥ 85% on `src/buildguard` before v1.0.0 (coverage is necessary but not sufficient — critical logic must be tested regardless of aggregate %).

## 36. Static Quality Gates & CI/CD
CI stages (GitHub Actions, public-repo hosted runners, zero cost): Checkout → Install → Lint (Ruff) → Format check (Ruff) → Type check (Mypy) → Unit tests → Integration tests → Coverage gate. Optional: Bandit, pip-audit. No PR merges with failing required checks. Dependency caching where useful.

## 37. Security, Logging, Configuration
- **`SECURITY.md`:** never commit `.env`, API keys, cloud credentials, or confidential datasets; enable secret scanning; use `.env.example`; pin & scan dependencies; validate API payloads; sanitize file paths; avoid arbitrary code execution; strict file-type/size limits on any upload.
- **Logging:** structured, minimum fields `timestamp, event, model_version, request_id, latency_ms, status`; never log sensitive raw project data unnecessarily.
- **Configuration:** externalized in YAML/TOML (`configs/`), no scattered magic numbers; every threshold justified or explicitly marked configurable.

---

## 38. Documentation Set (required before v1.0.0)
`README.md` · `docs/ARCHITECTURE.md` · `docs/DATA_DICTIONARY.md` · `docs/DATA_PRIVACY.md` · `docs/LEAKAGE_POLICY.md` · `docs/MODEL_CARD.md` · `docs/MONITORING.md` · `docs/LIMITATIONS.md` · `docs/RUNBOOK.md` · `docs/INTERVIEW_GUIDE.md` · `docs/adr/`.

## 39. Architecture Decision Records (minimum set)
```
0001-project-architecture.md          0007-calibration-strategy.md
0002-data-privacy-strategy.md         0008-threshold-policy.md
0003-temporal-validation.md           0009-uncertainty-method.md
0004-synthetic-data-design.md         0010-monitoring-design.md
0005-feature-pipeline.md              0011-zero-cost-deployment.md
0006-model-selection.md               0012-streamlit-fastapi-boundary.md
```
Each ADR: Context, Decision, Alternatives Considered, Consequences, Status.

## 40. README.md — Required Structure (final, authoritative version)
1. Project Overview
2. Business Problem
3. Objectives
4. Dataset
5. Data Architecture
6. Exploratory Data Analysis
7. Feature Engineering
8. Modeling
9. Evaluation
10. Results
11. Business Impact
12. Architecture
13. How to Run
14. Limitations
15. Future Improvements

The first screen must immediately answer: *What is this? Why does it matter? What did the model achieve? Where is the live demo? What technologies were used?*

> Note: this 15-section structure supersedes the earlier 21-section draft outline discussed in the full specification; content from the dropped sections (e.g., anti-leakage design, monitoring, engineering quality, deployment, roadmap) should be folded into the closest matching section above (mainly *Data Architecture*, *Modeling*, *Architecture*, *Limitations*, *Future Improvements*) or linked out to the relevant `docs/` file.

---

## 41. Git Workflow

**Branches:** `main`, optional `develop`, `feature/<name>`, `fix/<name>`, `docs/<name>`, `refactor/<name>`, `test/<name>` (or a documented trunk-based alternative).

**Issues:** every meaningful feature starts from an issue (e.g. `#12 Implement temporal split`).

**Pull Requests:** used even solo, for major changes; each explains Problem / Solution / Tests / Risks / Evidence. Prefer squash merge for cohesive features. **Never merge on failing CI.**

## 42. Commit Standard
All commits in English, Conventional-Commit style:
```
feat: add temporal project split
feat: implement CPI and SPI features
test: add leakage detection tests
fix: prevent future index values in features
refactor: isolate feature pipeline
docs: add model calibration ADR
ci: enforce coverage threshold
perf: reduce inference latency
security: validate uploaded dataset schema
chore: update development dependencies
```
**Avoid:** `update`, `fix`, `final`, `final2`, `changes`, `project done`, `new version`.

## 43. Commit & PR Plan

> **Operative rule for this project (owner directive):** **minimum 30 meaningful commits**, distributed across the whole development timeline — not front-loaded or manufactured. This adjusts the original engineering rubric's higher minimum downward for delivery speed, while preserving the "senior pattern" of steady, traceable, English-language commits tied to real milestones.
>
> **Stretch target (original rubric, still recommended for maximum interview signal):** 60–85 commits, distributed per the table below at full scale.

| Workstream | Min commits (30-commit plan) | Min commits (80-commit stretch plan) |
|---|---|---|
| Repository foundation | 2 | 4 |
| Data contracts & synthetic generator | 3 | 7 |
| EDA & data understanding | 2 | 5 |
| EVM & inflation features | 3 | 7 |
| Temporal / leakage controls | 2 | 5 |
| Baselines | 2 | 4 |
| Advanced modeling | 3 | 7 |
| Calibration / threshold / uncertainty | 3 | 6 |
| Evaluation / explainability | 2 | 5 |
| Monitoring | 2 | 5 |
| API / application | 3 | 5 |
| Testing / quality | 2 | 5 |
| CI/CD / security | 1 | 3 |
| Documentation / ADRs | 2 | 5 |
| Deployment / release | 1 | 2 |
| **Total** | **≥ 30** | **80 (target 70–85)** |

**Rule:** do not manufacture commits to hit a number. A well-paced 30–40 commit history tied to real milestones outranks 150 artificial micro-commits.

**Pull Requests:** minimum 12 meaningful PRs before v1.0.0 (recommended 15–20), e.g.:
```
#1 Project foundation            #7 Schedule-risk model
#2 Synthetic portfolio generator #8 Final-cost model
#3 EVM feature engine            #9 Calibration & threshold optimization
#4 Temporal anti-leakage split   #10 Monitoring
#5 Baseline models               #11 Public app
#6 Cost-risk model               #12 Release hardening
```

---

## 44. Release Strategy (semantic versioning)

| Version | Milestone deliverables |
|---|---|
| v0.1.0 | Data Foundation — schemas, synthetic data, EVM, validation |
| v0.3.0 | Modeling Baselines — temporal splits, baseline models, experiment tracking |
| v0.5.0 | Advanced Models — tuned models, calibration, threshold optimization |
| v0.7.0 | Production Interface — API, Streamlit app, model packaging |
| v0.9.0 | MLOps & Monitoring — drift, monitoring, full CI, model card |
| v1.0.0 | Production Portfolio Release — public deployment, final test eval, full docs, release notes, ≥85% coverage, no critical open bugs |

## 45. Roadmap (Phases 0–11)
0. Design (no code before target/timestamp/data-availability/evaluation strategy is defined)
1. Data Foundation
2. Domain Analytics (GETEC parity, EVM, inflation, executive descriptive analytics)
3. Anti-Leakage ML Foundation (temporal split, leakage tests, baselines)
4. Advanced Modeling (3 core tasks)
5. Decision Science (calibration, threshold, uncertainty, business-cost analysis)
6. Explainability (global/local, failure analysis, slice evaluation)
7. MLOps (MLflow, metadata, monitoring, retraining policy)
8. Productization (FastAPI, Streamlit, scenario simulator)
9. Quality Hardening (testing, coverage, typing, security, docs)
10. Deployment (Streamlit Community Cloud, smoke tests, runbook)
11. v1.0.0 (final release, tag, release notes, interview guide, final audit)

**Development sequence (must be followed in order):**
```
Problem definition → Data design → Data validation → Domain analytics → Leakage-safe validation
→ Baselines → Advanced models → Calibration → Threshold → Uncertainty → Explainability
→ Monitoring → API → UI → Deployment
```
Do not build the UI before the ML evaluation design is stable.

---

## 46. Code Review Checklist (self-review every major PR)
**Correctness:** solves the issue; edge cases handled; units consistent; temporal leakage impossible.
**ML methodology:** test set untouched; tuning restricted to train/CV; calibration/threshold separated correctly; baselines included.
**Engineering:** logic reusable; functions typed; config externalized; no duplication; train/serve feature logic shared.
**Testing:** new behavior tested; tests fail before fix when appropriate; coverage above threshold; CI passes.
**Documentation:** README/docs updated if behavior changed; ADR added for architectural decisions; public claims match implementation.

## 47. Senior-Level Failure Analysis (`reports/error_analysis/`) — mandatory
For each final model, analyze false negatives, false positives, largest regression errors, low-confidence predictions, out-of-distribution examples. Answer: where does it fail, which project types are hardest, does lifecycle stage matter, are large projects systematically underpredicted, does inflation regime change performance, what should a human reviewer check.

## 48. Stress Testing
Missing features, extreme-but-valid budgets, zero progress, near-completed projects, unseen categories, changed inflation regime, supplier anomalies, schema evolution, drifted distributions. **The app must fail safely.**

## 49. Performance & UX
Target: single prediction p95 < 500ms local CPU; reasonable dashboard load on free hosting; model artifact preferably < 100MB. UX: clear English, minimal animation, consistent formatting, readable on laptop screens, labeled units, explained risk bands, tooltips, clear distinction between estimates and actuals, visible uncertainty context. No experimental-notebook look.

## 50. Documentation Language Rule
Everything in English: repo name, README, code, functions, variables, classes, docstrings, comments, commit messages, branch names, issues, PRs, dashboards, charts, labels, model card, ADRs, release notes. No Portuguese/English mixing. Domain-specific proper nouns (e.g., `INCC`) may remain as-is but must be explained in English.

## 51. Technical Interview Readiness — `docs/INTERVIEW_GUIDE.md`
The author must be able to answer, without reading the code, questions across: Business, Data, Leakage, Modeling, Calibration, Threshold, Regression, Explainability, MLOps, Production (full question list per the original specification, Section 59).

## 52. Enterprise-Scale Reference Architecture
A separate, clearly labeled diagram — **"REFERENCE ARCHITECTURE — NOT THE PUBLIC DEMO"** — showing the target enterprise evolution (lakehouse, feature store, distributed training, model registry, batch/online serving, monitoring, alerts). Never claim these are implemented unless they actually are.

## 53. Ethical & Responsible Use
Document human oversight, uncertain predictions, out-of-domain use, incomplete data, model degradation, false-assurance risk. UI language: *"Estimated risk"* — never *"Project will overrun."*

---

## 54. Definition of Done — v1.0.0

- [ ] **Product:** live public app, executive dashboard, project diagnostic, scenario simulator, model health page all working.
- [ ] **Data:** reproducible synthetic/public dataset; provenance documented; contracts enforced; no confidential data in Git history.
- [ ] **ML:** all 3 core models complete; baselines documented; test set isolated; calibration evaluated; threshold optimized; uncertainty implemented; slice evaluation + error analysis completed.
- [ ] **Anti-leakage:** timestamps documented; forbidden features documented; leakage tests pass.
- [ ] **MLOps:** MLflow tracking; versioned model metadata; drift monitoring; retraining policy documented; monitoring report available.
- [ ] **Engineering:** modular `src/`; shared train/serve pipeline; FastAPI contracts; Docker builds; no secrets; valid `pyproject.toml` + lock file.
- [ ] **Testing:** unit, integration, leakage, API, monitoring tests pass; coverage ≥ 85%.
- [ ] **CI/CD:** lint, format, type-check, tests, coverage gate all pass in GitHub Actions.
- [ ] **Documentation:** README, architecture, data dictionary, privacy, leakage policy, model card, monitoring doc, limitations, runbook, interview guide, minimum ADR set — all complete.
- [ ] **Git evidence:** ≥ 30 meaningful commits (target 60–85), ≥ 12 meaningful PRs, issues demonstrating planning, English-only messages, `v1.0.0` release published, `CHANGELOG.md` updated.
- [ ] **Cost:** USD 0 recurring hosting; no paid database, API, monitoring SaaS, or LLM; optional cloud experiments not required for the live demo.

---

## 55. 10/10 Portfolio Scoring Rubric

| Dimension | Weight | 10/10 evidence |
|---|---|---|
| Business framing | 10% | Clear decisions, users, costs, assumptions |
| Data design | 10% | Contracts, provenance, privacy, realistic generation |
| Statistical rigor | 15% | Baselines, temporal split, leakage control, uncertainty |
| ML quality | 10% | Model comparison, tuning, calibration, threshold |
| Engineering | 15% | Modular package, typing, clean interfaces, Docker |
| Testing | 10% | ≥85% meaningful coverage, integration/leakage tests |
| MLOps | 10% | Tracking, versioning, drift, retraining policy |
| Production | 5% | Working public deployment |
| Documentation | 10% | README, model card, ADRs, runbook |
| Git process | 5% | Issues, PRs, meaningful commits, releases |

**Target: ≥ 90/100.** A weak score in statistical rigor, testing, or anti-leakage cannot be compensated by a beautiful UI.

## 56. Prohibited Practices (hard "never" list)
Never: commit proprietary company data · build entirely in notebooks · use future data in features · tune/calibrate/select thresholds on the final test set · claim causality from correlation · claim "enterprise-ready" without evidence · claim untested production scale · manufacture meaningless commits or fake Git history · hard-code metrics in the README · publish screenshots that don't match the current release · hide paid infrastructure as a dependency · create unnecessary microservices · add technologies just to pad the stack list · prioritize framework count over correctness.

## 57. What a Reviewer Should Conclude
That the author: understands construction economics and project controls; can translate domain knowledge into predictive features; understands temporal leakage and unbiased evaluation; can build calibrated decision-support models; understands uncertainty and business-cost trade-offs; writes modular, tested Python; understands production interfaces and train/serve consistency; uses CI and disciplined Git workflows; understands monitoring and retraining; communicates limitations instead of hiding them; and can clearly distinguish a free portfolio deployment from an enterprise reference architecture.

---

## 58. Initial Backlog — First 30 Issues

```
#1  Define business targets and prediction timestamps      #16 Add MLflow experiment tracking
#2  Create repository architecture                          #17 Implement probability calibration
#3  Document public-data and privacy strategy                #18 Implement business-cost threshold optimization
#4  Implement project data contracts                         #19 Add prediction uncertainty
#5  Build deterministic synthetic portfolio generator         #20 Build model evaluation & error-analysis report
#6  Implement EVM calculation engine                          #21 Add SHAP explainability
#7  Add inflation-adjustment feature layer                    #22 Implement drift monitoring
#8  Create temporal snapshot feature pipeline                 #23 Build FastAPI inference contracts
#9  Add automated leakage checks                              #24 Build executive Streamlit application
#10 Implement chronological/grouped data split                #25 Add model health dashboard
#11 Establish classification baselines                        #26 Add Docker image
#12 Establish regression baselines                            #27 Build GitHub Actions CI
#13 Train initial cost-overrun model                          #28 Add security and dependency checks
#14 Train initial schedule-delay model                        #29 Complete model card and runbook
#15 Train initial final-cost model                            #30 Deploy and release v1.0.0
```

---

## 59. Zero-Cost Infrastructure Notes (verify before deploying)
As of August 2026, the design is compatible with: GitHub Actions standard hosted runners for public repos; Streamlit Community Cloud; local/file-based MLflow; open-source Python libraries; packaged artifacts in-repo or as release assets when size permits. Free-tier policies change — **re-verify current limits immediately before deployment** and keep the mandatory public path independent of any paid infrastructure.

## 60. Final Positioning Statement

> BuildGuard AI is a production-oriented Construction Risk Intelligence platform that combines Earned Value Management, inflation-adjusted cost analytics, leakage-safe machine learning, calibrated risk scoring, probabilistic final-cost forecasting, explainability, and model monitoring to help construction and real-estate teams identify cost and schedule risk earlier.

**Subtitle:** Production-oriented ML for construction cost, schedule risk, and project forecasting.
**Tags:** `machine-learning` `data-science` `mlops` `construction` `proptech` `cost-control` `earned-value-management` `lightgbm` `fastapi` `streamlit` `mlflow` `shap` `model-monitoring`

## 61. Final Rule

Do not optimize BuildGuard AI for the number of technologies listed in the README. Optimize it for the quality of the answers to:

> Why was this architecture chosen? Why is this split leakage-safe? Why is this metric appropriate? Why should the probability be trusted? Why is this threshold useful to the business? Where does the model fail? How would you detect degradation? How can another engineer reproduce the result? What is actually deployed? What would change at enterprise scale?

If every answer is technically rigorous, evidenced by the repository, and clearly documented, BuildGuard AI functions as a credible Senior Data Scientist portfolio project — not a showcase demo.

---

**Project Status**
Specification: READY
Implementation: NOT STARTED / MIGRATION FROM GETEC ANALYTICS
Target Release: v1.0.0
Target Quality: Senior Data Scientist — International Portfolio
Recurring Production Cost: USD 0.00
