# Requirements

What BuildGuard AI is expected to do, for whom, and under which technical
constraints. Each requirement links to where it is implemented or to the
ADR that records how it was met. Results against these requirements live in
the [README](../README.md), the [model card](MODEL_CARD.md), and
[`reports/`](../reports/).

## 1. Product scope

BuildGuard AI is a **decision-support** tool for construction cost and
schedule risk. It does not make high-stakes financial decisions on its own,
and nothing it outputs is a guarantee of a project outcome.

It answers five questions for a construction portfolio:

1. Which projects are most likely to exceed their approved budget?
2. Which projects are most likely to miss their contractual schedule?
3. What is the expected final cost of each project?
4. What factors are currently driving the risk?
5. What should management investigate first?

### Users

| User | Needs |
|---|---|
| Executive leadership | Portfolio overview, overrun/delay probability, expected final cost, exposure, top drivers, ranking, confidence intervals |
| Construction / engineering management | CPI/SPI, deviation trends, actionable alerts |
| Planning & cost control | EVM metrics over time, forecast accuracy, model diagnostics |
| Data / ML teams | Pipeline traceability, model version, experiment history, feature definitions, drift metrics, reproducible training |

## 2. Prediction tasks

| Task | Type | Label | Output |
|---|---|---|---|
| Cost-overrun risk | Binary classification | `cost_overrun = real_final_cost > approved_budget × (1 + tolerance)` | Calibrated probability, risk band, SHAP drivers |
| Schedule-delay risk | Binary classification | `schedule_delay = actual_completion > planned_completion + tolerance_days` | Calibrated probability, risk band, SHAP drivers |
| Final cost (estimate at completion) | Regression | `final_cost_real` (inflation-adjusted, in original-budget dollars) | Point estimate plus an 80% prediction interval |

Tolerances are configurable in `configs/base.yaml: targets`. The cost label
is computed against the **inflation-adjusted** final cost, not the nominal
one — see [ADR-0004](adr/0004-synthetic-data-design.md) for the finding that
forced this choice.

Explicitly out of scope for the current version: survival / time-to-delay
modeling, supplier-level risk, change-order risk, anomaly detection, and a
combined management-priority score. None of them may be added at the cost of
the three core tasks.

## 3. Data

- **No confidential data.** The public repository and the deployed app run
  only on a deterministic synthetic portfolio
  ([ADR-0002](adr/0002-data-privacy-strategy.md),
  [`DATA_PRIVACY.md`](DATA_PRIVACY.md)).
- **Scale of the synthetic portfolio:** 100–500 projects, monthly
  snapshots, 20–80 work packages per project, a shared pool of 100–1,000
  suppliers. The current build uses 400 projects
  (`configs/base.yaml: synthetic_data`).
- **Realism relationships the generator must reproduce:** poor CPI raises
  cost-overrun risk; persistent SPI deterioration raises delay risk; more
  change orders raise final cost; procurement delays affect schedule;
  inflation raises nominal cost; high spend with low physical progress is a
  risk signal; supplier concentration raises exposure; risk evolves over
  the project lifecycle ([ADR-0004](adr/0004-synthetic-data-design.md)).
- **Core tables:** Projects, Project Snapshots, Work Packages, Change
  Orders, Suppliers, Economic Index ([`DATA_DICTIONARY.md`](DATA_DICTIONARY.md)).
- **Data contracts:** non-null keys, valid dates, `approved_budget > 0`,
  `actual_cost >= 0`, progress in `[0, 1]`, `earned_value >= 0`,
  chronological consistency, unique `project_id + snapshot_date`. A
  violation raises an error; values are never silently coerced
  (`src/buildguard/data/contracts.py`).
- **Economic indices** are read only through the `EconomicIndexProvider`
  interface. The public app runs on `DemoIndexProvider`; a real index needs
  a verified redistribution license first.

## 4. Domain analytics

- **Earned Value Management:** CV, SV, CPI, SPI, two independent EAC
  baselines (CPI-based and a schedule-adjusted composite), ETC, VAC. Every
  ratio handles a zero denominator explicitly
  ([`ARCHITECTURE.md`](ARCHITECTURE.md#4-evm-methodology)).
- **Inflation normalization:** nominal cost variance is split into an
  execution (operational) component and an inflation component. Reports and
  UI call this an *estimated* inflation-adjusted variance; it is not an
  exact causal decomposition.

## 5. Modeling and evaluation

- **No temporal leakage.** A prediction made at month `t` uses only data
  available on or before `t`. Forbidden: final cost, future change orders,
  future supplier delays, final completion status, future index values,
  whole-lifecycle aggregates, target-derived features. Enforced by
  automated tests ([`LEAKAGE_POLICY.md`](LEAKAGE_POLICY.md)).
- **Split design.** Chronological, project-grouped train (60%) /
  calibration (20%) / test (20%). The test split is used exactly once, for
  the final evaluation — never for tuning, calibration, threshold selection,
  or model comparison ([ADR-0003](adr/0003-temporal-validation.md)).
- **Baselines first.** Every model has to beat a meaningful
  construction-management baseline (a CPI rule, the deterministic EVM EAC),
  not only a naive statistical one.
- **Model choice is justified, not exhaustive.** Candidates are compared on
  performance, complexity, interpretability, and latency
  ([ADR-0006](adr/0006-model-selection.md)). Hyperparameter search uses
  Optuna on the train split only, with grouped cross-validation.
- **Calibration.** Raw, sigmoid, and isotonic calibration are compared on
  the calibration split by Brier score
  ([ADR-0007](adr/0007-calibration-strategy.md)).
- **Thresholds.** Never a silent 0.50. Thresholds minimize expected cost
  under the cost matrix in `configs/business.yaml`
  ([ADR-0008](adr/0008-threshold-policy.md)).
- **Uncertainty.** The final-cost estimate ships with a prediction interval
  whose coverage is measured empirically
  ([ADR-0009](adr/0009-uncertainty-method.md)).
- **Metrics.** Classification: ROC-AUC, PR-AUC, precision, recall, F1,
  Brier score, confusion matrix, calibration curve. Regression: MAE, RMSE,
  R², MAPE/SMAPE, and error in business terms (median dollar and percentage
  error).
- **Slice analysis.** Project type, size, construction standard, lifecycle
  stage, geography, and budget segment. A strong global metric with a weak
  subgroup is reported, not hidden.
- **Failure analysis.** False negatives, false positives, largest
  regression errors, low-confidence and out-of-distribution predictions,
  with what a human reviewer should check
  ([`reports/error_analysis/`](../reports/error_analysis/)).
- **Explainability.** Global (SHAP and permutation importance) and local
  (per-prediction SHAP) explanations. Every explanation surface carries the
  disclaimer *"Feature attribution explains the model prediction; it does
  not establish causality."*
- **Business impact.** Reported only as a scenario-based estimate with every
  assumption visible — never as realized savings.

## 6. Serving and monitoring

- **Train/serve consistency.** Training, batch scoring, and the API all
  build features through the same function
  (`buildguard.features.pipeline.build_feature_table`).
- **API.** `GET /health`, `GET /version`, `POST /predict/cost-risk`,
  `POST /predict/schedule-risk`, `POST /predict/final-cost`, with Pydantic
  validation and model metadata in every response. Invalid input fails as a
  `422`, never as a crash.
- **App.** Executive Overview, Project Diagnostic, Scenario Simulator
  (what-if only, explicitly not causal), Model Performance, Model Health,
  About / Governance. The app may call the prediction functions in-process;
  the API must remain independently runnable
  ([ADR-0012](adr/0012-streamlit-fastapi-boundary.md)).
- **Monitoring.** Data quality, data drift (PSI, KS, Wasserstein — chosen
  per variable type), prediction drift, performance when labels exist, and
  operational signals (latency, model version)
  ([`MONITORING.md`](MONITORING.md)).
- **Retraining.** Triggered by a policy, never automatically because drift
  exists: Detect → Investigate → Validate data → Retrain candidate →
  Compare against champion → Approve → Release.
- **Experiment tracking.** MLflow with a local SQLite backend; every run
  records parameters, metrics, data version, and git SHA.

## 7. Non-functional requirements

| Requirement | Target |
|---|---|
| Single-prediction latency | p95 < 500 ms on a local CPU |
| Model artifact size | < 100 MB in total |
| Test coverage on `src/buildguard` | ≥ 85% (enforced in CI) |
| Recurring hosting cost | USD 0 — no paid database, model endpoint, LLM, or monitoring SaaS ([ADR-0013](adr/0013-zero-cost-deployment.md)) |
| Reproducibility | Fixed seeds, pinned dependencies (`uv.lock`), Python 3.11, no machine-specific paths |
| Code quality | Ruff lint and format, `mypy --strict`, typed public APIs, configuration in `configs/` rather than magic numbers |
| Security | No secrets in Git, dependency and static-analysis scans in CI ([`SECURITY.md`](../SECURITY.md)) |
| Language | English throughout code, docs, and UI; domain terms such as INCC are explained in English |

## 8. Responsible use

- The UI says *"estimated risk"*, never *"the project will overrun."*
- Human review is required before any action on a prediction.
- Out-of-domain inputs, incomplete data, and model degradation are
  documented in [`LIMITATIONS.md`](LIMITATIONS.md) and the
  [model card](MODEL_CARD.md).
