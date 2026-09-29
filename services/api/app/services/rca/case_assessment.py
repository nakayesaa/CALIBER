"""Evaluate a case-specific causal map against evidence available at a point in time."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from services.api.app.schemas.api import (
    InvestigationEvidenceEvent,
    InvestigationEvidenceProgress,
    RCACausalLink,
    RCAExplanationCheck,
)


class CaseRule(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CaseStage(CaseRule):
    id: Literal["PROBABLE", "CONTAMINATION_SUPPORTED", "CAUSE_REPORTED", "REPAIR_REPORTED"]
    requires: list[str]
    summary: str
    decision: str


class CausalStep(CaseRule):
    id: str
    suspected: str
    reported: str
    report_event_id: str
    opening_signal: str | None = None


class Explanation(CaseRule):
    id: str
    title: str
    starting_basis: str
    supporting_event_ids: list[str]
    challenging_event_ids: list[str]
    next_check: str


class CasePolicy(CaseRule):
    policy_id: str
    stages: list[CaseStage] = Field(min_length=1)
    causal_path: list[CausalStep] = Field(min_length=1)
    explanations: list[Explanation] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_policy(self) -> CasePolicy:
        if self.stages[0].id != "PROBABLE" or self.stages[0].requires:
            raise ValueError("The first RCA stage must be the unconditional probable stage")
        for items in (self.stages, self.causal_path, self.explanations):
            identifiers = [item.id for item in items]
            if len(identifiers) != len(set(identifiers)):
                raise ValueError("RCA policy identifiers must be unique")
        return self


def load_case_policy(path: Path) -> CasePolicy:
    with path.open(encoding="utf-8") as stream:
        return CasePolicy.model_validate(yaml.safe_load(stream))


def assess_case(
    alert_id: str,
    as_of: datetime,
    events: list[InvestigationEvidenceEvent],
    opening_signals: set[str],
    policy: CasePolicy,
) -> InvestigationEvidenceProgress:
    visible = [event for event in events if event.occurred_at <= as_of]
    by_id = {event.event_id: event for event in visible}
    visible_ids = set(by_id)
    stage = next(
        stage for stage in reversed(policy.stages)
        if set(stage.requires) <= visible_ids
    )
    path = [
        RCACausalLink(
            link_id=step.id,
            label=step.reported if step.report_event_id in by_id else step.suspected,
            state=(
                "RCA_REPORTED" if step.report_event_id in by_id
                else "MONITORED_TREND" if step.opening_signal in opening_signals
                else "HYPOTHESIS"
            ),
            source_event=by_id.get(step.report_event_id),
        )
        for step in policy.causal_path
    ]
    explanations = []
    for item in policy.explanations:
        supporting = [by_id[event_id] for event_id in item.supporting_event_ids if event_id in by_id]
        challenging = [by_id[event_id] for event_id in item.challenging_event_ids if event_id in by_id]
        state = (
            "MIXED" if supporting and challenging
            else "SUPPORTED" if supporting
            else "WEAKENED" if challenging
            else "OPEN"
        )
        explanations.append(RCAExplanationCheck(
            explanation_id=item.id,
            title=item.title,
            starting_basis=item.starting_basis,
            state=state,
            supporting_events=supporting,
            challenging_events=challenging,
            next_check=item.next_check,
        ))
    next_event = next((event.occurred_at for event in events if event.occurred_at > as_of), None)
    return InvestigationEvidenceProgress(
        alert_id=alert_id,
        as_of=as_of,
        stage=stage.id,
        summary=stage.summary,
        decision_gate=stage.decision,
        events=visible,
        causal_path=path,
        explanations=explanations,
        next_event_at=next_event,
    )
