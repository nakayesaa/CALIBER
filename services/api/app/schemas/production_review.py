"""Production-only snapshots and bounded verification commands."""

from typing import Literal

from pydantic import AwareDatetime

from services.api.app.schemas.api import ProductionImpact
from services.api.app.schemas.coordination import CoordinationModel, Identifier
from services.api.app.schemas.scope_verification import (
    VerificationCreate,
    VerificationReport,
)
from services.api.app.schemas.scope_verification import (
    VerificationResponse as ProductionReportResponse,
)
from services.api.app.schemas.scope_verification import (
    VerificationSend as ProductionReportSend,
)

__all__ = ["ProductionEvidencePoint", "ProductionReport", "ProductionReportCreate", "ProductionReportResponse", "ProductionReportSend"]


class ProductionEvidencePoint(CoordinationModel):
    timestamp: AwareDatetime
    feed_rate_tph: float | None
    plant_rate_tph: float | None
    run_status: str
    operating_mode: str


class ProductionReportCreate(VerificationCreate):
    alert_id: Identifier | None = None


class ProductionReport(VerificationReport):
    scope: Literal["PRODUCTION"] = "PRODUCTION"
    impact: ProductionImpact
    points: list[ProductionEvidencePoint]
    alert_id: Identifier | None = None
