"""Human review records and bounded requests for an equipment investigation."""

from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

Text = Annotated[str, Field(min_length=1, max_length=2000)]
Identifier = Annotated[str, Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")]


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
