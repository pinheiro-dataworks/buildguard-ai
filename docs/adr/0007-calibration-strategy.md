# ADR-0007: Probability Calibration Strategy

**Status:** Accepted

## Context

Section 16 requires comparing raw vs. Platt/sigmoid vs. isotonic
calibration on data separate from the final test set, and requires
answering: "when BuildGuard says 70% risk, is that probability
approximately trustworthy?" A tree-ensemble classifier's raw
`predict_proba` output is a score, not a guaranteed-calibrated
probability -- Random Forest and LightGBM are both well known to produce
systematically over- or under-confident probabilities depending on
depth/leaf-size settings, which is exactly what Section 16 exists to catch
and correct.

## Decision

`src/buildguard/models/calibration.py: evaluate_calibration_methods()`
fits both calibration methods directly on `(raw_probability, label)`
pairs from the **calibration** split (never train, never test -- Section
12):

- **Sigmoid (Platt scaling)**, implemented as a one-feature
  `LogisticRegression` fit on the raw probability -- the textbook
  definition of Platt scaling, using a public, stable sklearn API rather
  than sklearn's private `_SigmoidCalibration` class or the
  `CalibratedClassifierCV`/`FrozenEstimator` wrapping route (see
  Alternatives -- that route was tried first and rejected).
- **Isotonic**, via `sklearn.isotonic.IsotonicRegression`.

Both are compared against the raw ("none") probabilities by Brier score;
`"none"` wins whenever calibration doesn't actually help, so calibration
is never forced on for its own sake.

**Real results (calibration split, full portfolio):**

| Task | Raw Brier | Sigmoid Brier | Isotonic Brier | Chosen |
|---|---|---|---|---|
| `cost_overrun` | 0.1327 | 0.1327 | **0.1223** | Isotonic |
| `schedule_delay` | 0.0723 | 0.0621 | **0.0592** | Isotonic |

Isotonic won both tasks -- a modest but real improvement on
`cost_overrun` (~8% Brier reduction) and a larger one on `schedule_delay`
(~18%). The calibrated model (an isotonic mapping composed with the
champion classifier) replaces the raw champion as the production artifact
in `models/*_champion.joblib`.

## Alternatives Considered

- **`CalibratedClassifierCV` wrapping the model via
  `sklearn.frozen.FrozenEstimator`** -- tried first, matching the modern
  sklearn-documented replacement for the deprecated `cv="prefit"` pattern.
  Rejected after hitting a concrete failure: `CalibratedClassifierCV`
  internally calls `cross_val_predict`, which requires the wrapped object
  to be a full sklearn estimator implementing both `fit` *and* `predict`.
  BuildGuard's own baselines (`buildguard.models.baselines`) only
  implement `predict_proba` (by design -- see their module docstring), so
  wrapping a baseline this way raises `InvalidParameterError` outright.
  Since a baseline can legitimately be a task's champion (it is, for
  `final_cost` -- ADR-0006), the calibration method had to work uniformly
  for baselines and real sklearn pipelines alike. This is the second time
  in this project a "must be a proper sklearn estimator" assumption broke
  on a custom baseline class (the first was MLflow's `sklearn.log_model`,
  Session H) -- calibrating directly on the probability output sidesteps
  the whole class of problem rather than patching around it again.
- **Only report Brier score, skip the calibration curve** -- rejected;
  Section 16 explicitly asks for the calibration curve, and a single
  scalar can hide *where* in probability space a model is miscalibrated
  (e.g. well-calibrated at low risk, overconfident at high risk).
  `CalibrationCurve.mean_predicted_value`/`fraction_of_positives` (10 bins
  by default) are computed and stored for exactly this reason, even though
  this ADR only tabulates the summary Brier scores.
- **Expected Calibration Error (ECE) instead of / alongside Brier score**
  -- Section 16 marks ECE optional ("(optionally) ECE"). Not implemented:
  Brier score alone was sufficient to make the sigmoid-vs-isotonic
  decision here, and adding a second metric with no disagreement to
  resolve would not have changed the outcome.

## Consequences

- `models/cost_overrun_champion.joblib` and
  `models/schedule_delay_champion.joblib` are now `CalibratedModel`
  wrappers (`buildguard.models.calibration.CalibratedModel`), not the raw
  Random Forest / LightGBM pipelines from ADR-0006 -- any code loading
  these artifacts must only ever call `.predict_proba(features)`, exactly
  as before; the wrapper is transparent to callers.
- Like ADR-0006's results, Brier scores here are measured in-sample on the
  same calibration-split rows the mapping was fit on (Section 12's
  CALIBRATION block is exactly where this fitting happens) -- genuinely
  held-out calibration quality is confirmed only at the one final test
  evaluation, a later phase.
- Any future model retrained for these tasks must re-run this comparison
  -- calibration quality is a property of a specific fitted model, not
  something that transfers across retraining.
