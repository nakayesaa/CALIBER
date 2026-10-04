"""A frozen, scope-verified case and its management decision."""

from typing import Literal

from pydantic import AwareDatetime, Field

from services.api.app.schemas.actions import ActionPlan
from services.api.app.schemas.api import AssetSummary
from services.api.app.schemas.coordination import CoordinationModel, Identifier, Text
from services.api.app.schemas.equipment_review import EquipmentReport
from services.api.app.schemas.production_review import ProductionReport
from services.api.app.schemas.rca import RCARecord


class GmSubmission(CoordinationModel):
    recipient_id: Identifier
    note: Text


class GmDecisionInput(CoordinationModel):
    expected_revision: int = Field(ge=0)
    decision: Literal['APPROVED', 'RETURNED']
    note: Text


class GmDecision(CoordinationModel):
    decision: Literal['APPROVED', 'RETURNED']
    note: Text
    actor_id: Identifier
    at: AwareDatetime


class GmReport(CoordinationModel):
    report_id: Identifier
    case_id: Identifier
    version: str = '01'
    revision: int = 0
    status: Literal['PENDING_REVIEW', 'APPROVED', 'RETURNED'] = 'PENDING_REVIEW'
    created_by: Identifier
    recipient_id: Identifier
    recipient_name: str
    submitted_at: AwareDatetime
    note: Text
    asset: AssetSummary
    alert_id: Identifier
    equipment_report: EquipmentReport
    production_report: ProductionReport
    rca: RCARecord | None = None
    action_plans: list[ActionPlan]
    decision: GmDecision | None = None
