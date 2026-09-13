"""HTTP request and response contracts for the KO-3201 vertical slice."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from services.api.app.schemas.actions import ActionPlan, ActionStatus
from services.api.app.schemas.alerts import AlertEvent, AlertStateTransition
from services.api.app.schemas.rca import RCARecord, RCAStatus
from services.api.app.schemas.retrieval import IncidentRetrievalResult


class APIModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SystemStatus(APIModel):
    phase: str
    api_status: str
    pipeline_artifacts: dict[str, bool]
    llm_enabled: bool


class AssetSummary(APIModel):
    asset_id: str
    tag: str
    name: str
    plant_id: str
    plant_name: str
    equipment_family: str
    equipment_type: str
    equipment_class: str
    discipline: str
    criticality: str
    monitoring_method: str


class AssetOverview(APIModel):
    asset: AssetSummary
    timeline_start: AwareDatetime
    timeline_end: AwareDatetime
    latest_decision_state: str
    highest_alert_severity: str | None
    alert_count: int


class TelemetryPoint(APIModel):
    timestamp: AwareDatetime
    operating_mode: str
    run_status: str
    radial_vibration_micron: float
    water_in_oil_ppm: float
    lube_oil_pressure_barg: float
    bearing_metal_temperature_degc: float
    feed_rate_tph: float
    discharge_pressure_barg: float
    anomaly_score: float | None
    anomaly_threshold: float
    is_anomaly: bool
    decision_state: str
    severity_rank: int
    alarm_breadth: int
    breached_signals: list[str]


class TelemetrySeries(APIModel):
    asset_id: str
    total_points: int
    returned_points: int
    points: list[TelemetryPoint]


class AlertDetail(APIModel):
    alert: AlertEvent
    state_transitions: list[AlertStateTransition]
    opening_snapshot: dict[str, object]
    similar_incidents: list[IncidentRetrievalResult]
    rca: RCARecord | None
    action_plans: list[ActionPlan]


class RCAGenerateRequest(APIModel):
    requested_by: str = Field(min_length=1)
    mode: Literal["ai", "prepared"] = "ai"


class RCAStatusUpdate(APIModel):
    status: RCAStatus
    actor: str = Field(min_length=1)
    note: str = Field(min_length=1)
    occurred_at: datetime | None = None


class ActionPlanCreateRequest(APIModel):
    hypothesis_id: str = Field(min_length=1)


class ActionStatusUpdate(APIModel):
    status: ActionStatus
    actor: str = Field(min_length=1)
    note: str = Field(min_length=1)
    occurred_at: datetime | None = None
