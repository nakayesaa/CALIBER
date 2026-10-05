"""HTTP routes for equipment investigation and controlled follow-up workflows."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status

from services.api.app.schemas.actions import ActionPlan
from services.api.app.schemas.alerts import AlertEvent
from services.api.app.schemas.api import (
    ActionPlanCreateRequest,
    ActionStatusUpdate,
    AlertDetail,
    AssetOverview,
    AssetSummary,
    InvestigationEvidenceProgress,
    PlantRateSeries,
    RCAGenerateRequest,
    RCAStatusUpdate,
    SystemStatus,
    TelemetrySeries,
)
from services.api.app.schemas.case_packet import CasePacket, CasePacketCreate
from services.api.app.schemas.coordination import (
    AssignmentInput,
    AssignmentResponse,
    CaseReview,
    CrossCheckInput,
    Participant,
    ReviewInput,
    WorkflowSession,
)
from services.api.app.schemas.driver_analysis import DriverAnalysis
from services.api.app.schemas.effectiveness import EffectivenessReview
from services.api.app.schemas.equipment import EquipmentInvestigation
from services.api.app.schemas.equipment_review import (
    EquipmentEvidence,
    EquipmentMonitoringAsset,
    EquipmentReport,
    EquipmentReportCreate,
    EquipmentReportResponse,
)
from services.api.app.schemas.gm_review import GmDecisionInput, GmReport, GmSubmission
from services.api.app.schemas.production_review import (
    ProductionReport,
    ProductionReportCreate,
    ProductionReportResponse,
    ProductionReportSend,
)
from services.api.app.schemas.rca import RCARecord
from services.api.app.schemas.retrieval import IncidentRetrievalResult
from services.api.app.schemas.traceability import (
    DataSourceDetail,
    DataSourceSummary,
    TraceClaim,
)
from services.api.app.security import Principal, WriteMode
from services.api.app.services.artifacts import ArtifactNotFoundError
from services.api.app.services.backend import (
    BackendService,
    LLMConfigurationError,
    LLMGenerationError,
)
from services.api.app.services.coordination import PARTICIPANTS, participant
from services.api.app.services.traceability import TraceabilityNotFoundError

router = APIRouter(prefix="/api/v1")


def get_backend(request: Request) -> BackendService:
    return request.app.state.backend


Backend = Annotated[BackendService, Depends(get_backend)]


def get_mutation_principal(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> Principal:
    return request.app.state.write_authorizer.authorize(authorization)


MutationPrincipal = Annotated[Principal, Depends(get_mutation_principal)]


def selected_participant(request: Request, selected: str | None) -> Participant:
    # ponytail: local demo switching only; bearer identity remains server-configured.
    configured = os.getenv("CALIBER_WORKFLOW_PERSON_ID", "demo-operator")
    local = request.app.state.write_authorizer.mode == WriteMode.LOCAL
    if not local and selected is not None and selected != configured:
        raise HTTPException(status_code=403, detail="Workflow identity is fixed by the server")
    try:
        return participant(selected if local and selected else configured)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error


def get_workflow_participant(
    request: Request,
    _principal: MutationPrincipal,
    x_caliber_person: Annotated[str | None, Header(max_length=160)] = None,
) -> Participant:
    return selected_participant(request, x_caliber_person)


WorkflowParticipant = Annotated[Participant, Depends(get_workflow_participant)]


def get_report_reader(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    x_caliber_person: Annotated[str | None, Header(max_length=160)] = None,
) -> Participant:
    if request.app.state.write_authorizer.mode == WriteMode.BEARER:
        request.app.state.write_authorizer.authorize(authorization)
    return selected_participant(request, x_caliber_person)


ReportReader = Annotated[Participant, Depends(get_report_reader)]


@router.get('/workflow/case-packets', response_model=list[CasePacket], tags=['workflow'])
def case_packets(backend: Backend, person: ReportReader) -> list[CasePacket]:
    try:
        return backend.case_packets(person)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error


@router.post('/workflow/case-packets', response_model=CasePacket, status_code=201, tags=['workflow'])
def create_case_packet(payload: CasePacketCreate, backend: Backend, person: WorkflowParticipant) -> CasePacket:
    try:
        return backend.create_case_packet(payload, person)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except FileNotFoundError as error:
        raise not_found(error) from error
    except ValueError as error:
        raise conflict(error) from error


@router.get('/workflow/case-packets/{case_id}', response_model=CasePacket, tags=['workflow'])
def case_packet(case_id: str, backend: Backend, person: ReportReader) -> CasePacket:
    try:
        return backend.case_packet(case_id, person)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except FileNotFoundError as error:
        raise not_found(error) from error


@router.post('/workflow/case-packets/{case_id}/readiness', response_model=CasePacket, tags=['workflow'])
def case_packet_readiness(case_id: str, backend: Backend, person: WorkflowParticipant) -> CasePacket:
    try:
        return backend.case_packet(case_id, person, require_ready=True)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except FileNotFoundError as error:
        raise not_found(error) from error
    except ValueError as error:
        raise conflict(error) from error


@router.post('/workflow/case-packets/{case_id}/submit-to-gm', response_model=GmReport, status_code=201, tags=['workflow'])
def submit_to_gm(case_id: str, payload: GmSubmission, backend: Backend, person: WorkflowParticipant) -> GmReport:
    try:
        return backend.submit_to_gm(case_id, payload, person)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except FileNotFoundError as error:
        raise not_found(error) from error
    except ValueError as error:
        raise conflict(error) from error


@router.get('/workflow/gm-reports', response_model=list[GmReport], tags=['workflow'])
def gm_reports(backend: Backend, person: ReportReader) -> list[GmReport]:
    return backend.gm_reports(person)


@router.get('/workflow/assigned-actions', response_model=list[ActionPlan], tags=['workflow'])
def assigned_actions(backend: Backend, person: ReportReader) -> list[ActionPlan]:
    try:
        return backend.assigned_actions(person)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error


@router.get('/workflow/gm-reports/{report_id}/actions', response_model=list[ActionPlan], tags=['workflow'])
def gm_actions(report_id: str, backend: Backend, person: ReportReader) -> list[ActionPlan]:
    try:
        return backend.gm_actions(report_id, person)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except FileNotFoundError as error:
        raise not_found(error) from error


@router.post('/workflow/gm-reports/{report_id}/actions/{source_action_id}/assignment', response_model=ActionPlan, tags=['workflow'])
def assign_gm_action(report_id: str, source_action_id: str, payload: AssignmentInput, backend: Backend, person: WorkflowParticipant) -> ActionPlan:
    try:
        return backend.assign_gm_action(report_id, source_action_id, payload, person)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except FileNotFoundError as error:
        raise not_found(error) from error
    except ValueError as error:
        raise conflict(error) from error


@router.get('/workflow/gm-reports/{report_id}', response_model=GmReport, tags=['workflow'])
def gm_report(report_id: str, backend: Backend, person: ReportReader) -> GmReport:
    try:
        return backend.gm_report(report_id, person)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except FileNotFoundError as error:
        raise not_found(error) from error


@router.post('/workflow/gm-reports/{report_id}/decision', response_model=GmReport, tags=['workflow'])
def decide_gm_report(report_id: str, payload: GmDecisionInput, backend: Backend, person: WorkflowParticipant) -> GmReport:
    try:
        return backend.decide_gm_report(report_id, payload, person)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except FileNotFoundError as error:
        raise not_found(error) from error
    except ValueError as error:
        raise conflict(error) from error


@router.get("/workflow/production-reports", response_model=list[ProductionReport], tags=["workflow"])
def production_reports(backend: Backend, person: ReportReader) -> list[ProductionReport]:
    return backend.verification_reports("PRODUCTION", person)


@router.post("/workflow/production-reports", response_model=ProductionReport, status_code=201, tags=["workflow"])
def create_production_report(payload: ProductionReportCreate, backend: Backend, person: WorkflowParticipant) -> ProductionReport:
    try:
        return backend.create_verification_report(payload, person)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except FileNotFoundError as error:
        raise not_found(error) from error
    except ValueError as error:
        raise conflict(error) from error


@router.get("/workflow/production-reports/{report_id}", response_model=ProductionReport, tags=["workflow"])
def production_report(report_id: str, backend: Backend, person: ReportReader) -> ProductionReport:
    try:
        return backend.verification_report(report_id, "PRODUCTION", person)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except FileNotFoundError as error:
        raise not_found(error) from error


@router.post("/workflow/production-reports/{report_id}/send", response_model=ProductionReport, tags=["workflow"])
def send_production_report(report_id: str, payload: ProductionReportSend, backend: Backend, person: WorkflowParticipant) -> ProductionReport:
    try:
        return backend.send_verification_report(report_id, "PRODUCTION", payload.expected_revision, person)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except FileNotFoundError as error:
        raise not_found(error) from error
    except ValueError as error:
        raise conflict(error) from error


@router.post("/workflow/production-reports/{report_id}/response", response_model=ProductionReport, tags=["workflow"])
def respond_production_report(report_id: str, payload: ProductionReportResponse, backend: Backend, person: WorkflowParticipant) -> ProductionReport:
    try:
        return backend.respond_verification_report(report_id, "PRODUCTION", payload, person)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except FileNotFoundError as error:
        raise not_found(error) from error
    except ValueError as error:
        raise conflict(error) from error


@router.get("/workflow/equipment-monitoring", response_model=list[EquipmentMonitoringAsset], tags=["workflow"])
def equipment_monitoring(backend: Backend, person: ReportReader) -> list[EquipmentMonitoringAsset]:
    try:
        return backend.equipment_monitoring(person)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error


@router.get("/workflow/equipment-monitoring/{asset_id}", response_model=EquipmentEvidence, tags=["workflow"])
def operator_equipment_evidence(asset_id: str, backend: Backend, person: ReportReader) -> EquipmentEvidence:
    try:
        return backend.operator_equipment_evidence(asset_id, person)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except FileNotFoundError as error:
        raise not_found(error) from error
    except ValueError as error:
        raise conflict(error) from error


@router.get("/workflow/equipment-reports", response_model=list[EquipmentReport], tags=["workflow"])
def equipment_reports(backend: Backend, person: ReportReader) -> list[EquipmentReport]:
    return backend.verification_reports("EQUIPMENT", person)


@router.post("/workflow/equipment-reports", response_model=EquipmentReport, status_code=201, tags=["workflow"])
def create_equipment_report(payload: EquipmentReportCreate, backend: Backend, person: WorkflowParticipant) -> EquipmentReport:
    try:
        return backend.create_verification_report(payload, person)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except FileNotFoundError as error:
        raise not_found(error) from error
    except ValueError as error:
        raise conflict(error) from error


@router.get("/workflow/equipment-reports/{report_id}", response_model=EquipmentReport, tags=["workflow"])
def equipment_report(report_id: str, backend: Backend, person: ReportReader) -> EquipmentReport:
    try:
        return backend.verification_report(report_id, "EQUIPMENT", person)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except FileNotFoundError as error:
        raise not_found(error) from error


@router.post("/workflow/equipment-reports/{report_id}/send", response_model=EquipmentReport, tags=["workflow"])
def send_equipment_report(report_id: str, payload: ProductionReportSend, backend: Backend, person: WorkflowParticipant) -> EquipmentReport:
    try:
        return backend.send_verification_report(report_id, "EQUIPMENT", payload.expected_revision, person)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except FileNotFoundError as error:
        raise not_found(error) from error
    except ValueError as error:
        raise conflict(error) from error


@router.post("/workflow/equipment-reports/{report_id}/response", response_model=EquipmentReport, tags=["workflow"])
def respond_equipment_report(report_id: str, payload: EquipmentReportResponse, backend: Backend, person: WorkflowParticipant) -> EquipmentReport:
    try:
        return backend.respond_verification_report(report_id, "EQUIPMENT", payload, person)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except FileNotFoundError as error:
        raise not_found(error) from error
    except ValueError as error:
        raise conflict(error) from error


@router.get("/workflow/session", response_model=WorkflowSession, tags=["workflow"])
def workflow_session(
    request: Request, x_caliber_person: Annotated[str | None, Header(max_length=160)] = None
) -> WorkflowSession:
    return WorkflowSession(
        current=selected_participant(request, x_caliber_person),
        participants=PARTICIPANTS,
        can_switch=request.app.state.write_authorizer.mode == WriteMode.LOCAL,
    )


@router.get("/alerts/{alert_id}/cross-check", response_model=CaseReview, tags=["workflow"])
def get_cross_check(alert_id: str, backend: Backend) -> CaseReview:
    try:
        return backend.case_review(alert_id)
    except FileNotFoundError as error:
        raise not_found(error) from error


@router.post("/alerts/{alert_id}/cross-check", response_model=CaseReview, tags=["workflow"])
def submit_cross_check(
    alert_id: str, payload: CrossCheckInput, backend: Backend, person: WorkflowParticipant
) -> CaseReview:
    try:
        return backend.submit_cross_check(alert_id, payload, person)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except FileNotFoundError as error:
        raise not_found(error) from error
    except ValueError as error:
        raise conflict(error) from error


@router.post("/alerts/{alert_id}/cross-check/review", response_model=CaseReview, tags=["workflow"])
def review_cross_check(
    alert_id: str, payload: ReviewInput, backend: Backend, person: WorkflowParticipant
) -> CaseReview:
    try:
        return backend.review_cross_check(alert_id, payload, person)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except FileNotFoundError as error:
        raise not_found(error) from error
    except ValueError as error:
        raise conflict(error) from error


def not_found(error: FileNotFoundError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))


def conflict(error: ValueError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))


@router.get("/status", response_model=SystemStatus, tags=["system"])
def project_status(backend: Backend) -> SystemStatus:
    return backend.status()


@router.get(
    "/data-sources",
    response_model=list[DataSourceSummary],
    tags=["traceability"],
)
def list_data_sources(backend: Backend) -> list[DataSourceSummary]:
    return backend.list_data_sources()


@router.get(
    "/data-sources/{source_key}",
    response_model=DataSourceDetail,
    tags=["traceability"],
)
def data_source_detail(source_key: str, backend: Backend) -> DataSourceDetail:
    try:
        return backend.data_source_detail(source_key)
    except TraceabilityNotFoundError as error:
        raise not_found(FileNotFoundError(error.args[0])) from error


@router.get(
    "/traceability/claims/{trace_id}",
    response_model=TraceClaim,
    tags=["traceability"],
)
def traceability_claim(
    trace_id: str, backend: Backend, asset_id: str = "asset-ko-3201"
) -> TraceClaim:
    try:
        return backend.traceability_claim(trace_id, asset_id)
    except TraceabilityNotFoundError as error:
        raise not_found(FileNotFoundError(error.args[0])) from error
    except ArtifactNotFoundError as error:
        raise not_found(error) from error


@router.get("/assets", response_model=list[AssetSummary], tags=["assets"])
def list_assets(backend: Backend) -> list[AssetSummary]:
    try:
        return backend.list_assets()
    except ArtifactNotFoundError as error:
        raise not_found(error) from error


@router.get(
    "/assets/{asset_id}/overview",
    response_model=AssetOverview,
    tags=["assets"],
)
def asset_overview(asset_id: str, backend: Backend) -> AssetOverview:
    try:
        return backend.asset_overview(asset_id)
    except ArtifactNotFoundError as error:
        raise not_found(error) from error


@router.get(
    "/assets/{asset_id}/investigation", response_model=EquipmentInvestigation, tags=["assets"]
)
def equipment_investigation(asset_id: str, backend: Backend) -> EquipmentInvestigation:
    try:
        return backend.equipment_investigation(asset_id)
    except ArtifactNotFoundError as error:
        raise not_found(error) from error
    except (ValueError, OSError) as error:
        raise HTTPException(status_code=422, detail="HE analytics unavailable; rebuild with make he-train and make he-alerts") from error


@router.get(
    "/assets/{asset_id}/effectiveness",
    response_model=EffectivenessReview,
    tags=["actions"],
)
def asset_effectiveness(asset_id: str, backend: Backend) -> EffectivenessReview:
    try:
        review = backend.effectiveness_review(asset_id)
    except ArtifactNotFoundError as error:
        raise not_found(error) from error
    if review is None:
        raise HTTPException(
            status_code=404,
            detail=f"Effectiveness review not found for asset: {asset_id}",
        )
    return review


@router.get(
    "/assets/{asset_id}/telemetry",
    response_model=TelemetrySeries,
    tags=["assets"],
)
def asset_telemetry(
    asset_id: str,
    backend: Backend,
    start: str | None = None,
    end: str | None = None,
    max_points: Annotated[int, Query(ge=10, le=5000)] = 720,
) -> TelemetrySeries:
    try:
        return backend.telemetry(asset_id, start, end, max_points)
    except ArtifactNotFoundError as error:
        raise not_found(error) from error
    except (ValueError, TypeError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get(
    "/assets/{asset_id}/production-rate",
    response_model=PlantRateSeries,
    tags=["assets"],
)
def asset_production_rate(asset_id: str, backend: Backend) -> PlantRateSeries:
    try:
        return backend.plant_rate_daily(asset_id)
    except ArtifactNotFoundError as error:
        raise not_found(error) from error
    except (ValueError, TypeError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/alerts", response_model=list[AlertEvent], tags=["alerts"])
def list_alerts(backend: Backend, asset_id: str | None = None) -> list[AlertEvent]:
    try:
        return backend.list_alerts(asset_id)
    except ArtifactNotFoundError as error:
        raise not_found(error) from error


@router.get(
    "/alerts/{alert_id}",
    response_model=AlertDetail,
    tags=["alerts"],
)
def alert_detail(alert_id: str, backend: Backend) -> AlertDetail:
    try:
        return backend.alert_detail(alert_id)
    except ArtifactNotFoundError as error:
        raise not_found(error) from error


@router.get(
    "/alerts/{alert_id}/investigation-evidence",
    response_model=InvestigationEvidenceProgress,
    tags=["rca"],
)
def investigation_evidence(
    alert_id: str, backend: Backend, as_of: datetime | None = None
) -> InvestigationEvidenceProgress:
    try:
        return backend.investigation_evidence(alert_id, as_of)
    except ArtifactNotFoundError as error:
        raise not_found(error) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get(
    "/alerts/{alert_id}/driver-analysis",
    response_model=DriverAnalysis,
    tags=["alerts"],
)
def alert_driver_analysis(
    alert_id: str,
    backend: Backend,
    timestamp: datetime | None = None,
) -> DriverAnalysis:
    try:
        return backend.driver_analysis(alert_id, timestamp)
    except (ArtifactNotFoundError, FileNotFoundError) as error:
        raise not_found(FileNotFoundError(str(error))) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get(
    "/alerts/{alert_id}/similar-incidents",
    response_model=list[IncidentRetrievalResult],
    tags=["rca"],
)
def similar_incidents(
    alert_id: str,
    backend: Backend,
) -> list[IncidentRetrievalResult]:
    try:
        return backend.similar_incidents(alert_id)
    except ArtifactNotFoundError as error:
        raise not_found(error) from error


@router.get(
    "/alerts/{alert_id}/rca",
    response_model=RCARecord,
    tags=["rca"],
)
def get_rca(alert_id: str, backend: Backend) -> RCARecord:
    try:
        record = backend.get_rca(alert_id)
    except ArtifactNotFoundError as error:
        raise not_found(error) from error
    if record is None:
        raise HTTPException(status_code=404, detail=f"RCA not found for alert: {alert_id}")
    return record


@router.post(
    "/alerts/{alert_id}/rca",
    response_model=RCARecord,
    tags=["rca"],
)
def generate_rca(
    alert_id: str,
    payload: RCAGenerateRequest,
    request: Request,
    backend: Backend,
    principal: MutationPrincipal,
) -> RCARecord:
    try:
        if payload.mode == "ai":
            request.app.state.rca_rate_limiter.enforce(principal.subject)
        return backend.generate_rca(alert_id, principal.display_name, payload.mode)
    except ArtifactNotFoundError as error:
        raise not_found(error) from error
    except LLMConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except LLMGenerationError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@router.patch("/rca/{rca_id}/status", response_model=RCARecord, tags=["rca"])
def update_rca_status(
    rca_id: str,
    payload: RCAStatusUpdate,
    backend: Backend,
    person: WorkflowParticipant,
) -> RCARecord:
    try:
        return backend.transition_rca(
            rca_id,
            payload.status,
            person,
            payload.note,
            payload.occurred_at,
        )
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except FileNotFoundError as error:
        raise not_found(error) from error
    except ValueError as error:
        raise conflict(error) from error


@router.post(
    "/rca/{rca_id}/action-plans",
    response_model=ActionPlan,
    tags=["actions"],
)
def create_action_plan(
    rca_id: str,
    payload: ActionPlanCreateRequest,
    backend: Backend,
    person: WorkflowParticipant,
) -> ActionPlan:
    try:
        return backend.create_action_plan(rca_id, payload.hypothesis_id, person)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except FileNotFoundError as error:
        raise not_found(error) from error
    except ValueError as error:
        raise conflict(error) from error


@router.get(
    "/action-plans/{plan_id}",
    response_model=ActionPlan,
    tags=["actions"],
)
def get_action_plan(plan_id: str, backend: Backend) -> ActionPlan:
    try:
        return backend.get_action_plan(plan_id)
    except ArtifactNotFoundError as error:
        raise not_found(error) from error


@router.patch(
    "/actions/{action_id}/status",
    response_model=ActionPlan,
    tags=["actions"],
)
def update_action_status(
    action_id: str,
    payload: ActionStatusUpdate,
    backend: Backend,
    person: WorkflowParticipant,
) -> ActionPlan:
    try:
        return backend.transition_action(
            action_id,
            payload.status,
            person,
            payload.note,
            payload.occurred_at,
            payload.evidence,
            payload.expected_revision,
        )
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except FileNotFoundError as error:
        raise not_found(error) from error
    except ValueError as error:
        raise conflict(error) from error


@router.post("/actions/{action_id}/assignment", response_model=ActionPlan, tags=["workflow"])
def assign_action(
    action_id: str, payload: AssignmentInput, backend: Backend, person: WorkflowParticipant
) -> ActionPlan:
    try:
        return backend.delegate_action(action_id, payload, person)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except FileNotFoundError as error:
        raise not_found(error) from error
    except ValueError as error:
        raise conflict(error) from error


@router.post(
    "/actions/{action_id}/assignment/response", response_model=ActionPlan, tags=["workflow"]
)
def respond_to_action(
    action_id: str, payload: AssignmentResponse, backend: Backend, person: WorkflowParticipant
) -> ActionPlan:
    try:
        return backend.respond_to_action(action_id, payload, person)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except FileNotFoundError as error:
        raise not_found(error) from error
    except ValueError as error:
        raise conflict(error) from error
