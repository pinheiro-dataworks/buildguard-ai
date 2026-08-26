"""Unit tests for temporal / lifecycle features (Section 8.2 / 18)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from buildguard.features.temporal import (
    consecutive_decline_streak,
    lifecycle_fraction,
    lifecycle_stage,
    months_since_start,
    months_to_planned_completion,
    trailing_change,
)

pytestmark = pytest.mark.unit


class TestMonthsSinceStart:
    def test_matches_hand_calculation(self) -> None:
        start = pd.Series(pd.to_datetime(["2022-01-15"]))
        snapshot = pd.Series(pd.to_datetime(["2022-04-30"]))
        assert months_since_start(snapshot, start).iloc[0] == 3

    def test_zero_at_the_start_month(self) -> None:
        start = pd.Series(pd.to_datetime(["2022-06-01"]))
        assert months_since_start(start, start).iloc[0] == 0


class TestMonthsToPlannedCompletion:
    def test_positive_before_completion(self) -> None:
        snapshot = pd.Series(pd.to_datetime(["2022-04-30"]))
        completion = pd.Series(pd.to_datetime(["2023-01-15"]))
        assert months_to_planned_completion(snapshot, completion).iloc[0] == 9

    def test_negative_after_completion(self) -> None:
        snapshot = pd.Series(pd.to_datetime(["2023-06-30"]))
        completion = pd.Series(pd.to_datetime(["2023-01-15"]))
        assert months_to_planned_completion(snapshot, completion).iloc[0] < 0


class TestLifecycleFraction:
    def test_zero_at_start_one_at_planned_completion(self) -> None:
        start = pd.Series(pd.to_datetime(["2022-01-01"]))
        completion = pd.Series(pd.to_datetime(["2023-01-01"]))
        assert lifecycle_fraction(start, start, completion).iloc[0] == pytest.approx(0.0)
        assert lifecycle_fraction(completion, start, completion).iloc[0] == pytest.approx(1.0)

    def test_exceeds_one_past_planned_completion(self) -> None:
        start = pd.Series(pd.to_datetime(["2022-01-01"]))
        completion = pd.Series(pd.to_datetime(["2023-01-01"]))
        late_snapshot = pd.Series(pd.to_datetime(["2023-07-01"]))
        assert lifecycle_fraction(late_snapshot, start, completion).iloc[0] > 1.0


class TestLifecycleStage:
    def test_buckets_match_thresholds(self) -> None:
        fractions = pd.Series([0.1, 0.5, 0.9, 1.2])
        stages = lifecycle_stage(fractions, early_threshold=0.33, late_threshold=0.66)
        assert stages.tolist() == ["early", "mid", "late", "late"]

    def test_boundary_values_are_exclusive_to_the_lower_bucket(self) -> None:
        fractions = pd.Series([0.33, 0.66])
        stages = lifecycle_stage(fractions, early_threshold=0.33, late_threshold=0.66)
        assert stages.tolist() == ["early", "mid"]


class TestTrailingChange:
    def test_first_snapshot_per_project_is_nan(self) -> None:
        df = pd.DataFrame(
            {
                "project_id": ["A", "A"],
                "snapshot_date": pd.to_datetime(["2022-01-31", "2022-02-28"]),
                "cpi": [1.0, 0.9],
            }
        )
        result = trailing_change(df, "cpi", periods=1)
        assert np.isnan(result.iloc[0])
        assert result.iloc[1] == pytest.approx(-0.1)

    def test_does_not_cross_project_boundaries(self) -> None:
        df = pd.DataFrame(
            {
                "project_id": ["A", "B"],
                "snapshot_date": pd.to_datetime(["2022-02-28", "2022-01-31"]),
                "cpi": [0.9, 1.0],
            }
        )
        result = trailing_change(df, "cpi", periods=1)
        assert result.isna().all()  # each project only has one snapshot

    def test_result_is_reindexed_to_caller_row_order(self) -> None:
        df = pd.DataFrame(
            {
                "project_id": ["A", "A", "A"],
                "snapshot_date": pd.to_datetime(["2022-03-31", "2022-01-31", "2022-02-28"]),
                "cpi": [0.8, 1.0, 0.9],
            }
        )
        result = trailing_change(df, "cpi", periods=1)
        # Row 0 (March, latest chronologically) should show Feb -> Mar change.
        assert result.iloc[0] == pytest.approx(0.8 - 0.9)


class TestConsecutiveDeclineStreak:
    def test_streak_increments_on_consecutive_declines(self) -> None:
        df = pd.DataFrame(
            {
                "project_id": ["A"] * 4,
                "snapshot_date": pd.to_datetime(
                    ["2022-01-31", "2022-02-28", "2022-03-31", "2022-04-30"]
                ),
                "spi": [1.0, 0.95, 0.90, 0.92],
            }
        )
        streak = consecutive_decline_streak(df, "spi")
        assert streak.tolist() == [0, 1, 2, 0]

    def test_streak_resets_on_nan(self) -> None:
        df = pd.DataFrame(
            {
                "project_id": ["A"] * 3,
                "snapshot_date": pd.to_datetime(["2022-01-31", "2022-02-28", "2022-03-31"]),
                "spi": [1.0, 0.9, np.nan],
            }
        )
        streak = consecutive_decline_streak(df, "spi")
        assert streak.tolist() == [0, 1, 0]

    def test_does_not_cross_project_boundaries(self) -> None:
        df = pd.DataFrame(
            {
                "project_id": ["A", "A", "B", "B"],
                "snapshot_date": pd.to_datetime(
                    ["2022-01-31", "2022-02-28", "2022-01-31", "2022-02-28"]
                ),
                "spi": [1.0, 0.9, 1.0, 0.8],
            }
        )
        streak = consecutive_decline_streak(df, "spi")
        # Both projects independently start fresh and decline once.
        assert streak.tolist() == [0, 1, 0, 1]
