"""Cross-check and review must preserve accountability before delegation."""

from datetime import UTC, datetime

import pytest

from services.api.app.schemas.actions import ActionItem
from services.api.app.schemas.coordination import (
    AssignmentInput,
    AssignmentResponse,
    CaseReview,
    CrossCheckInput,
    ReviewInput,
)
from services.api.app.services.coordination import (
    assign_action,
    participant,
    respond_to_assignment,
    review_case,
    submit_case,
)

NOW = datetime(2026, 9, 29, tzinfo=UTC)


def action_record() -> ActionItem:
    return ActionItem(
        action_id="action-001",
        template_id="template-001",
        rca_id="rca-001",
        hypothesis_id="hypothesis-001",
        action_type="CORRECTIVE",
        title="Review oil path",
        guidance="Inspect documented oil path",
        owner_role="Rotating Equipment Engineer",
        priority="HIGH",
        due_date="2026-10-01",
        status="APPROVED",
        completion_criteria="Attach inspection record",
        effectiveness_check="Confirm stable oil condition",
    )


def test_cross_check_requires_operator_then_independent_supervisor() -> None:
    case = CaseReview(alert_id="alert-001")
    data = CrossCheckInput(
        note="Checked oil indication against source records",
        references=["signal:water_in_oil"],
        expected_revision=0,
    )
    with pytest.raises(PermissionError):
        submit_case(case, data, participant("demo-maintenance"), NOW)
    submitted = submit_case(case, data, participant("demo-operator"), NOW)
    assert submitted.status == "PENDING_REVIEW"
    assert submitted.submitted_by == "demo-operator"
    with pytest.raises(PermissionError):
        review_case(
            submitted,
            ReviewInput(decision="VERIFIED", note="Reviewed source", expected_revision=1),
            participant("demo-operator"),
            NOW,
        )
    verified = review_case(
        submitted,
        ReviewInput(decision="VERIFIED", note="Reviewed source", expected_revision=1),
        participant("demo-supervisor"),
        NOW,
    )
    assert verified.status == "VERIFIED"
    assert verified.reviewed_by == "demo-supervisor"
    assert len(verified.history) == 2
    with pytest.raises(ValueError, match="revision"):
        review_case(
            submitted,
            ReviewInput(decision="VERIFIED", note="Stale decision", expected_revision=0),
            participant("demo-supervisor"),
            NOW,
        )
    with pytest.raises(ValueError):
        submit_case(verified, data, participant("demo-operator"), NOW)


def test_changes_requested_returns_to_operator_without_losing_history() -> None:
    submitted = submit_case(
        CaseReview(alert_id="alert-001"),
        CrossCheckInput(
            note="Initial check", references=["source:production"], expected_revision=0
        ),
        participant("demo-operator"),
        NOW,
    )
    returned = review_case(
        submitted,
        ReviewInput(decision="CHANGES_REQUESTED", note="Need the sample ID", expected_revision=1),
        participant("demo-supervisor"),
        NOW,
    )
    updated = submit_case(
        returned,
        CrossCheckInput(
            note="Sample ID attached", references=["lab:sample-001"], expected_revision=2
        ),
        participant("demo-operator"),
        NOW,
    )
    assert updated.reviewed_by is None
    assert updated.revision == 3
    assert len(updated.history) == 3


def test_assignment_requires_verified_case_and_compatible_named_owner() -> None:
    action = action_record()
    case = CaseReview(alert_id="alert-001", status="VERIFIED")
    data = AssignmentInput(
        person_id="demo-maintenance",
        due_date="2026-10-01",
        expected_status="APPROVED",
        note="Review contamination path",
    )
    with pytest.raises(ValueError, match="verified"):
        assign_action(
            action, data, participant("demo-supervisor"), CaseReview(alert_id="alert-001"), NOW
        )
    with pytest.raises(PermissionError):
        assign_action(action, data, participant("demo-operator"), case, NOW)
    with pytest.raises(ValueError, match="owner role"):
        assign_action(
            action,
            data.model_copy(update={"person_id": "demo-instrument"}),
            participant("demo-supervisor"),
            case,
            NOW,
        )
    assigned = assign_action(action, data, participant("demo-supervisor"), case, NOW)
    assert assigned.assignment.person_id == "demo-maintenance"
    with pytest.raises(PermissionError):
        respond_to_assignment(
            assigned,
            AssignmentResponse(decision="ACCEPT", note="Accepted scope", expected_revision=1),
            participant("demo-reliability"),
            NOW,
        )
    blocked = respond_to_assignment(
        assigned,
        AssignmentResponse(decision="BLOCK", note="Need inspection access", expected_revision=1),
        participant("demo-maintenance"),
        NOW,
    )
    assert blocked.assignment.blocked_reason == "Need inspection access"
    accepted = respond_to_assignment(
        blocked,
        AssignmentResponse(decision="ACCEPT", note="Access confirmed", expected_revision=2),
        participant("demo-maintenance"),
        NOW,
    )
    assert accepted.assignment.accepted_at == NOW
    assert accepted.assignment.blocked_reason is None
    assert len(accepted.assignment.history) == 3
    revised = assign_action(
        assigned,
        data.model_copy(
            update={
                "due_date": NOW.date(),
                "expected_assigned_to": "demo-maintenance",
                "expected_revision": 1,
            }
        ),
        participant("demo-supervisor"),
        case,
        NOW,
    )
    with pytest.raises(ValueError, match="changed"):
        assign_action(
            revised,
            data.model_copy(
                update={"expected_assigned_to": "demo-maintenance", "expected_revision": 1}
            ),
            participant("demo-supervisor"),
            case,
            NOW,
        )
    with pytest.raises(ValueError, match="changed"):
        respond_to_assignment(
            revised,
            AssignmentResponse(decision="ACCEPT", note="Old tab", expected_revision=1),
            participant("demo-maintenance"),
            NOW,
        )
    assert revised.assignment.history[0].recipient_id == "demo-maintenance"
    assert revised.assignment.history[0].due_date.isoformat() == "2026-10-01"


def test_execution_requires_requirements_completion_and_independent_verification() -> None:
    from services.api.app.schemas.coordination import ExecutionEvidenceInput, RequirementCheck
    from services.api.app.services.coordination import record_execution_evidence

    supervisor = participant("demo-supervisor")
    engineer = participant("demo-maintenance")
    assigned = assign_action(
        action_record(),
        AssignmentInput(
            person_id=engineer.person_id,
            due_date="2026-10-01",
            expected_status="APPROVED",
            note="Assigned",
        ),
        supervisor,
        CaseReview(alert_id="alert-001", status="VERIFIED"),
        NOW,
    )
    accepted = respond_to_assignment(
        assigned,
        AssignmentResponse(decision="ACCEPT", note="Accepted", expected_revision=1),
        engineer,
        NOW,
    )
    with pytest.raises(ValueError, match="requirement"):
        record_execution_evidence(accepted, "IN_PROGRESS", None, engineer, NOW)
    checks = [
        RequirementCheck(
            requirement=key,
            disposition="CONFIRMED",
            reference="record:approved-001",
            note="Reviewed documented requirement",
        )
        for key in ("PROCEDURE", "AUTHORIZATION", "CHANGE_CONTROL")
    ]
    started = record_execution_evidence(
        accepted, "IN_PROGRESS", ExecutionEvidenceInput(requirements=checks), engineer, NOW
    ).model_copy(update={"status": "IN_PROGRESS"})
    with pytest.raises(ValueError, match="completion"):
        record_execution_evidence(started, "EFFECTIVENESS_REVIEW", None, engineer, NOW)
    completed = record_execution_evidence(
        started,
        "EFFECTIVENESS_REVIEW",
        ExecutionEvidenceInput(
            reference="work:001", finding="Inspection completed with documented acceptance"
        ),
        engineer,
        NOW,
    ).model_copy(update={"status": "EFFECTIVENESS_REVIEW"})
    with pytest.raises(PermissionError):
        record_execution_evidence(
            completed,
            "CLOSED",
            ExecutionEvidenceInput(reference="review:001", finding="Outcome verified"),
            engineer,
            NOW,
        )
    closed = record_execution_evidence(
        completed,
        "CLOSED",
        ExecutionEvidenceInput(
            reference="review:001", finding="Outcome verified against monitoring criteria"
        ),
        supervisor,
        NOW,
    )
    assert closed.verification.actor_id == supervisor.person_id
    assert closed.completion.actor_id == engineer.person_id
