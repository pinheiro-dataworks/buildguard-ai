# ADR-0010: Held-Out Evaluation, Explainability & Failure Analysis Design

**Status:** Accepted

## Context

Three requirements converge on the same moment in the project: Section 18
mandates slice analysis across six dimensions ("a high global metric with
poor subgroup behavior must be documented, not hidden"); Section 20
mandates global/local SHAP explanations with a fixed causality disclaimer;
Section 47 mandates a senior-level failure analysis (false negatives,
false positives, largest regression errors, low-confidence predictions,
out-of-distribution examples) answering specific questions about which
project types, lifecycle stages, and inflation regimes are hardest.

All three need the same thing to be honest: the **test split**, untouched
since ADR-0003, used for exactly the one evaluation it was reserved for.
Everything up to this point (training, calibration, threshold selection,
conformal quantile fitting) deliberately never touched it. This ADR covers
the design of the module that finally does.

## Decision

**Separate measurement from fitting/selection.** `evaluation/classification.py`,
`evaluation/regression.py`, and `evaluation/calibration.py` only compute
metrics on a `(y_true, prediction)` pair the caller supplies -- they never
fit a calibrator, select a threshold, or pick a champion. That already
happened in `models/calibration.py` (Section 16) and `models/thresholds.py`
(Section 17) on the calibration split; this module answers a narrower
question: given those already-frozen decisions, how do they hold up on
data that never influenced them. `evaluation/calibration.py` in particular
exists specifically to close a limitation `models/calibration.py`'s own
docstring flags: its Brier score is measured in-sample, on the same
calibration rows the mapping was fit on.

**Seven slice dimensions**, not six: the mandatory Section 18 set (project
type, project size, construction standard, lifecycle stage, geography,
budget segment) plus an `inflation_regime` dimension (a 3-way quantile
bucket of `inflation_multiplier`), added specifically to give Section 47's
"does inflation regime change performance" question a real, computed
answer rather than a qualitative guess. Size, budget, and inflation regime
are continuous, so all three are bucketed with the same
`slices.bucket_by_quantile` (tercile split) used for lifecycle-stage-style
categorical slicing elsewhere.

**ROC-AUC as the slice metric for classification tasks**, MAE (plus mean
signed error, to separate noise from directional bias) for `final_cost`.
ROC-AUC was chosen over PR-AUC for cross-slice comparability: PR-AUC's own
baseline shifts with each slice's positive rate, which would make two
slices' scores not directly comparable to each other; ROC-AUC's 0.5
baseline is constant regardless of class balance.

**Out-of-distribution flagging via a per-feature train-range envelope**:
a test row is flagged if any `NUMERIC_FEATURE_COLUMNS` value falls outside
`[train.min(), train.max()]` for that column. Deliberately the simplest
thing that works, not a learned novelty detector -- Section 47 asks what a
*human reviewer* should check, and a reviewer can audit "this CPI is
outside the range the model ever trained on" at a glance in a way an
IsolationForest score cannot be sanity-checked at all.

**Near-threshold band (+/-0.05) as the "low-confidence" definition**,
not a band around 0.50. Both classifiers' optimized thresholds (Section
17) sit far from 0.50 by design (0.080 for `cost_overrun`, 0.140 for
`schedule_delay`) because the business cost matrix (`configs/business.yaml`)
values recall far above precision -- the actual decision boundary a human
reviewer should distrust the most is the one the system actually uses to
decide, not the geometric center of `[0, 1]`.

**Failure-analysis reports are generated code, not hand-authored prose.**
`scripts/evaluate.py` renders `reports/error_analysis/*.md` directly from
the same computed arrays that populate `reports/experiments/test_set_metrics.json`
-- every number in the narrative comes from one deterministic run
(fixed seed), so re-running `make evaluate` after retraining regenerates
both files in lockstep. Nothing in either file is transcribed by hand.

### Real results (test split, 752 rows / 41 projects, none seen before this run)

```
cost_overrun:    ROC-AUC 0.9495  PR-AUC 0.9008  precision 0.551  recall 0.974
                 Brier (holdout) 0.1129  vs. Brier (in-sample, ADR-0007) 0.1223
schedule_delay:  ROC-AUC 0.9002  PR-AUC 0.8949  precision 0.725  recall 0.929
                 Brier (holdout) 0.1452  vs. Brier (in-sample, ADR-0007) 0.0592
final_cost:      MAE $1,607,528  RMSE $3,032,636  R2 0.959  MAPE 7.0%
                 conformal coverage (holdout) 0.899  vs. target 0.80
                 (vs. in-sample coverage 0.801, ADR-0009)
```

Two genuine findings this run surfaces that were previously only
theoretical risks flagged in earlier ADRs:

- **`schedule_delay`'s isotonic calibration does not fully generalize.**
  ADR-0007 selected isotonic by in-sample Brier (0.0592); out-of-sample it
  degrades to 0.1452 -- worse than `cost_overrun`'s corresponding
  degradation (0.1223 -> 0.1129, which if anything improved). This is
  visible directly in the holdout calibration curve
  (`reports/experiments/test_set_metrics.json:tasks.schedule_delay.holdout_calibration`):
  several mid-range probability bins land 20-30 points off the diagonal.
  Isotonic regression's step-function flexibility, which won it the
  in-sample comparison, is also what makes it more prone to overfitting
  the calibration split's specific quirks than the smoother sigmoid
  mapping.
- **`cost_overrun` is materially weaker in one geography.** The `state`
  slice's worst value is `ES` at AUC 0.597 (n=76) -- close to random,
  against a global AUC of 0.9495 (`reports/error_analysis/cost_overrun_failure_analysis.md`).
  This is exactly the "high global metric, poor subgroup behavior" case
  Section 18 requires documenting rather than hiding.

Both findings are real, reproducible (`make evaluate` regenerates them
identically under the fixed seed), and neither was fabricated after the
fact -- they are why this ADR exists rather than a plain "explainability
added" note.

## Alternatives Considered

- **Compute slice metrics on the calibration split instead of test** --
  rejected. The calibration split was already used to fit calibrators and
  select thresholds; scoring slices there would repeat the same in-sample
  optimism ADR-0007 explicitly flags, defeating Section 47's purpose.
- **A learned novelty/outlier detector for out-of-distribution flagging**
  (e.g. `IsolationForest`, Mahalanobis distance) -- more statistically
  principled but opaque to the human reviewer Section 47 is written for;
  a per-feature range check is auditable without trusting a second model.
- **Static Plotly/matplotlib figures in `reports/figures/` for the
  calibration curves and slice tables** -- deferred, not rejected. The
  Streamlit dashboard (Phase 8) is `plotly`'s actual intended home in this
  project and will render these same numbers interactively; building a
  static-image version now would be thrown away once Phase 8 lands.
- **Explaining the calibrated probability directly (differentiate through
  the isotonic/sigmoid calibrator)** -- rejected, consistent with
  `explainability/shap.py`'s own module docstring: the calibration mapping
  is a monotonic 1-D transform of the base score, so it changes probability
  *scale* but never *which* features drove the prediction; explaining the
  pre-calibration score is both correct and far simpler.

## Consequences

- `schedule_delay`'s out-of-sample calibration gap and `cost_overrun`'s
  `ES`-state weakness are now documented findings, not open questions --
  both must be carried forward into `docs/LIMITATIONS.md` and
  `docs/MODEL_CARD.md` once those are written (Session N), not left
  sitting only in `reports/error_analysis/`.
- `final_cost`'s holdout coverage (0.899) running above its 0.80 target
  means the conformal interval is currently wider than the guarantee
  strictly requires -- conservative, not incorrect, but a concrete
  candidate for ADR-0009's deferred "asymmetric interval" alternative if a
  future session revisits uncertainty quantification.
- Every number in this ADR and in `reports/error_analysis/*.md` traces back
  to one `make evaluate` run against `git_sha` recorded in
  `reports/experiments/test_set_metrics.json` -- retraining the champions
  invalidates these specific figures until `make evaluate` is re-run, and
  this ADR's "Real results" block should be refreshed at that point rather
  than left stale.
