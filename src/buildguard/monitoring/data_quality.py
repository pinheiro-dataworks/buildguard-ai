"""Data quality monitoring (Section 23).

Tracks the five signals Section 23's Data Quality row names: missing
values, schema violations, unexpected categories, range violations, and
duplicate keys. Schema violations reuse the same `buildguard.data.contracts`
validators already enforced at ingestion (Section 8.5) -- monitoring never
re-implements what a contract already checks, it just reports when one
fails on a later batch. Range violations reuse the same
"outside the reference split's observed range" idea
`scripts/evaluate.py`'s failure analysis introduced (Section 47); the two
are now expressed through the same functions so the range definition can
never drift between the two callers.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class DataQualityReport:
    n_rows: int
    missing_value_counts: dict[str, int]
    missing_value_rates: dict[str, float]
    schema_violations: list[str]
    unexpected_categories: dict[str, list[str]]
    range_violation_counts: dict[str, int]
    duplicate_key_count: int

    @property
    def is_clean(self) -> bool:
        return (
            not self.schema_violations
            and not any(self.unexpected_categories.values())
            and not any(self.range_violation_counts.values())
            and self.duplicate_key_count == 0
        )


def missing_value_summary(df: pd.DataFrame) -> tuple[dict[str, int], dict[str, float]]:
    counts = df.isna().sum()
    rates = counts / len(df) if len(df) else counts.astype(float)
    return (
        {str(k): int(v) for k, v in counts.items()},
        {str(k): float(v) for k, v in rates.items()},
    )


def unexpected_categories(df: pd.DataFrame, expected: dict[str, set[str]]) -> dict[str, list[str]]:
    """For each `column -> allowed values` pair, the values actually present that aren't allowed."""
    found: dict[str, list[str]] = {}
    for column, allowed in expected.items():
        if column not in df.columns:
            continue
        actual = set(df[column].dropna().unique())
        unexpected = sorted(str(v) for v in (actual - allowed))
        found[column] = unexpected
    return found


def reference_ranges(df: pd.DataFrame, columns: list[str]) -> dict[str, tuple[float, float]]:
    """`{column: (min, max)}` observed in `df`, for use as a later batch's expected envelope."""
    return {
        col: (float(df[col].min()), float(df[col].max())) for col in columns if col in df.columns
    }


def range_violation_mask(df: pd.DataFrame, ranges: dict[str, tuple[float, float]]) -> pd.Series:
    """Row-level boolean mask: True where any ranged column falls outside its envelope."""
    mask = pd.Series(False, index=df.index)
    for col, (lo, hi) in ranges.items():
        if col not in df.columns:
            continue
        mask |= (df[col] < lo) | (df[col] > hi)
    return mask


def range_violations(df: pd.DataFrame, ranges: dict[str, tuple[float, float]]) -> dict[str, int]:
    """Per-column count of rows falling outside that column's `(min, max)` envelope."""
    counts: dict[str, int] = {}
    for col, (lo, hi) in ranges.items():
        if col not in df.columns:
            continue
        counts[col] = int(((df[col] < lo) | (df[col] > hi)).sum())
    return counts


def duplicate_key_count(df: pd.DataFrame, key_columns: list[str]) -> int:
    return int(df.duplicated(subset=key_columns).sum())


def run_data_quality_checks(
    df: pd.DataFrame,
    *,
    schema_validator: Callable[[pd.DataFrame], pd.DataFrame] | None = None,
    expected_categories: dict[str, set[str]] | None = None,
    numeric_ranges: dict[str, tuple[float, float]] | None = None,
    key_columns: list[str] | None = None,
) -> DataQualityReport:
    """Run every applicable Section 23 data-quality check against `df`.

    Every argument is optional -- pass only the checks relevant to the
    table/batch being monitored (e.g. `key_columns` for a table with a
    natural key, `numeric_ranges` from `reference_ranges()` on a trusted
    prior batch).
    """
    missing_counts, missing_rates = missing_value_summary(df)

    schema_violations: list[str] = []
    if schema_validator is not None:
        try:
            schema_validator(df)
        except Exception as exc:
            schema_violations.append(str(exc))

    return DataQualityReport(
        n_rows=len(df),
        missing_value_counts=missing_counts,
        missing_value_rates=missing_rates,
        schema_violations=schema_violations,
        unexpected_categories=unexpected_categories(df, expected_categories or {}),
        range_violation_counts=range_violations(df, numeric_ranges or {}),
        duplicate_key_count=duplicate_key_count(df, key_columns) if key_columns else 0,
    )
