"""Shared feature preprocessing for every model that consumes the feature table.

Promoted out of `baselines.py` once `classification.py`/`regression.py`
(Session H) needed the identical numeric/categorical handling -- exactly
the point at which sharing stops being a guess about future needs and
starts being real duplication (Section 27: "no duplicated feature logic").
"""

from __future__ import annotations

from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

NUMERIC_FEATURE_COLUMNS: tuple[str, ...] = (
    "gross_floor_area_m2",
    "number_of_towers",
    "number_of_units",
    "cpi",
    "spi",
    "cost_variance",
    "schedule_variance",
    "inflation_multiplier",
    "operational_variance",
    "inflation_component",
    "months_since_start",
    "months_to_planned_completion",
    "lifecycle_fraction",
    "cpi_trend",
    "spi_trend",
    "cpi_decline_streak",
    "spi_decline_streak",
    "change_order_count_to_date",
    "change_order_amount_to_date",
    "change_order_amount_ratio_to_date",
)
CATEGORICAL_FEATURE_COLUMNS: tuple[str, ...] = (
    "project_type",
    "construction_standard",
    "lifecycle_stage",
)


def build_preprocessor() -> ColumnTransformer:
    """Median-impute + standardize numeric features, mode-impute + one-hot categoricals."""
    numeric = Pipeline(
        steps=[
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
        ]
    )
    categorical = Pipeline(
        steps=[
            ("impute", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ]
    )
    return ColumnTransformer(
        transformers=[
            ("numeric", numeric, list(NUMERIC_FEATURE_COLUMNS)),
            ("categorical", categorical, list(CATEGORICAL_FEATURE_COLUMNS)),
        ]
    )
