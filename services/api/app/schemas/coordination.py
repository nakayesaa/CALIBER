"""Human review records and bounded requests for an equipment investigation."""

from datetime import date
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

Text = Annotated[str, Field(min_length=1, max_length=2000)]
Identifier = Annotated[
    str, Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
]


class CoordinationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Participant(CoordinationModel):
    person_id: Identifier
    display_name: str
    role: Literal["OPERATOR", "SUPERVISOR", "ENGINEER", "MANAGER"]
    owner_roles: list[str] = Field(default_factory=list)


class WorkflowSession(CoordinationModel):
    current: Participant
    participants: list[Participant]
    can_switch: bool


class CrossCheckInput(CoordinationModel):
    note: Text
    references: list[Text] = Field(min_length=1, max_length=10)
    human_context: str = Field(default="", max_length=2000)
    expected_revision: int = Field(ge=0)


class ReviewInput(CoordinationModel):
    decision: Literal["VERIFIED", "CHANGES_REQUESTED"]
    note: Text
    expected_revision: int = Field(ge=0)


class ReviewHistory(CoordinationModel):
    status: str
    actor_id: Identifier
    occurred_at: AwareDatetime
    note: Text
    recipient_id: Identifier | None = None
    due_date: date | None = None


class CaseReview(CoordinationModel):
    alert_id: Identifier
    status: Literal["DRAFT", "PENDING_REVIEW", "VERIFIED", "CHANGES_REQUESTED"] = "DRAFT"
    revision: int = 0
    note: str = ""
    references: list[str] = Field(default_factory=list)
    human_context: str = ""
    submitted_by: str | None = None
    reviewed_by: str | None = None
    history: list[ReviewHistory] = Field(default_factory=list)


class AssignmentInput(CoordinationModel):
    person_id: Identifier
    due_date: date
    expected_status: Literal[
        "PROPOSED", "APPROVED", "IN_PROGRESS", "EFFECTIVENESS_REVIEW", "CLOSED", "REJECTED"
    ]
    expected_assigned_to: Identifier | None = None
    expected_revision: int = Field(default=0, ge=0)
    note: Text


class AssignmentResponse(CoordinationModel):
    decision: Literal["ACCEPT", "BLOCK"]
    note: Text
    expected_revision: int = Field(ge=1)


class ActionAssignment(CoordinationModel):
    revision: int = Field(default=1, ge=1)
    person_id: Identifier
    assigned_by: Identifier
    assigned_at: AwareDatetime
    accepted_at: AwareDatetime | None = None
    blocked_reason: str | None = None
    history: list[ReviewHistory] = Field(default_factory=list)


class RequirementCheck(CoordinationModel):
    requirement: Literal["PROCEDURE", "AUTHORIZATION", "CHANGE_CONTROL"]
    disposition: Literal["CONFIRMED", "NOT_APPLICABLE"]
    reference: Text
    note: Text


class ExecutionEvidenceInput(CoordinationModel):
    requirements: list[RequirementCheck] = Field(default_factory=list, max_length=3)
    reference: Text | None = None
    finding: Text | None = None


class ExecutionEvidence(CoordinationModel):
    reference: Text
    finding: Text
    actor_id: Identifier
    occurred_at: AwareDatetime
    outcome: Literal["COMPLETED", "EFFECTIVE", "REWORK_REQUIRED"]
