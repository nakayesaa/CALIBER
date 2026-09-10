"""Validated contracts for model-independent feature engineering."""

from __future__ import annotations

from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class FeatureConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ConcernDirection(StrEnum):
    HIGH = "HIGH"
    LOW = "LOW"


class ConditionSignalConfig(FeatureConfigModel):
    source_column: str
    unit: str
    direction_of_concern: ConcernDirection
    alarm_limit: float
    trip_limit: float
    include_raw: bool = True
    delta_periods: list[int] = Field(min_length=1)
    rolling_windows: list[int] = Field(min_length=1)
    trend_periods: list[int] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_periods_and_limits(self) -> "ConditionSignalConfig":
        periods = self.delta_periods + self.rolling_windows + self.trend_periods
        if any(period <= 0 for period in periods):
            raise ValueError("All feature periods must be positive")
        for group in [self.delta_periods, self.rolling_windows, self.trend_periods]:
            if len(group) != len(set(group)):
                raise ValueError("Periods must be unique within each transformation")
        if self.direction_of_concern == ConcernDirection.HIGH:
            if self.trip_limit <= self.alarm_limit:
                raise ValueError("High-concern trip limit must exceed alarm limit")
        elif self.trip_limit >= self.alarm_limit:
            raise ValueError("Low-concern trip limit must be below alarm limit")
        return self


class ProcessSignalConfig(FeatureConfigModel):
    source_column: str
    unit: str
    include_raw: bool = True
    delta_periods: list[int] = Field(min_length=1)
    rolling_windows: list[int] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_periods(self) -> "ProcessSignalConfig":
        periods = self.delta_periods + self.rolling_windows
        if any(period <= 0 for period in periods):
            raise ValueError("All feature periods must be positive")
        if len(self.delta_periods) != len(set(self.delta_periods)):
            raise ValueError("Delta periods must be unique")
        if len(self.rolling_windows) != len(set(self.rolling_windows)):
            raise ValueError("Rolling windows must be unique")
        return self


class FeatureOutputConfig(FeatureConfigModel):
    metadata_columns: list[str] = Field(min_length=1)
    label_columns: list[str] = Field(min_length=1)


class EligibilityConfig(FeatureConfigModel):
    training_operating_modes: list[str] = Field(min_length=1)
    scoring_operating_modes: list[str] = Field(min_length=1)
    required_run_status: str
    training_requires_source_eligibility: bool = True
    training_requires_below_alarm: bool = True


class FeaturePipelineConfig(FeatureConfigModel):
    pipeline_id: str
    pipeline_version: str
    input_scenario_id: str
    expected_frequency: str
    condition_signals: dict[str, ConditionSignalConfig]
    process_signals: dict[str, ProcessSignalConfig]
    eligibility: EligibilityConfig
    output: FeatureOutputConfig

    @model_validator(mode="after")
    def validate_signal_sets(self) -> "FeaturePipelineConfig":
        if not self.condition_signals:
            raise ValueError("At least one condition signal is required")
        if not self.process_signals:
            raise ValueError("At least one process signal is required")
        source_columns = [
            signal.source_column
            for signal in [*self.condition_signals.values(), *self.process_signals.values()]
        ]
        if len(source_columns) != len(set(source_columns)):
            raise ValueError("Configured source columns must be unique")
        return self


class FeatureRole(StrEnum):
    MODEL_INPUT = "MODEL_INPUT"
    EXPLANATION_ONLY = "EXPLANATION_ONLY"


class FeatureCatalogEntry(FeatureConfigModel):
    feature_name: str
    feature_role: FeatureRole
    feature_group: str
    source_column: str
    transformation: str
    window_hours: int | None = None
    unit: str
    description: str


class FeatureManifest(FeatureConfigModel):
    pipeline_id: str
    pipeline_version: str
    input_scenario_id: str
    input_sha256: str
    generated_at: AwareDatetime
    row_count: int
    complete_row_count: int
    training_row_count: int
    scoring_row_count: int
    lookback_hours: int
    model_feature_columns: list[str]
    explanation_feature_columns: list[str]
    metadata_columns: list[str]
    label_columns: list[str]
    eligibility_columns: list[str]
    leakage_policy: str
    training_policy: str


class FeatureQualityCheck(FeatureConfigModel):
    name: str
    status: str
    actual: int | float | str | bool | dict[str, int]


class FeatureQualityReport(FeatureConfigModel):
    status: str
    pipeline_id: str
    checks: list[FeatureQualityCheck]
