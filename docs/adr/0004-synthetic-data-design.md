# ADR-0004: Synthetic Portfolio Generator Design

**Status:** Accepted

## Context

Per [ADR-0002](0002-data-privacy-strategy.md), BuildGuard AI's entire
public-facing pipeline runs on synthetic data. A synthetic generator that
just draws independent random numbers per column would fail the project's
actual purpose: the required realism relationships in Section 8.2 of
`BUILDGUARD_AI_PROJECT_SCOPE.md` (poor CPI -> overrun risk, SPI
deterioration -> delay risk, change-order ratio -> higher final cost,
procurement delay -> schedule impact, inflation -> nominal cost, low
physical/high financial progress -> risk, supplier concentration ->
exposure, risk evolving over the lifecycle) only show up if the tables are
internally *correlated* the way a real portfolio is.

## Decision

`src/buildguard/data/synthetic.py` generates every project from a single
seeded `numpy.random.Generator`, using a **latent per-project risk profile**
(`_RiskProfile`: cost/schedule efficiency base + drift, change-order
propensity, supplier-quality mean, committed-cost buffer) that is never
exposed as a column, but consistently drives every table:

- **Snapshots** are simulated month-by-month. `earned_value = BAC x
  actual_progress` and `actual_cost = earned_value / cost_efficiency(t)`,
  where `cost_efficiency(t)` follows the project's drift trend plus monthly
  noise -- so CPI is *generated to already equal* the intended trend, not
  reverse-engineered afterward. The same pattern drives SPI via a
  `schedule_efficiency(t)` term.
- **Change orders** are drawn with a Poisson count whose rate is
  `change_order_propensity x (1 / cost_efficiency_base)`-weighted, so
  worse-run projects get more of them, and their approved amounts are added
  directly into the same month's `actual_cost` -- so "more change orders"
  mechanically causes "higher final cost," not just correlates with it.
- **Suppliers** are drawn from a shared pool smaller than
  `n_projects x suppliers_per_project`, with Pareto-distributed popularity
  weights, so a handful of "star" suppliers serve many projects
  (concentration risk) by construction.
- **Inflation** is a separate, deterministic monthly index
  (`_generate_economic_index`) applied multiplicatively to convert each
  month's "real" cost into the `actual_cost` actually reported --
  `planned_cost` stays in original-budget terms, so the wedge between
  planned and actual is *partly* inflation and *partly* execution, exactly
  the decomposition Section 10 (inflation normalization, a later phase)
  exists to untangle.
- **Physical vs. financial progress**: `actual_progress` (schedule-driven)
  and `actual_cost` (cost-efficiency-driven) are generated from independent
  efficiency trajectories, so "high spend, low physical progress" emerges
  naturally whenever a project's cost efficiency is poor while its schedule
  efficiency is closer to on-track -- no separate mechanism was needed.
- **Lifecycle evolution**: both efficiency trajectories include a `drift`
  term applied against lifecycle position `t = elapsed_months /
  duration_months`, so risk visibly worsens (or improves) as a project
  progresses, rather than being drawn once and held constant.

There is no `actual_completion_date` or `final_cost` column (Section 8.4
has none either) -- both are derived later from the snapshot history: a
completed project's last snapshot has `actual_progress == 1.0`, and that
row's `snapshot_date` / `actual_cost` are the completion date / final cost.
Projects that haven't reached 1.0 by `reference_date` are in-flight
(censored) and carry no resolved label -- deliberate, not a gap (Section 11).

Every table is validated against its `buildguard.data.contracts` schema
before `generate_portfolio()` returns; a contract violation here means the
generator itself has a bug, and must fail loudly rather than ship
malformed demo data.

## A caught design bug, and a validated (not "wrong") finding

**Bug caught by the smoke test, fixed before this ADR was written:** the
first implementation drove `actual_progress` increments from the *planned*
S-curve's derivative, which goes to zero once the planned duration is over.
A delayed project would then permanently stall (observed: stuck at ~95%
forever). Fixed by driving the increment from a constant
`1 / duration_months` base rate scaled by `schedule_efficiency`, decoupled
from the planned curve entirely -- `planned_progress` still correctly
plateaus at 1.0 after the planned finish date (that's real EVM behavior for
PV), but it no longer gates whether `actual_progress` can keep moving.

**Not a bug, a validated finding:** at full scale (400 projects), the
*nominal* nominal cost-overrun rate (`actual_cost > approved_budget x
1.10`) among completed projects is ~79%, but the *inflation-adjusted*
overrun rate is ~47%. This gap is intentional and expected -- `approved_budget`
is fixed in original-approval terms while `actual_cost` is nominal, so
multi-year inflation alone pushes most projects' nominal spend above their
nominal budget. This is exactly the problem Section 10 exists to solve, and
it means **the primary classification target (Section 6.1) must be defined
against an inflation-adjusted figure**, not raw nominal `actual_cost` --
recorded here so the decision isn't lost before the inflation-normalization
layer (Phase 2) and the label-definition work (Phase 3) land.

## Alternatives Considered

- **Fully independent column-by-column sampling** -- rejected: cannot
  produce the correlated realism Section 8.2 requires; a model trained on
  it would learn nothing resembling real construction risk.
- **Vectorized (NumPy-array) simulation instead of per-project Python
  loops** -- rejected for now: at n=400 projects the loop-based simulation
  runs in ~17s, which is fine for an occasional `make data` run, and the
  per-project loop is far easier to reason about and debug than a fully
  vectorized month-by-month state machine. Revisit only if scale grows
  enough to matter.
- **Deriving `cost_efficiency`/`schedule_efficiency` purely from project
  attributes (type, standard, size) with no latent per-project randomness**
  -- rejected: would make every project of the same type/standard behave
  identically net of noise, losing the individual-project heterogeneity
  needed for meaningful slice analysis (Section 18) and error analysis
  (Section 47).

## Consequences

- The generator is the single source of realism in this project; future
  changes to it should be smoke-tested (small `n_projects`, inspect one
  project's full snapshot history) before trusting `make data` output, the
  way this ADR's bug was actually caught.
- The label-definition step (Phase 3) must explicitly decide whether
  `cost_overrun` is computed on nominal or inflation-adjusted final cost --
  this ADR does not resolve that, it just prevents the decision from being
  made by accident.
- `configs/base.yaml: synthetic_data` fully parameterizes scale
  (`n_projects`, supplier pool, work-package counts, history window,
  in-flight fraction) -- changing the demo dataset's size or time range
  never requires touching `synthetic.py` itself.
