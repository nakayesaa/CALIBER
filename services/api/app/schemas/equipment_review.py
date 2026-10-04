"""Equipment-only evidence snapshots and structured operator checks."""

from typing import Literal, Self

from pydantic import AwareDatetime, Field, model_validator

from services.api.app.schemas.alerts import AlertStateTransition
from services.api.app.schemas.api import (
    AssetSummary,
    InvestigationEvidenceEvent,
    RCAExplanationCheck,
)
from services.api.app.schemas.coordination import CoordinationModel, Identifier, Text
from services.api.app.schemas.driver_analysis import DriverAnalysis
from services.api.app.schemas.scope_verification import (
    VerificationCreate,
    VerificationReport,
    VerificationResponse,
    VerificationReviewRecord,
)


class EquipmentEvidencePoint(CoordinationModel):
    timestamp: AwareDatetime
    operating_mode: str
    run_status: str
    anomaly_score: float | None
    decision_state: str
    radial_vibration_micron: float | None = None
    water_in_oil_ppm: float | None = None
    lube_oil_pressure_barg: float | None = None
    bearing_metal_temperature_degc: float | None = None
    tube_dp: float | None = None
    heat_duty: float | None = None
    cold_outlet_temp: float | None = None
    heavy_ends: float | None = None


class EquipmentMonitoringAsset(CoordinationModel):
    asset: AssetSummary
    timeline_start: AwareDatetime
    timeline_end: AwareDatetime
    latest_decision_state: str
    highest_alert_severity: str | None
    alert_count: int


class EquipmentAlertContext(CoordinationModel):
    alert_id: Identifier
    asset_id: Identifier
    first_signal_at: AwareDatetime
    opened_at: AwareDatetime
    highest_severity: str
    highest_severity_rank: int


class EquipmentEvidence(CoordinationModel):
    alert: EquipmentAlertContext
    as_of: AwareDatetime
    window_start: AwareDatetime
    window_end: AwareDatetime
    points: list[EquipmentEvidencePoint]
    transitions: list[AlertStateTransition]
    drivers: DriverAnalysis
    events: list[InvestigationEvidenceEvent]
    explanations: list[RCAExplanationCheck]
    validation_note: str | None = None


class EquipmentReportCreate(VerificationCreate):
    alert_id: Identifier


class EquipmentVerificationCheck(CoordinationModel):
    check: Literal["DATA_VALIDITY", "OPERATING_CONTEXT", "ABNORMAL_BEHAVIOUR", "SUPPORTING_EVIDENCE"]
    result: Literal["VERIFIED", "ISSUE", "MISSING"]
    finding: Text
    reference: Text | None = None


class EquipmentReportResponse(VerificationResponse):
    checks: list[EquipmentVerificationCheck] = Field(min_length=4, max_length=4)
    human_context: Text

    @model_validator(mode="after")
    def validate_checks(self) -> Self:
        if len({item.check for item in self.checks}) != 4:
            raise ValueError("Complete each equipment verification check exactly once")
        if any(item.result != "MISSING" and not item.reference for item in self.checks):
            raise ValueError("Verified findings and discrepancies require a source reference")
        results = {item.result for item in self.checks}
        if self.decision == "APPROVED" and results != {"VERIFIED"}:
            raise ValueError("All four checks must be verified before accepting this report")
        if self.decision == "CHANGES_REQUESTED" and "ISSUE" not in results:
            raise ValueError("Identify the discrepancy that needs correction")
        if self.decision == "UNABLE_TO_VALIDATE" and "MISSING" not in results:
            raise ValueError("Identify the missing evidence that prevents verification")
        return self


class EquipmentReviewRecord(VerificationReviewRecord):
    checks: list[EquipmentVerificationCheck]
    human_context: Text


class EquipmentReport(VerificationReport):
    scope: Literal["EQUIPMENT"] = "EQUIPMENT"
    evidence: EquipmentEvidence
    review: EquipmentReviewRecord | None = None
