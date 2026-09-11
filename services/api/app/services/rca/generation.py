"""Grounded RCA prompt construction, provider boundary, and validation."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Protocol

import yaml

from services.api.app.schemas.rca import (
    RCAGeneration,
    RCAGenerationConfig,
    RCAProviderResult,
    RCARecord,
    RCAStatus,
)
from services.api.app.schemas.retrieval import RAGEvidencePackage


SYSTEM_PROMPT = """You are a manufacturing reliability engineer preparing an early-warning RCA draft.
Use only the supplied alert snapshot and historical analogues. Treat analogues as investigation clues, not confirmed causes. Never invent measurements, inspections, or source conclusions. Rank up to three distinct hypotheses. Confidence must reflect evidence strength and uncertainty. Cite only IDs from allowed_evidence_ids and allowed_incident_ids. Each hypothesis needs a test that could disconfirm it. Recommend safe investigation steps, but do not authorize equipment operation or maintenance execution. Human review is mandatory."""


class RCAProvider(Protocol):
    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> RCAProviderResult: ...


def load_generation_config(path: Path) -> RCAGenerationConfig:
    return RCAGenerationConfig.model_validate(
        yaml.safe_load(path.read_text(encoding="utf-8"))
    )


def evidence_identifiers(package: RAGEvidencePackage) -> tuple[list[str], list[str]]:
    query = package.query
    evidence_ids = [
        f"alert:{query.alert_id}",
        *[f"signal:{signal}" for signal in query.breached_signals],
        *[f"signal:{signal}" for signal in query.supporting_signals],
    ]
    incident_ids = [item.incident_id for item in package.historical_analogues]
    return list(dict.fromkeys(evidence_ids)), list(dict.fromkeys(incident_ids))


def build_rca_prompts(package: RAGEvidencePackage) -> tuple[str, str]:
    evidence_ids, incident_ids = evidence_identifiers(package)
    payload = {
        "allowed_evidence_ids": evidence_ids,
        "allowed_incident_ids": incident_ids,
        "evidence_package": package.model_dump(mode="json"),
    }
    return SYSTEM_PROMPT, json.dumps(payload, separators=(",", ":"), sort_keys=True)


def validate_grounding(
    generation: RCAGeneration,
    allowed_evidence_ids: list[str],
    allowed_incident_ids: list[str],
) -> None:
    evidence = set(allowed_evidence_ids)
    incidents = set(allowed_incident_ids)
    errors: list[str] = []
    for hypothesis in generation.hypotheses:
        cited_evidence = {
            *hypothesis.supporting_evidence_ids,
            *hypothesis.contradicting_evidence_ids,
        }
        unknown_evidence = cited_evidence - evidence
        unknown_incidents = set(hypothesis.analogue_incident_ids) - incidents
        if not hypothesis.supporting_evidence_ids:
            errors.append(f"{hypothesis.hypothesis_id} has no supporting evidence")
        if unknown_evidence:
            errors.append(
                f"{hypothesis.hypothesis_id} cites unknown evidence {sorted(unknown_evidence)}"
            )
        if unknown_incidents:
            errors.append(
                f"{hypothesis.hypothesis_id} cites unknown incidents {sorted(unknown_incidents)}"
            )
    if errors:
        raise ValueError("RCA grounding validation failed: " + "; ".join(errors))


def generate_rca_record(
    package: RAGEvidencePackage,
    provider: RCAProvider,
) -> RCARecord:
    system_prompt, user_prompt = build_rca_prompts(package)
    result = provider.generate(system_prompt, user_prompt)
    allowed_evidence_ids, allowed_incident_ids = evidence_identifiers(package)
    validate_grounding(
        result.generation,
        allowed_evidence_ids,
        allowed_incident_ids,
    )
    return RCARecord(
        rca_id=f"rca-{package.query.alert_id}",
        alert_id=package.query.alert_id,
        evidence_package_id=package.package_id,
        status=RCAStatus.AI_DRAFT,
        provider=result.provider,
        model=result.model,
        response_id=result.response_id,
        generation=result.generation,
        allowed_evidence_ids=allowed_evidence_ids,
        allowed_incident_ids=allowed_incident_ids,
    )


class OpenAIRCAProvider:
    """OpenAI Responses API adapter with schema-validated output."""

    def __init__(
        self,
        config: RCAGenerationConfig,
        api_key: str | None = None,
        client: object | None = None,
    ) -> None:
        self.config = config
        self.model = os.getenv(
            config.model_environment_variable,
            config.default_model,
        )
        if client is None:
            from openai import OpenAI

            client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
        self.client = client

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> RCAProviderResult:
        response = self.client.responses.parse(
            model=self.model,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            text_format=RCAGeneration,
            reasoning={"effort": self.config.reasoning_effort},
            max_output_tokens=self.config.maximum_output_tokens,
            store=False,
        )
        if response.status != "completed":
            raise RuntimeError(f"OpenAI RCA response ended with status {response.status}")
        if response.output_parsed is None:
            raise RuntimeError("OpenAI RCA response did not contain structured output")
        usage = response.usage
        return RCAProviderResult(
            provider="openai",
            model=response.model,
            response_id=response.id,
            generation=response.output_parsed,
            input_tokens=getattr(usage, "input_tokens", None),
            output_tokens=getattr(usage, "output_tokens", None),
        )
