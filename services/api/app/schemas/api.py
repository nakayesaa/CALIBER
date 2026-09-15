"""HTTP request and response contracts for the KO-3201 vertical slice."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from services.api.app.schemas.actions import ActionPlan, ActionStatus
from services.api.app.schemas.alerts import AlertEvent, AlertStateTransition
from services.api.app.schemas.rca import RCARecord, RCAStatus
from services.api.app.schemas.retrieval import IncidentRetrievalResult

ActorName = Annotated[str, Field(min_length=1, max_length=120)]
WorkflowNote = Annotated[str, Field(min_length=1, max_length=2000)]
WorkflowIdentifier = Annotated[
    str,
    Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"),
]


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


class ProductionBaseline(APIModel):
    method: Literal["CONTEXTUAL_HEALTHY_MEDIAN"]
    expected_feed_tph: float
    representative_plant_rate_tph: float
    plant_rate_tolerance_tph: float
    healthy_sample_count: int
    reference_start: AwareDatetime
    reference_end: AwareDatetime
    confidence: Literal["HIGH", "MEDIUM", "LOW"]
    source_reference: str


class ProductionImpact(APIModel):
    metric: Literal["PRODUCTION_SHORTFALL"]
    provenance: Literal["CALCULATED"]
    window_start: AwareDatetime
    window_end: AwareDatetime
    offline_hours: float
    actual_feed_tonnes: float
    expected_feed_tonnes: float
    estimated_shortfall_tonnes: float
    baseline: ProductionBaseline


class AssetOverview(APIModel):
    asset: AssetSummary
    timeline_start: AwareDatetime
    timeline_end: AwareDatetime
    latest_decision_state: str
    highest_alert_severity: str | None
    alert_count: int
    production_impact: ProductionImpact | None


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
    motor_current_a: float
    plant_rate_tph: float
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


class PreparedWorkflow(APIModel):
    rca: RCARecord
    action_plans: list[ActionPlan]


class AlertDetail(APIModel):
    alert: AlertEvent
    state_transitions: list[AlertStateTransition]
    opening_snapshot: dict[str, object]
    similar_incidents: list[IncidentRetrievalResult]
    rca: RCARecord | None
    action_plans: list[ActionPlan]
    prepared_workflow: PreparedWorkflow | None = None


class RCAGenerateRequest(APIModel):
    requested_by: ActorName
    mode: Literal["ai", "prepared"] = "ai"


class RCAStatusUpdate(APIModel):
    status: RCAStatus
    actor: ActorName
    note: WorkflowNote
    occurred_at: datetime | None = None


class ActionPlanCreateRequest(APIModel):
    hypothesis_id: WorkflowIdentifier


class ActionStatusUpdate(APIModel):
    status: ActionStatus
    actor: ActorName
    note: WorkflowNote
    occurred_at: datetime | None = None
