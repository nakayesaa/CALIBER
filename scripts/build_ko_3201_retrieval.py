#!/usr/bin/env python3
"""Build and validate KO-3201 historical incident retrieval outputs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import yaml
from pydantic import BaseModel

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from services.api.app.schemas.retrieval import (
    IncidentDocument,
    IncidentRetrievalConfig,
    IncidentRetrievalResult,
    RAGEvidencePackage,
    RetrievalManifest,
    RetrievalQuery,
    RetrievalValidationCheck,
    RetrievalValidationReport,
)
from services.api.app.services.rca.incident_retrieval import (
    build_alert_open_query,
    build_incident_documents,
    eligible_documents,
    retrieve_incidents,
)

LOCAL_TIMEZONE = ZoneInfo("Asia/Jakarta")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument("--normalized", type=Path, default=None)
    parser.add_argument("--alerts", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--alert-id", type=str, default=None)
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require_passing_report(
    path: Path,
    description: str,
    accepted_statuses: set[str] | None = None,
) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"Missing {description}: {path}")
    report = json.loads(path.read_text(encoding="utf-8"))
    accepted = accepted_statuses or {"PASS"}
    if report.get("status") not in accepted:
        raise RuntimeError(f"{description} must pass before incident retrieval")


def load_config(root: Path) -> tuple[IncidentRetrievalConfig, Path]:
    path = root / "data/catalog/ko_3201_retrieval_config.yaml"
    config = IncidentRetrievalConfig.model_validate(
        yaml.safe_load(path.read_text(encoding="utf-8"))
    )
    return config, path


def select_alert(alerts: pd.DataFrame, alert_id: str | None) -> dict[str, Any]:
    if alert_id:
        selected = alerts.loc[alerts["alert_id"].astype(str).eq(alert_id)]
    else:
        selected = alerts
    if len(selected) != 1:
        hint = "Pass --alert-id when more than one alert exists."
        raise ValueError(f"Expected exactly one alert. {hint}")
    return selected.iloc[0].to_dict()


def select_asset(assets: pd.DataFrame, asset_id: str) -> dict[str, Any]:
    selected = assets.loc[assets["asset_id"].astype(str).eq(asset_id)]
    if len(selected) != 1:
        raise ValueError(f"Expected one asset row for {asset_id}")
    return selected.iloc[0].to_dict()


def build_alert_snapshot(
    alert: dict[str, Any],
    decisions: pd.DataFrame,
) -> dict[str, Any]:
    timestamps = pd.to_datetime(decisions["timestamp"], errors="raise")
    opening = decisions.loc[timestamps.eq(pd.Timestamp(alert["opened_at"]))]
    if len(opening) != 1:
        raise ValueError("Exactly one decision must match alert opened_at")
    row = opening.iloc[0]
    breached = [] if pd.isna(row["breached_signals"]) else str(row["breached_signals"]).split(";")
    driver = "" if pd.isna(row["top_driver_1"]) else str(row["top_driver_1"])
    return {
        "alert_id": str(alert["alert_id"]),
        "asset_id": str(alert["asset_id"]),
        "opened_at": pd.Timestamp(alert["opened_at"]).isoformat(),
        "decision_state": str(row["decision_state"]),
        "decision_reason": str(row["decision_reason"]),
        "anomaly_score": float(row["anomaly_score"]),
        "anomaly_threshold": float(row["anomaly_threshold"]),
        "alarm_breadth": int(row["alarm_breadth"]),
        "breached_signals": breached,
        "primary_driver": driver.removeprefix("condition."),
    }


def build_validation_report(
    config: IncidentRetrievalConfig,
    query: RetrievalQuery,
    eligible: list[IncidentDocument],
    results: list[IncidentRetrievalResult],
) -> RetrievalValidationReport:
    excluded = set(config.eligibility.exclude_incident_ids)
    result_ids = [result.incident_id for result in results]
    mechanism_counts = Counter(result.failure_mechanism for result in results)
    checks = [
        RetrievalValidationCheck(
            name="eligible_corpus_is_non_empty",
            status="PASS" if eligible else "FAIL",
            actual=len(eligible),
        ),
        RetrievalValidationCheck(
            name="configured_incidents_are_excluded",
            status="PASS" if not excluded.intersection(result_ids) else "FAIL",
            actual=not bool(excluded.intersection(result_ids)),
        ),
        RetrievalValidationCheck(
            name="all_sources_precede_query_time",
            status=(
                "PASS"
                if all(document.occurred_at < query.as_of for document in eligible)
                else "FAIL"
            ),
            actual=all(document.occurred_at < query.as_of for document in eligible),
        ),
        RetrievalValidationCheck(
            name="results_are_unique",
            status="PASS" if len(result_ids) == len(set(result_ids)) else "FAIL",
            actual=len(set(result_ids)),
        ),
        RetrievalValidationCheck(
            name="ranks_are_contiguous",
            status=(
                "PASS"
                if [result.rank for result in results] == list(range(1, len(results) + 1))
                else "FAIL"
            ),
            actual=len(results),
        ),
        RetrievalValidationCheck(
            name="diversity_limit_is_respected",
            status=(
                "PASS"
                if max(mechanism_counts.values(), default=0)
                <= config.diversity.maximum_per_failure_mechanism
                else "FAIL"
            ),
            actual=max(mechanism_counts.values(), default=0),
        ),
        RetrievalValidationCheck(
            name="result_count_within_top_k",
            status="PASS" if 0 < len(results) <= config.top_k else "FAIL",
            actual=len(results),
        ),
    ]
    status = "PASS" if all(check.status == "PASS" for check in checks) else "FAIL"
    if status != "PASS":
        failed = [check.name for check in checks if check.status == "FAIL"]
        raise RuntimeError("Retrieval validation failed: " + ", ".join(failed))
    return RetrievalValidationReport(
        status=status,
        retriever_id=config.retriever_id,
        query_id=query.query_id,
        eligible_document_count=len(eligible),
        result_count=len(results),
        checks=checks,
        evaluation_scope="Integrity and ranking-behavior checks without relevance ground truth",
        known_limitations=[
            "The incident database has no expert relevance judgments for retrieval evaluation.",
            "Historical analogue rows do not contain confirmed root-cause narratives.",
        ],
    )


def model_to_row(model: BaseModel) -> dict[str, Any]:
    row = model.model_dump(mode="json")
    for key, value in row.items():
        if isinstance(value, (list, dict)):
            row[key] = json.dumps(value, separators=(",", ":"), sort_keys=True)
    return row


def write_models(
    path: Path,
    models: list[BaseModel],
    model_type: type[BaseModel],
) -> None:
    rows = [model_to_row(model) for model in models]
    fieldnames = list(rows[0]) if rows else list(model_type.model_fields)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def write_json(path: Path, payload: BaseModel | dict[str, Any]) -> None:
    content = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else payload
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(content, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def run(
    root: Path,
    normalized_directory: Path | None = None,
    alert_directory: Path | None = None,
    output: Path | None = None,
    alert_id: str | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    normalized_directory = (
        normalized_directory or root / "data/normalized/ko_3201"
    ).resolve()
    alert_directory = (alert_directory or root / "data/alerts/ko_3201/v1").resolve()
    output = (output or root / "data/retrieval/ko_3201/v1").resolve()
    require_passing_report(
        normalized_directory / "validation_report.json",
        "canonical data validation",
        {"PASS", "PASS_WITH_DOCUMENTED_WARNINGS"},
    )
    require_passing_report(
        alert_directory / "technical_validation.json", "alert technical validation"
    )

    paths = {
        "incidents": normalized_directory / "incidents.csv",
        "labels": normalized_directory / "incident_labels.csv",
        "assets": normalized_directory / "assets.csv",
        "alerts": alert_directory / "alerts.csv",
        "decisions": alert_directory / "hourly_alert_decisions.csv",
    }
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing retrieval inputs: " + ", ".join(missing))

    config, config_path = load_config(root)
    incidents = pd.read_csv(paths["incidents"])
    labels = pd.read_csv(paths["labels"])
    assets = pd.read_csv(paths["assets"])
    alerts = pd.read_csv(paths["alerts"])
    decisions = pd.read_csv(paths["decisions"])
    alert = select_alert(alerts, alert_id)
    asset = select_asset(assets, str(alert["asset_id"]))
    documents = build_incident_documents(incidents, labels)
    query = build_alert_open_query(alert, asset, decisions, config)
    eligible = eligible_documents(documents, query, config)
    results = retrieve_incidents(documents, query, config)
    validation = build_validation_report(config, query, eligible, results)
    snapshot = build_alert_snapshot(alert, decisions)
    evidence_package = RAGEvidencePackage(
        package_id=f"rag-{query.query_id}",
        created_for_stage="EARLY_WARNING_RCA",
        query=query,
        alert_snapshot=snapshot,
        historical_analogues=results,
        evidence_boundaries=[
            "Use only evidence in this package.",
            "Treat retrieved incidents as analogues, not confirmed causes.",
            "State uncertainty and identify evidence needed to distinguish hypotheses.",
        ],
        requested_output=[
            "Ranked probable cause hypotheses with evidence for and against",
            "Missing checks or measurements needed to confirm each hypothesis",
            "Immediate investigation guidance linked to the alert evidence",
        ],
    )
    manifest = RetrievalManifest(
        retriever_id=config.retriever_id,
        retriever_version=config.retriever_version,
        generated_at=datetime.now(LOCAL_TIMEZONE),
        config_sha256=sha256_file(config_path),
        incidents_sha256=sha256_file(paths["incidents"]),
        incident_labels_sha256=sha256_file(paths["labels"]),
        assets_sha256=sha256_file(paths["assets"]),
        alerts_sha256=sha256_file(paths["alerts"]),
        hourly_decisions_sha256=sha256_file(paths["decisions"]),
        source_document_count=len(documents),
        eligible_document_count=len(eligible),
        result_count=len(results),
        query_as_of=query.as_of,
    )

    write_models(output / "eligible_incident_documents.csv", eligible, IncidentDocument)
    write_json(output / "retrieval_query.json", query)
    write_models(output / "retrieval_results.csv", results, IncidentRetrievalResult)
    write_json(output / "rag_evidence_package.json", evidence_package)
    write_json(output / "retrieval_manifest.json", manifest)
    write_json(output / "technical_validation.json", validation)
    return {
        "status": validation.status,
        "retriever_id": config.retriever_id,
        "query_id": query.query_id,
        "query_as_of": query.as_of.isoformat(),
        "query_signals": query.breached_signals,
        "supporting_signals": query.supporting_signals,
        "source_documents": len(documents),
        "eligible_documents": len(eligible),
        "retrieval_results": len(results),
        "evidence_package": str(output / "rag_evidence_package.json"),
    }


def main() -> None:
    args = parse_args()
    report = run(args.root, args.normalized, args.alerts, args.output, args.alert_id)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
