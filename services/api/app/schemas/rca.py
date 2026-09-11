"""Contracts for grounded RCA generation and review."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RCAModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CauseCategory(StrEnum):
    LUBRICATION_CONTAMINATION = "LUBRICATION_CONTAMINATION"
    BEARING_DEGRADATION = "BEARING_DEGRADATION"
    MECHANICAL_VIBRATION = "MECHANICAL_VIBRATION"
    INSTRUMENTATION_ISSUE = "INSTRUMENTATION_ISSUE"
    UNDETERMINED = "UNDETERMINED"


class InvestigationPriority(StrEnum):
    IMMEDIATE = "IMMEDIATE"
    HIGH = "HIGH"
    ROUTINE = "ROUTINE"


class RCAStatus(StrEnum):
    AI_DRAFT = "AI_DRAFT"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class CauseHypothesis(RCAModel):
    hypothesis_id: str
    rank: int = Field(ge=1)
    category: CauseCategory
    title: str
    mechanism: str
    confidence: float = Field(ge=0, le=1)
    rationale: str
    supporting_evidence_ids: list[str]
    contradicting_evidence_ids: list[str]
    analogue_incident_ids: list[str]
    missing_evidence: list[str]
    disconfirming_condition: str


class InvestigationStep(RCAModel):
    step_id: str
    priority: InvestigationPriority
    instruction: str
    rationale: str
    expected_evidence: str
    owner_role: str
    safety_gate: bool


class RCAGeneration(RCAModel):
    executive_summary: str
    hypotheses: list[CauseHypothesis] = Field(min_length=1, max_length=3)
    investigation_steps: list[InvestigationStep] = Field(min_length=1, max_length=6)
    operating_guidance: str
    requires_human_review: bool

    @model_validator(mode="after")
    def validate_ranking(self) -> "RCAGeneration":
        ranks = [hypothesis.rank for hypothesis in self.hypotheses]
        identifiers = [hypothesis.hypothesis_id for hypothesis in self.hypotheses]
        if ranks != list(range(1, len(ranks) + 1)):
            raise ValueError("Hypothesis ranks must be contiguous from one")
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Hypothesis IDs must be unique")
        if not self.requires_human_review:
            raise ValueError("AI-generated RCA must require human review")
        return self


class RCAProviderResult(RCAModel):
    provider: str
    model: str
    response_id: str
    generation: RCAGeneration
    input_tokens: int | None = None
    output_tokens: int | None = None


class RCARecord(RCAModel):
    rca_id: str
    alert_id: str
    evidence_package_id: str
    status: RCAStatus
    provider: str
    model: str
    response_id: str
    generation: RCAGeneration
    allowed_evidence_ids: list[str]
    allowed_incident_ids: list[str]


class RCAGenerationConfig(RCAModel):
    generator_id: str
    generator_version: str
    provider: str
    model_environment_variable: str
    default_model: str
    maximum_output_tokens: int = Field(ge=256)
    reasoning_effort: str
    prompt_version: str
