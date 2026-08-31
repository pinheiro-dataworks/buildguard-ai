"""Business impact scenario (Section 21).

```
active_projects x avg_financial_exposure x overrun_prevalence
x model_recall x avoidable_impact_assumption
= estimated_decision_support_value
```

Every factor is either measured directly from the portfolio and the
held-out test metrics, or an explicit, labeled assumption from
`configs/business.yaml`. The result is a **scenario-based estimated
impact**, never a claim of realized savings (Section 21 is explicit that
"the model saved $X" without real evidence is never acceptable).

"Active" means in-flight (`is_resolved` is `False` in
`buildguard.data.labels.resolve_outcomes`'s output) -- a project that has
already finished has nothing left to intervene on. "Overrun prevalence"
is measured on the resolved population, the only place a real historical
rate is knowable; there is no way to know the true rate for projects
still in flight, which is exactly why this is a scenario, not a forecast.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

SCENARIO_LABEL = "Scenario-based estimated impact"


@dataclass(frozen=True)
class BusinessImpactResult:
    active_projects: int
    avg_financial_exposure: float
    overrun_prevalence: float
    model_recall: float
    avoidable_impact_assumption: float
    estimated_decision_support_value: float
    label: str = SCENARIO_LABEL


def compute_business_impact(
    projects: pd.DataFrame,
    outcomes: pd.DataFrame,
    model_recall: float,
    avoidable_impact_assumption: float,
) -> BusinessImpactResult:
    """`projects` is the raw Projects table; `outcomes` is
    `resolve_outcomes(...)`'s output for the same portfolio."""
    active_ids = outcomes.loc[~outcomes["is_resolved"], "project_id"]
    active = projects.loc[projects["project_id"].isin(active_ids)]
    resolved = outcomes.loc[outcomes["is_resolved"]]

    # `.mean()` on an empty selection is NaN, which would silently poison
    # the product below (0 * NaN = NaN, not 0) -- zero active projects
    # means zero exposure and zero estimated value, not an undefined one.
    avg_financial_exposure = float(active["approved_budget"].mean()) if len(active) else 0.0
    overrun_prevalence = float(resolved["cost_overrun"].mean()) if len(resolved) else 0.0
    estimated_value = (
        len(active)
        * avg_financial_exposure
        * overrun_prevalence
        * model_recall
        * avoidable_impact_assumption
    )

    return BusinessImpactResult(
        active_projects=len(active),
        avg_financial_exposure=avg_financial_exposure,
        overrun_prevalence=overrun_prevalence,
        model_recall=model_recall,
        avoidable_impact_assumption=avoidable_impact_assumption,
        estimated_decision_support_value=estimated_value,
    )
