"""Build a deterministic backend-owned workflow preview for the case demonstration."""

from __future__ import annotations

from datetime import timedelta

from services.api.app.schemas.actions import ActionPlan, ActionPolicyConfig, ActionStatus
from services.api.app.schemas.rca import RCAGenerationConfig, RCARecord, RCAStatus
from services.api.app.schemas.retrieval import RAGEvidencePackage
from services.api.app.services.actions.workflow import (
    build_action_plan,
    transition_action,
    update_plan_status,
)
from services.api.app.services.demo.prepared_rca import PreparedRCAProvider
from services.api.app.services.rca.generation import generate_rca_record, transition_rca


def build_prepared_workflow(
    package: RAGEvidencePackage,
    generation_config: RCAGenerationConfig,
    action_policy: ActionPolicyConfig,
) -> tuple[RCARecord, ActionPlan]:
    """Return an approved RCA and representative action progress without persistence."""
    rca = generate_rca_record(
        package,
        PreparedRCAProvider(),
        generation_config,
        requested_by="Reliability Engineer",
    )
    reviewed_at = rca.evidence_as_of + timedelta(hours=1)
    rca = transition_rca(
        rca,
        RCAStatus.UNDER_REVIEW,
        "Reliability Engineer",
        "Evidence review started against the governed alert package.",
        reviewed_at,
    )
    approved_at = reviewed_at + timedelta(hours=4)
    rca = transition_rca(
        rca,
        RCAStatus.APPROVED,
        "Reliability Engineer",
        "Leading cause accepted for the prepared case workflow.",
        approved_at,
    )

    leading_hypothesis = rca.generation.hypotheses[0]
    plan = build_action_plan(
        rca,
        leading_hypothesis.hypothesis_id,
        action_policy,
        approved_at.date(),
    )
    target_sequences = {
        "CONTAINMENT": [
            ActionStatus.APPROVED,
            ActionStatus.IN_PROGRESS,
            ActionStatus.EFFECTIVENESS_REVIEW,
            ActionStatus.CLOSED,
        ],
        "CORRECTIVE": [ActionStatus.APPROVED, ActionStatus.IN_PROGRESS],
        "PREVENTIVE": [ActionStatus.APPROVED],
    }
    actions = []
    transition_time = approved_at
    for action in plan.actions:
        changed = action
        for next_status in target_sequences[action.action_type.value]:
            transition_time += timedelta(hours=1)
            changed = transition_action(
                changed,
                next_status,
                action_policy,
                rca.status,
                changed.owner_role,
                f"Prepared case advanced to {next_status.value.lower().replace('_', ' ')}.",
                transition_time,
            )
        actions.append(changed)
    return rca, update_plan_status(plan.model_copy(update={"actions": actions}))
