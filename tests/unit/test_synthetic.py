"""Tests for the synthetic portfolio generator (Section 8.2 / 35)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from buildguard.config import BaseAppConfig, load_base_config
from buildguard.data import contracts
from buildguard.data.economic_index import DemoIndexProvider
from buildguard.data.synthetic import PortfolioDataset, generate_portfolio

pytestmark = pytest.mark.unit


def _small_config(n_projects: int = 20, seed: int = 42) -> BaseAppConfig:
    base = load_base_config()
    small_synthetic = base.synthetic_data.model_copy(update={"n_projects": n_projects})
    return base.model_copy(update={"seed": seed, "synthetic_data": small_synthetic})


@pytest.fixture(scope="module")
def dataset() -> PortfolioDataset:
    return generate_portfolio(_small_config())


class TestDeterminism:
    def test_same_seed_produces_identical_tables(self) -> None:
        cfg = _small_config(seed=7)
        first = generate_portfolio(cfg)
        second = generate_portfolio(cfg)
        assert first.projects.equals(second.projects)
        assert first.snapshots.equals(second.snapshots)
        assert first.work_packages.equals(second.work_packages)
        assert first.change_orders.equals(second.change_orders)
        assert first.suppliers.equals(second.suppliers)
        assert first.economic_index.equals(second.economic_index)

    def test_different_seed_produces_different_projects(self) -> None:
        a = generate_portfolio(_small_config(seed=1))
        b = generate_portfolio(_small_config(seed=2))
        assert not a.projects.equals(b.projects)


class TestContractCompliance:
    """generate_portfolio() already validates internally; these calls are a
    defense-in-depth check that the *returned* tables independently satisfy
    every data contract, not just whatever validate_* saw before dropping
    internal-only columns.
    """

    def test_projects_satisfy_contract(self, dataset: PortfolioDataset) -> None:
        contracts.validate_projects(dataset.projects)

    def test_snapshots_satisfy_contract(self, dataset: PortfolioDataset) -> None:
        contracts.validate_project_snapshots(dataset.snapshots)

    def test_work_packages_satisfy_contract(self, dataset: PortfolioDataset) -> None:
        contracts.validate_work_packages(dataset.work_packages)

    def test_change_orders_satisfy_contract(self, dataset: PortfolioDataset) -> None:
        contracts.validate_change_orders(dataset.change_orders)

    def test_suppliers_satisfy_contract(self, dataset: PortfolioDataset) -> None:
        contracts.validate_suppliers(dataset.suppliers)

    def test_economic_index_satisfies_contract(self, dataset: PortfolioDataset) -> None:
        contracts.validate_economic_index(dataset.economic_index)

    def test_snapshots_within_project_lifecycle(self, dataset: PortfolioDataset) -> None:
        contracts.check_snapshots_within_project_lifecycle(dataset.projects, dataset.snapshots)


class TestScale:
    def test_project_count_matches_config(self, dataset: PortfolioDataset) -> None:
        assert len(dataset.projects) == 20

    def test_every_project_has_at_least_one_snapshot(self, dataset: PortfolioDataset) -> None:
        snapshot_project_ids = set(dataset.snapshots["project_id"])
        assert snapshot_project_ids == set(dataset.projects["project_id"])

    def test_every_project_has_work_packages_and_suppliers(self, dataset: PortfolioDataset) -> None:
        assert set(dataset.work_packages["project_id"]) == set(dataset.projects["project_id"])
        assert set(dataset.suppliers["project_id"]) == set(dataset.projects["project_id"])

    def test_suppliers_only_reference_known_projects(self, dataset: PortfolioDataset) -> None:
        assert set(dataset.suppliers["project_id"]) <= set(dataset.projects["project_id"])

    def test_change_orders_only_reference_known_projects(self, dataset: PortfolioDataset) -> None:
        if len(dataset.change_orders) > 0:
            assert set(dataset.change_orders["project_id"]) <= set(dataset.projects["project_id"])


class TestRealism:
    def test_some_but_not_all_projects_completed(self, dataset: PortfolioDataset) -> None:
        last = dataset.snapshots.sort_values("snapshot_date").groupby("project_id").tail(1)
        completed_fraction = (last["actual_progress"] >= 1.0).mean()
        # With in_flight_fraction ~0.12 this should land well inside (0, 1);
        # a value of exactly 0 or 1 would mean the in-flight/censoring logic
        # (or the progress-accumulation loop) isn't doing anything.
        assert 0.0 < completed_fraction < 1.0

    def test_snapshots_are_chronologically_increasing_per_project(
        self, dataset: PortfolioDataset
    ) -> None:
        for _, group in dataset.snapshots.groupby("project_id"):
            dates = group.sort_values("snapshot_date")["snapshot_date"].to_numpy()
            assert np.all(np.diff(dates) > np.timedelta64(0, "ns"))

    def test_actual_progress_never_decreases_within_a_project(
        self, dataset: PortfolioDataset
    ) -> None:
        for _, group in dataset.snapshots.groupby("project_id"):
            progress = group.sort_values("snapshot_date")["actual_progress"].to_numpy()
            assert np.all(np.diff(progress) >= -1e-9)

    def test_committed_cost_at_least_actual_cost(self, dataset: PortfolioDataset) -> None:
        # committed_cost = actual_cost * (1 + buffer), buffer >= 0 by design.
        assert (dataset.snapshots["committed_cost"] >= dataset.snapshots["actual_cost"]).all()

    def test_earned_value_never_exceeds_budget(self, dataset: PortfolioDataset) -> None:
        merged = dataset.snapshots.merge(
            dataset.projects[["project_id", "approved_budget"]], on="project_id"
        )
        assert (merged["earned_value"] <= merged["approved_budget"] + 1e-6).all()

    def test_inflation_materially_inflates_nominal_final_cost(
        self, dataset: PortfolioDataset
    ) -> None:
        """Regression guard for the documented nominal-vs-real overrun gap
        (see docs/adr/0004-synthetic-data-design.md): completed projects'
        nominal final cost should systematically exceed their inflation-
        adjusted equivalent, since actual_cost is nominal by construction.
        """
        last = dataset.snapshots.sort_values("snapshot_date").groupby("project_id").tail(1)
        completed = last[last["actual_progress"] >= 1.0].merge(
            dataset.projects[["project_id", "planned_start_date"]], on="project_id"
        )
        if len(completed) == 0:
            pytest.skip("no completed projects in this small sample")

        cfg = _small_config().synthetic_data
        provider = DemoIndexProvider(
            reference_date=cfg.reference_date, history_years=cfg.history_years
        )

        def _real_cost(row: pd.Series) -> float:
            index_at_start = provider.value_at(row["planned_start_date"])
            index_at_end = provider.value_at(row["snapshot_date"])
            return float(row["actual_cost"] * index_at_start / index_at_end)

        completed["real_actual_cost"] = completed.apply(_real_cost, axis=1)
        # Nominal cost must be at or above the inflation-adjusted cost for
        # (almost) every completed project -- the index is non-decreasing.
        assert (completed["actual_cost"] >= completed["real_actual_cost"] - 1e-6).all()
        assert completed["actual_cost"].sum() > completed["real_actual_cost"].sum()


class TestEconomicIndex:
    def test_index_is_monotonically_non_decreasing(self, dataset: PortfolioDataset) -> None:
        values = dataset.economic_index.sort_values("reference_month")["index_value"].to_numpy()
        assert np.all(np.diff(values) >= 0)

    def test_index_covers_the_full_history_window(self, dataset: PortfolioDataset) -> None:
        cfg = _small_config().synthetic_data
        months = dataset.economic_index["reference_month"]
        assert months.min() <= pd.Timestamp(cfg.reference_date) - pd.DateOffset(
            years=cfg.history_years
        ) + pd.DateOffset(months=2)
        assert months.max() <= pd.Timestamp(cfg.reference_date)
