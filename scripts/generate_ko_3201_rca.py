#!/usr/bin/env python3
"""Validate or run grounded OpenAI RCA generation for KO-3201."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from services.api.app.schemas.rca import RCARecord
from services.api.app.schemas.retrieval import RAGEvidencePackage
from services.api.app.services.rca.generation import (
    OpenAIRCAProvider,
    build_rca_prompts,
    evidence_identifiers,
    generate_rca_record,
    load_generation_config,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument("--evidence", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--preflight", action="store_true")
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require_retrieval_validation(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"Missing retrieval validation: {path}")
    report = json.loads(path.read_text(encoding="utf-8"))
    if report.get("status") != "PASS":
        raise RuntimeError("Retrieval validation must pass before RCA generation")


def write_json(path: Path, payload: dict[str, Any] | RCARecord) -> None:
    content = payload.model_dump(mode="json") if isinstance(payload, RCARecord) else payload
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(content, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def run(
    root: Path,
    evidence_path: Path | None = None,
    output: Path | None = None,
    preflight: bool = False,
) -> dict[str, Any]:
    root = root.resolve()
    retrieval_directory = root / "data/retrieval/ko_3201/v1"
    evidence_path = (
        evidence_path or retrieval_directory / "rag_evidence_package.json"
    ).resolve()
    output = (output or root / "data/rca/ko_3201/v1").resolve()
    config_path = root / "data/catalog/ko_3201_rca_generation.yaml"
    require_retrieval_validation(retrieval_directory / "technical_validation.json")
    if not evidence_path.is_file():
        raise FileNotFoundError(f"Missing RAG evidence package: {evidence_path}")

    config = load_generation_config(config_path)
    load_dotenv(root / ".env", override=False)
    package = RAGEvidencePackage.model_validate_json(
        evidence_path.read_text(encoding="utf-8")
    )
    system_prompt, user_prompt = build_rca_prompts(package)
    evidence_ids, incident_ids = evidence_identifiers(package)
    preview = {
        "status": "READY",
        "generator_id": config.generator_id,
        "prompt_version": config.prompt_version,
        "provider": config.provider,
        "model": os.getenv(
            config.model_environment_variable,
            config.default_model,
        ),
        "evidence_package_id": package.package_id,
        "evidence_as_of": package.query.as_of.isoformat(),
        "allowed_evidence_ids": evidence_ids,
        "allowed_incident_ids": incident_ids,
        "system_prompt_sha256": hashlib.sha256(system_prompt.encode()).hexdigest(),
        "user_prompt_sha256": hashlib.sha256(user_prompt.encode()).hexdigest(),
        "evidence_package_sha256": sha256_file(evidence_path),
        "output_schema": "RCAGeneration",
    }
    write_json(output / "rca_request_preview.json", preview)
    if preflight:
        return preview

    enabled = os.getenv("CALIBER_LLM_ENABLED", "false").strip().lower() == "true"
    if not enabled:
        raise RuntimeError("Set CALIBER_LLM_ENABLED=true in .env before running RCA")
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("Set OPENAI_API_KEY in the local .env before running RCA")
    provider = OpenAIRCAProvider(config)
    record = generate_rca_record(package, provider, config)
    write_json(output / "rca_record.json", record)
    return {
        "status": record.status,
        "rca_id": record.rca_id,
        "model": record.model,
        "hypothesis_count": len(record.generation.hypotheses),
        "top_hypothesis": record.generation.hypotheses[0].title,
        "artifact": str(output / "rca_record.json"),
    }


def main() -> None:
    args = parse_args()
    report = run(args.root, args.evidence, args.output, args.preflight)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
