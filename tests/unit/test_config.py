"""Unit tests for typed configuration loading (src/buildguard/config.py)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from buildguard.config import (
    BaseAppConfig,
    BusinessConfig,
    load_base_config,
    load_business_config,
)

pytestmark = pytest.mark.unit


def _base_config_dict(**synthetic_data_overrides: Any) -> dict[str, Any]:
    synthetic_data = {
        "n_projects": 100,
        "work_packages_per_project_min": 20,
        "work_packages_per_project_max": 80,
        "suppliers_pool_size": 400,
        "suppliers_per_project_min": 3,
        "suppliers_per_project_max": 12,
        "monthly_observations_min": 12,
        "monthly_observations_max": 48,
        "reference_date": "2026-01-01",
        "history_years": 5,
        "min_start_lead_months": 1,
        "in_flight_fraction": 0.12,
        **synthetic_data_overrides,
    }
    return {
        "seed": 1,
        "paths": {
            "data_sample": "data/sample",
            "data_processed": "data/processed",
            "models_dir": "models",
            "reports_dir": "reports",
            "mlflow_tracking_uri": "file:./mlruns",
        },
        "targets": {"cost_overrun_tolerance": 0.1, "schedule_delay_tolerance_days": 14},
        "synthetic_data": synthetic_data,
        "split": {"train_fraction": 0.6, "calibration_fraction": 0.2, "test_fraction": 0.2},
        "features": {
            "lifecycle_early_threshold": 0.33,
            "lifecycle_late_threshold": 0.66,
            "trend_window_months": 3,
        },
    }


def _write_config(tmp_path: Path, name: str, data: dict[str, Any]) -> Path:
    path = tmp_path / name
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_load_base_config_from_repo() -> None:
    config = load_base_config()
    assert isinstance(config, BaseAppConfig)
    assert config.seed == 42
    assert 0 < config.targets.cost_overrun_tolerance < 1
    assert config.synthetic_data.n_projects >= 100


def test_load_business_config_from_repo() -> None:
    config = load_business_config()
    assert isinstance(config, BusinessConfig)
    assert config.cost_risk.false_negative_cost > config.cost_risk.false_positive_cost


def test_split_fractions_must_sum_to_one(tmp_path: Path) -> None:
    data = _base_config_dict()
    data["split"] = {"train_fraction": 0.5, "calibration_fraction": 0.3, "test_fraction": 0.3}
    bad_path = _write_config(tmp_path, "bad_base.yaml", data)

    with pytest.raises(ValidationError, match="sum to 1"):
        load_base_config(bad_path)


def test_work_package_min_le_max_enforced(tmp_path: Path) -> None:
    data = _base_config_dict(work_packages_per_project_min=80, work_packages_per_project_max=20)
    bad_path = _write_config(tmp_path, "bad_wp.yaml", data)

    with pytest.raises(ValidationError):
        load_base_config(bad_path)


def test_suppliers_per_project_min_le_max_enforced(tmp_path: Path) -> None:
    data = _base_config_dict(suppliers_per_project_min=12, suppliers_per_project_max=3)
    bad_path = _write_config(tmp_path, "bad_suppliers.yaml", data)

    with pytest.raises(ValidationError):
        load_base_config(bad_path)


def test_suppliers_per_project_max_cannot_exceed_pool_size(tmp_path: Path) -> None:
    data = _base_config_dict(suppliers_pool_size=5, suppliers_per_project_max=12)
    bad_path = _write_config(tmp_path, "bad_pool.yaml", data)

    with pytest.raises(ValidationError):
        load_base_config(bad_path)


def test_min_start_lead_months_cannot_exceed_min_duration(tmp_path: Path) -> None:
    data = _base_config_dict(min_start_lead_months=24, monthly_observations_min=12)
    bad_path = _write_config(tmp_path, "bad_lead.yaml", data)

    with pytest.raises(ValidationError):
        load_base_config(bad_path)


def test_missing_config_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_base_config(tmp_path / "does_not_exist.yaml")


def test_lifecycle_thresholds_must_be_ordered(tmp_path: Path) -> None:
    data = _base_config_dict()
    data["features"] = {
        "lifecycle_early_threshold": 0.7,
        "lifecycle_late_threshold": 0.3,
        "trend_window_months": 3,
    }
    bad_path = _write_config(tmp_path, "bad_lifecycle.yaml", data)

    with pytest.raises(ValidationError):
        load_base_config(bad_path)
