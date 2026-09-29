"""Role checks and human cross-check transitions, independent of HTTP and storage."""

from datetime import datetime

from services.api.app.schemas.coordination import (
    CaseReview,
    CrossCheckInput,
    Participant,
    ReviewHistory,
    ReviewInput,
)

# These are demo identities, not a company employee directory.
PARTICIPANTS = [
    Participant(person_id="demo-operator", display_name="Demo OP-01 · Operator", role="OPERATOR"),
    Participant(person_id="demo-supervisor", display_name="Demo SV-01 · Supervisor", role="SUPERVISOR", owner_roles=["Shift Supervisor"]),
    Participant(person_id="demo-maintenance", display_name="Demo MT-01 · Maintenance", role="ENGINEER", owner_roles=["Rotating Equipment Engineer"]),
    Participant(person_id="demo-reliability", display_name="Demo RE-01 · Reliability", role="ENGINEER", owner_roles=["Reliability Engineer", "Condition Monitoring Engineer"]),
    Participant(person_id="demo-instrument", display_name="Demo IN-01 · Instrument", role="ENGINEER", owner_roles=["Instrument Engineer"]),
    Participant(person_id="demo-planner", display_name="Demo PL-01 · Planner", role="ENGINEER", owner_roles=["Maintenance Planner"]),
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


def submit_case(case: CaseReview, data: CrossCheckInput, person: Participant, now: datetime) -> CaseReview:
    require_role(person, "OPERATOR")
    if data.expected_revision != case.revision:
        raise ValueError("Case revision changed; reload before submitting")
    if case.status not in {"DRAFT", "CHANGES_REQUESTED"}:
        raise ValueError("Cross-check can only be submitted from draft or returned review")
    return case.model_copy(update={
        "status": "PENDING_REVIEW", "revision": case.revision + 1,
        "note": data.note, "references": data.references, "human_context": data.human_context,
        "submitted_by": person.person_id, "reviewed_by": None,
        "history": [*case.history, ReviewHistory(status="PENDING_REVIEW", actor_id=person.person_id, occurred_at=now, note=data.note)],
    })


def review_case(case: CaseReview, data: ReviewInput, person: Participant, now: datetime) -> CaseReview:
    require_role(person, "SUPERVISOR")
    if data.expected_revision != case.revision:
        raise ValueError("Case revision changed; reload before reviewing")
    if case.status != "PENDING_REVIEW" or person.person_id == case.submitted_by:
        raise ValueError("Review needs a pending cross-check and a different reviewer")
    return case.model_copy(update={
        "status": data.decision, "revision": case.revision + 1, "reviewed_by": person.person_id,
        "history": [*case.history, ReviewHistory(status=data.decision, actor_id=person.person_id, occurred_at=now, note=data.note)],
    })
