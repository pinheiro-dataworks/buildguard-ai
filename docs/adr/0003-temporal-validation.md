# ADR-0003: Temporal Validation Strategy

**Status:** Accepted

## Context

Section 12 requires a train/calibration/test design where the test set is
used for exactly one final, unbiased evaluation, and where project-level
contamination across splits is prevented. BuildGuard's data is inherently
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
   This is the Section 12 `GroupKFold`-style guarantee, applied to a single
   deterministic split rather than K folds -- BuildGuard doesn't
   cross-validate across the calibration/test boundary, so K-fold
   machinery would add complexity with no corresponding benefit here (it
   is still the right tool for hyperparameter tuning *within* the train
   split, which happens later, in Session H/G).
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
  rejected: matches Section 12's contamination requirement but not its
  preference for a chronological split. A model evaluated on a random mix
  of old/new projects looks better than one evaluated the way it will
  actually be used -- scoring a portfolio of currently-active projects it
  has never seen, all newer than its training data.
- **K-Fold / StratifiedGroupKFold cross-validation across all data** --
  rejected for the train/calibration/test boundary specifically (Section
  12 wants one final held-out test, not K test folds); still the right
  choice *inside* the train split for hyperparameter search, which is a
  separate, later decision (Session G/H).
- **Rolling-origin / walk-forward temporal CV** -- the most rigorous
  option for a pure time-series problem, and worth reconsidering if
  BuildGuard ever needs periodic retraining evaluation (Section 24). Not
  adopted for the initial train/calibration/test split: it multiplies the
  number of models trained/evaluated for comparatively little benefit at
  this project's scale (400 projects, single training run), and adds
  complexity Section 61's "optimize for correct answers, not technology
  count" argues against introducing before it's needed.

## Consequences

- Every downstream consumer (baselines, models, calibration, threshold
  optimization) gets project-level train/calibration/test membership from
  one shared function -- no risk of two pieces of code disagreeing about
  which project belongs to which split.
- The test split, once assigned, must never be touched again until the one
  final evaluation (Section 12); this ADR does not enforce that
  procedurally, `docs/LEAKAGE_POLICY.md` Section 5 records the
  discipline required of every script that consumes the split.
- Because assignment is chronological, train/calibration/test are not
  guaranteed to have identical class balance or subgroup composition --
  this must be checked (not assumed) once labels exist, and is exactly why
  Section 18's slice analysis exists.
