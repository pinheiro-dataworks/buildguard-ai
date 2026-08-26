"""Deterministic synthetic construction-portfolio generator (Section 8.2).

Generates the six core tables (Projects, Project Snapshots, Work Packages,
Change Orders, Suppliers, Economic Index) from a single seeded
`numpy.random.Generator`, so the whole portfolio is byte-identical across
runs and machines given the same `configs/base.yaml` (Section 26, Section
8.1 — no external data, no `datetime.now()`, no machine-specific state).

Design rationale, and how the required realism relationships (Section 8.2)
are encoded, is recorded in `docs/adr/0004-synthetic-data-design.md`. In
short: each project gets a latent, unobserved "risk profile" (cost/schedule
efficiency trends) that consistently drives its snapshots, change orders,
and supplier performance — so a "bad" project looks bad across every table,
the way correlated risk actually behaves in real portfolios.

There is no separate `actual_completion_date` or `final_cost` column in the
data model (Section 8.4) — both are *derived*, later, from the snapshot
history: a project's final cost is the `actual_cost` of its last snapshot,
and its actual completion date is that snapshot's `snapshot_date`, once
`actual_progress` has reached 1.0. Projects still short of 1.0 progress at
`reference_date` are in-flight (censored) and carry no resolved label yet —
this is intentional, not a gap; see Section 11 on temporal integrity.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from buildguard.config import BaseAppConfig, SyntheticDataConfig
from buildguard.data.economic_index import DemoIndexProvider, EconomicIndexProvider
from buildguard.data.enums import (
    ChangeOrderCategory,
    ChangeOrderStatus,
    ConstructionStandard,
    ProjectType,
    SupplierCategory,
)
from buildguard.features import evm

_CITIES: tuple[tuple[str, str], ...] = (
    ("Sao Paulo", "SP"),
    ("Rio de Janeiro", "RJ"),
    ("Belo Horizonte", "MG"),
    ("Curitiba", "PR"),
    ("Porto Alegre", "RS"),
    ("Salvador", "BA"),
    ("Recife", "PE"),
    ("Fortaleza", "CE"),
    ("Brasilia", "DF"),
    ("Campinas", "SP"),
    ("Florianopolis", "SC"),
    ("Goiania", "GO"),
    ("Vitoria", "ES"),
    ("Manaus", "AM"),
    ("Belem", "PA"),
)

_PROJECT_TYPE_WEIGHTS: dict[ProjectType, float] = {
    ProjectType.RESIDENTIAL: 0.40,
    ProjectType.COMMERCIAL: 0.25,
    ProjectType.INDUSTRIAL: 0.15,
    ProjectType.INFRASTRUCTURE: 0.10,
    ProjectType.MIXED_USE: 0.10,
}

_STANDARD_WEIGHTS: dict[ConstructionStandard, float] = {
    ConstructionStandard.ECONOMY: 0.20,
    ConstructionStandard.STANDARD: 0.45,
    ConstructionStandard.HIGH_STANDARD: 0.25,
    ConstructionStandard.LUXURY: 0.10,
}

# Illustrative demo cost-per-m2 (local currency units), not a real market
# reference -- only used to make synthetic budgets internally consistent.
_COST_PER_M2_BY_STANDARD: dict[ConstructionStandard, float] = {
    ConstructionStandard.ECONOMY: 1800.0,
    ConstructionStandard.STANDARD: 2500.0,
    ConstructionStandard.HIGH_STANDARD: 3800.0,
    ConstructionStandard.LUXURY: 6000.0,
}

_AREA_LOGNORMAL_MEAN_BY_TYPE: dict[ProjectType, float] = {
    ProjectType.RESIDENTIAL: 8.6,  # ~ exp(8.6) ~ 5,400 m2 median
    ProjectType.COMMERCIAL: 8.3,
    ProjectType.INDUSTRIAL: 9.0,
    ProjectType.INFRASTRUCTURE: 9.2,
    ProjectType.MIXED_USE: 8.8,
}

_CHANGE_ORDER_CATEGORY_WEIGHTS: dict[ChangeOrderCategory, float] = {
    ChangeOrderCategory.SCOPE_CHANGE: 0.30,
    ChangeOrderCategory.DESIGN_ERROR: 0.20,
    ChangeOrderCategory.SITE_CONDITION: 0.20,
    ChangeOrderCategory.REGULATORY: 0.10,
    ChangeOrderCategory.CLIENT_REQUEST: 0.15,
    ChangeOrderCategory.OTHER: 0.05,
}

_SUPPLIER_CATEGORIES: tuple[SupplierCategory, ...] = tuple(SupplierCategory)

_WORK_PACKAGE_NAMES: tuple[str, ...] = (
    "Site Preparation",
    "Earthworks",
    "Foundations",
    "Structure",
    "Masonry",
    "Roofing",
    "Waterproofing",
    "Facade",
    "Electrical",
    "Plumbing",
    "HVAC",
    "Fire Safety Systems",
    "Elevators",
    "Interior Finishes",
    "Painting",
    "Landscaping",
    "Utilities Connection",
    "Commissioning",
    "Final Cleaning",
    "Demolition",
)


@dataclass(frozen=True)
class PortfolioDataset:
    """The six core tables of a generated synthetic portfolio (Section 8.4)."""

    projects: pd.DataFrame
    snapshots: pd.DataFrame
    work_packages: pd.DataFrame
    change_orders: pd.DataFrame
    suppliers: pd.DataFrame
    economic_index: pd.DataFrame


@dataclass(frozen=True)
class _RiskProfile:
    """Latent, unobserved per-project parameters driving every table below."""

    cost_efficiency_base: float
    cost_efficiency_drift: float
    schedule_efficiency_base: float
    schedule_efficiency_drift: float
    change_order_propensity: float
    supplier_quality_mean: float
    committed_buffer_fraction: float


def _s_curve(t: float) -> float:
    """Smooth 0->1 progress shape (slow start, fast middle, slow finish)."""
    clamped = min(max(t, 0.0), 1.0)
    return 0.5 - 0.5 * math.cos(math.pi * clamped)


def _weighted_choice(rng: np.random.Generator, weights: dict[str, float]) -> str:
    keys = list(weights.keys())
    probs = np.array(list(weights.values()), dtype=float)
    probs = probs / probs.sum()
    return str(rng.choice(keys, p=probs))


def _sample_projects(rng: np.random.Generator, cfg: SyntheticDataConfig) -> pd.DataFrame:
    reference_date = pd.Timestamp(cfg.reference_date)
    earliest_start = reference_date - pd.DateOffset(years=cfg.history_years)
    rows = []
    for i in range(cfg.n_projects):
        project_type = ProjectType(_weighted_choice(rng, _PROJECT_TYPE_WEIGHTS))  # type: ignore[arg-type]
        standard = ConstructionStandard(_weighted_choice(rng, _STANDARD_WEIGHTS))  # type: ignore[arg-type]
        city, state = _CITIES[rng.integers(0, len(_CITIES))]

        duration_months = int(
            rng.integers(cfg.monthly_observations_min, cfg.monthly_observations_max + 1)
        )

        is_intended_in_flight = rng.random() < cfg.in_flight_fraction
        if is_intended_in_flight:
            latest_start = reference_date - pd.DateOffset(months=cfg.min_start_lead_months)
            window_start = max(
                earliest_start, reference_date - pd.DateOffset(months=duration_months)
            )
        else:
            window_start = earliest_start
            # ~30% delay buffer so an on-time-or-slightly-late project has
            # still very likely finished by reference_date.
            buffer_months = max(cfg.min_start_lead_months, int(duration_months * 1.3))
            latest_start = reference_date - pd.DateOffset(months=buffer_months)
            latest_start = max(latest_start, earliest_start)

        span_days = max((latest_start - window_start).days, 1)
        planned_start_date = window_start + pd.Timedelta(days=int(rng.integers(0, span_days + 1)))
        planned_completion_date = planned_start_date + pd.DateOffset(months=duration_months)

        area_mean = _AREA_LOGNORMAL_MEAN_BY_TYPE[project_type]
        gross_floor_area_m2 = float(rng.lognormal(mean=area_mean, sigma=0.5))
        gross_floor_area_m2 = float(np.clip(gross_floor_area_m2, 800.0, 120_000.0))

        number_of_towers = int(1 + rng.poisson(0.4)) if gross_floor_area_m2 > 6000 else 1
        avg_unit_size = 65.0 if project_type == ProjectType.RESIDENTIAL else 0.0
        number_of_units = (
            max(1, round(gross_floor_area_m2 / avg_unit_size)) if avg_unit_size > 0 else 0
        )

        cost_per_m2 = _COST_PER_M2_BY_STANDARD[standard] * float(rng.normal(1.0, 0.08))
        approved_budget = round(max(gross_floor_area_m2 * cost_per_m2, 50_000.0), 2)

        rows.append(
            {
                "project_id": f"PRJ-{i + 1:04d}",
                "project_type": project_type.value,
                "city": city,
                "state": state,
                "gross_floor_area_m2": round(gross_floor_area_m2, 1),
                "number_of_towers": number_of_towers,
                "number_of_units": number_of_units,
                "construction_standard": standard.value,
                "planned_start_date": planned_start_date.normalize(),
                "planned_completion_date": planned_completion_date.normalize(),
                "approved_budget": approved_budget,
                # internal-only, dropped before returning the public table
                "duration_months_internal": duration_months,
            }
        )
    return pd.DataFrame(rows)


def _sample_risk_profiles(
    rng: np.random.Generator, projects: pd.DataFrame
) -> dict[str, _RiskProfile]:
    profiles: dict[str, _RiskProfile] = {}
    for project_id in projects["project_id"]:
        cost_base = float(np.clip(rng.normal(1.0, 0.12), 0.55, 1.35))
        cost_drift = float(rng.normal(-0.05, 0.09))
        schedule_base = float(np.clip(rng.normal(1.0, 0.15), 0.5, 1.4))
        schedule_drift = float(rng.normal(-0.04, 0.08))
        # Worse cost efficiency -> more change orders (Section 8.2).
        co_propensity = float(max(0.05, (2.0 - cost_base) * 0.9 + rng.normal(0, 0.15)))
        # Better-run projects tend to vet suppliers better (Section 8.2).
        supplier_quality = float(np.clip(5.0 + 2.5 * cost_base + rng.normal(0, 0.6), 0.0, 10.0))
        committed_buffer = float(rng.uniform(0.02, 0.15))
        profiles[project_id] = _RiskProfile(
            cost_efficiency_base=cost_base,
            cost_efficiency_drift=cost_drift,
            schedule_efficiency_base=schedule_base,
            schedule_efficiency_drift=schedule_drift,
            change_order_propensity=co_propensity,
            supplier_quality_mean=supplier_quality,
            committed_buffer_fraction=committed_buffer,
        )
    return profiles


def _generate_change_orders(
    rng: np.random.Generator,
    projects: pd.DataFrame,
    risk_profiles: dict[str, _RiskProfile],
) -> pd.DataFrame:
    rows = []
    co_counter = 0
    for record in projects.to_dict("records"):
        project_id = str(record["project_id"])
        planned_start_date = pd.Timestamp(record["planned_start_date"])
        approved_budget = float(record["approved_budget"])
        duration_months = int(record["duration_months_internal"])

        profile = risk_profiles[project_id]
        expected_count = profile.change_order_propensity * (duration_months / 12.0)
        n_change_orders = int(rng.poisson(max(expected_count, 0.05)))
        for _ in range(n_change_orders):
            co_counter += 1
            effective_month = int(rng.integers(0, duration_months))
            date = planned_start_date + pd.DateOffset(months=effective_month)
            category = ChangeOrderCategory(
                _weighted_choice(rng, _CHANGE_ORDER_CATEGORY_WEIGHTS)  # type: ignore[arg-type]
            )
            fraction_of_budget = float(rng.lognormal(mean=math.log(0.015), sigma=0.8))
            fraction_of_budget = min(fraction_of_budget, 0.15)
            amount = round(approved_budget * fraction_of_budget, 2)
            status = ChangeOrderStatus(
                _weighted_choice(rng, {"approved": 0.75, "pending": 0.15, "rejected": 0.10})
            )
            rows.append(
                {
                    "change_order_id": f"CO-{co_counter:05d}",
                    "project_id": project_id,
                    "date": date.normalize(),
                    "category": category.value,
                    "approved_amount": amount if status == ChangeOrderStatus.APPROVED else 0.0,
                    "status": status.value,
                    "_effective_month": effective_month,
                }
            )
    columns = ["change_order_id", "project_id", "date", "category", "approved_amount", "status"]
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(rows)


def _simulate_snapshots(
    projects: pd.DataFrame,
    risk_profiles: dict[str, _RiskProfile],
    change_orders: pd.DataFrame,
    index_provider: EconomicIndexProvider,
    rng: np.random.Generator,
    reference_date: pd.Timestamp,
) -> pd.DataFrame:
    rows = []
    for record in projects.to_dict("records"):
        project_id = str(record["project_id"])
        planned_start = pd.Timestamp(record["planned_start_date"])
        approved_budget = float(record["approved_budget"])
        duration_months = int(record["duration_months_internal"])

        profile = risk_profiles[project_id]
        project_cos = change_orders.loc[change_orders["project_id"] == project_id]

        actual_progress_prev = 0.0
        # A monthly work "capacity", independent of the planned S-curve. The
        # planned curve is only used for the *reported* planned_progress
        # (PV plateaus at BAC once the planned finish date passes -- that's
        # correct EVM behavior) -- it must NOT drive the actual-progress
        # increment, or a delayed project's planned_increment collapses to
        # zero once t > 1 and the project can never reach 100% (this was a
        # real bug caught by the smoke test: projects stalled forever at
        # ~95% once they ran past their planned completion date).
        base_monthly_rate = 1.0 / duration_months
        # Worst case (schedule_eff pinned at its floor for the whole
        # project) needs duration_months / 0.35 ~= 2.9x the planned
        # duration; reference_date is the real backstop for anything slower.
        max_months = int(duration_months * 3.0) + 12
        for month_idx in range(max_months):
            snapshot_date = (planned_start + pd.offsets.MonthEnd(0)) + pd.offsets.MonthEnd(
                month_idx
            )
            if snapshot_date > reference_date:
                break  # censored: not yet observable as of "today"

            t = (month_idx + 1) / duration_months
            planned_progress = _s_curve(min(t, 1.0))

            schedule_noise = float(rng.normal(0, 0.03))
            schedule_eff = float(
                np.clip(
                    profile.schedule_efficiency_base
                    + profile.schedule_efficiency_drift * min(t, 1.5)
                    + schedule_noise,
                    0.35,
                    1.5,
                )
            )
            actual_progress = min(1.0, actual_progress_prev + base_monthly_rate * schedule_eff)

            cost_noise = float(rng.normal(0, 0.025))
            cost_eff = float(
                np.clip(
                    profile.cost_efficiency_base
                    + profile.cost_efficiency_drift * min(t, 1.5)
                    + cost_noise,
                    0.4,
                    1.5,
                )
            )

            planned_value = approved_budget * planned_progress
            earned_value = approved_budget * actual_progress
            actual_cost_real = earned_value / cost_eff

            cumulative_co_real = float(
                project_cos.loc[
                    project_cos["_effective_month"] <= month_idx, "approved_amount"
                ].sum()
            )
            actual_cost_real_total = actual_cost_real + cumulative_co_real

            inflation_multiplier = index_provider.value_at(snapshot_date) / index_provider.value_at(
                planned_start
            )
            actual_cost_nominal = actual_cost_real_total * inflation_multiplier

            committed_cost = actual_cost_nominal * (1.0 + profile.committed_buffer_fraction)

            cpi_now = earned_value / actual_cost_nominal if actual_cost_nominal > 0 else np.nan
            forecast_cost = float(
                evm.estimate_at_completion_cpi(
                    pd.Series([approved_budget]), pd.Series([cpi_now])
                ).iloc[0]
            )
            if not np.isfinite(forecast_cost):
                forecast_cost = approved_budget

            rows.append(
                {
                    "project_id": project_id,
                    "snapshot_date": snapshot_date.normalize(),
                    "planned_progress": round(planned_progress, 4),
                    "actual_progress": round(actual_progress, 4),
                    "planned_cost": round(planned_value, 2),
                    "actual_cost": round(actual_cost_nominal, 2),
                    "committed_cost": round(committed_cost, 2),
                    "earned_value": round(earned_value, 2),
                    "forecast_cost": round(forecast_cost, 2),
                }
            )

            actual_progress_prev = actual_progress
            if actual_progress >= 1.0:
                break

    return pd.DataFrame(rows)


def _generate_work_packages(
    rng: np.random.Generator,
    projects: pd.DataFrame,
    risk_profiles: dict[str, _RiskProfile],
    snapshots: pd.DataFrame,
    cfg: SyntheticDataConfig,
) -> pd.DataFrame:
    last_status = snapshots.sort_values("snapshot_date").groupby("project_id").tail(1)
    last_status_by_project = last_status.set_index("project_id")

    rows = []
    for record in projects.to_dict("records"):
        project_id = str(record["project_id"])
        approved_budget = float(record["approved_budget"])

        profile = risk_profiles[project_id]
        status = last_status_by_project.loc[project_id]
        n_packages = int(
            rng.integers(cfg.work_packages_per_project_min, cfg.work_packages_per_project_max + 1)
        )
        shares = rng.dirichlet(np.ones(n_packages))
        for j in range(n_packages):
            name = _WORK_PACKAGE_NAMES[j % len(_WORK_PACKAGE_NAMES)]
            suffix = (
                "" if j < len(_WORK_PACKAGE_NAMES) else f" ({j // len(_WORK_PACKAGE_NAMES) + 1})"
            )
            budget = round(max(approved_budget * shares[j], 500.0), 2)
            noise = float(rng.normal(0, 0.08))
            actual_cost = round(budget / max(profile.cost_efficiency_base + noise, 0.3), 2)
            planned_progress = float(status["planned_progress"])  # type: ignore[arg-type]
            wp_noise = float(np.clip(rng.normal(0, 0.05), -0.2, 0.2))
            actual_progress = float(np.clip(status["actual_progress"] + wp_noise, 0.0, 1.0))
            rows.append(
                {
                    "project_id": project_id,
                    "work_package_id": f"WP-{j + 1:03d}",
                    "work_package_name": f"{name}{suffix}",
                    "budget": budget,
                    "actual_cost": actual_cost,
                    "planned_progress": round(planned_progress, 4),
                    "actual_progress": round(actual_progress, 4),
                }
            )
    return pd.DataFrame(rows)


def _generate_suppliers(
    rng: np.random.Generator,
    projects: pd.DataFrame,
    risk_profiles: dict[str, _RiskProfile],
    cfg: SyntheticDataConfig,
) -> pd.DataFrame:
    # A shared pool smaller than (n_projects * suppliers_per_project) creates
    # realistic concentration: some suppliers serve many projects.
    pool_size = cfg.suppliers_pool_size
    pool_categories = [
        _SUPPLIER_CATEGORIES[i % len(_SUPPLIER_CATEGORIES)] for i in range(pool_size)
    ]
    # A handful of "star" suppliers are drawn far more often than the rest.
    popularity = rng.pareto(a=2.0, size=pool_size) + 0.1
    popularity = popularity / popularity.sum()

    rows = []
    for record in projects.to_dict("records"):
        project_id = str(record["project_id"])
        approved_budget = float(record["approved_budget"])

        profile = risk_profiles[project_id]
        n_suppliers = int(
            rng.integers(cfg.suppliers_per_project_min, cfg.suppliers_per_project_max + 1)
        )
        chosen = rng.choice(pool_size, size=n_suppliers, replace=False, p=popularity)
        remaining_value = approved_budget * float(rng.uniform(0.5, 0.85))
        shares = rng.dirichlet(np.ones(n_suppliers))
        for k, supplier_idx in enumerate(chosen):
            contract_value = round(max(remaining_value * shares[k], 1000.0), 2)
            quality_score = float(
                np.clip(rng.normal(profile.supplier_quality_mean, 1.0), 0.0, 10.0)
            )
            # Worse-vetted suppliers deliver later, more often (Section 8.2:
            # procurement delay -> schedule impact).
            delay_mean = (7.0 - quality_score) * 4.0
            delivery_delay_days = round(rng.normal(delay_mean, 10.0))
            rework_cost = round(
                contract_value
                * max(0.0, (7.0 - quality_score) / 100.0)
                * float(rng.uniform(0.5, 1.5)),
                2,
            )
            rows.append(
                {
                    "supplier_id": f"SUP-{supplier_idx + 1:04d}",
                    "supplier_category": pool_categories[supplier_idx].value,
                    "project_id": project_id,
                    "contract_value": contract_value,
                    "delivery_delay_days": delivery_delay_days,
                    "quality_score": round(quality_score, 2),
                    "rework_cost": rework_cost,
                }
            )
    return pd.DataFrame(rows)


def generate_portfolio(config: BaseAppConfig) -> PortfolioDataset:
    """Generate the full synthetic BuildGuard AI portfolio from `config`.

    Deterministic: the same `config.seed` and `config.synthetic_data`
    always produce byte-identical output (Section 26). Every returned table
    is validated against its data contract (`buildguard.data.contracts`)
    before being returned -- a contract violation here is a generator bug,
    and must fail loudly rather than ship silently malformed demo data.
    """
    from buildguard.data import contracts

    cfg = config.synthetic_data
    reference_date = pd.Timestamp(cfg.reference_date)
    rng = np.random.default_rng(config.seed)

    index_provider = DemoIndexProvider(
        reference_date=cfg.reference_date, history_years=cfg.history_years
    )
    economic_index = index_provider.get_series()
    projects_internal = _sample_projects(rng, cfg)
    risk_profiles = _sample_risk_profiles(rng, projects_internal)
    change_orders = _generate_change_orders(rng, projects_internal, risk_profiles)
    snapshots = _simulate_snapshots(
        projects_internal, risk_profiles, change_orders, index_provider, rng, reference_date
    )
    work_packages = _generate_work_packages(rng, projects_internal, risk_profiles, snapshots, cfg)
    suppliers = _generate_suppliers(rng, projects_internal, risk_profiles, cfg)

    projects = projects_internal.drop(columns=["duration_months_internal"])
    change_orders = change_orders.drop(columns=["_effective_month"])

    contracts.validate_projects(projects)
    contracts.validate_project_snapshots(snapshots)
    contracts.check_snapshots_within_project_lifecycle(projects, snapshots)
    contracts.validate_work_packages(work_packages)
    contracts.validate_change_orders(change_orders)
    contracts.validate_suppliers(suppliers)
    contracts.validate_economic_index(economic_index)

    return PortfolioDataset(
        projects=projects,
        snapshots=snapshots,
        work_packages=work_packages,
        change_orders=change_orders,
        suppliers=suppliers,
        economic_index=economic_index,
    )
