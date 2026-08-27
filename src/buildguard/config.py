"""Typed, externalized configuration loading.

Every threshold and magic number referenced by ``src/buildguard`` should
resolve back to a value declared in ``configs/*.yaml`` and modeled here,
rather than being hard-coded at the call site (Section 27/37 of
``BUILDGUARD_AI_PROJECT_SCOPE.md``).
"""

from __future__ import annotations

import datetime as dt
from functools import cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, model_validator

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIGS_DIR = PROJECT_ROOT / "configs"


class PathsConfig(BaseModel):
    data_sample: Path
    data_processed: Path
    models_dir: Path
    reports_dir: Path
    mlflow_tracking_uri: str


class TargetsConfig(BaseModel):
    cost_overrun_tolerance: float = Field(ge=0, le=1)
    schedule_delay_tolerance_days: int = Field(ge=0)


class SyntheticDataConfig(BaseModel):
    n_projects: int = Field(ge=1)
    work_packages_per_project_min: int = Field(ge=1)
    work_packages_per_project_max: int = Field(ge=1)
    suppliers_pool_size: int = Field(ge=1)
    suppliers_per_project_min: int = Field(ge=1)
    suppliers_per_project_max: int = Field(ge=1)
    monthly_observations_min: int = Field(ge=1)
    monthly_observations_max: int = Field(ge=1)
    reference_date: dt.date
    history_years: int = Field(ge=1)
    min_start_lead_months: int = Field(ge=1)
    in_flight_fraction: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def _check_ranges(self) -> SyntheticDataConfig:
        if self.work_packages_per_project_min > self.work_packages_per_project_max:
            raise ValueError("work_packages_per_project_min must be <= _max")
        if self.suppliers_per_project_min > self.suppliers_per_project_max:
            raise ValueError("suppliers_per_project_min must be <= suppliers_per_project_max")
        if self.suppliers_per_project_max > self.suppliers_pool_size:
            raise ValueError("suppliers_per_project_max cannot exceed suppliers_pool_size")
        if self.monthly_observations_min > self.monthly_observations_max:
            raise ValueError("monthly_observations_min must be <= _max")
        if self.min_start_lead_months > self.monthly_observations_min:
            raise ValueError("min_start_lead_months must be <= monthly_observations_min")
        return self


class FeaturesConfig(BaseModel):
    lifecycle_early_threshold: float = Field(gt=0, lt=1)
    lifecycle_late_threshold: float = Field(gt=0, lt=1)
    trend_window_months: int = Field(ge=1)

    @model_validator(mode="after")
    def _check_thresholds_ordered(self) -> FeaturesConfig:
        if self.lifecycle_early_threshold >= self.lifecycle_late_threshold:
            raise ValueError("lifecycle_early_threshold must be < lifecycle_late_threshold")
        return self


class BaselinesConfig(BaseModel):
    cpi_risk_threshold: float = Field(gt=0)


class TrainingConfig(BaseModel):
    optuna_n_trials: int = Field(ge=1)
    cv_splits: int = Field(ge=2)
    mlflow_experiment_name: str


class UncertaintyConfig(BaseModel):
    target_coverage: float = Field(gt=0, lt=1)


class SplitConfig(BaseModel):
    train_fraction: float = Field(gt=0, lt=1)
    calibration_fraction: float = Field(gt=0, lt=1)
    test_fraction: float = Field(gt=0, lt=1)

    @model_validator(mode="after")
    def _check_sums_to_one(self) -> SplitConfig:
        total = self.train_fraction + self.calibration_fraction + self.test_fraction
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"split fractions must sum to 1.0, got {total}")
        return self


class BaseAppConfig(BaseModel):
    seed: int
    paths: PathsConfig
    targets: TargetsConfig
    synthetic_data: SyntheticDataConfig
    split: SplitConfig
    features: FeaturesConfig
    baselines: BaselinesConfig
    training: TrainingConfig
    uncertainty: UncertaintyConfig


class CostMatrix(BaseModel):
    false_negative_cost: float = Field(gt=0)
    false_positive_cost: float = Field(gt=0)


class BusinessImpactConfig(BaseModel):
    avoidable_impact_assumption: float = Field(ge=0, le=1)


class BusinessConfig(BaseModel):
    cost_risk: CostMatrix
    schedule_risk: CostMatrix
    business_impact: BusinessImpactConfig


def _read_yaml(path: Path) -> dict[str, object]:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected a YAML mapping at top level in {path}, got {type(data)}")
    return data


@cache
def load_base_config(path: Path | None = None) -> BaseAppConfig:
    """Load and validate ``configs/base.yaml`` (or an explicit override path)."""
    resolved = path or (CONFIGS_DIR / "base.yaml")
    return BaseAppConfig.model_validate(_read_yaml(resolved))


@cache
def load_business_config(path: Path | None = None) -> BusinessConfig:
    """Load and validate ``configs/business.yaml`` (or an explicit override path)."""
    resolved = path or (CONFIGS_DIR / "business.yaml")
    return BusinessConfig.model_validate(_read_yaml(resolved))
