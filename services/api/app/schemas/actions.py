"""Contracts for corrective and preventive action planning."""

from __future__ import annotations

from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from services.api.app.schemas.rca import CauseCategory


class ActionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ActionType(StrEnum):
    CONTAINMENT = "CONTAINMENT"
    CORRECTIVE = "CORRECTIVE"
    PREVENTIVE = "PREVENTIVE"


class ActionPriority(StrEnum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"


class ActionStatus(StrEnum):
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    IN_PROGRESS = "IN_PROGRESS"
    EFFECTIVENESS_REVIEW = "EFFECTIVENESS_REVIEW"
    CLOSED = "CLOSED"
    REJECTED = "REJECTED"


class ActionTemplate(ActionModel):
    template_id: str
    action_type: ActionType
    title: str
    guidance: str
    default_owner_role: str
    priority: ActionPriority
    due_in_days: int = Field(ge=0)
    completion_criteria: str
    effectiveness_check: str
    affected_scope: str | None = None
    execution_route: str | None = None
    change_control: str | None = None


class CauseActionPolicy(ActionModel):
    cause_category: CauseCategory
    actions: list[ActionTemplate] = Field(min_length=1)

    @model_validator(mode="after")
    def require_action_coverage(self) -> CauseActionPolicy:
        types = {action.action_type for action in self.actions}
        required = {ActionType.CONTAINMENT, ActionType.CORRECTIVE, ActionType.PREVENTIVE}
        if types != required:
            raise ValueError("Each cause policy requires containment, corrective, and preventive actions")
        return self


class ActionWorkflowPolicy(ActionModel):
    transitions: dict[ActionStatus, list[ActionStatus]]

    @model_validator(mode="after")
    def validate_state_coverage(self) -> ActionWorkflowPolicy:
        if set(self.transitions) != set(ActionStatus):
            raise ValueError("Workflow must define transitions for every action status")
        return self


class ActionPolicyConfig(ActionModel):
    policy_id: str
    policy_version: str
    cause_policies: list[CauseActionPolicy]
    workflow: ActionWorkflowPolicy

    @model_validator(mode="after")
    def validate_categories(self) -> ActionPolicyConfig:
        categories = [policy.cause_category for policy in self.cause_policies]
        if len(categories) != len(set(categories)):
            raise ValueError("Cause action policies must be unique")
        if set(categories) != set(CauseCategory):
            raise ValueError("Action policy must cover every RCA cause category")
        return self


class ActionStatusTransition(ActionModel):
    previous_status: ActionStatus
    new_status: ActionStatus
    actor: str
    occurred_at: AwareDatetime
    note: str


class ActionItem(ActionModel):
    action_id: str
    template_id: str
    rca_id: str
    hypothesis_id: str
    action_type: ActionType
    title: str
    guidance: str
    owner_role: str
    priority: ActionPriority
    due_date: str
    status: ActionStatus
    completion_criteria: str
    effectiveness_check: str
    affected_scope: str | None = None
    execution_route: str | None = None
    change_control: str | None = None
    status_history: list[ActionStatusTransition] = Field(default_factory=list)


class ActionPlan(ActionModel):
    plan_id: str
    rca_id: str
    alert_id: str
    selected_hypothesis_id: str
    selected_cause_category: CauseCategory
    policy_id: str
    status: ActionStatus
    actions: list[ActionItem] = Field(min_length=1)
