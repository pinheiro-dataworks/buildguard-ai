"""Unit tests for data quality monitoring (Section 23)."""

from __future__ import annotations

import pandas as pd
import pytest

from buildguard.monitoring.data_quality import (
    DataQualityReport,
    duplicate_key_count,
    missing_value_summary,
    range_violation_mask,
    range_violations,
    reference_ranges,
    run_data_quality_checks,
    unexpected_categories,
)

pytestmark = pytest.mark.monitoring


def _clean_projects() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "project_id": ["PRJ-001", "PRJ-002", "PRJ-003"],
            "project_type": ["residential", "commercial", "residential"],
            "gross_floor_area_m2": [1000.0, 2000.0, 1500.0],
        }
    )


class TestMissingValueSummary:
    def test_no_missing_values_reports_zero(self) -> None:
        counts, rates = missing_value_summary(_clean_projects())
        assert all(c == 0 for c in counts.values())
        assert all(r == 0.0 for r in rates.values())

    def test_missing_values_are_counted_and_rated(self) -> None:
        df = _clean_projects()
        df.loc[0, "gross_floor_area_m2"] = None
        counts, rates = missing_value_summary(df)
        assert counts["gross_floor_area_m2"] == 1
        assert rates["gross_floor_area_m2"] == pytest.approx(1 / 3)


class TestUnexpectedCategories:
    def test_clean_categories_report_nothing(self) -> None:
        result = unexpected_categories(
            _clean_projects(), {"project_type": {"residential", "commercial", "industrial"}}
        )
        assert result["project_type"] == []

    def test_unseen_category_is_flagged(self) -> None:
        df = _clean_projects()
        df.loc[0, "project_type"] = "spaceport"
        result = unexpected_categories(df, {"project_type": {"residential", "commercial"}})
        assert result["project_type"] == ["spaceport"]

    def test_missing_column_is_skipped_not_raised(self) -> None:
        result = unexpected_categories(_clean_projects(), {"not_a_column": {"x"}})
        assert result == {}


class TestRangeViolations:
    def test_reference_ranges_match_the_observed_min_max(self) -> None:
        ranges = reference_ranges(_clean_projects(), ["gross_floor_area_m2"])
        assert ranges["gross_floor_area_m2"] == (1000.0, 2000.0)

    def test_in_range_values_are_not_flagged(self) -> None:
        ranges = {"gross_floor_area_m2": (500.0, 3000.0)}
        counts = range_violations(_clean_projects(), ranges)
        assert counts["gross_floor_area_m2"] == 0

    def test_out_of_range_values_are_counted(self) -> None:
        df = _clean_projects()
        df.loc[0, "gross_floor_area_m2"] = 50_000.0
        ranges = {"gross_floor_area_m2": (500.0, 3000.0)}
        counts = range_violations(df, ranges)
        assert counts["gross_floor_area_m2"] == 1

    def test_row_level_mask_matches_column_level_count(self) -> None:
        df = _clean_projects()
        df.loc[0, "gross_floor_area_m2"] = 50_000.0
        ranges = {"gross_floor_area_m2": (500.0, 3000.0)}
        mask = range_violation_mask(df, ranges)
        assert int(mask.sum()) == range_violations(df, ranges)["gross_floor_area_m2"]


class TestDuplicateKeyCount:
    def test_unique_keys_report_zero(self) -> None:
        assert duplicate_key_count(_clean_projects(), ["project_id"]) == 0

    def test_duplicated_key_is_counted(self) -> None:
        df = pd.concat([_clean_projects(), _clean_projects().iloc[[0]]], ignore_index=True)
        assert duplicate_key_count(df, ["project_id"]) == 1


class TestRunDataQualityChecks:
    def test_clean_data_produces_a_clean_report(self) -> None:
        report = run_data_quality_checks(
            _clean_projects(),
            expected_categories={"project_type": {"residential", "commercial", "industrial"}},
            numeric_ranges={"gross_floor_area_m2": (500.0, 3000.0)},
            key_columns=["project_id"],
        )
        assert isinstance(report, DataQualityReport)
        assert report.is_clean
        assert report.n_rows == 3

    def test_a_single_real_problem_makes_the_report_not_clean(self) -> None:
        df = _clean_projects()
        df.loc[0, "project_type"] = "spaceport"
        report = run_data_quality_checks(
            df, expected_categories={"project_type": {"residential", "commercial"}}
        )
        assert not report.is_clean

    def test_schema_validator_failure_is_captured_not_raised(self) -> None:
        def _always_fails(df: pd.DataFrame) -> pd.DataFrame:
            raise ValueError("simulated contract violation")

        report = run_data_quality_checks(_clean_projects(), schema_validator=_always_fails)
        assert len(report.schema_violations) == 1
        assert "simulated contract violation" in report.schema_violations[0]
        assert not report.is_clean
