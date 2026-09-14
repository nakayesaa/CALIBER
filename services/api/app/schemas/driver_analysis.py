"""Contracts for local, signal-level explanations of an anomaly decision."""

from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class DriverAnalysisModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SignalContribution(DriverAnalysisModel):
    driver_name: str
    signal_key: str
    source_field: str
    unit: str
    direction_of_concern: Literal["HIGH", "LOW"]
    value: float
    healthy_baseline: float
    alarm_limit: float
    trip_limit: float
    engineering_state: Literal["NORMAL", "ALARM", "TRIP"]
    trend: Literal["RISING", "FALLING", "STABLE"]
    first_alarm_at: AwareDatetime | None
    alarm_persistence_hours: int = Field(ge=0)
    chronology_rank: int | None = Field(default=None, ge=1)
    raw_model_impact: float = Field(ge=0)
    contribution_percent: float = Field(ge=0, le=100)


class DriverAnalysis(DriverAnalysisModel):
    alert_id: str
    asset_id: str
    model_id: str
    as_of: AwareDatetime
    anomaly_score: float = Field(ge=0, le=100)
    method: Literal["GROUPED_COUNTERFACTUAL_BASELINE_REPLACEMENT"]
    interpretation: str
    contributions: list[SignalContribution] = Field(min_length=1)
