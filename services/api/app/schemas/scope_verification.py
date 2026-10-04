"""Shared report envelope and version-bound scope decisions."""

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field

from services.api.app.schemas.api import AssetSummary
from services.api.app.schemas.coordination import CoordinationModel, Identifier, Text


class VerificationCreate(CoordinationModel):
    request_id: UUID
    asset_id: Identifier
    recipient_id: Identifier
    due_at: AwareDatetime
    note: Text


class VerificationSend(CoordinationModel):
    expected_revision: int = Field(ge=0)


class VerificationResponse(VerificationSend):
    decision: Literal["APPROVED", "CHANGES_REQUESTED", "UNABLE_TO_VALIDATE"]
    note: Text
    attested: bool = False


class VerificationReviewRecord(CoordinationModel):
    decision: Literal["APPROVED", "CHANGES_REQUESTED", "UNABLE_TO_VALIDATE"]
    note: Text
    actor_id: Identifier
    at: AwareDatetime


class VerificationReport(CoordinationModel):
    report_id: Identifier
    version: str = "01"
    revision: int = 0
    status: Literal["DRAFT", "SENT", "APPROVED", "CHANGES_REQUESTED", "UNABLE_TO_VALIDATE"] = "DRAFT"
    scope: Literal["PRODUCTION", "EQUIPMENT"]
    asset: AssetSummary
    created_by: Identifier
    supervisor: str
    recipient_id: Identifier
    recipient_name: str
    created_at: AwareDatetime
    due_at: AwareDatetime
    sent_at: AwareDatetime | None = None
    note: Text
    review: VerificationReviewRecord | None = None
