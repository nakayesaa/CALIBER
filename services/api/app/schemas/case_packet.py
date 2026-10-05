"""A version-bound equipment and production verification packet."""

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime

from services.api.app.schemas.api import AssetSummary
from services.api.app.schemas.coordination import CoordinationModel, Identifier


class CasePacketCreate(CoordinationModel):
    request_id: UUID
    equipment_report_id: Identifier
    production_report_id: Identifier


class CasePacketRecord(CoordinationModel):
    case_id: Identifier
    version: str = '01'
    created_by: Identifier
    created_at: AwareDatetime
    asset: AssetSummary
    alert_id: Identifier
    window_start: AwareDatetime
    window_end: AwareDatetime
    equipment_report_id: Identifier
    production_report_id: Identifier
    equipment_version: str
    production_version: str


class CaseScopeStatus(CoordinationModel):
    scope: Literal['EQUIPMENT', 'PRODUCTION']
    report_id: Identifier
    version: str
    recipient_name: str
    status: str
    verified: bool
    note: str | None = None


class CasePacket(CasePacketRecord):
    scopes: list[CaseScopeStatus]
    verified_scopes: int
    required_scopes: int = 2
    can_escalate: bool
    state: Literal['AWAITING_VERIFICATION', 'NEEDS_CORRECTION', 'EVIDENCE_REQUIRED', 'UNAVAILABLE', 'READY_FOR_GM']
    summary: str
