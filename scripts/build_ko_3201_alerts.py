#!/usr/bin/env python3
"""Build and validate KO-3201 hourly alert decisions and grouped events."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
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

from services.api.app.schemas.alerts import (  # noqa: E402
    AlertEngineManifest,
    AlertEvent,
    AlertPolicyConfig,
    AlertStateTransition,
    AlertValidationCheck,
    AlertValidationReport,
)
from services.api.app.services.alerts.decision_engine import (  # noqa: E402
    AlertDecisionResult,
    build_alert_decisions,
    decision_input_columns,
    evaluate_alert_decisions,
)


LOCAL_TIMEZONE = ZoneInfo("Asia/Jakarta")
EVALUATION_ONLY_COLUMNS = ["scenario_phase", "health_state", "event_marker"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument(
        "--scores",
        type=Path,
        default=None,
        help="Scored model directory (default: data/scored/ko_3201/v1)",
    )
    parser.add_argument(
        "--features",
        type=Path,
        default=None,
        help="Feature directory (default: data/features/ko_3201/v1)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Alert output directory (default: data/alerts/ko_3201/v1)",
    )
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_policy(root: Path) -> tuple[AlertPolicyConfig, Path]:
    path = root / "data/catalog/ko_3201_alert_policy.yaml"
    policy = AlertPolicyConfig.model_validate(
        yaml.safe_load(path.read_text(encoding="utf-8"))
    )
    return policy, path


def require_passing_report(path: Path, description: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"Missing {description}: {path}")
    report = json.loads(path.read_text(encoding="utf-8"))
    if report.get("status") != "PASS":
        raise RuntimeError(f"{description} must pass before alert decisions")


def build_manifest(
    policy: AlertPolicyConfig,
    policy_path: Path,
    scores_path: Path,
    features_path: Path,
    result: AlertDecisionResult,
) -> AlertEngineManifest:
    ratio_columns = list(policy.evidence.alarm_ratio_columns.values())
    return AlertEngineManifest(
        policy_id=policy.policy_id,
        policy_version=policy.policy_version,
        input_model_id=policy.input_model_id,
        generated_at=datetime.now(LOCAL_TIMEZONE),
        scored_timeline_sha256=sha256_file(scores_path),
        feature_table_sha256=sha256_file(features_path),
        policy_sha256=sha256_file(policy_path),
        hourly_decision_rows=len(result.hourly_decisions),
        alert_event_count=len(result.events),
        state_transition_count=len(result.transitions),
        decision_input_columns=[*decision_input_columns(policy), *ratio_columns],
        evaluation_only_columns=EVALUATION_ONLY_COLUMNS,
    )


def build_validation_report(
    policy: AlertPolicyConfig,
    result: AlertDecisionResult,
    source_rows: int,
) -> AlertValidationReport:
    decisions = result.hourly_decisions
    severity_names = {rule.name for rule in policy.severity_rules}
    allowed_states = {"NORMAL", "SUPPRESSED", *severity_names}
    decision_states = set(decisions["decision_state"].astype(str))
    event_ids = [event.alert_id for event in result.events]
    checks = [
        AlertValidationCheck(
            name="hourly_decision_row_count",
            status="PASS" if len(decisions) == source_rows else "FAIL",
            actual=len(decisions),
        ),
        AlertValidationCheck(
            name="decision_states_follow_policy",
            status="PASS" if decision_states <= allowed_states else "FAIL",
            actual=bool(decision_states <= allowed_states),
        ),
        AlertValidationCheck(
            name="alert_event_ids_are_unique",
            status="PASS" if len(event_ids) == len(set(event_ids)) else "FAIL",
            actual=len(set(event_ids)),
        ),
        AlertValidationCheck(
            name="evaluation_labels_excluded_from_decisions",
            status=(
                "PASS"
                if not set(EVALUATION_ONLY_COLUMNS).intersection(decisions.columns)
                else "FAIL"
            ),
            actual=not bool(
                set(EVALUATION_ONLY_COLUMNS).intersection(decisions.columns)
            ),
        ),
        AlertValidationCheck(
            name="candidate_anomalies_have_evidence",
            status=(
                "PASS"
                if (
                    ~decisions["candidate_anomaly"]
                    | decisions["has_condition_driver"]
                    | decisions["alarm_breadth"].gt(0)
                ).all()
                else "FAIL"
            ),
            actual=bool(
                (
                    ~decisions["candidate_anomaly"]
                    | decisions["has_condition_driver"]
                    | decisions["alarm_breadth"].gt(0)
                ).all()
            ),
        ),
    ]
    status = "PASS" if all(check.status == "PASS" for check in checks) else "FAIL"
    if status != "PASS":
        failed = [check.name for check in checks if check.status == "FAIL"]
        raise RuntimeError("Alert validation failed: " + ", ".join(failed))
    return AlertValidationReport(
        status=status,
        policy_id=policy.policy_id,
        checks=checks,
    )


def model_to_row(model: BaseModel) -> dict[str, Any]:
    row = model.model_dump(mode="json")
    for key, value in row.items():
        if isinstance(value, (list, dict)):
            row[key] = json.dumps(value, separators=(",", ":"), sort_keys=True)
    return row


def write_frame(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    serialized = frame.copy()
    serialized["timestamp"] = serialized["timestamp"].map(
        lambda value: pd.Timestamp(value).isoformat()
    )
    serialized.to_csv(temporary, index=False)
    temporary.replace(path)


def write_models(
    path: Path,
    models: list[BaseModel],
    model_type: type[BaseModel],
) -> None:
    rows = [model_to_row(model) for model in models]
    fieldnames = list(rows[0]) if rows else list(model_type.model_fields)
    temporary = path.with_suffix(path.suffix + ".tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def write_json(path: Path, payload: BaseModel | dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    content = (
        payload.model_dump(mode="json")
        if isinstance(payload, BaseModel)
        else payload
    )
    temporary.write_text(
        json.dumps(content, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def run(
    root: Path,
    score_directory: Path | None = None,
    feature_directory: Path | None = None,
    output: Path | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    score_directory = (
        score_directory or root / "data/scored/ko_3201/v1"
    ).resolve()
    feature_directory = (
        feature_directory or root / "data/features/ko_3201/v1"
    ).resolve()
    output = (output or root / "data/alerts/ko_3201/v1").resolve()
    scores_path = score_directory / "hourly_anomaly_scores.csv"
    features_path = feature_directory / "feature_table.csv"
    require_passing_report(
        root / "artifacts/models/ko_3201/v1/technical_validation.json",
        "model technical validation",
    )
    require_passing_report(
        feature_directory / "feature_quality_report.json",
        "feature quality report",
    )
    if not scores_path.is_file() or not features_path.is_file():
        raise FileNotFoundError("Missing scored timeline or feature table")

    policy, policy_path = load_policy(root)
    scores = pd.read_csv(scores_path)
    features = pd.read_csv(features_path)
    result = build_alert_decisions(scores, features, policy)
    evaluation = evaluate_alert_decisions(
        result.hourly_decisions,
        scores,
        result.events,
        policy,
    )
    manifest = build_manifest(
        policy,
        policy_path,
        scores_path,
        features_path,
        result,
    )
    validation = build_validation_report(policy, result, len(scores))
    write_frame(output / "hourly_alert_decisions.csv", result.hourly_decisions)
    write_models(output / "alerts.csv", list(result.events), AlertEvent)
    write_models(
        output / "alert_state_transitions.csv",
        list(result.transitions),
        AlertStateTransition,
    )
    write_json(output / "alert_evaluation.json", evaluation)
    write_json(output / "alert_manifest.json", manifest)
    write_json(output / "technical_validation.json", validation)
    return {
        "status": validation.status,
        "policy_id": policy.policy_id,
        "hourly_decision_rows": len(result.hourly_decisions),
        "alert_events": len(result.events),
        "state_transitions": len(result.transitions),
        "first_detection_by_state": evaluation["first_detection_by_state"],
        "lead_time_hours_by_state": evaluation["lead_time_hours_by_state"],
        "normal_user_alert_hours": evaluation["normal_user_alert_hours"],
        "recovery_user_alert_hours": evaluation["recovery_user_alert_hours"],
    }


def main() -> None:
    args = parse_args()
    report = run(args.root, args.scores, args.features, args.output)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
