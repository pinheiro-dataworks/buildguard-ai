# Limitations

Every item here is a real, measured finding from this project's own runs
(ADRs and `reports/`), not a hedge added for appearances — Section 18's
rule ("a high global metric with poor subgroup behavior must be
documented, not hidden") applies to this whole document, not just slice
analysis.

## 1. Synthetic data only — no real-world validation

Every number in this repository is measured on a deterministic synthetic
portfolio (`src/buildguard/data/synthetic.py`, [ADR-0004](adr/0004-synthetic-data-design.md)),
not real client or project data. The realism relationships (EVM dynamics,
inflation exposure, change-order patterns) are constructed to be
plausible, not fit to observed real-world distributions. Metrics here
describe how well the models learn *this* synthetic generator's patterns
— they say nothing about performance on a real construction portfolio
until validated against one.

## 2. `cost_overrun` has a materially weak geography subgroup

Global test-set ROC-AUC is 0.9495, but the `ES` state slice (n=76) scores
0.597 — close to random. See [ADR-0010](adr/0010-evaluation-explainability-design.md)
and `reports/error_analysis/cost_overrun_failure_analysis.md`. A
prediction for a project in this state should be treated as
low-confidence regardless of the reported probability.

## 3. `schedule_delay`'s calibration degrades out-of-sample

Isotonic calibration won on the calibration split (Brier 0.059) but
degrades to 0.145 on the genuinely held-out test split — a real
generalization gap, not measurement noise. The same task's ROC-AUC drops
from 0.974 (calibration-split baseline) to 0.900 (test) and recall from
98.4% to 92.9%. See [ADR-0010](adr/0010-evaluation-explainability-design.md),
[ADR-0011](adr/0011-monitoring-drift-detection.md). Notably, this
degradation was **not visible in prediction drift** (PSI ~0.002) — only
label-dependent performance monitoring caught it, which is itself a
limitation of drift-only monitoring in a production setting where labels
lag behind predictions.

## 4. `final_cost`'s uncertainty interval is wider than necessary

The 80%-target conformal interval achieves 89.9% empirical coverage on
the test split — safe, but conservative. The interval is symmetric
around the point forecast; [ADR-0009](adr/0009-uncertainty-method.md)
flagged asymmetric intervals as a candidate refinement if residuals turn
out skewed, which this result suggests they may be.

## 5. `final_cost`'s champion has no learned explanation

The champion is `BAC / CPI` ([ADR-0006](adr/0006-model-selection.md)), a
formula, not a fitted model. No SHAP or permutation-importance
explanation applies to it — the formula itself is the explanation, but
that also means it cannot express interaction effects a learned model
might capture, and its two tuned-model competitors (LightGBM, Random
Forest) both scored worse on the calibration split.

## 6. Work Packages and Suppliers are excluded from features entirely

Both tables represent status "as of the project's last snapshot," not a
real per-row time series ([`LEAKAGE_POLICY.md`](LEAKAGE_POLICY.md)
Section 6). Including them as-is would leak each project's *final* state
into every *earlier* prediction. They are excluded rather than included
unsafely — meaning supplier performance and work-package-level detail
play no role in any prediction today, even though they are plausibly
informative.

## 7. Operational monitoring has no live traffic yet

`monitoring.performance.measure_inference_latency` reports real, measured
latency, but request volume and error rate stay unpopulated until the
FastAPI service has real production traffic — there is no deployed
public instance yet. See [`MONITORING.md`](MONITORING.md) Section 5.

## 8. The custom Streamlit sidebar router has no per-page URLs

Chosen over `st.navigation()` after that API's sidebar nav proved unable
to render below the logo/title as the design spec requires
([ADR-0012](adr/0012-streamlit-fastapi-boundary.md)). The trade-off:
no deep-linking to a specific page and no browser back-button support
for in-app navigation.

## 9. Business impact is not yet quantified

Section 21's decision-support value estimate (active projects × exposure
× overrun prevalence × recall × avoidable-impact assumption) has not
been computed or documented yet — tracked as pending in `README.md`
Section 11.

## 10. Feature drift between train and test is real, but expected

`make monitor`'s real run found 10 of 23 features significantly drifted
between the train and test splits (dominated by `inflation_multiplier`
and `months_since_start`). This is the expected signature of the
chronological anti-leakage split itself, not a data defect — but it does
mean any single PSI alert needs the same investigation step Section 24
requires before being read as a problem. See
[ADR-0011](adr/0011-monitoring-drift-detection.md) and
[`MONITORING.md`](MONITORING.md) Section 3.
