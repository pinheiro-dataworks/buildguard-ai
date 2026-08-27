"""Unit tests for the chronological, project-grouped split (Section 12)."""

from __future__ import annotations

import pandas as pd
import pytest

from buildguard.config import SplitConfig
from buildguard.data.split import (
    SplitAssignment,
    chronological_project_split,
    filter_by_split,
)

pytestmark = pytest.mark.unit


def _projects(n: int) -> pd.DataFrame:
    # Deliberately shuffled start dates to prove the split sorts them.
    dates = pd.date_range("2020-01-01", periods=n, freq="7D")
    shuffled = dates.to_list()
    shuffled = shuffled[::2] + shuffled[1::2]  # interleave, not chronological
    return pd.DataFrame(
        {
            "project_id": [f"PRJ-{i:03d}" for i in range(n)],
            "planned_start_date": shuffled,
        }
    )


def _split_config(train: float = 0.6, calibration: float = 0.2, test: float = 0.2) -> SplitConfig:
    return SplitConfig(train_fraction=train, calibration_fraction=calibration, test_fraction=test)


class TestChronologicalProjectSplit:
    def test_every_project_assigned_exactly_once(self) -> None:
        projects = _projects(100)
        assignment = chronological_project_split(projects, _split_config())
        all_ids = (
            assignment.train_project_ids
            | assignment.calibration_project_ids
            | assignment.test_project_ids
        )
        assert all_ids == set(projects["project_id"])
        assert len(all_ids) == 100  # no duplicates across splits

    def test_splits_are_disjoint(self) -> None:
        projects = _projects(100)
        assignment = chronological_project_split(projects, _split_config())
        assert not (assignment.train_project_ids & assignment.calibration_project_ids)
        assert not (assignment.train_project_ids & assignment.test_project_ids)
        assert not (assignment.calibration_project_ids & assignment.test_project_ids)

    def test_split_sizes_match_fractions(self) -> None:
        projects = _projects(100)
        assignment = chronological_project_split(projects, _split_config(0.6, 0.2, 0.2))
        assert len(assignment.train_project_ids) == 60
        assert len(assignment.calibration_project_ids) == 20
        assert len(assignment.test_project_ids) == 20

    def test_train_holds_the_oldest_projects_test_the_newest(self) -> None:
        projects = pd.DataFrame(
            {
                "project_id": [f"PRJ-{i:02d}" for i in range(10)],
                "planned_start_date": pd.date_range("2020-01-01", periods=10, freq="30D"),
            }
        )
        assignment = chronological_project_split(projects, _split_config(0.6, 0.2, 0.2))
        # Oldest 6 -> train, next 2 -> calibration, newest 2 -> test.
        assert assignment.train_project_ids == {f"PRJ-{i:02d}" for i in range(6)}
        assert assignment.calibration_project_ids == {f"PRJ-{i:02d}" for i in (6, 7)}
        assert assignment.test_project_ids == {f"PRJ-{i:02d}" for i in (8, 9)}

    def test_deterministic_across_calls(self) -> None:
        projects = _projects(50)
        a = chronological_project_split(projects, _split_config())
        b = chronological_project_split(projects, _split_config())
        assert a == b

    def test_ties_broken_by_project_id(self) -> None:
        # All same start date -> order must fall back to project_id.
        projects = pd.DataFrame(
            {
                "project_id": ["PRJ-C", "PRJ-A", "PRJ-B"],
                "planned_start_date": pd.to_datetime(["2022-01-01"] * 3),
            }
        )
        assignment = chronological_project_split(projects, _split_config(1 / 3, 1 / 3, 1 / 3))
        assert assignment.train_project_ids == {"PRJ-A"}

    def test_empty_projects_raises(self) -> None:
        empty = pd.DataFrame(columns=["project_id", "planned_start_date"])
        with pytest.raises(ValueError, match="empty"):
            chronological_project_split(empty, _split_config())

    def test_duplicate_project_id_raises(self) -> None:
        projects = pd.DataFrame(
            {
                "project_id": ["PRJ-A", "PRJ-A"],
                "planned_start_date": pd.to_datetime(["2022-01-01", "2022-02-01"]),
            }
        )
        with pytest.raises(ValueError, match="duplicate"):
            chronological_project_split(projects, _split_config())


class TestSplitOf:
    def test_returns_correct_split_name(self) -> None:
        assignment = SplitAssignment(
            train_project_ids=frozenset({"A"}),
            calibration_project_ids=frozenset({"B"}),
            test_project_ids=frozenset({"C"}),
        )
        assert assignment.split_of("A") == "train"
        assert assignment.split_of("B") == "calibration"
        assert assignment.split_of("C") == "test"

    def test_unknown_project_raises_keyerror(self) -> None:
        assignment = SplitAssignment(
            train_project_ids=frozenset({"A"}),
            calibration_project_ids=frozenset(),
            test_project_ids=frozenset(),
        )
        with pytest.raises(KeyError):
            assignment.split_of("UNKNOWN")


class TestFilterBySplit:
    def test_filters_rows_to_the_given_project_ids(self) -> None:
        df = pd.DataFrame({"project_id": ["A", "B", "C"], "value": [1, 2, 3]})
        filtered = filter_by_split(df, frozenset({"A", "C"}))
        assert set(filtered["project_id"]) == {"A", "C"}
        assert list(filtered.index) == [0, 1]  # reset_index applied

    def test_snapshots_of_excluded_project_never_appear(self) -> None:
        snapshots = pd.DataFrame(
            {
                "project_id": ["A", "A", "B", "B"],
                "snapshot_date": pd.to_datetime(
                    ["2022-01-31", "2022-02-28", "2022-01-31", "2022-02-28"]
                ),
            }
        )
        filtered = filter_by_split(snapshots, frozenset({"A"}))
        assert (filtered["project_id"] == "A").all()
        assert len(filtered) == 2
