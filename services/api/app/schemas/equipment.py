"""Asset-neutral source series and an evidence-backed equipment investigation."""

from datetime import date
from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from services.api.app.schemas.alerts import AlertEvent, AlertStateTransition
from services.api.app.schemas.api import APIModel, AssetSummary, InvestigationEvidenceEvent


class EquipmentPoint(APIModel):
    timestamp: AwareDatetime
    value: float = Field(allow_inf_nan=False)
    source_reference: str
    source_status: str | None = None


class EquipmentSignal(APIModel):
    key: str
    label: str
    unit: str
    direction: Literal["HIGH", "LOW"] | None = None
    alarm_limit: float | None = None
    trip_limit: float | None = None
    cadence: Literal["WEEKLY", "HOURLY"]
    source_key: str
    points: list[EquipmentPoint]

    @model_validator(mode="after")
    def ordered_points(self):
        dates = [point.timestamp for point in self.points]
        if dates != sorted(set(dates)):
            raise ValueError("Signal points must have unique ascending timestamps")
        interval = 604800 if self.cadence == "WEEKLY" else 3600
        if any(
            (right - left).total_seconds() != interval
            for left, right in zip(dates, dates[1:], strict=False)
        ):
            raise ValueError("Signal timestamps must match the declared cadence")
        if self.direction and (self.alarm_limit is None or self.trip_limit is None):
            raise ValueError("Condition signals require alarm and trip limits")
        if self.direction:
            sign = 1 if self.direction == "HIGH" else -1
            if sign * (self.trip_limit - self.alarm_limit) <= 0:
                raise ValueError("Trip limit must be more severe than alarm limit")
        return self


class EquipmentAssessment(APIModel):
    timestamp: AwareDatetime
    state: Literal["NORMAL", "WATCH", "WARNING", "HIGH", "CRITICAL"]
    score: float = Field(ge=0, le=100)
    breached_signals: list[str]
    reason: str
    source_status: str


class EquipmentSourceAction(APIModel):
    id: str
    title: str
    action_type: Literal["CORRECTIVE", "PREVENTIVE"]
    owner: str
    due_date: date
    status: str
    source_reference: str


class EquipmentOperatingState(APIModel):
    timestamp: AwareDatetime
    state: Literal["ON", "OFF"]
    source_reference: str


class EquipmentInvestigation(APIModel):
    asset: AssetSummary
    signals: list[EquipmentSignal]
    assessments: list[EquipmentAssessment]
    transitions: list[AlertStateTransition]
    alert: AlertEvent
    events: list[InvestigationEvidenceEvent]
    source_actions: list[EquipmentSourceAction]
    operating_states: list[EquipmentOperatingState] = Field(default_factory=list)
    quality_issues: list[str]
    reported_downtime_hours: float = Field(ge=0)
    reported_production_loss_tonnes: float = Field(ge=0)
