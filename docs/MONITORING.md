# Monitoring & Retraining Policy

**Rule:** monitoring is implemented, not just documented. Every number in this document comes from a real
`make monitor` run against the actual generated portfolio and the actual
trained/calibrated champions -- never simulated drift on data constructed
to make a demo look interesting. Full design rationale and the complete
real-results snapshot: [ADR-0011](adr/0011-monitoring-drift-detection.md).

## 1. What is monitored

| Category | Signals | Module | Reference vs. current |
|---|---|---|---|
| Data quality | Missing values, schema violations, unexpected categories, range violations, duplicate keys | `buildguard.monitoring.data_quality` | Projects / Project Snapshots / Change Orders, validated against their own contracts |
| Data drift | PSI (numeric + categorical), KS test + Wasserstein distance (numeric only) | `buildguard.monitoring.drift` | **train** split (reference) vs. **test** split (current) |
| Prediction drift | Predicted-probability / predicted-cost distribution, risk-band proportions | `buildguard.monitoring.drift` + `models.thresholds.risk_band` | **calibration** split (reference) vs. **test** split (current) |
| Performance | ROC-AUC, PR-AUC\*, Recall, Brier Score, MAE | `buildguard.monitoring.performance` (reuses `buildguard.evaluation`) | Calibration-split baseline (training/calibration time) vs. held-out test-split result (`make evaluate`) |
| Operational | Inference latency (real, measured), prediction count, errors, model version, data version | `buildguard.monitoring.performance` | N/A -- point-in-time measurement |

\* PR-AUC is computed by `evaluation.classification` but has no recorded
calibration-split baseline to compare against (training only tracked
ROC-AUC for champion selection), so it is reported in
`reports/experiments/test_set_metrics.json` but not compared here.

Run it:

```bash
make evaluate  # must run first -- monitor.py reads its output
make monitor
```

Writes `reports/monitoring/monitoring_report.json`. Every task's summary
metrics are also logged as an MLflow run (`stage=monitoring`).

## 2. Why these reference/current pairs

The deployed app runs on a fixed synthetic portfolio, so there is no real
second batch of production data to compare against. Rather than inventing one,
monitoring reuses the splits that already exist for a different reason:
feature drift compares **train vs. test** (the same chronological split
every held-out evaluation relies on); prediction and performance
drift compare **calibration vs. test** (calibration is what the decision
threshold was tuned against). Both pairings are honest stand-ins for "the
next batch of data" until real production history exists to replace them.

## 3. Reading a drift alert correctly

**A PSI/KS alert is a prompt to investigate, not evidence of a problem.**
The real run behind ADR-0011 found 10 of 23 features significantly
drifted between train and test -- dominated by `inflation_multiplier` and
`months_since_start`. Investigating (the mandatory second step of the retraining policy)
showed this is the *expected* signature of the chronological
train/calibration/test split itself (older projects in train have simply
had more calendar time to accrue inflation and lifecycle progress than
newer projects in test) -- not a data pipeline defect. Any monitoring
surface (including the Model Health page) must present drift alerts with
this context, not as a bare red flag.

By contrast, that same run's `schedule_delay` performance-monitoring
result (ROC-AUC 0.974 -> 0.900, Brier 0.059 -> 0.145) *is* a genuine
finding -- and notably, `schedule_delay`'s **prediction drift was
negligible** (PSI ~0.002) even though its accuracy dropped sharply.
Prediction drift alone would have missed this; only the label-dependent
performance/calibration checks caught it. This is why the retraining policy uses
multiple independent trigger types rather than relying on drift detection
by itself.

## 4. Retraining policy

```
Detect -> Investigate -> Validate data -> Retrain candidate -> Compare vs. champion -> Approve -> Release
```

**Never auto-retrain solely because a trigger fired.** `scripts/monitor.py`
only ever writes a report (`retraining_triggers` in
`monitoring_report.json`) -- it has no code path that calls
`scripts/train.py`. Every trigger past "Detect" requires a human to walk
through Investigate -> ... -> Release explicitly.

| Trigger | Computed by `make monitor`? | How |
|---|---|---|
| PSI above the critical threshold | Yes | Any feature-drift result with `psi_severity == "significant"` |
| Performance drop > X% | Yes | `monitoring.performance_drop_threshold` (default 5% relative) via `compare_classification_metrics`/`compare_regression_metrics` |
| Calibration deterioration | Yes | Brier-score-specific degradation beyond `monitoring.calibration_brier_degradation_threshold` (default 0.03 absolute) |
| Schema changes | Yes | Any table's `DataQualityReport.schema_violations` non-empty |
| New labeled-data volume > N | No -- policy only | Requires a real, ongoing labeling pipeline this demo doesn't have; N is a volume threshold for a human process, not a single-run computation. Reference value: 50 newly-resolved projects since the last training run. |
| Scheduled quarterly evaluation | No -- policy only | Calendar-driven, not data-driven; re-run `make train && make calibrate && make evaluate && make monitor` every 90 days regardless of whether any other trigger fired. |

**Operational thresholds** (also never auto-retrain triggers, but worth
watching once the API records requests): inference error rate materially
above 0, or p95 latency approaching the 500ms target.

## 5. Known limitation: operational monitoring has no live traffic

`measure_inference_latency` times *real* repeated calls into each
champion's own `predict`/`predict_proba` -- not a placeholder -- so the
latency figures in `monitoring_report.json` are genuine local
measurements (see ADR-0011 for the actual numbers, all comfortably under
the 500ms target). What it cannot report is real request volume or error
rate: the public app predicts in-process and the API keeps no request log.
`PredictionLogEntry` / `summarize_operational_log` are ready for
per-request entries once a request log exists; until then, this half of
operational monitoring stays inert rather than populated with invented
traffic.

## 6. Model Health page

The app's Model Health page (`app/page_modules/model_health.py`) renders
the last `make monitor` run from `monitoring_report.json`: retraining
triggers, data quality, feature drift (train vs. test), the performance
comparison, and measured inference latency, as tables. It does not yet
plot the drifted distributions themselves.
