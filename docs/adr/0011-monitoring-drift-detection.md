# ADR-0011: Monitoring, Drift Detection & Retraining Trigger Design

**Status:** Accepted

## Context

Section 23 requires monitoring to be **implemented, not just documented**,
across five categories (data quality, data drift, prediction drift,
performance, operational) and a dedicated Model Health page (Phase 8).
Section 24 requires a retraining policy with specific triggers, explicit
that drift alone must never auto-trigger a retrain. Unlike Sections
16-19 (Phase 5) and 18/20/47 (Phase 6), there is no live production
system yet to monitor -- no deployed API, no real request stream, no
second batch of genuinely new labeled data. Every design decision below
is about how to implement *real, computed* monitoring against that
constraint honestly, rather than either skipping it (deferring everything
to "once the API exists") or faking it (inventing synthetic drift on data
constructed to make a demo look interesting).

## Decision

**Reuse the existing train/calibration/test splits as monitoring's
reference/current pairs**, rather than fabricating a second dataset.
Two pairings, each already meaningful for a different reason:

- **Feature drift**: reference = **train** split, current = **test**
  split -- the same chronological split every other Section 18/47
  comparison in this project already relies on, standing in for
  "the next batch of production data" until real production history
  exists.
- **Prediction drift**: reference = **calibration** split (what the
  threshold was tuned against, Section 17), current = **test** split --
  isolates drift in the model's *output* from drift in its *inputs*.

**PSI for every variable type, KS test and Wasserstein distance for
numeric only** (`src/buildguard/monitoring/drift.py`). PSI needs only a
way to bucket a distribution, so it applies uniformly to numeric
(quantile-binned) and categorical (category-proportion) columns alike;
KS and Wasserstein are defined for continuous distributions specifically
and are computed only where that is mathematically meaningful. Severity
uses the industry-standard PSI cutoffs (< 0.10 none, 0.10-0.25 moderate,
>= 0.25 significant), externalized as `configs/base.yaml: monitoring.psi_warning_threshold`
/ `psi_critical_threshold` rather than hard-coded.

**Performance monitoring compares two different runs' real numbers, not
a self-comparison.** Baseline = each task's calibration-split metric,
already recorded during training/calibration
(`reports/experiments/training_summary.json`'s `calibration_auc`,
`calibration_summary.json`'s `brier_scores`/`recall_at_threshold`).
Current = the same task's genuinely held-out test-split metric from
Session J (`reports/experiments/test_set_metrics.json`). This reuses
`buildguard.evaluation`'s metric functions rather than recomputing them a
second way (Section 27) -- `buildguard.monitoring.performance` only adds
the comparison-and-threshold logic evaluation didn't need.

**Risk bands** (`models/thresholds.risk_band()`): "low" below the
optimized decision threshold, the flagged zone above it split at its own
midpoint into "medium"/"high". This is a display/reporting convenience
(Section 23's risk-band proportions, the Section 28 API response shape),
not a second business-cost decision the way the threshold itself is.

**Operational latency is measured for real, not simulated**
(`monitoring.performance.measure_inference_latency`): it times actual
repeated calls into each champion's own `predict`/`predict_proba` -- the
same code path Phase 8's FastAPI service will call per request. Request
volume and error rate have no real traffic to report on yet (no API
exists); `PredictionLogEntry`/`summarize_operational_log` are the
aggregation half of that story, ready for the API to append real entries
to once it exists, rather than a stub with no code behind it.

**Retraining triggers: computed where a single run can, documented where
it can't** (Section 24 lists six). Four are evaluated for real by
`scripts/monitor.py` against this run's actual signals: PSI above the
critical threshold, performance drop beyond
`monitoring.performance_drop_threshold`, calibration deterioration
(Brier-score-specific degradation beyond
`monitoring.calibration_brier_degradation_threshold`), and schema
violations. Two are calendar/volume-driven policy that no single run can
evaluate -- new labeled-data volume above N, and scheduled quarterly
evaluation -- and are documented as policy in `docs/MONITORING.md` rather
than computed. **The script only flags triggers; it never retrains** --
Section 24's "Never auto-retrain solely because drift exists" is enforced
structurally (`scripts/monitor.py` has no code path that calls
`scripts/train.py`), not just by convention.

### Real results (full portfolio, this session's run)

```
Data quality:     0 violations across Projects / Snapshots / Change Orders
                   (400 / 11,953 / 897 rows) -- schema, categories, ranges, duplicate keys all clean.

Feature drift:     10 of 23 features significant (PSI >= 0.25), train vs. test split.
                   Dominated by inflation_multiplier (PSI 1.94) and months_since_start
                   (PSI 1.87) -- both structurally expected from a *chronological* split
                   (older/train projects have had more calendar time to accrue inflation
                   and lifecycle progress than newer/test projects), not a data problem.
                   change_order_*_to_date, cpi, cost_variance, spi_trend/decline_streak
                   drift for the same underlying reason (they scale with lifecycle
                   progress and inflation exposure).

Prediction drift:  cost_overrun / schedule_delay probability output and risk-band
                   proportions: PSI "none" for both (calibration vs. test split) --
                   the model's *output distribution* barely moved.
                   final_cost predicted-cost distribution: PSI 0.59 (significant),
                   consistent with the same chronological-split effect above (BAC/CPI
                   scales with each era's inflation exposure).

Performance:       cost_overrun: no metric degraded (ROC-AUC 0.898 -> 0.950, an
                   improvement; Brier 0.122 -> 0.113).
                   schedule_delay: ROC-AUC 0.974 -> 0.900, recall 0.984 -> 0.929,
                   Brier 0.059 -> 0.145 -- all three degraded beyond threshold.
                   final_cost: MAE $1.96M -> $1.61M, improved.

Operational:       cost_overrun (RandomForest) p50=14.9ms / p95=20.8ms
                   schedule_delay (LightGBM) p50=4.6ms / p95=5.6ms
                   final_cost (formula) p50=0.02ms / p95=0.03ms
                   All comfortably under Section 49's 500ms p95 target.

Triggers fired:    psi_above_critical_threshold, performance_drop_above_threshold,
                   calibration_deterioration -- all three point at schedule_delay.
                   schema_changes: not fired.
```

A genuinely useful nuance this run surfaces: **prediction drift alone
would have missed the `schedule_delay` problem.** Its probability output
and risk-band proportions barely moved (PSI ~0.002) between the
calibration and test cohorts, even though its held-out accuracy dropped
sharply. Only the label-dependent performance and calibration checks
caught it -- exactly why Section 24 lists multiple independent trigger
types instead of relying on drift detection alone.

## Alternatives Considered

- **Simulate an artificially drifted batch (e.g. perturb CPI/SPI ranges)
  to demonstrate the detectors** -- rejected as the *primary* demonstration:
  it would prove the math works (already covered by unit tests with
  synthetic shifted distributions) but say nothing real about this
  project's actual data or models. Using the real train/test and
  calibration/test splits instead produced genuine, previously-undiscovered
  findings (the chronological feature drift, the `schedule_delay`
  performance drop) that a synthetic demo never would have.
- **A learned/statistical novelty detector (e.g. `IsolationForest`) for
  drift, instead of PSI/KS/Wasserstein** -- rejected for the same reason
  ADR-0010 rejected it for out-of-distribution flagging: opaque to a human
  reviewer, and Section 23 names PSI/KS/Wasserstein explicitly.
- **Treat all six Section 24 triggers as equally "implementable" and stub
  the two calendar/volume ones with a fake computed value** -- rejected;
  a fabricated "47 new labeled projects" number with no real labeling
  pipeline behind it would be exactly the kind of dishonest placeholder
  this project's "never fabricate metrics" rule forbids. Documenting them
  as policy, honestly labeled as not computed, is more defensible than a
  number with nothing real behind it.
- **Fire a retraining action automatically when triggers fire** -- Section
  24 explicitly forbids this ("Never auto-retrain solely because drift
  exists"); `scripts/monitor.py` only ever writes a report.

## Consequences

- The chronological feature-drift finding is not a bug to fix -- it is
  the expected signature of the anti-leakage temporal split design
  (ADR-0003) and should be read as confirmation the split is doing what
  it is supposed to, not as evidence of a data pipeline problem. This
  must be stated plainly wherever monitoring results are shown (Model
  Health page, Phase 8) so a PSI alert on `inflation_multiplier` doesn't
  get misread as a production incident.
- `schedule_delay`'s three fired triggers (PSI, performance drop,
  calibration deterioration) are a real, standing finding that -- per
  Section 24's Detect -> **Investigate** -> ... workflow -- warrants
  human investigation before any retraining decision, not an automatic
  one. This carries forward into `docs/LIMITATIONS.md` and
  `docs/MODEL_CARD.md` once written (Session N), alongside ADR-0010's
  matching finding.
- Operational monitoring's request-volume/error-rate half stays inert
  until Phase 8's FastAPI service exists to feed it real entries -- the
  aggregation logic is complete and tested now, but `reports/monitoring/`
  will not show real traffic numbers until then.
- Re-running `make monitor` after any retraining or new `make evaluate`
  run regenerates this report deterministically against whatever is
  currently in `models/` and `reports/experiments/` -- like ADR-0010, the
  "Real results" block above is a snapshot that should be refreshed
  alongside the champions it measures, not treated as permanent.
