"""Acceptance tests for the keyless KO-3201 RCA and CA/PA architecture."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.build_ko_3201_actions import run as run_actions
from scripts.generate_ko_3201_rca import run as run_rca
from services.api.app.schemas.rca import (
    RCAGeneration,
    RCAProviderResult,
)
from services.api.app.schemas.retrieval import RAGEvidencePackage
from services.api.app.services.rca.generation import (
    build_rca_prompts,
    generate_rca_record,
    load_generation_config,
)

ROOT = Path(__file__).resolve().parents[3]
RETRIEVAL_DIRECTORY = ROOT / "data/retrieval/ko_3201/v1"


@pytest.fixture(scope="module")
def evidence_package() -> RAGEvidencePackage:
    path = RETRIEVAL_DIRECTORY / "rag_evidence_package.json"
    validation = RETRIEVAL_DIRECTORY / "technical_validation.json"
    if not path.is_file() or not validation.is_file():
        pytest.skip("KO-3201 retrieval outputs are not available")
    return RAGEvidencePackage.model_validate_json(path.read_text(encoding="utf-8"))


def generation_for(package: RAGEvidencePackage) -> RCAGeneration:
    analogue_id = package.historical_analogues[0].incident_id
    return RCAGeneration.model_validate(
        {
            "executive_summary": "The alert requires investigation of lubrication and bearing condition.",
            "hypotheses": [
                {
                    "hypothesis_id": "hypothesis-1",
                    "rank": 1,
                    "category": "LUBRICATION_CONTAMINATION",
                    "title": "Lubrication contamination",
                    "mechanism": "Water can reduce oil-film performance and contribute to bearing distress.",
                    "confidence": 0.7,
                    "rationale": "Water is breached and bearing indicators support investigation.",
                    "supporting_evidence_ids": ["signal:water_in_oil"],
                    "contradicting_evidence_ids": [],
                    "analogue_incident_ids": [analogue_id],
                    "missing_evidence": ["Independent oil analysis"],
                    "disconfirming_condition": "Independent testing finds no water contamination.",
                }
            ],
            "investigation_steps": [
                {
                    "step_id": "step-1",
                    "priority": "IMMEDIATE",
                    "instruction": "Collect an independent oil sample.",
                    "rationale": "Verify the breached water indication.",
                    "expected_evidence": "Traceable water concentration result.",
                    "owner_role": "Reliability Engineer",
                    "safety_gate": True,
                }
            ],
            "operating_guidance": "Escalate the operating decision to the responsible authority.",
            "requires_human_review": True,
        }
    )


def test_preflight_builds_request_without_api_key(
    evidence_package: RAGEvidencePackage,
    tmp_path: Path,
) -> None:
    report = run_rca(ROOT, output=tmp_path, preflight=True)

    assert report["status"] == "READY"
    assert report["output_schema"] == "RCAGeneration"
    assert report["evidence_as_of"] == "2026-02-23T19:00:00+07:00"
    assert (tmp_path / "rca_request_preview.json").is_file()


def test_prompt_does_not_contain_current_case_outcome(
    evidence_package: RAGEvidencePackage,
) -> None:
    _, user_prompt = build_rca_prompts(evidence_package)

    assert "LEAKING_OIL_COOLER_TUBE" not in user_prompt
    assert "incident-0002" not in user_prompt


def test_grounded_provider_result_builds_action_proposal(
    evidence_package: RAGEvidencePackage,
    tmp_path: Path,
) -> None:
    generation = generation_for(evidence_package)

    class FakeProvider:
        def generate(self, system_prompt: str, user_prompt: str) -> RCAProviderResult:
            assert system_prompt
            assert user_prompt
            return RCAProviderResult(
                provider="test",
                model="test-model",
                response_id="response-test",
                generation=generation,
                input_tokens=100,
                output_tokens=80,
            )

    config = load_generation_config(
        ROOT / "data/catalog/ko_3201_rca_generation.yaml"
    )
    rca = generate_rca_record(evidence_package, FakeProvider(), config)
    rca_path = tmp_path / "rca_record.json"
    rca_path.write_text(
        json.dumps(rca.model_dump(mode="json")),
        encoding="utf-8",
    )
    action_output = tmp_path / "actions"
    report = run_actions(ROOT, rca_path, action_output)
    action_plan = json.loads(
        (action_output / "action_plan.json").read_text(encoding="utf-8")
    )

    assert report["status"] == "PASS"
    assert report["action_count"] == 3
    assert action_plan["status"] == "PROPOSED"
    assert [action["action_type"] for action in action_plan["actions"]] == [
        "CONTAINMENT",
        "CORRECTIVE",
        "PREVENTIVE",
    ]
