"""Unit tests for grounded RCA and governed CA/PA boundaries."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from services.api.app.schemas.actions import ActionStatus
from services.api.app.schemas.rca import (
    RCAGeneration,
    RCAGenerationConfig,
    RCAProviderResult,
    RCARecord,
    RCAStatus,
)
from services.api.app.services.actions.workflow import (
    build_action_plan,
    load_action_policy,
    transition_action,
)
from services.api.app.services.rca.generation import (
    OpenAIRCAProvider,
    transition_rca,
    validate_grounding,
)


ROOT = Path(__file__).resolve().parents[3]


def sample_generation() -> RCAGeneration:
    return RCAGeneration.model_validate(
        {
            "executive_summary": "Water contamination is the leading investigation path.",
            "hypotheses": [
                {
                    "hypothesis_id": "hypothesis-1",
                    "rank": 1,
                    "category": "LUBRICATION_CONTAMINATION",
                    "title": "Water ingress into the lubrication system",
                    "mechanism": "Water degrades oil-film performance and can accelerate bearing distress.",
                    "confidence": 0.72,
                    "rationale": "Water is breached while bearing condition indicators contribute to the anomaly.",
                    "supporting_evidence_ids": ["signal:water_in_oil"],
                    "contradicting_evidence_ids": [],
                    "analogue_incident_ids": ["incident-0213"],
                    "missing_evidence": ["Independent laboratory oil result"],
                    "disconfirming_condition": "Independent sampling finds water within specification.",
                }
            ],
            "investigation_steps": [
                {
                    "step_id": "step-1",
                    "priority": "IMMEDIATE",
                    "instruction": "Collect a controlled oil sample.",
                    "rationale": "Confirm the online water indication.",
                    "expected_evidence": "Independent water concentration result.",
                    "owner_role": "Reliability Engineer",
                    "safety_gate": True,
                }
            ],
            "operating_guidance": "Escalate the operating decision to the responsible operations authority.",
            "requires_human_review": True,
        }
    )


def sample_rca(status: RCAStatus = RCAStatus.AI_DRAFT) -> RCARecord:
    return RCARecord(
        rca_id="rca-alert-1",
        alert_id="alert-1",
        evidence_package_id="package-1",
        evidence_as_of="2026-02-23T19:00:00+07:00",
        status=status,
        generator_id="generator-1",
        prompt_version="prompt-1",
        provider="test",
        model="test-model",
        response_id="response-1",
        generation=sample_generation(),
        allowed_evidence_ids=["alert:alert-1", "signal:water_in_oil"],
        allowed_incident_ids=["incident-0213"],
    )


def test_grounding_rejects_unknown_citations() -> None:
    generation = sample_generation()
    changed = generation.model_copy(deep=True)
    changed.hypotheses[0].supporting_evidence_ids.append("signal:future_trip")

    with pytest.raises(ValueError, match="unknown evidence"):
        validate_grounding(
            changed,
            ["signal:water_in_oil"],
            ["incident-0213"],
        )


def test_openai_adapter_requests_structured_non_stored_output() -> None:
    calls: list[dict[str, object]] = []

    class FakeResponses:
        def parse(self, **kwargs: object) -> SimpleNamespace:
            calls.append(kwargs)
            return SimpleNamespace(
                status="completed",
                output_parsed=sample_generation(),
                model="test-model",
                id="response-1",
                usage=SimpleNamespace(input_tokens=100, output_tokens=80),
            )

    client = SimpleNamespace(responses=FakeResponses())
    config = RCAGenerationConfig(
        generator_id="generator-1",
        generator_version="1.0.0",
        provider="openai",
        model_environment_variable="TEST_RCA_MODEL",
        default_model="test-model",
        maximum_output_tokens=1200,
        reasoning_effort="low",
        prompt_version="prompt-1",
    )
    result = OpenAIRCAProvider(config, client=client).generate("system", "user")

    assert isinstance(result, RCAProviderResult)
    assert calls[0]["text_format"] is RCAGeneration
    assert calls[0]["store"] is False
    assert calls[0]["model"] == "test-model"


def test_action_plan_is_policy_driven_and_deterministic() -> None:
    policy = load_action_policy(ROOT / "data/catalog/ko_3201_action_policy.yaml")
    first = build_action_plan(sample_rca(), "hypothesis-1", policy, date(2026, 2, 23))
    second = build_action_plan(sample_rca(), "hypothesis-1", policy, date(2026, 2, 23))

    assert first == second
    assert [action.action_type for action in first.actions] == [
        "CONTAINMENT",
        "CORRECTIVE",
        "PREVENTIVE",
    ]
    assert [action.due_date for action in first.actions] == [
        "2026-02-23",
        "2026-03-02",
        "2026-03-25",
    ]


def test_action_approval_requires_reviewed_rca() -> None:
    policy = load_action_policy(ROOT / "data/catalog/ko_3201_action_policy.yaml")
    plan = build_action_plan(sample_rca(), "hypothesis-1", policy, date(2026, 2, 23))

    with pytest.raises(ValueError, match="before the RCA is approved"):
        transition_action(
            plan.actions[0],
            ActionStatus.APPROVED,
            policy,
            RCAStatus.AI_DRAFT,
            "reviewer-1",
            "Ready to execute",
            datetime(2026, 2, 23, tzinfo=timezone.utc),
        )
    approved = transition_action(
        plan.actions[0],
        ActionStatus.APPROVED,
        policy,
        RCAStatus.APPROVED,
        "reviewer-1",
        "Ready to execute",
        datetime(2026, 2, 23, tzinfo=timezone.utc),
    )
    assert approved.status == ActionStatus.APPROVED
    assert approved.status_history[0].actor == "reviewer-1"


def test_rca_review_follows_audited_state_machine() -> None:
    draft = sample_rca()
    reviewed = transition_rca(
        draft,
        RCAStatus.UNDER_REVIEW,
        "engineer-1",
        "Review started",
        datetime(2026, 2, 23, tzinfo=timezone.utc),
    )
    approved = transition_rca(
        reviewed,
        RCAStatus.APPROVED,
        "engineer-1",
        "Evidence accepted",
        datetime(2026, 2, 24, tzinfo=timezone.utc),
    )

    assert approved.status == RCAStatus.APPROVED
    assert len(approved.status_history) == 2
    with pytest.raises(ValueError, match="Invalid RCA transition"):
        transition_rca(
            draft,
            RCAStatus.APPROVED,
            "engineer-1",
            "Skipped review",
            datetime(2026, 2, 23, tzinfo=timezone.utc),
        )
