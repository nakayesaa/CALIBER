"""Deterministic CA/PA planning and workflow transitions."""

from __future__ import annotations

import hashlib
from datetime import date, timedelta
from pathlib import Path

import yaml

from services.api.app.schemas.actions import (
    ActionItem,
    ActionPlan,
    ActionPolicyConfig,
    ActionStatus,
)
from services.api.app.schemas.rca import RCARecord, RCAStatus


def load_action_policy(path: Path) -> ActionPolicyConfig:
    return ActionPolicyConfig.model_validate(
        yaml.safe_load(path.read_text(encoding="utf-8"))
    )


def build_action_plan(
    rca: RCARecord,
    selected_hypothesis_id: str,
    policy: ActionPolicyConfig,
    planning_date: date,
) -> ActionPlan:
    hypotheses = {
        hypothesis.hypothesis_id: hypothesis
        for hypothesis in rca.generation.hypotheses
    }
    if selected_hypothesis_id not in hypotheses:
        raise ValueError(f"Unknown RCA hypothesis: {selected_hypothesis_id}")
    hypothesis = hypotheses[selected_hypothesis_id]
    cause_policies = {
        cause_policy.cause_category: cause_policy
        for cause_policy in policy.cause_policies
    }
    cause_policy = cause_policies[hypothesis.category]
    plan_id = _stable_id("plan", rca.rca_id, selected_hypothesis_id, policy.policy_id)
    actions = [
        ActionItem(
            action_id=_stable_id("action", plan_id, template.template_id),
            template_id=template.template_id,
            rca_id=rca.rca_id,
            hypothesis_id=selected_hypothesis_id,
            action_type=template.action_type,
            title=template.title,
            guidance=template.guidance,
            owner_role=template.default_owner_role,
            priority=template.priority,
            due_date=(planning_date + timedelta(days=template.due_in_days)).isoformat(),
            status=ActionStatus.PROPOSED,
            completion_criteria=template.completion_criteria,
            effectiveness_check=template.effectiveness_check,
        )
        for template in cause_policy.actions
    ]
    return ActionPlan(
        plan_id=plan_id,
        rca_id=rca.rca_id,
        alert_id=rca.alert_id,
        selected_hypothesis_id=selected_hypothesis_id,
        selected_cause_category=hypothesis.category,
        policy_id=policy.policy_id,
        status=ActionStatus.PROPOSED,
        actions=actions,
    )


def transition_action(
    action: ActionItem,
    new_status: ActionStatus,
    policy: ActionPolicyConfig,
    rca_status: RCAStatus,
) -> ActionItem:
    allowed = policy.workflow.transitions.get(action.status, [])
    if new_status not in allowed:
        raise ValueError(f"Invalid action transition: {action.status} -> {new_status}")
    if new_status == ActionStatus.APPROVED and rca_status != RCAStatus.APPROVED:
        raise ValueError("Actions cannot be approved before the RCA is approved")
    return action.model_copy(update={"status": new_status})


def update_plan_status(plan: ActionPlan) -> ActionPlan:
    statuses = {action.status for action in plan.actions}
    if len(statuses) == 1:
        status = next(iter(statuses))
    elif ActionStatus.IN_PROGRESS in statuses:
        status = ActionStatus.IN_PROGRESS
    elif ActionStatus.EFFECTIVENESS_REVIEW in statuses:
        status = ActionStatus.EFFECTIVENESS_REVIEW
    elif ActionStatus.APPROVED in statuses:
        status = ActionStatus.APPROVED
    else:
        status = ActionStatus.PROPOSED
    return plan.model_copy(update={"status": status})


def _stable_id(prefix: str, *parts: str) -> str:
    value = "|".join(parts).encode("utf-8")
    return f"{prefix}-{hashlib.sha256(value).hexdigest()[:12]}"
