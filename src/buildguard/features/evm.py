"""Earned Value Management (EVM) formulas (Section 9).

Operates on `pandas.Series` so it composes directly into the feature
pipeline (`src/buildguard/features/pipeline.py`, later) over full snapshot
tables, and is shared verbatim between training and inference (Section 28)
so these formulas are never re-implemented at the call site.

Every ratio guards against division by zero: a zero denominator produces
``NaN`` (the metric is genuinely undefined), never a silently coerced 0 or
``inf``. A project with ``AC == 0`` or ``PV == 0`` simply has no meaningful
CPI/SPI yet — this is a normal, expected state for very early snapshots,
not a data-quality failure.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """Elementwise ``numerator / denominator``, NaN wherever denominator == 0."""
    with np.errstate(divide="ignore", invalid="ignore"):
        result = numerator / denominator
    return result.where(denominator != 0, other=np.nan)


def cost_variance(earned_value: pd.Series, actual_cost: pd.Series) -> pd.Series:
    """CV = EV - AC.

    Business meaning: positive means the work performed so far cost less
    than budgeted for that work (favorable); negative means it cost more
    (unfavorable) — a leading indicator distinct from raw AC vs. budget.
    """
    return earned_value - actual_cost


def schedule_variance(earned_value: pd.Series, planned_value: pd.Series) -> pd.Series:
    """SV = EV - PV.

    Business meaning: positive means more value has been earned than was
    planned by this point (ahead, in cost-equivalent terms); negative means
    behind schedule. SV is a cost-denominated proxy for schedule health, not
    a direct time measure.
    """
    return earned_value - planned_value


def cost_performance_index(earned_value: pd.Series, actual_cost: pd.Series) -> pd.Series:
    """CPI = EV / AC.

    Business meaning: cost efficiency of work performed. CPI > 1 means every
    dollar spent bought more than a dollar of planned value (efficient);
    CPI < 1 signals a cost-overrun trend. Undefined (NaN) when AC == 0.
    """
    return _safe_divide(earned_value, actual_cost)


def schedule_performance_index(earned_value: pd.Series, planned_value: pd.Series) -> pd.Series:
    """SPI = EV / PV.

    Business meaning: schedule efficiency. SPI > 1 means ahead of schedule;
    SPI < 1 signals a delay trend. Undefined (NaN) when PV == 0.
    """
    return _safe_divide(earned_value, planned_value)


def estimate_at_completion_cpi(budget_at_completion: pd.Series, cpi: pd.Series) -> pd.Series:
    """EAC (cost-based) = BAC / CPI.

    Business meaning: assumes the cost efficiency observed so far (CPI)
    holds for all remaining work. The simplest, most commonly used EAC
    baseline; ignores schedule performance. Undefined (NaN) when CPI == 0.
    """
    return _safe_divide(budget_at_completion, cpi)


def estimate_at_completion_composite(
    budget_at_completion: pd.Series,
    actual_cost: pd.Series,
    earned_value: pd.Series,
    cpi: pd.Series,
    spi: pd.Series,
) -> pd.Series:
    """EAC (schedule-adjusted) = AC + (BAC - EV) / (CPI * SPI).

    Business meaning: a second, independent EAC baseline (Section 9
    requires at least two) that discounts remaining work by *both* cost and
    schedule efficiency — more conservative than the CPI-only baseline when
    a project is simultaneously over budget and behind schedule, which is
    the historically riskier combination. Undefined (NaN) when
    ``CPI * SPI == 0``.
    """
    remaining_work = budget_at_completion - earned_value
    combined_efficiency = cpi * spi
    return actual_cost + _safe_divide(remaining_work, combined_efficiency)


def estimate_to_complete(
    estimate_at_completion: pd.Series, actual_cost: pd.Series
) -> pd.Series:
    """ETC = EAC - AC.

    Business meaning: the cost still expected to be spent from today until
    project completion, under whichever EAC baseline was used to derive it.
    """
    return estimate_at_completion - actual_cost


def variance_at_completion(
    budget_at_completion: pd.Series, estimate_at_completion: pd.Series
) -> pd.Series:
    """VAC = BAC - EAC.

    Business meaning: positive means the project is currently expected to
    finish under budget; negative means an expected overrun at completion,
    under whichever EAC baseline was used to derive it.
    """
    return budget_at_completion - estimate_at_completion
