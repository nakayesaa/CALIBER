"""Persist management handoffs without changing RCA or action execution state."""

from __future__ import annotations

import re
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING

from services.api.app.schemas.actions import ActionPlan, ActionStatus, ActionStatusTransition
from services.api.app.schemas.coordination import AssignmentInput, Participant
from services.api.app.schemas.gm_review import GmDecision, GmDecisionInput, GmReport, GmSubmission
from services.api.app.services.actions.workflow import update_plan_status
from services.api.app.services.coordination import (
    assign_authorized_action,
    participant,
    require_role,
)
from services.api.app.services.file_io import atomic_write_json
from services.api.app.services.scope_verification import load_report, packet_record, packet_view

if TYPE_CHECKING:
    from services.api.app.services.backend import BackendService


def report_path(root: Path, report_id: str) -> Path:
    if not re.fullmatch(r'gm-[a-f0-9]{32}', report_id):
        raise FileNotFoundError('GM report not found')
    return root / 'data/actions/gm-reports' / f'{report_id}.json'


def can_read(report: GmReport, person: Participant) -> bool:
    return (person.role == 'SUPERVISOR' and report.created_by == person.person_id) or (person.role == 'MANAGER' and report.recipient_id == person.person_id)


def read_report(root: Path, report_id: str, person: Participant) -> GmReport:
    report = GmReport.model_validate_json(report_path(root, report_id).read_text())
    if not can_read(report, person):
        raise PermissionError('This GM report is outside your assigned scope')
    return report


def submit(backend: BackendService, case_id: str, data: GmSubmission, person: Participant, now: datetime) -> GmReport:
    record = packet_record(backend.root, case_id, person)
    report_id = f'gm-{case_id.removeprefix("case-")}'
    path = report_path(backend.root, report_id)
    if path.is_file():
        report = read_report(backend.root, report_id, person)
        if (report.recipient_id, report.note) != (data.recipient_id, data.note):
            raise ValueError('This case was already submitted; open its existing GM report')
        return report
    packet = packet_view(backend.root, record)
    if not packet.can_escalate:
        raise ValueError(packet.summary)
    recipient = participant(data.recipient_id)
    if recipient.role != 'MANAGER':
        raise ValueError('Select a General Manager to review this case')
    detail = backend.alert_detail(record.alert_id)
    prepared = detail.prepared_workflow
    report = GmReport(
        report_id=report_id, case_id=case_id, created_by=person.person_id,
        recipient_id=recipient.person_id, recipient_name=recipient.display_name,
        submitted_at=now, note=data.note, asset=record.asset, alert_id=record.alert_id,
        equipment_report=load_report(backend.root, record.equipment_report_id),
        production_report=load_report(backend.root, record.production_report_id),
        rca=detail.rca or (prepared.rca if prepared else None),
        action_plans=detail.action_plans or (prepared.action_plans if prepared else []),
    )
    atomic_write_json(path, report)
    return report


def decide(report: GmReport, data: GmDecisionInput, person: Participant, now: datetime) -> GmReport:
    require_role(person, 'MANAGER')
    if person.person_id != report.recipient_id:
        raise PermissionError('Only the designated GM may decide this report')
    if report.status != 'PENDING_REVIEW' or report.revision != data.expected_revision:
        raise ValueError('Report changed or was already decided; reload before responding')
    decision = GmDecision(decision=data.decision, note=data.note, actor_id=person.person_id, at=now)
    return report.model_copy(update={'status': data.decision, 'revision': report.revision + 1, 'decision': decision})


def require_authorized(report: GmReport) -> None:
    if report.status != 'APPROVED' or report.decision is None or report.decision.decision != 'APPROVED' or report.decision.actor_id != report.recipient_id:
        raise ValueError('GM approval is required before assigning or executing this work')


def execution_plan(report: GmReport, source: ActionPlan) -> ActionPlan:
    def identifier(prefix, value):
        return f'{prefix}-{sha256(f"{report.report_id}|{value}".encode()).hexdigest()[:24]}'
    return source.model_copy(update={
        'plan_id': identifier('gm-plan', source.plan_id), 'gm_report_id': report.report_id,
        'status': ActionStatus.PROPOSED,
        'actions': [action.model_copy(update={
            'action_id': identifier('gm-action', action.action_id), 'source_action_id': action.action_id,
            'status': ActionStatus.PROPOSED, 'revision': 0, 'assignment': None,
            'requirements': [], 'completion': None, 'verification': None,
            'evidence_history': [], 'status_history': [],
        }) for action in source.actions if action.action_type != 'CONTAINMENT'],
    })


def validate_execution(root: Path, plan: ActionPlan, person: Participant) -> GmReport:
    report = GmReport.model_validate_json(report_path(root, plan.gm_report_id).read_text())
    require_authorized(report)
    if person.role == 'SUPERVISOR' and person.person_id != report.created_by:
        raise PermissionError('Only the case supervisor may manage this work')
    source = next((item for item in report.action_plans if execution_plan(report, item).plan_id == plan.plan_id), None)
    if source is None:
        raise ValueError('Execution plan is not part of the approved GM report')
    expected = execution_plan(report, source)
    immutable = ('template_id', 'rca_id', 'hypothesis_id', 'action_type', 'title', 'guidance', 'owner_role', 'priority', 'completion_criteria', 'effectiveness_check', 'affected_scope', 'execution_route', 'change_control', 'source_action_id')
    if (plan.rca_id, plan.alert_id, plan.selected_hypothesis_id, plan.selected_cause_category, plan.policy_id) != (expected.rca_id, expected.alert_id, expected.selected_hypothesis_id, expected.selected_cause_category, expected.policy_id) or len(plan.actions) != len(expected.actions):
        raise ValueError('Execution plan differs from authorized work')
    for action, original in zip(plan.actions, expected.actions, strict=True):
        if action.action_id != original.action_id or any(getattr(action, key) != getattr(original, key) for key in immutable):
            raise ValueError('Execution action differs from authorized work')
    return report


def assign(backend: BackendService, report_id: str, source_action_id: str, data: AssignmentInput, person: Participant, now: datetime) -> ActionPlan:
    report = read_report(backend.root, report_id, person)
    require_role(person, 'SUPERVISOR')
    require_authorized(report)
    source = next((plan for plan in report.action_plans if any(action.action_id == source_action_id and action.action_type != 'CONTAINMENT' for action in plan.actions)), None)
    if source is None:
        raise FileNotFoundError('Proposed action not found in this GM report')
    fresh = execution_plan(report, source)
    repository = backend._repository_for_alert(report.alert_id)
    plan = next((plan for plan in repository.list_action_plans(report.alert_id) if plan.plan_id == fresh.plan_id), fresh)
    validate_execution(backend.root, plan, person)
    if data.due_date < now.date():
        raise ValueError('Choose a deadline today or later')
    action = next(action for action in plan.actions if action.source_action_id == source_action_id)
    if action.status != data.expected_status or (action.assignment.person_id if action.assignment else None) != data.expected_assigned_to or (action.assignment.revision if action.assignment else 0) != data.expected_revision:
        raise ValueError('Assignment changed; reload before delegating')
    if action.status == ActionStatus.PROPOSED:
        action = action.model_copy(update={'status': ActionStatus.APPROVED, 'status_history': [ActionStatusTransition(previous_status=ActionStatus.PROPOSED, new_status=ActionStatus.APPROVED, actor=person.display_name, occurred_at=now, note=f'GM authorization {report.report_id}: {data.note}')]})
        data = data.model_copy(update={'expected_status': 'APPROVED'})
    changed = assign_authorized_action(action, data, person, now).model_copy(update={'revision': action.revision + 1})
    result = update_plan_status(plan.model_copy(update={'actions': [changed if item.action_id == action.action_id else item for item in plan.actions]}))
    repository.save_action_plan(result)
    return result
