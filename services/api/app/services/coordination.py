"""Role checks and human cross-check transitions, independent of HTTP and storage."""

from datetime import datetime

from services.api.app.schemas.actions import ActionItem, ActionStatus
from services.api.app.schemas.coordination import (
    ActionAssignment,
    AssignmentInput,
    AssignmentResponse,
    CaseReview,
    CrossCheckInput,
    ExecutionEvidence,
    ExecutionEvidenceInput,
    Participant,
    ReviewHistory,
    ReviewInput,
)

# These are demo identities, not a company employee directory.
PARTICIPANTS = [
    Participant(person_id="demo-operator", display_name="Demo OP-01 · Operator", role="OPERATOR"),
    Participant(
        person_id="demo-supervisor",
        display_name="Demo SV-01 · Supervisor",
        role="SUPERVISOR",
        owner_roles=["Shift Supervisor"],
    ),
    Participant(
        person_id="demo-reviewer",
        display_name="Demo SV-02 · Supervisor",
        role="SUPERVISOR",
        owner_roles=["Shift Supervisor"],
    ),
    Participant(
        person_id="demo-maintenance",
        display_name="Demo MT-01 · Maintenance",
        role="ENGINEER",
        owner_roles=["Rotating Equipment Engineer"],
    ),
    Participant(
        person_id="demo-reliability",
        display_name="Demo RE-01 · Reliability",
        role="ENGINEER",
        owner_roles=["Reliability Engineer", "Condition Monitoring Engineer"],
    ),
    Participant(
        person_id="demo-instrument",
        display_name="Demo IN-01 · Instrument",
        role="ENGINEER",
        owner_roles=["Instrument Engineer"],
    ),
    Participant(
        person_id="demo-planner",
        display_name="Demo PL-01 · Planner",
        role="ENGINEER",
        owner_roles=["Maintenance Planner"],
    ),
    Participant(person_id="demo-manager", display_name="Demo MG-01 · Manager", role="MANAGER"),
]


def participant(person_id: str) -> Participant:
    for person in PARTICIPANTS:
        if person.person_id == person_id:
            return person
    raise PermissionError("Unknown workflow identity")


def require_role(person: Participant, *roles: str) -> None:
    if person.role not in roles:
        raise PermissionError("This operation is outside the current role's authority")


def require_verified(case: CaseReview) -> None:
    if case.status != "VERIFIED":
        raise ValueError("A supervisor-verified cross-check is required")


def assign_action(
    action: ActionItem, data: AssignmentInput, person: Participant, case: CaseReview, now: datetime
) -> ActionItem:
    require_role(person, "SUPERVISOR")
    require_verified(case)
    current_owner = action.assignment.person_id if action.assignment else None
    revision = action.assignment.revision if action.assignment else 0
    if (
        action.status != data.expected_status
        or current_owner != data.expected_assigned_to
        or revision != data.expected_revision
    ):
        raise ValueError("Assignment changed; reload before delegating")
    if action.status != ActionStatus.APPROVED and not (
        action.status == ActionStatus.IN_PROGRESS and action.assignment is None
    ):
        raise ValueError("Assign approved work; started assignments cannot be replaced")
    assignee = participant(data.person_id)
    if action.owner_role not in assignee.owner_roles:
        raise ValueError("The assignee does not match the required owner role")
    history = action.assignment.history if action.assignment else []
    assigned = ActionAssignment(
        revision=revision + 1,
        person_id=assignee.person_id,
        assigned_by=person.person_id,
        assigned_at=now,
        history=[
            *history,
            ReviewHistory(
                status="ASSIGNED",
                actor_id=person.person_id,
                occurred_at=now,
                note=data.note,
                recipient_id=assignee.person_id,
                due_date=data.due_date,
            ),
        ],
    )
    return action.model_copy(update={"assignment": assigned, "due_date": data.due_date.isoformat()})


def respond_to_assignment(
    action: ActionItem, data: AssignmentResponse, person: Participant, now: datetime
) -> ActionItem:
    if action.assignment is None or action.assignment.person_id != person.person_id:
        raise PermissionError("Only the assigned person can respond to this task")
    if action.status not in {ActionStatus.APPROVED, ActionStatus.IN_PROGRESS}:
        raise ValueError("This task is not awaiting acceptance or active work")
    if data.expected_revision != action.assignment.revision:
        raise ValueError("Assignment changed; reload before responding")
    assigned = action.assignment.model_copy(
        update={
            "revision": action.assignment.revision + 1,
            "accepted_at": now if data.decision == "ACCEPT" else action.assignment.accepted_at,
            "blocked_reason": data.note if data.decision == "BLOCK" else None,
            "history": [
                *action.assignment.history,
                ReviewHistory(
                    status=data.decision, actor_id=person.person_id, occurred_at=now, note=data.note
                ),
            ],
        }
    )
    return action.model_copy(update={"assignment": assigned})


def require_assignee(action: ActionItem, person: Participant) -> None:
    if action.assignment is None or action.assignment.person_id != person.person_id:
        raise PermissionError("Only the assigned person can execute this task")
    if action.assignment.accepted_at is None or action.assignment.blocked_reason:
        raise ValueError("Accept the assignment and resolve blockers before execution")


def record_execution_evidence(
    action: ActionItem,
    status: ActionStatus,
    data: ExecutionEvidenceInput | None,
    person: Participant,
    now: datetime,
) -> ActionItem:
    rework = (
        status == ActionStatus.IN_PROGRESS and action.status == ActionStatus.EFFECTIVENESS_REVIEW
    )
    if status == ActionStatus.CLOSED or rework:
        require_role(person, "SUPERVISOR")
        if action.assignment is None or person.person_id == action.assignment.person_id:
            raise PermissionError(
                "Verification requires a reviewer different from the assigned person"
            )
        if action.completion is None:
            raise ValueError("Recorded completion evidence is required before verification")
    elif status in {ActionStatus.IN_PROGRESS, ActionStatus.EFFECTIVENESS_REVIEW}:
        require_assignee(action, person)
    checks = data.requirements if data and data.requirements else action.requirements
    if status in {ActionStatus.IN_PROGRESS, ActionStatus.EFFECTIVENESS_REVIEW, ActionStatus.CLOSED}:
        if len(checks) != 3 or {item.requirement for item in checks} != {
            "PROCEDURE",
            "AUTHORIZATION",
            "CHANGE_CONTROL",
        }:
            raise ValueError("Document all three execution requirements before proceeding")
    changed = action.model_copy(update={"requirements": checks})
    if status == ActionStatus.EFFECTIVENESS_REVIEW or status == ActionStatus.CLOSED or rework:
        if data is None or not data.reference or not data.finding:
            raise ValueError("Supply completion or verification evidence reference and finding")
        outcome = (
            "REWORK_REQUIRED"
            if rework
            else "EFFECTIVE"
            if status == ActionStatus.CLOSED
            else "COMPLETED"
        )
        evidence = ExecutionEvidence(
            reference=data.reference,
            finding=data.finding,
            actor_id=person.person_id,
            occurred_at=now,
            outcome=outcome,
        )
        changed = changed.model_copy(
            update={
                "completion" if outcome == "COMPLETED" else "verification": evidence,
                "evidence_history": [*action.evidence_history, evidence],
            }
        )
    return changed


def submit_case(
    case: CaseReview, data: CrossCheckInput, person: Participant, now: datetime
) -> CaseReview:
    require_role(person, "OPERATOR")
    if data.expected_revision != case.revision:
        raise ValueError("Case revision changed; reload before submitting")
    if case.status not in {"DRAFT", "CHANGES_REQUESTED"}:
        raise ValueError("Cross-check can only be submitted from draft or returned review")
    return case.model_copy(
        update={
            "status": "PENDING_REVIEW",
            "revision": case.revision + 1,
            "note": data.note,
            "references": data.references,
            "human_context": data.human_context,
            "submitted_by": person.person_id,
            "reviewed_by": None,
            "history": [
                *case.history,
                ReviewHistory(
                    status="PENDING_REVIEW",
                    actor_id=person.person_id,
                    occurred_at=now,
                    note=data.note,
                ),
            ],
        }
    )


def review_case(
    case: CaseReview, data: ReviewInput, person: Participant, now: datetime
) -> CaseReview:
    require_role(person, "SUPERVISOR")
    if data.expected_revision != case.revision:
        raise ValueError("Case revision changed; reload before reviewing")
    if case.status != "PENDING_REVIEW" or person.person_id == case.submitted_by:
        raise ValueError("Review needs a pending cross-check and a different reviewer")
    return case.model_copy(
        update={
            "status": data.decision,
            "revision": case.revision + 1,
            "reviewed_by": person.person_id,
            "history": [
                *case.history,
                ReviewHistory(
                    status=data.decision, actor_id=person.person_id, occurred_at=now, note=data.note
                ),
            ],
        }
    )
