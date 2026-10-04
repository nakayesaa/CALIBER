"""Shared immutable equipment and production report handoff."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from services.api.app.schemas.case_packet import (
    CasePacket,
    CasePacketCreate,
    CasePacketRecord,
    CaseScopeStatus,
)
from services.api.app.schemas.coordination import Participant
from services.api.app.schemas.equipment_review import (
    EquipmentReport,
    EquipmentReportCreate,
    EquipmentReportResponse,
    EquipmentReviewRecord,
)
from services.api.app.schemas.production_review import (
    ProductionEvidencePoint,
    ProductionReport,
    ProductionReportCreate,
    ProductionReportResponse,
)
from services.api.app.schemas.scope_verification import VerificationReport, VerificationReviewRecord
from services.api.app.services.coordination import participant, require_role
from services.api.app.services.file_io import atomic_write_json

if TYPE_CHECKING:
    from services.api.app.services.backend import BackendService


def report_path(root: Path, report_id: str) -> Path:
    match = re.fullmatch(r"(production|equipment)-[a-f0-9]{32}", report_id)
    if not match:
        raise FileNotFoundError("Verification report not found")
    return root / "data/actions" / f"{match[1]}-reports" / f"{report_id}.json"


def load_report(root: Path, report_id: str) -> ProductionReport | EquipmentReport:
    path = report_path(root, report_id)
    model = EquipmentReport if report_id.startswith("equipment-") else ProductionReport
    return model.model_validate_json(path.read_text(encoding="utf-8"))


def can_read(report: VerificationReport, person: Participant) -> bool:
    return (
        person.role == "SUPERVISOR" and person.person_id == report.created_by
    ) or (
        person.role == "OPERATOR" and person.person_id == report.recipient_id
        and report.status != "DRAFT" and report.asset.plant_id in person.plant_ids
        and report.scope in person.scopes
        and (report.scope != "EQUIPMENT" or report.asset.asset_id in person.asset_ids)
    )


def create_report(backend: BackendService, data: ProductionReportCreate | EquipmentReportCreate, person: Participant, now: datetime) -> ProductionReport | EquipmentReport:
    require_role(person, "SUPERVISOR")
    equipment = isinstance(data, EquipmentReportCreate)
    scope = "EQUIPMENT" if equipment else "PRODUCTION"
    report_id = f"{scope.lower()}-{data.request_id.hex}"
    path = report_path(backend.root, report_id)
    if path.is_file():
        existing = load_report(backend.root, report_id)
        if existing.created_by != person.person_id:
            raise PermissionError("This report belongs to another supervisor")
        if (existing.asset.asset_id, existing.recipient_id, existing.due_at, existing.note) != (
            data.asset_id, data.recipient_id, data.due_at, data.note,
        ):
            raise ValueError("Request identifier already belongs to a different report")
        if equipment and (not isinstance(existing, EquipmentReport) or existing.evidence.alert.alert_id != data.alert_id):
            raise ValueError("Request identifier already belongs to a different alert")
        if not equipment and data.alert_id is not None and existing.alert_id != data.alert_id:
            raise ValueError('Request identifier already belongs to a different production alert')
        return existing
    if data.due_at <= now:
        raise ValueError("Response deadline must be in the future")
    overview = backend.asset_overview(data.asset_id)
    recipient = participant(data.recipient_id)
    if recipient.role != "OPERATOR" or scope not in recipient.scopes or overview.asset.plant_id not in recipient.plant_ids or (equipment and data.asset_id not in recipient.asset_ids):
        raise ValueError("Select an operator assigned to this plant, asset and scope")
    envelope = dict(
        report_id=report_id, asset=overview.asset, created_by=person.person_id,
        supervisor=person.display_name, recipient_id=recipient.person_id,
        recipient_name=recipient.display_name, created_at=now, due_at=data.due_at, note=data.note,
    )
    if equipment:
        report = EquipmentReport(**envelope, evidence=backend.equipment_review_evidence(data.asset_id, data.alert_id))
        atomic_write_json(path, report)
        return report
    alert = backend.alert_detail(data.alert_id).alert if data.alert_id else max(
        backend.list_alerts(data.asset_id), key=lambda item: item.highest_severity_rank, default=None,
    )
    if alert is not None and alert.asset_id != data.asset_id:
        raise ValueError('Production alert does not belong to the selected equipment')
    impact = backend._production_impact(data.asset_id, alert)
    if impact is None:
        raise ValueError("No calculated production window is available for this asset")
    series = backend.telemetry(
        data.asset_id, (impact.window_start - timedelta(hours=48)).isoformat(),
        (impact.window_end + timedelta(hours=48)).isoformat(), 1000,
    )
    if not series.points or series.returned_points != series.total_points:
        raise ValueError("Complete supporting production records are required")
    fields = set(ProductionEvidencePoint.model_fields)
    report = ProductionReport(
        **envelope, impact=impact, alert_id=alert.alert_id,
        points=[ProductionEvidencePoint.model_validate(point.model_dump(include=fields)) for point in series.points],
    )
    atomic_write_json(path, report)
    return report


def send(report: VerificationReport, revision: int, person: Participant, now: datetime) -> VerificationReport:
    require_role(person, "SUPERVISOR")
    if report.created_by != person.person_id:
        raise PermissionError("This report belongs to another supervisor")
    if report.status != "DRAFT" or report.revision != revision:
        raise ValueError("Report changed or was already sent; reload before sending")
    if report.due_at <= now:
        raise ValueError("The response deadline has passed; prepare a new report")
    return report.model_copy(update={"status": "SENT", "sent_at": now, "revision": revision + 1})


def respond(report: ProductionReport | EquipmentReport, data: ProductionReportResponse | EquipmentReportResponse, person: Participant, now: datetime) -> ProductionReport | EquipmentReport:
    if person.role != "OPERATOR" or person.person_id != report.recipient_id or not can_read(report, person):
        raise PermissionError("Only the designated scope operator may verify this report")
    if report.status != "SENT" or data.expected_revision != report.revision:
        raise ValueError("Report changed or was already reviewed; reload before responding")
    if data.decision == "APPROVED" and not data.attested:
        raise ValueError("Confirm that you checked this report version before approving")
    record = dict(decision=data.decision, note=data.note, actor_id=person.person_id, at=now)
    if isinstance(report, EquipmentReport):
        if not isinstance(data, EquipmentReportResponse):
            raise ValueError("Equipment reports require the equipment verification checklist")
        review = EquipmentReviewRecord(**record, checks=data.checks, human_context=data.human_context)
    else:
        if isinstance(data, EquipmentReportResponse):
            raise ValueError("Production reports require a production scope response")
        review = VerificationReviewRecord(**record)
    return report.model_copy(update={
        "status": data.decision, "revision": report.revision + 1,
        "review": review,
    })


def packet_path(root: Path, case_id: str) -> Path:
    if not re.fullmatch(r'case-[a-f0-9]{32}', case_id):
        raise FileNotFoundError('Case packet not found')
    return root / 'data/actions/case-packets' / f'{case_id}.json'


def packet_record(root: Path, case_id: str, person: Participant) -> CasePacketRecord:
    require_role(person, 'SUPERVISOR')
    record = CasePacketRecord.model_validate_json(packet_path(root, case_id).read_text())
    if record.created_by != person.person_id:
        raise PermissionError('This case packet belongs to another supervisor')
    return record


def packet_view(root: Path, record: CasePacketRecord) -> CasePacket:
    scopes = []
    for scope, report_id, version in (
        ('EQUIPMENT', record.equipment_report_id, record.equipment_version),
        ('PRODUCTION', record.production_report_id, record.production_version),
    ):
        try:
            report = load_report(root, report_id)
            alert_id = report.evidence.alert.alert_id if isinstance(report, EquipmentReport) else report.alert_id
            if (report.scope, report.version, report.asset.asset_id, report.created_by, alert_id) != (scope, version, record.asset.asset_id, record.created_by, record.alert_id):
                raise ValueError('Bound report identity or version changed')
            verified = report.status == 'APPROVED' and report.review is not None and report.review.decision == 'APPROVED' and report.review.actor_id == report.recipient_id
            scopes.append(CaseScopeStatus(scope=scope, report_id=report_id, version=version, recipient_name=report.recipient_name, status=report.status, verified=verified, note=report.review.note if report.review else None))
        except (FileNotFoundError, ValueError):
            scopes.append(CaseScopeStatus(scope=scope, report_id=report_id, version=version, recipient_name='Unavailable', status='UNAVAILABLE', verified=False, note='Bound report is missing or no longer matches this case.'))
    count = sum(item.verified for item in scopes)
    statuses = {item.status for item in scopes}
    if count == 2:
        state = 'READY_FOR_GM'
    elif 'UNAVAILABLE' in statuses:
        state = 'UNAVAILABLE'
    elif 'CHANGES_REQUESTED' in statuses:
        state = 'NEEDS_CORRECTION'
    elif 'UNABLE_TO_VALIDATE' in statuses:
        state = 'EVIDENCE_REQUIRED'
    else:
        state = 'AWAITING_VERIFICATION'
    waiting = ', '.join(item.scope.title() for item in scopes if not item.verified)
    summary = 'Ready for GM review' if count == 2 else f'{count} of 2 scopes verified — waiting for {waiting}.'
    return CasePacket(**record.model_dump(), scopes=scopes, verified_scopes=count, can_escalate=count == 2, state=state, summary=summary)


def create_packet(backend: BackendService, data: CasePacketCreate, person: Participant, now: datetime) -> CasePacket:
    require_role(person, 'SUPERVISOR')
    case_id = f'case-{data.request_id.hex}'
    path = packet_path(backend.root, case_id)
    if path.is_file():
        record = packet_record(backend.root, case_id, person)
        if (record.equipment_report_id, record.production_report_id) != (data.equipment_report_id, data.production_report_id):
            raise ValueError('Request identifier already belongs to a different case packet')
        return packet_view(backend.root, record)
    equipment = backend.verification_report(data.equipment_report_id, 'EQUIPMENT', person)
    production = backend.verification_report(data.production_report_id, 'PRODUCTION', person)
    if equipment.asset.asset_id != production.asset.asset_id or equipment.evidence.alert.alert_id != production.alert_id:
        raise ValueError('Select equipment and production reports for the same asset and alert. Prepare a new production report if its alert reference is missing.')
    for existing in (backend.root / 'data/actions/case-packets').glob('case-*.json'):
        record = CasePacketRecord.model_validate_json(existing.read_text())
        if record.equipment_report_id == equipment.report_id or record.production_report_id == production.report_id:
            raise ValueError('A selected report is already bound to a case packet; open that packet or prepare new reports')
    record = CasePacketRecord(
        case_id=case_id, created_by=person.person_id, created_at=now, asset=equipment.asset,
        alert_id=equipment.evidence.alert.alert_id,
        window_start=min(equipment.evidence.window_start, production.impact.window_start),
        window_end=max(equipment.evidence.window_end, production.impact.window_end),
        equipment_report_id=equipment.report_id, production_report_id=production.report_id,
        equipment_version=equipment.version, production_version=production.version,
    )
    atomic_write_json(path, record)
    return packet_view(backend.root, record)
