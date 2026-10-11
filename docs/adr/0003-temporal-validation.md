# ADR-0003: Temporal Validation Strategy

**Status:** Accepted

## Context

The evaluation design needs a train/calibration/test split where the test
set is used for exactly one final, unbiased evaluation, and where
project-level contamination across splits is prevented. BuildGuard's data is inherently
both temporal (monthly snapshots over each project's life) and grouped
(many snapshot rows share one `project_id`). A naive random row split would
violate both properties at once: it would put some of a project's early
snapshots in train and its later ones in test, letting a model implicitly
"see the future" for projects it's also being tested on, and it would mix
old and new projects across all three splits, understating how the model
would perform on a portfolio that is entirely newer than anything it was
trained on -- the actual deployment scenario for a running system.

## Decision

`buildguard.data.split.chronological_project_split`:

1. **Group by project, always.** A project's `project_id` is assigned to
   exactly one split; every row for that project (snapshots, features,
   change orders, ...) inherits that assignment via `filter_by_split`.
   This is the same guarantee `GroupKFold` gives, applied to a single
   deterministic split rather than K folds -- BuildGuard doesn't
   cross-validate across the calibration/test boundary, so K-fold
   machinery would add complexity with no corresponding benefit here (it
   is still the right tool for hyperparameter tuning *within* the train
   split -- see ADR-0006).
2. **Order chronologically by `planned_start_date`**, ties broken by
   `project_id` for determinism. Train gets the oldest 60%, calibration
   the next 20%, test the newest 20% (`configs/base.yaml: split`).
3. Not stratified by outcome. BuildGuard's target labels
   (`cost_overrun`, `schedule_delay`) are themselves only resolved for
   completed projects, and completion status correlates with *how old* a
   project is -- stratifying by an outcome that is partly a function of
   the same chronological axis being split on would reintroduce a subtle
   form of the leakage this split exists to prevent.

## Alternatives Considered

- **Random row-level split (no grouping)** -- rejected: violates the
  project-grouping requirement outright; a model could trivially
  memorize a project's later snapshots from ones seen in training.
- **Random project-level split (grouped, but not chronological)** --
  rejected: prevents contamination but loses the chronological ordering. A model evaluated on a random mix
  of old/new projects looks better than one evaluated the way it will
  actually be used -- scoring a portfolio of currently-active projects it
  has never seen, all newer than its training data.
- **K-Fold / StratifiedGroupKFold cross-validation across all data** --
  rejected for the train/calibration/test boundary specifically (the design
  needs one final held-out test, not K test folds); still the right choice
  *inside* the train split for hyperparameter search (ADR-0006).
- **Rolling-origin / walk-forward temporal CV** -- the most rigorous
  option for a pure time-series problem, and worth reconsidering if
  BuildGuard ever needs periodic retraining evaluation (`docs/MONITORING.md`). Not
  adopted for the initial train/calibration/test split: it multiplies the
  number of models trained/evaluated for comparatively little benefit at
  this project's scale (400 projects, single training run), and adds
  complexity that is not worth introducing before it is needed.

## Consequences

- Every downstream consumer (baselines, models, calibration, threshold
  optimization) gets project-level train/calibration/test membership from
  one shared function -- no risk of two pieces of code disagreeing about
  which project belongs to which split.
- The test split, once assigned, must never be touched again until the one
  final evaluation; this ADR does not enforce that procedurally,
  `docs/LEAKAGE_POLICY.md` ("Temporal validation strategy") records the
  discipline required of every script that consumes the split.
- Because assignment is chronological, train/calibration/test are not
  guaranteed to have identical class balance or subgroup composition --
  this must be checked (not assumed) once labels exist, and is exactly why
  slice analysis is part of the evaluation (ADR-0010).
