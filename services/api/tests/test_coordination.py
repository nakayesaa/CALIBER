"""Cross-check and review must preserve accountability before delegation."""

from datetime import UTC, datetime

import pytest

from services.api.app.schemas.coordination import CaseReview, CrossCheckInput, ReviewInput
from services.api.app.services.coordination import participant, review_case, submit_case

NOW = datetime(2026, 9, 29, tzinfo=UTC)


def test_cross_check_requires_operator_then_independent_supervisor() -> None:
    case = CaseReview(alert_id="alert-001")
    data = CrossCheckInput(note="Checked oil indication against source records", references=["signal:water_in_oil"], expected_revision=0)
    with pytest.raises(PermissionError):
        submit_case(case, data, participant("demo-maintenance"), NOW)
    submitted = submit_case(case, data, participant("demo-operator"), NOW)
    assert submitted.status == "PENDING_REVIEW"
    assert submitted.submitted_by == "demo-operator"
    with pytest.raises(PermissionError):
        review_case(submitted, ReviewInput(decision="VERIFIED", note="Reviewed source", expected_revision=1), participant("demo-operator"), NOW)
    verified = review_case(submitted, ReviewInput(decision="VERIFIED", note="Reviewed source", expected_revision=1), participant("demo-supervisor"), NOW)
    assert verified.status == "VERIFIED"
    assert verified.reviewed_by == "demo-supervisor"
    assert len(verified.history) == 2
    with pytest.raises(ValueError, match="revision"):
        review_case(submitted, ReviewInput(decision="VERIFIED", note="Stale decision", expected_revision=0), participant("demo-supervisor"), NOW)
    with pytest.raises(ValueError):
        submit_case(verified, data, participant("demo-operator"), NOW)


def test_changes_requested_returns_to_operator_without_losing_history() -> None:
    submitted = submit_case(CaseReview(alert_id="alert-001"), CrossCheckInput(note="Initial check", references=["source:production"], expected_revision=0), participant("demo-operator"), NOW)
    returned = review_case(submitted, ReviewInput(decision="CHANGES_REQUESTED", note="Need the sample ID", expected_revision=1), participant("demo-supervisor"), NOW)
    updated = submit_case(returned, CrossCheckInput(note="Sample ID attached", references=["lab:sample-001"], expected_revision=2), participant("demo-operator"), NOW)
    assert updated.reviewed_by is None
    assert updated.revision == 3
    assert len(updated.history) == 3
