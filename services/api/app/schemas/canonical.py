"""Validated canonical contracts shared by ingestion, API, and analytics.

The models intentionally keep source facts, derived values, and human decisions
separate.  They are strict so a source schema change fails during ingestion
instead of silently changing product behavior.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator


class CanonicalModel(BaseModel):
    """Base configuration for all canonical records."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        use_enum_values=True,
    )


class SourceType(StrEnum):
    OBSERVED_ANCHOR = "OBSERVED_ANCHOR"
    SYNTHETIC_NORMAL = "SYNTHETIC_NORMAL"
    SYNTHETIC_ANOMALY = "SYNTHETIC_ANOMALY"
    SYNTHETIC_INTERVENTION = "SYNTHETIC_INTERVENTION"
    DERIVED_FEATURE = "DERIVED_FEATURE"
    HUMAN_CONFIRMED = "HUMAN_CONFIRMED"


class QualityFlag(StrEnum):
    VALID = "VALID"
    TIMEZONE_ASSUMED = "TIMEZONE_ASSUMED"
    MISSING = "MISSING"
    DUPLICATE = "DUPLICATE"
    OUT_OF_ORDER = "OUT_OF_ORDER"
    STALE_OR_FLATLINE = "STALE_OR_FLATLINE"
    PLAUSIBILITY_WARNING = "PLAUSIBILITY_WARNING"
    UNIT_CONFLICT = "UNIT_CONFLICT"
    AMBIGUOUS_MEASUREMENT = "AMBIGUOUS_MEASUREMENT"
    SOURCE_DISAGREEMENT = "SOURCE_DISAGREEMENT"
    CADENCE_DIFFERENCE = "CADENCE_DIFFERENCE"
    MISSING_EVIDENCE = "MISSING_EVIDENCE"


class DirectionOfConcern(StrEnum):
    HIGH = "HIGH"
    LOW = "LOW"
    BOTH = "BOTH"


class OperatingMode(StrEnum):
    RUNNING_STEADY = "RUNNING_STEADY"
    STARTUP = "STARTUP"
    SHUTDOWN_TRANSIENT = "SHUTDOWN_TRANSIENT"
    OFFLINE_TRIP = "OFFLINE_TRIP"
    OFFLINE_PLANNED = "OFFLINE_PLANNED"
    MAINTENANCE = "MAINTENANCE"
    RESTART = "RESTART"
    UNKNOWN = "UNKNOWN"


class HealthState(StrEnum):
    NORMAL = "NORMAL"
    WATCH = "WATCH"
    ALARM = "ALARM"
    CRITICAL = "CRITICAL"
    TRIP = "TRIP"
    RECOVERY_MONITORING = "RECOVERY_MONITORING"
    UNKNOWN = "UNKNOWN"


class WorkflowStatus(StrEnum):
    NEW_REGISTERED = "NEW_REGISTERED"
    RCA_PROCESS = "RCA_PROCESS"
    CA_PA_EXECUTION = "CA_PA_EXECUTION"
    MONITORING_RESULT = "MONITORING_RESULT"
    RISK_CLOSED = "RISK_CLOSED"
    RISK_CANCELED = "RISK_CANCELED"


class EvidenceType(StrEnum):
    SENSOR = "SENSOR"
    LAB = "LAB"
    INSPECTION = "INSPECTION"
    WORK_ORDER = "WORK_ORDER"
    HUMAN_STATEMENT = "HUMAN_STATEMENT"
    HISTORICAL_ANALOGY = "HISTORICAL_ANALOGY"
    AI_INFERENCE = "AI_INFERENCE"


class VerificationStatus(StrEnum):
    AVAILABLE_VERIFIED = "AVAILABLE_VERIFIED"
    AVAILABLE_UNVERIFIED = "AVAILABLE_UNVERIFIED"
    REFERENCED_NOT_AVAILABLE = "REFERENCED_NOT_AVAILABLE"
    REQUESTED = "REQUESTED"
    REJECTED = "REJECTED"


class HypothesisStatus(StrEnum):
    PROPOSED = "PROPOSED"
    UNDER_REVIEW = "UNDER_REVIEW"
    REJECTED = "REJECTED"
    CONFIRMED = "CONFIRMED"


class ActionType(StrEnum):
    CONTAINMENT = "CONTAINMENT"
    CORRECTIVE = "CORRECTIVE"
    PREVENTIVE = "PREVENTIVE"
    PROACTIVE = "PROACTIVE"


class ActionStatus(StrEnum):
    PROPOSED = "PROPOSED"
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"
    WAIVED = "WAIVED"


class EffectivenessResult(StrEnum):
    PENDING = "PENDING"
    INITIAL_EFFECTIVE = "INITIAL_EFFECTIVE"
    EFFECTIVE = "EFFECTIVE"
    INCONCLUSIVE = "INCONCLUSIVE"
    INEFFECTIVE = "INEFFECTIVE"
    RECURRENCE = "RECURRENCE"


class Asset(CanonicalModel):
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
    design_life: str | None = None
    monitoring_method: str | None = None
    active: bool = True
    source_type: SourceType = SourceType.OBSERVED_ANCHOR
    source_reference: str


class SignalDefinition(CanonicalModel):
    signal_id: str
    asset_id: str
    canonical_name: str
    source_name: str
    description: str
    unit: str
    measurement_type: str
    direction_of_concern: DirectionOfConcern
    typical_value: float | None = None
    alarm_limit: float | None = None
    trip_limit: float | None = None
    source_key: str
    source_sheet: str
    source_cadence: str
    quality_status: str


class SignalObservation(CanonicalModel):
    observation_id: str
    asset_id: str
    signal_id: str
    timestamp: AwareDatetime
    value: float | None
    operating_mode: OperatingMode
    health_state: HealthState
    source_type: SourceType
    source_reference: str
    source_cadence: str
    scenario_id: str | None = None
    quality_flag: QualityFlag
    timezone_assumption: str | None = None
    ingestion_version: str
    ingested_at: AwareDatetime


class ProductionObservation(CanonicalModel):
    observation_id: str
    asset_id: str
    timestamp: AwareDatetime
    metric_name: str
    value: float
    unit: str
    operating_mode: OperatingMode
    source_type: SourceType
    source_reference: str
    quality_flag: QualityFlag
    timezone_assumption: str | None = None
    ingestion_version: str
    ingested_at: AwareDatetime


class OperatingPeriod(CanonicalModel):
    operating_period_id: str
    asset_id: str
    started_at: AwareDatetime
    ended_at: AwareDatetime
    operating_mode: OperatingMode
    source_status: str
    source_type: SourceType
    source_reference: str
    timezone_assumption: str | None = None

    @field_validator("ended_at")
    @classmethod
    def ended_at_must_be_after_start(cls, value: datetime, info: Any) -> datetime:
        start = info.data.get("started_at")
        if start is not None and value <= start:
            raise ValueError("ended_at must be after started_at")
        return value


class Incident(CanonicalModel):
    incident_id: str
    source_serial: int
    mto_number: str | None = None
    ar_number: str | None = None
    asset_tag: str
    asset_id: str | None = None
    is_anchor_asset: bool = False
    plant_id: str
    occurred_at: AwareDatetime
    title: str
    highest_impact: str
    equipment_class: str
    pre_risk: str
    risk_score: float
    owner: str
    workflow_status: WorkflowStatus
    discipline_raw: str
    equipment_type_raw: str
    component_raw: str
    mechanism_raw: str
    downtime_hours: float = Field(ge=0)
    actual_loss_kusd: float = Field(ge=0)
    potential_loss_kusd: float = Field(ge=0)
    total_loss_kusd: float = Field(ge=0)
    rca_due_date: str | None = None
    source_type: SourceType = SourceType.OBSERVED_ANCHOR
    source_reference: str


class IncidentLabel(CanonicalModel):
    incident_id: str
    equipment_family: str
    discipline: str
    component: str
    observed_symptoms: list[str]
    failure_family: str
    failure_mechanism: str
    probable_cause_family: str | None = None
    source_reported_root_cause: str | None = None
    business_consequences: list[str]
    confidence: float = Field(ge=0, le=1)
    normalization_method: str
    normalization_reason: str
    review_status: str


class RCACase(CanonicalModel):
    rca_case_id: str
    incident_id: str
    asset_id: str
    problem_statement: str
    source_reported_root_cause: str
    workflow_status: WorkflowStatus
    owner: str
    occurred_at: AwareDatetime
    reported_at: AwareDatetime
    source_type: SourceType
    source_reference: str
    app_confirmation_status: str


class Evidence(CanonicalModel):
    evidence_id: str
    rca_case_id: str
    incident_id: str
    asset_id: str
    evidence_type: EvidenceType
    title: str
    observed_at: AwareDatetime | None = None
    content_summary: str
    verification_status: VerificationStatus
    evidence_grade: str
    source_type: SourceType
    source_reference: str
    quality_flag: QualityFlag


class Hypothesis(CanonicalModel):
    hypothesis_id: str
    rca_case_id: str
    incident_id: str
    asset_id: str
    statement: str
    rank: int = Field(ge=1)
    confidence: float = Field(ge=0, le=1)
    status: HypothesisStatus
    supporting_evidence_ids: list[str]
    contradicting_evidence_ids: list[str]
    missing_evidence: list[str]
    generated_by: str
    source_type: SourceType


class Action(CanonicalModel):
    action_id: str
    rca_case_id: str
    incident_id: str
    asset_id: str
    action_type: ActionType
    description: str
    owner: str
    due_date: str | None = None
    priority: str
    status: ActionStatus
    required_evidence: str
    completion_evidence_id: str | None = None
    approved_by: str | None = None
    completed_at: AwareDatetime | None = None
    source_type: SourceType
    source_reference: str


class EffectivenessCheck(CanonicalModel):
    effectiveness_check_id: str
    rca_case_id: str
    incident_id: str
    asset_id: str
    monitoring_start: AwareDatetime
    monitoring_end: AwareDatetime
    baseline_window: str
    comparison_metrics: dict[str, Any]
    recurrence_detected: bool
    result: EffectivenessResult
    explanation: str
    approved_by: str | None = None
    approved_at: AwareDatetime | None = None
    source_type: SourceType
    source_reference: str


class QualityIssue(CanonicalModel):
    issue_id: str
    severity: str
    entity_type: str
    entity_id: str
    quality_flag: QualityFlag
    description: str
    source_references: list[str]
    resolution_status: str
    blocks_scoring: bool

