"""Validated contracts for historical incident retrieval."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RetrievalConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class TfidfConfig(RetrievalConfigModel):
    analyzer: str
    ngram_range: tuple[int, int]
    sublinear_tf: bool = True

    @model_validator(mode="after")
    def validate_ngrams(self) -> "TfidfConfig":
        lower, upper = self.ngram_range
        if lower < 1 or upper < lower:
            raise ValueError("TF-IDF ngram range is invalid")
        return self


class HybridWeights(RetrievalConfigModel):
    word_similarity: float = Field(ge=0, le=1)
    character_similarity: float = Field(ge=0, le=1)
    equipment_family: float = Field(ge=0, le=1)
    discipline: float = Field(ge=0, le=1)
    component_overlap: float = Field(ge=0, le=1)
    symptom_overlap: float = Field(ge=0, le=1)
    plant: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_total(self) -> "HybridWeights":
        if abs(sum(self.model_dump().values()) - 1.0) > 1e-9:
            raise ValueError("Hybrid retrieval weights must sum to one")
        return self


class QueryMapping(RetrievalConfigModel):
    symptom: str
    component: str
    narrative: str


class RetrievalEligibility(RetrievalConfigModel):
    exclude_incident_ids: list[str] = Field(min_length=1)
    require_occurred_before_alert_open: bool = True


class RetrievalDiversity(RetrievalConfigModel):
    maximum_per_failure_mechanism: int = Field(ge=1)


class IncidentRetrievalConfig(RetrievalConfigModel):
    retriever_id: str
    retriever_version: str
    input_alert_policy_id: str
    top_k: int = Field(ge=1, le=25)
    minimum_hybrid_score: float = Field(ge=0, le=1)
    word_vectorizer: TfidfConfig
    character_vectorizer: TfidfConfig
    weights: HybridWeights
    eligibility: RetrievalEligibility
    diversity: RetrievalDiversity
    signal_mappings: dict[str, QueryMapping]

    @model_validator(mode="after")
    def validate_mappings(self) -> "IncidentRetrievalConfig":
        if not self.signal_mappings:
            raise ValueError("At least one signal mapping is required")
        return self


class IncidentDocument(RetrievalConfigModel):
    incident_id: str
    occurred_at: datetime
    asset_tag: str
    plant_id: str
    title: str
    highest_impact: str
    equipment_family: str
    discipline: str
    component: str
    observed_symptoms: list[str]
    failure_family: str
    failure_mechanism: str
    business_consequences: list[str]
    downtime_hours: float
    total_loss_kusd: float
    source_reference: str
    search_text: str


class RetrievalQuery(RetrievalConfigModel):
    query_id: str
    alert_id: str
    as_of: datetime
    asset_id: str
    asset_tag: str
    plant_id: str
    equipment_family: str
    discipline: str
    components: list[str]
    observed_symptoms: list[str]
    breached_signals: list[str]
    primary_driver: str
    narrative: str
    search_text: str


class IncidentRetrievalResult(RetrievalConfigModel):
    query_id: str
    rank: int = Field(ge=1)
    incident_id: str
    occurred_at: datetime
    asset_tag: str
    title: str
    equipment_family: str
    discipline: str
    component: str
    failure_mechanism: str
    observed_symptoms: list[str]
    business_consequences: list[str]
    hybrid_score: float = Field(ge=0, le=1)
    word_similarity: float = Field(ge=0, le=1)
    character_similarity: float = Field(ge=0, le=1)
    equipment_family_score: float = Field(ge=0, le=1)
    discipline_score: float = Field(ge=0, le=1)
    component_overlap_score: float = Field(ge=0, le=1)
    symptom_overlap_score: float = Field(ge=0, le=1)
    plant_score: float = Field(ge=0, le=1)
    match_reasons: list[str]
    source_reference: str
