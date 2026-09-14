"""Product contracts for post-action recovery and effectiveness evidence."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class EffectivenessModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class EffectivenessMetric(EffectivenessModel):
    signal_key: str
    label: str
    unit: str
    direction_of_concern: Literal["HIGH", "LOW"]
    before: float
    after: float
    improvement_percent: float
    outcome: Literal["IMPROVED", "STABLE", "DETERIORATED"]


class EffectivenessReview(EffectivenessModel):
    effectiveness_check_id: str
    rca_case_id: str
    incident_id: str
    asset_id: str
    monitoring_start: datetime
    monitoring_end: datetime
    monitoring_periods: int
    baseline_window: str
    result: Literal[
        "PENDING",
        "INITIAL_EFFECTIVE",
        "EFFECTIVE",
        "INCONCLUSIVE",
        "INEFFECTIVE",
        "RECURRENCE",
    ]
    recurrence_detected: bool
    recovery_confirmed: bool
    approval_status: Literal["PENDING_REVIEW", "APPROVED"]
    closure_eligible: bool
    explanation: str
    approved_by: str | None
    approved_at: datetime | None
    source_reference: str
    metrics: list[EffectivenessMetric]
