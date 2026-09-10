"""Validated contracts for anomaly training, scoring, and evaluation."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class AnomalyConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ChronologicalSplitConfig(AnomalyConfigModel):
    fit_fraction: float = Field(gt=0.5, lt=0.95)
    minimum_fit_rows: int = Field(ge=100)
    minimum_calibration_rows: int = Field(ge=50)


class RobustScalerConfig(AnomalyConfigModel):
    quantile_range: tuple[float, float]
    with_centering: bool = True
    with_scaling: bool = True
    unit_variance: bool = False

    @model_validator(mode="after")
    def validate_quantile_range(self) -> "RobustScalerConfig":
        lower, upper = self.quantile_range
        if not 0 < lower < upper < 100:
            raise ValueError("Scaler quantiles must satisfy 0 < lower < upper < 100")
        return self


class IsolationForestConfig(AnomalyConfigModel):
    n_estimators: int = Field(ge=50)
    max_samples: int | float | Literal["auto"]
    max_features: float = Field(gt=0, le=1)
    bootstrap: bool = False
    n_jobs: int

    @model_validator(mode="after")
    def validate_max_samples(self) -> "IsolationForestConfig":
        if isinstance(self.max_samples, float) and not 0 < self.max_samples <= 1:
            raise ValueError("Float max_samples must satisfy 0 < value <= 1")
        if isinstance(self.max_samples, int) and self.max_samples < 2:
            raise ValueError("Integer max_samples must be at least 2")
        return self


class ScoreCalibrationConfig(AnomalyConfigModel):
    anomaly_quantile: float = Field(gt=0.9, lt=1)
    median_normalized_score: float = Field(ge=0, lt=50)
    threshold_normalized_score: float = Field(gt=0, lt=100)
    exponent_clip: float = Field(gt=0)

    @model_validator(mode="after")
    def validate_score_anchors(self) -> "ScoreCalibrationConfig":
        if self.median_normalized_score >= self.threshold_normalized_score:
            raise ValueError("Median score must be below threshold score")
        return self


class DriverConfig(AnomalyConfigModel):
    maximum_drivers: int = Field(ge=1, le=5)
    included_feature_suffixes: list[str] = Field(min_length=1)


class EvaluationConfig(AnomalyConfigModel):
    normal_phases: list[str] = Field(min_length=1)
    degradation_phases: list[str] = Field(min_length=1)
    trip_phase: str
    recovery_phases: list[str] = Field(min_length=1)


class AnomalyModelConfig(AnomalyConfigModel):
    model_id: str
    model_version: str
    input_pipeline_id: str
    random_seed: int
    expected_feature_count: int = Field(ge=1)
    split: ChronologicalSplitConfig
    scaler: RobustScalerConfig
    estimator: IsolationForestConfig
    calibration: ScoreCalibrationConfig
    drivers: DriverConfig
    evaluation: EvaluationConfig


class ModelManifest(AnomalyConfigModel):
    model_id: str
    model_version: str
    estimator: str
    scaler: str
    input_pipeline_id: str
    feature_table_sha256: str
    model_config_sha256: str
    trained_at: AwareDatetime
    fit_started_at: AwareDatetime
    fit_ended_at: AwareDatetime
    fit_rows: int
    calibration_rows: int
    scoring_rows: int
    feature_count: int
    feature_columns: list[str]
    raw_anomaly_threshold: float
    normalized_anomaly_threshold: float
    score_transform: dict[str, float]
    driver_profiles: list[dict[str, Any]]
    artifact_file: str
    artifact_sha256: str


class ModelValidationCheck(AnomalyConfigModel):
    name: str
    status: str
    actual: int | float | str | bool


class ModelValidationReport(AnomalyConfigModel):
    status: str
    model_id: str
    checks: list[ModelValidationCheck]
