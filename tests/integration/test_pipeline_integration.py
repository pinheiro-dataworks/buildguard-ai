"""Integration tests: raw sample data -> validation -> features -> prediction.

Uses the small, committed `data/sample/` CSVs -- not the regenerated
400-project portfolio every other test/script works from. This is the
closest thing this project has to "what a fresh `git clone` actually
exercises," proving the full pipeline holds together end to end rather
than each stage only being tested in isolation.
"""

from __future__ import annotations

import joblib
import pandas as pd
import pytest

from buildguard.config import PROJECT_ROOT, load_base_config
from buildguard.data import contracts
from buildguard.data.economic_index import DemoIndexProvider
from buildguard.features.pipeline import build_feature_table
from buildguard.models.preprocessing import CATEGORICAL_FEATURE_COLUMNS, NUMERIC_FEATURE_COLUMNS

pytestmark = pytest.mark.integration

SAMPLE_DIR = PROJECT_ROOT / "data" / "sample"
MODELS_DIR = PROJECT_ROOT / "models"


@pytest.fixture(scope="module")
def raw_tables() -> dict[str, pd.DataFrame]:
    return {
        "projects": pd.read_csv(
            SAMPLE_DIR / "projects.csv",
            parse_dates=["planned_start_date", "planned_completion_date"],
        ),
        "snapshots": pd.read_csv(
            SAMPLE_DIR / "project_snapshots.csv", parse_dates=["snapshot_date"]
        ),
        "change_orders": pd.read_csv(SAMPLE_DIR / "change_orders.csv", parse_dates=["date"]),
    }


@pytest.fixture(scope="module")
def features(raw_tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    cfg = load_base_config()
    provider = DemoIndexProvider(
        reference_date=cfg.synthetic_data.reference_date,
        history_years=cfg.synthetic_data.history_years,
    )
    return build_feature_table(
        raw_tables["projects"],
        raw_tables["snapshots"],
        raw_tables["change_orders"],
        provider,
        cfg.features,
    )


class TestRawToValidated:
    def test_sample_projects_pass_the_contract(self, raw_tables: dict[str, pd.DataFrame]) -> None:
        validated = contracts.validate_projects(raw_tables["projects"])
        assert len(validated) == len(raw_tables["projects"]) > 0

    def test_sample_snapshots_pass_the_contract(self, raw_tables: dict[str, pd.DataFrame]) -> None:
        validated = contracts.validate_project_snapshots(raw_tables["snapshots"])
        assert len(validated) == len(raw_tables["snapshots"]) > 0

    def test_sample_change_orders_pass_the_contract(
        self, raw_tables: dict[str, pd.DataFrame]
    ) -> None:
        validated = contracts.validate_change_orders(raw_tables["change_orders"])
        assert len(validated) == len(raw_tables["change_orders"]) > 0

    def test_cross_table_chronology_holds(self, raw_tables: dict[str, pd.DataFrame]) -> None:
        contracts.check_snapshots_within_project_lifecycle(
            raw_tables["projects"], raw_tables["snapshots"]
        )


class TestValidatedToFeatures:
    def test_one_feature_row_per_snapshot_row(
        self, features: pd.DataFrame, raw_tables: dict[str, pd.DataFrame]
    ) -> None:
        assert len(features) == len(raw_tables["snapshots"])

    def test_every_model_input_column_is_present(self, features: pd.DataFrame) -> None:
        for col in (*NUMERIC_FEATURE_COLUMNS, *CATEGORICAL_FEATURE_COLUMNS):
            assert col in features.columns

    def test_no_label_or_forbidden_leakage_column_is_present(self, features: pd.DataFrame) -> None:
        for forbidden in ("final_cost", "final_cost_real", "cost_overrun", "schedule_delay"):
            assert forbidden not in features.columns


class TestFeaturesToPrediction:
    def test_cost_overrun_champion_predicts_valid_probabilities(
        self, features: pd.DataFrame
    ) -> None:
        model = joblib.load(MODELS_DIR / "cost_overrun_champion.joblib")
        proba = model.predict_proba(features)[:, 1]
        assert len(proba) == len(features)
        assert ((proba >= 0.0) & (proba <= 1.0)).all()

    def test_schedule_delay_champion_predicts_valid_probabilities(
        self, features: pd.DataFrame
    ) -> None:
        model = joblib.load(MODELS_DIR / "schedule_delay_champion.joblib")
        proba = model.predict_proba(features)[:, 1]
        assert len(proba) == len(features)
        assert ((proba >= 0.0) & (proba <= 1.0)).all()

    def test_final_cost_champion_predicts_positive_finite_costs(
        self, features: pd.DataFrame
    ) -> None:
        model = joblib.load(MODELS_DIR / "final_cost_champion.joblib")
        prediction = model.predict(features)
        assert len(prediction) == len(features)
        assert (prediction > 0).all()
        assert pd.Series(prediction).notna().all()
