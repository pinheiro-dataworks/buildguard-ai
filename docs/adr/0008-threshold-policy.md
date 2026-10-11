# ADR-0008: Business-Cost Threshold Policy

**Status:** Accepted

## Context

A 0.50 classification threshold silently assumes that a missed overrun
and a false alarm cost the same, which is rarely true. The threshold
should instead minimize a configurable business-cost matrix, and the
chosen threshold, precision, recall, expected business cost, and confusion
matrix should all be reported -- measured on calibration data, never test.

## Decision

`configs/business.yaml` defines an asymmetric cost matrix per
classification task -- missing a real overrun/delay (a false negative) is
defined as costing more than a false alarm (a false positive):

| Task | False negative cost | False positive cost |
|---|---|---|
| `cost_overrun` | 10 | 2 |
| `schedule_delay` | 8 | 2 |

`src/buildguard/models/thresholds.py: optimize_threshold()` sweeps 199
candidate thresholds strictly between 0 and 1 on the **calibration**
split's *calibrated* probabilities (ADR-0007's output feeds directly
into this, not the raw model), and picks the threshold minimizing
`expected_cost = false_negatives * fn_cost + false_positives * fp_cost`.

**Real results (calibration split, full portfolio, on the calibrated
probabilities from ADR-0007):**

| Task | Threshold | Precision | Recall | Expected cost | Confusion (TP/FP/TN/FN) |
|---|---|---|---|---|---|
| `cost_overrun` | 0.080 | 0.682 | 0.977 | 936 | 799 / 373 / 588 / 19 |
| `schedule_delay` | 0.140 | 0.864 | 0.984 | 460 | 1028 / 162 / 572 / 17 |

Both optimized thresholds land well below 0.50 -- a direct, visible
consequence of the cost asymmetry: since missing a real overrun/delay
(10x and 8x, respectively, as costly as a false alarm) is punished so much
more heavily, the optimum trades a large number of false positives
(373 and 162) for very few false negatives (19 and 17), reaching ~98%
recall on both tasks. This is the intended behavior -- BuildGuard is a
decision-support tool, so an analyst investigating an extra false alarm is
a far smaller cost than a genuine overrun going undetected.

## Alternatives Considered

- **Fixed 0.50 threshold** -- would have meant materially fewer flagged projects (lower recall) at
  each task's default operating point, missing real overruns/delays the
  cost matrix says are expensive to miss.
- **Maximize F1 score instead of minimizing expected cost** -- rejected:
  F1 weights precision and recall equally, which silently assumes false
  positives and false negatives are equally costly. That assumption is
  exactly what `configs/business.yaml` exists to make explicit and
  overridable instead of implicit.
- **Youden's J statistic (maximize `sensitivity + specificity - 1`)** --
  a common threshold-selection heuristic, rejected for the same reason as
  F1: it has no notion of the actual business cost asymmetry, only of
  balancing the two error rates evenly.
- **A finer or coarser threshold grid** -- 199 candidates (step size
  0.005) was chosen as more than fine enough to find a stable optimum on
  a cost surface this smooth, without the cost of a much larger sweep.

## Consequences

- The precision/recall trade-off here (moderate precision, very high
  recall) must be stated plainly in any UI or report surface -- e.g. "~7
  in 10 flagged cost-overrun projects are true positives, and the model
  catches ~98% of real overruns" -- rather than reporting accuracy alone,
  which would look artificially strong given the class balance.
- Changing `configs/business.yaml`'s cost matrix (a legitimate business
  decision, e.g. if false alarms turn out to cost more analyst time than
  assumed) requires re-running `scripts/calibrate.py`, not a code change --
  this was the explicit point of externalizing the matrix.
- Like calibration (ADR-0007), these metrics are measured on the same
  calibration-split data the threshold was optimized against -- expected
  to look slightly better than genuinely held-out performance, confirmed
  only at the one final test evaluation.
