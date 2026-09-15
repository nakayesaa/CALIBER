"""HTTP routes for the KO-3201 backend vertical slice."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from services.api.app.schemas.actions import ActionPlan
from services.api.app.schemas.alerts import AlertEvent
from services.api.app.schemas.api import (
    ActionPlanCreateRequest,
    ActionStatusUpdate,
    AlertDetail,
    AssetOverview,
    AssetSummary,
    RCAGenerateRequest,
    RCAStatusUpdate,
    SystemStatus,
    TelemetrySeries,
)
from services.api.app.schemas.driver_analysis import DriverAnalysis
from services.api.app.schemas.effectiveness import EffectivenessReview
from services.api.app.schemas.rca import RCARecord
from services.api.app.schemas.retrieval import IncidentRetrievalResult
from services.api.app.schemas.traceability import (
    DataSourceDetail,
    DataSourceSummary,
    TraceClaim,
)
from services.api.app.services.artifacts import ArtifactNotFoundError
from services.api.app.services.backend import (
    BackendService,
    LLMConfigurationError,
    LLMGenerationError,
)
from services.api.app.services.traceability import TraceabilityNotFoundError

router = APIRouter(prefix="/api/v1")


def get_backend(request: Request) -> BackendService:
    return request.app.state.backend


Backend = Annotated[BackendService, Depends(get_backend)]


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
def traceability_claim(trace_id: str, backend: Backend) -> TraceClaim:
    try:
        return backend.traceability_claim(trace_id)
    except TraceabilityNotFoundError as error:
        raise not_found(FileNotFoundError(error.args[0])) from error


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
    request: RCAGenerateRequest,
    backend: Backend,
) -> RCARecord:
    try:
        return backend.generate_rca(alert_id, request.requested_by, request.mode)
    except ArtifactNotFoundError as error:
        raise not_found(error) from error
    except LLMConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except LLMGenerationError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@router.patch("/rca/{rca_id}/status", response_model=RCARecord, tags=["rca"])
def update_rca_status(
    rca_id: str,
    request: RCAStatusUpdate,
    backend: Backend,
) -> RCARecord:
    try:
        return backend.transition_rca(
            rca_id,
            request.status,
            request.actor,
            request.note,
            request.occurred_at,
        )
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
    request: ActionPlanCreateRequest,
    backend: Backend,
) -> ActionPlan:
    try:
        return backend.create_action_plan(rca_id, request.hypothesis_id)
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
    request: ActionStatusUpdate,
    backend: Backend,
) -> ActionPlan:
    try:
        return backend.transition_action(
            action_id,
            request.status,
            request.actor,
            request.note,
            request.occurred_at,
        )
    except FileNotFoundError as error:
        raise not_found(error) from error
    except ValueError as error:
        raise conflict(error) from error
