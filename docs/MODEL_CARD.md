# Model Card — BuildGuard AI

**BuildGuard AI is decision support, not an autonomous decision-maker.**
Every output on this card is a probability or a point forecast with an
uncertainty interval, meant for a human reviewer to weigh alongside
context the model does not have — never a verdict.

## Overview

| | |
|---|---|
| Project | BuildGuard AI |
| Owner | Renan ([pinheiro-dataworks](https://github.com/pinheiro-dataworks/buildguard-ai)) |
| App version | see `GET /version` (live `app_version`/`data_version`) |
| Models | `cost_overrun` (classifier), `schedule_delay` (classifier), `final_cost` (regressor) |
| Training/evaluation data | Deterministic synthetic construction portfolio, 400 projects ([ADR-0004](adr/0004-synthetic-data-design.md)) — **no real client or project data** |

## Intended use

Triage-level risk signals for a construction portfolio: which projects
are most likely to overrun their budget, miss their schedule, and what
their expected final cost is, with the model's own drivers surfaced for
each prediction (SHAP, Section 20). Intended for a human reviewer
(project controls, PM office) deciding what to investigate first — not
for automated action.

## Out-of-scope use

- **Not validated on real-world data.** Every metric on this card comes
  from the synthetic portfolio's held-out test split (see
  [`LIMITATIONS.md`](LIMITATIONS.md) Section 1). Do not treat these
  numbers as evidence of real-deployment performance without separate
  validation.
- **Not an autonomous decision-maker.** No prediction here should trigger
  an automated financial, contractual, or personnel action.
- **Not for legal, audit, or compliance determinations** about individual
  projects or the people responsible for them.
- **Not causal.** Feature attribution (SHAP, permutation importance)
  explains what drove a *prediction*; it does not establish what would
  change the *outcome* if intervened on.

## Features

Shared input schema (`src/buildguard/models/preprocessing.py`), built by
`buildguard.features.pipeline.build_feature_table` — the same function
used for training, batch scoring, and the live API (Section 28):

- **Numeric (20):** `gross_floor_area_m2`, `number_of_towers`,
  `number_of_units`, `cpi`, `spi`, `cost_variance`, `schedule_variance`,
  `inflation_multiplier`, `operational_variance`, `inflation_component`,
  `months_since_start`, `months_to_planned_completion`,
  `lifecycle_fraction`, `cpi_trend`, `spi_trend`, `cpi_decline_streak`,
  `spi_decline_streak`, `change_order_count_to_date`,
  `change_order_amount_to_date`, `change_order_amount_ratio_to_date`.
- **Categorical (3):** `project_type`, `construction_standard`,
  `lifecycle_stage`.

Full column-level reference: [`DATA_DICTIONARY.md`](DATA_DICTIONARY.md).
Anti-leakage guarantees: [`LEAKAGE_POLICY.md`](LEAKAGE_POLICY.md).

## Models, metrics, and calibration

Test-split results below are the **one** final evaluation this project
allows itself per Section 12/[ADR-0003](adr/0003-temporal-validation.md)
— measured on 752 rows / 41 projects never touched before that run.

### `cost_overrun` — Random Forest classifier

| | |
|---|---|
| Calibration | Isotonic (Brier 0.122 in-sample → 0.113 test) |
| Decision threshold | 0.080 (business-cost optimized, [ADR-0008](adr/0008-threshold-policy.md)) |
| Test ROC-AUC / PR-AUC | 0.9495 / 0.9008 |
| Test precision / recall @ threshold | 55.1% / 97.4% |
| Weakest subgroup | `ES` state, AUC 0.597 (n=76) — see [`LIMITATIONS.md`](LIMITATIONS.md) |

### `schedule_delay` — LightGBM classifier

| | |
|---|---|
| Calibration | Isotonic (Brier 0.059 in-sample → **0.145 test**) |
| Decision threshold | 0.140 (business-cost optimized) |
| Test ROC-AUC / PR-AUC | 0.9002 / 0.8949 |
| Test precision / recall @ threshold | 72.5% / 92.9% |
| Known issue | Out-of-sample calibration/AUC degradation — see [`LIMITATIONS.md`](LIMITATIONS.md) |

### `final_cost` — Deterministic EAC (`BAC / CPI`)

| | |
|---|---|
| Type | Formula baseline, not a fitted model ([ADR-0006](adr/0006-model-selection.md)) |
| Uncertainty | Split-conformal 80% interval, quantile ≈ $3.09M ([ADR-0009](adr/0009-uncertainty-method.md)) |
| Test MAE / RMSE / R² | $1.61M / $3.03M / 0.959 |
| Test empirical coverage | 89.9% (target 80% — conservative) |

Full numbers: `reports/experiments/test_set_metrics.json`. Full failure
analysis (false negatives/positives, SHAP drivers, hardest subgroups,
largest errors): `reports/error_analysis/`.

## Known limitations and risk considerations

See [`LIMITATIONS.md`](LIMITATIONS.md) for the complete list. The two
that most directly affect how a prediction should be trusted:
`cost_overrun`'s weak `ES`-state subgroup, and `schedule_delay`'s
out-of-sample calibration gap. The business cost matrix
(`configs/business.yaml`) values missing a real overrun/delay far above
a false alarm (10x for cost, 8x for schedule) — both classifiers'
thresholds are deliberately tuned toward high recall, low precision as a
result ([ADR-0008](adr/0008-threshold-policy.md)); expect roughly 4-5
false alarms for every true positive investigated.

## Drift policy and retraining criteria

Full detail: [`MONITORING.md`](MONITORING.md). Summary: `make monitor`
computes data quality, feature/prediction drift (PSI/KS/Wasserstein), and
performance-vs-baseline comparisons against the real portfolio and
champions. Four of Section 24's six retraining triggers are computed for
real (PSI above threshold, performance drop, calibration deterioration,
schema changes); two are calendar/volume-driven policy, not computed by
a single run. **Retraining is never automatic** — every trigger requires
a human to run Detect → Investigate → Validate → Retrain → Compare →
Approve → Release; `scripts/monitor.py` has no code path that calls
`scripts/train.py`.

## Human-oversight requirements

- Every prediction response carries its calibration method and decision
  threshold (never a bare score) and, for `final_cost`, an explicit
  uncertainty interval.
- A human must review any prediction flagged out-of-distribution, near
  the decision threshold, or in a subgroup `reports/error_analysis/`
  identifies as weak (Section 47).
- A fired retraining trigger requires human investigation before any
  retraining action — see Drift policy above.
- The mandatory causality disclaimer ("Feature attribution explains the
  model prediction; it does not establish causality") is shown on every
  explanation-bearing surface (Project Diagnostic, Scenario Simulator).
