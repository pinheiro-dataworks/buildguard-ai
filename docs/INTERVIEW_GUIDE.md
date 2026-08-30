# Interview Guide

Self-quiz for defending this project without reading the code. Every
answer below traces back to a real decision, ADR, or measured number in
this repository — if an answer here ever drifts from the code, the code
is the source of truth and this file needs updating, not the other way
around.

## Business

**What does BuildGuard AI actually predict?** Three things per project
snapshot: cost-overrun probability, schedule-delay probability, and an
expected final cost with an 80% uncertainty interval — never a single
"will this project fail" verdict.

**Why three separate models instead of one composite risk score?** Each
answers a different management question (budget risk, schedule risk,
cost forecast) with a different natural output type (two probabilities,
one point-forecast-plus-interval) and a different cost-of-error profile
(`configs/business.yaml`'s cost matrix differs per task). A single
blended score would hide which dimension is actually driving concern.

**Why is `cost_overrun`'s threshold 0.080, not 0.50?** Section 17
forbids a silent 0.50 default. `configs/business.yaml` says missing a
real overrun costs 10x a false alarm; sweeping 199 thresholds to
minimize expected cost lands at 0.080, trading precision (55.1%) for
recall (97.4%) — deliberately, because under this cost matrix a missed
overrun is far more expensive than an analyst checking a false alarm.

## Data

**Why synthetic data, and how is it not just a toy?** Zero-cost and zero
privacy risk (no real client data anywhere), but built to be internally
consistent: a per-project latent risk profile drives correlated EVM
dynamics, inflation exposure, and change-order patterns so the realism
relationships Section 8.2 requires hold by construction, not by hoping a
generic random generator happens to look plausible ([ADR-0004](adr/0004-synthetic-data-design.md)).

**What are the six core tables, and why are two of them unused in
features?** Projects, Project Snapshots, Work Packages, Change Orders,
Suppliers, Economic Index. Work Packages and Suppliers are excluded from
`build_feature_table` entirely — both represent "status as of the
project's last snapshot," not a real per-row time series, so including
them would leak each project's final state into every earlier prediction
point ([`LEAKAGE_POLICY.md`](LEAKAGE_POLICY.md) Section 6).

**How is inflation actually handled?** `actual_cost` is nominal
(compounds with a demo construction-cost index over time);
`approved_budget`/`planned_cost` are real (original-approval terms).
`inflation.py` decomposes nominal cost variance into an operational
(execution) component and an inflation (price-growth) component —
verified as an exact identity against `evm.cost_variance`, zero
reconstruction error.

## Leakage

**What is the leakage rule, concretely?** For a feature row whose
prediction timestamp is `snapshot_date`, every input to that row must
have its own timestamp `<= snapshot_date`
([`LEAKAGE_POLICY.md`](LEAKAGE_POLICY.md)). Enforced structurally, not
just by convention: change-order features use `pandas.merge_asof(...,
direction="backward")`, which cannot see a change order dated after the
snapshot regardless of what the calling code does.

**How is this actually tested, not just claimed?**
`tests/leakage/test_pipeline_leakage.py` injects a far-future change
order and asserts it never affects any row's cumulative features; checks
same-day inclusion (boundary is `<=`, not `<`); checks cross-project
isolation; checks output is invariant to input row order (a pipeline
that depended on row order for its as-of logic would be a latent leakage
risk even if today's tests happened to pass).

**Why a chronological, project-grouped split instead of random
k-fold?** Splitting at the snapshot-row level would let one project's
history appear in more than one split; splitting randomly by project
would let the model "see the future" relative to test-set projects'
actual calendar position. Train (60%, oldest) / calibration (20%) / test
(20%, newest) by `planned_start_date` matches how the model will
actually be used — scoring projects that started after the ones it
trained on ([ADR-0003](adr/0003-temporal-validation.md)).

## Modeling

**Why did a formula beat two tuned ML models for `final_cost`?** The
deterministic EAC baseline (`BAC / CPI`) scored 1.96M calibration MAE
against tuned LightGBM's 4.11M — confirmed at two different scales, not
a fluke. `BAC/CPI` already encodes the exact mechanism (current cost
efficiency projected forward); a tree model has to *rediscover* that
relationship from noisier proxy features and generally does worse until
given a lot more data ([ADR-0006](adr/0006-model-selection.md)).

**What beat what for the two classifiers?** Random Forest for
`cost_overrun` (0.898 calibration AUC vs. 0.888 logistic regression),
LightGBM for `schedule_delay` (0.974 vs. 0.816). Both tuned via Optuna
with `GroupKFold` grouped by `project_id` — never plain k-fold, which
would let one project's rows split across train and validation folds
within the search itself.

## Calibration

**Why isotonic over sigmoid (Platt) calibration?** Selected by lowest
Brier score on the calibration split for both tasks (`cost_overrun`
0.122 vs. sigmoid's near-identical 0.133; `schedule_delay` 0.059 vs.
0.062) — not a default preference, an empirical comparison
([ADR-0007](adr/0007-calibration-strategy.md)).

**Why fit calibrators directly on `(raw_probability, label)` pairs
instead of `CalibratedClassifierCV`?** That wrapper requires the wrapped
object to implement both `fit` and `predict` as a full sklearn
estimator; BuildGuard's own baseline classes only implement
`predict_proba`. Fitting a one-feature `LogisticRegression` (Platt) or
`IsotonicRegression` directly on the raw probability output works
uniformly for baselines and real sklearn pipelines alike.

**Is calibration actually trustworthy out-of-sample?** For
`cost_overrun`, yes — Brier held (0.122 → 0.113, even improved) on the
test split. For `schedule_delay`, no — it degrades to 0.145, a real,
documented finding ([`LIMITATIONS.md`](LIMITATIONS.md)), not something
discovered and then hidden.

## Threshold

**What does "199 candidate thresholds" actually mean and why that
number?** An evenly-spaced sweep strictly between 0 and 1 (endpoints
excluded — a threshold of exactly 0 or 1 always predicts one class,
never a real decision point), picking whichever minimizes `false
negatives × fn_cost + false positives × fp_cost`. 199 was chosen as
comfortably finer than needed for a smooth 1-D cost surface, not tuned
to hit a particular answer.

**What would change if false-positive cost doubled?** The threshold
would move up (fewer flagged projects, higher precision, lower recall)
— re-running `make calibrate` after editing `configs/business.yaml` is
the only required step; no code change.

## Regression

**How is `final_cost` actually evaluated, beyond MAE?** RMSE (penalizes
large errors more), R², MAPE/SMAPE (percentage terms, both reported
since MAPE alone can blow up for smaller/cheaper projects), and two
business-terms numbers: median dollar error and median percent error —
Section 18's explicit ask for something a non-technical reader can use
without decoding RMSE.

**How is the 80% uncertainty interval actually validated?** Split
conformal prediction: the calibration-split's absolute residuals, at the
`ceil((n+1)*coverage)/n` finite-sample-corrected quantile (not the naive
quantile). Real result: 80.1% in-sample coverage, 89.9% held-out test
coverage — both meeting or exceeding the 80% target, though the test
result is conservative (wider than strictly required — see
[`LIMITATIONS.md`](LIMITATIONS.md)).

## Explainability

**Why does SHAP need `model_output="probability"` explicitly?** Without
it, LightGBM's SHAP values come out in raw log-odds space while
RandomForest's come out in probability space directly — the additive
identity `base_value + shap_values.sum() == predicted_probability` only
holds for both families when forced into the same space via an explicit
background sample.

**Global feature importance shows two different rankings (SHAP vs.
permutation) — which one is "right"?** Neither is more "right" — they
measure different things over different feature spaces (SHAP: encoded/
one-hot space; permutation: original input space) and are reported side
by side deliberately, since disagreement between them (common under
correlated features) is itself informative, not noise to average away.

**Why no SHAP explanation for `final_cost`?** Its champion is a formula
(`BAC / CPI`), not a fitted model — the formula itself already is the
complete explanation; there is nothing for SHAP to attribute.

## MLOps

**What does the monitoring pipeline actually check?** Data quality
(missing values, schema violations, unexpected categories, range
violations, duplicate keys), feature and prediction drift (PSI for every
type, KS test + Wasserstein for numeric), performance vs. a recorded
baseline, and real (measured, not simulated) inference latency — all
against the real portfolio and champions, in one `make monitor` run.

**Give a real example of monitoring catching something drift alone
would have missed.** `schedule_delay`'s prediction drift was negligible
(PSI ~0.002) between the calibration and test cohorts, yet its accuracy
collapsed (AUC 0.974 → 0.900). Only the label-dependent performance
comparison caught it — proof that drift detection and performance
monitoring answer different questions.

**Does a fired retraining trigger retrain the model?** No, by
construction — `scripts/monitor.py` contains no call to
`scripts/train.py`. Every trigger is a flag for a human to investigate
(Section 24's mandatory Detect → Investigate → ... sequence, detailed in
[`RUNBOOK.md`](RUNBOOK.md)).

## Production

**How does the Streamlit app call predictions without a second
implementation?** It calls the same FastAPI endpoint *functions*
directly, in-process (`app/data_access.py`) — not over HTTP, and not a
separate prediction code path. One implementation, two callers
([ADR-0012](adr/0012-streamlit-fastapi-boundary.md)).

**What happens if a request has an unseen category or malformed data?**
Pydantic validation rejects it as a 422 for type/range/enum violations;
`buildguard.data.contracts` (the same validators used at ingestion)
catches cross-field violations Pydantic can't express (e.g. a
completion date before the start date) — also a 422, never a crash
(Section 48: "the app must fail safely").

**What's actually deployed today, honestly?** Nothing publicly yet
(Session O). Locally runnable end to end via `make train && make
calibrate && make api && make app`; CI runs the full pipeline plus tests
on every push ([`RUNBOOK.md`](RUNBOOK.md)).
