# ADR-0009: Final-Cost Uncertainty Method

**Status:** Accepted

## Context

Section 19 requires at least one valid uncertainty-quantification method
for the final-cost forecast (conformal prediction, quantile regression, or
bootstrap interval), with empirically evaluated coverage. This task's
particular constraint (ADR-0006): the `final_cost` champion is
`DeterministicEacBaseline` -- a zero-parameter closed-form formula
(`BAC / CPI`), not a fitted regressor. Quantile regression is not directly
applicable to a model with no notion of predictive distribution to begin
with, and refitting a *different* model purely to get quantiles would mean
shipping uncertainty bounds for a forecast nobody is actually using.

## Decision

**Split conformal prediction**
(`src/buildguard/models/uncertainty.py: fit_conformal_quantile()`),
because it is model-agnostic: it only needs a stream of `(actual, point
prediction)` pairs, regardless of whether those predictions came from a
formula or a fitted model. On the **calibration** split (never train,
never test -- Section 12):

1. Compute absolute residuals `|actual - predicted|` for every calibration
   row.
2. Take the `ceil((n + 1) * coverage) / n` empirical quantile of those
   residuals (the standard finite-sample conformal correction, not the
   naive quantile -- this is what gives the method its coverage
   guarantee even at finite sample sizes).
3. Report `[point_prediction - quantile, point_prediction + quantile]` as
   a symmetric interval around any future point prediction from the same
   model.

**Real result (calibration split, full portfolio, target 80% coverage):**

```
Conformal quantile:     $3,085,625
Example interval width: $6,171,250  (+/- the quantile, symmetric)
In-sample coverage:     0.801  (target: 0.80)
```

The empirical coverage lands almost exactly on the 0.80 target, confirming
the implementation is statistically correct (independently verified on
genuinely held-out synthetic data in `tests/unit/test_uncertainty.py`,
where the same method achieves 0.812 coverage against an 0.80 target on
data the quantile was never fit on).

## Alternatives Considered

- **Quantile regression** (e.g. LightGBM with a pinball loss objective) --
  rejected as the *primary* method: it would require training and
  shipping a second, different model purely to produce interval bounds
  around a point forecast nobody is deploying (the champion is the EAC
  formula, not a fitted regressor) -- exactly the "re-derive a worse
  version of the EAC formula under a different name" trap flagged in
  ADR-0006. Worth reconsidering only if a future session's `final_cost`
  champion becomes a real fitted model.
- **Bootstrap interval** (resample the calibration set, refit, take the
  spread of predictions) -- doesn't apply cleanly here either:
  `DeterministicEacBaseline` has no fitting step to bootstrap over (it's a
  formula, not an estimator with sampling variance in its parameters);
  bootstrapping the *residual distribution* instead collapses to
  something very close to split conformal without the same finite-sample
  coverage guarantee.
- **Asymmetric / non-symmetric intervals** (e.g. via conformalized
  quantile regression) -- a legitimate refinement if residuals turn out
  to be skewed (a project running over budget arguably has more room to
  overshoot than undershoot). Not attempted here to keep the first
  uncertainty pass simple and auditable; worth checking once slice
  evaluation (a later phase) shows whether the residual distribution is
  actually symmetric across project types/sizes.

## Consequences

- Every `final_cost` prediction the UI (Phase 8) shows must be
  accompanied by this interval, in the exact style Section 19's own
  worked example uses: "Expected Final Cost: $X / 80% Prediction
  Interval: $X - quantile to $X + quantile" -- never a bare point number.
- The interval width ($6.17M) is wide relative to typical project budgets
  in the synthetic portfolio -- this is an honest reflection of how much
  residual spread the EAC formula leaves even after conditioning on
  current CPI, not a bug to be hidden; it should be reported as-is.
- Coverage here is checked in-sample (the calibration split, same rows the
  quantile was fit on) for the *actual* production artifact -- the
  genuinely held-out coverage check (`tests/unit/test_uncertainty.py`'s
  0.812-vs-0.80 result) uses synthetic data specifically constructed for
  that test, not this task's real calibration split. True held-out
  coverage on real data is confirmed only at the one final test
  evaluation, a later phase.
