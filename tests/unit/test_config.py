"""Unit tests for typed configuration loading (src/buildguard/config.py)."""

from __future__ import annotations

from pathlib import Path

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
    bad_config = {
        "seed": 1,
        "paths": {
            "data_sample": "data/sample",
            "models_dir": "models",
            "reports_dir": "reports",
            "mlflow_tracking_uri": "file:./mlruns",
        },
        "targets": {"cost_overrun_tolerance": 0.1, "schedule_delay_tolerance_days": 14},
        "synthetic_data": {
            "n_projects": 100,
            "work_packages_per_project_min": 20,
            "work_packages_per_project_max": 80,
            "suppliers_total_min": 100,
            "suppliers_total_max": 1000,
            "monthly_observations_min": 12,
            "monthly_observations_max": 48,
        },
        "split": {
            "train_fraction": 0.5,
            "calibration_fraction": 0.3,
            "test_fraction": 0.3,
        },  # sums to 1.1
    }
    bad_path = tmp_path / "bad_base.yaml"
    bad_path.write_text(yaml.safe_dump(bad_config), encoding="utf-8")

    with pytest.raises(ValidationError, match="sum to 1"):
        load_base_config(bad_path)


def test_synthetic_data_min_le_max_enforced(tmp_path: Path) -> None:
    bad_config = {
        "seed": 1,
        "paths": {
            "data_sample": "data/sample",
            "models_dir": "models",
            "reports_dir": "reports",
            "mlflow_tracking_uri": "file:./mlruns",
        },
        "targets": {"cost_overrun_tolerance": 0.1, "schedule_delay_tolerance_days": 14},
        "synthetic_data": {
            "n_projects": 100,
            "work_packages_per_project_min": 80,
            "work_packages_per_project_max": 20,  # min > max
            "suppliers_total_min": 100,
            "suppliers_total_max": 1000,
            "monthly_observations_min": 12,
            "monthly_observations_max": 48,
        },
        "split": {"train_fraction": 0.6, "calibration_fraction": 0.2, "test_fraction": 0.2},
    }
    bad_path = tmp_path / "bad_base2.yaml"
    bad_path.write_text(yaml.safe_dump(bad_config), encoding="utf-8")

    with pytest.raises(ValidationError):
        load_base_config(bad_path)


def test_missing_config_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_base_config(tmp_path / "does_not_exist.yaml")
