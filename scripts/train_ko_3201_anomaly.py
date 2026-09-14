#!/usr/bin/env python3
"""Train, calibrate, score, and validate the KO-3201 anomaly model."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import joblib
import numpy as np
import pandas as pd
import yaml
from pydantic import BaseModel


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from services.api.app.schemas.anomaly import (  # noqa: E402
    AnomalyModelConfig,
    ModelManifest,
    ModelValidationCheck,
    ModelValidationReport,
)
from services.api.app.services.analytics.anomaly_model import (  # noqa: E402
    AnomalyModelBundle,
    TrainingSplit,
    evaluate_scored_timeline,
    fit_anomaly_model,
    numeric_matrix,
    prepare_training_split,
    raw_anomaly_scores,
    score_feature_table,
    validate_feature_contract,
)


LOCAL_TIMEZONE = ZoneInfo("Asia/Jakarta")


@dataclass(frozen=True)
class TrainingInputs:
    config: AnomalyModelConfig
    config_path: Path
    feature_table: pd.DataFrame
    feature_manifest: dict[str, Any]
    feature_table_path: Path
    feature_columns: list[str]
    split: TrainingSplit


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument(
        "--features",
        type=Path,
        default=None,
        help="Feature directory (default: data/features/ko_3201/v1)",
    )
    parser.add_argument(
        "--artifacts",
        type=Path,
        default=None,
        help="Model artifact directory (default: artifacts/models/ko_3201/v1)",
    )
    parser.add_argument(
        "--scores",
        type=Path,
        default=None,
        help="Scored output directory (default: data/scored/ko_3201/v1)",
    )
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="Validate all inputs and print the planned split without fitting",
    )
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_model_config(root: Path) -> tuple[AnomalyModelConfig, Path]:
    path = root / "data/catalog/ko_3201_anomaly_model.yaml"
    config = AnomalyModelConfig.model_validate(
        yaml.safe_load(path.read_text(encoding="utf-8"))
    )
    return config, path


def parse_boolean(series: pd.Series, column: str) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.astype(bool)
    normalized = series.astype(str).str.strip().str.lower()
    allowed = {"true", "false", "1", "0"}
    unexpected = set(normalized) - allowed
    if unexpected:
        raise ValueError(f"Invalid boolean values in {column}: {sorted(unexpected)}")
    return normalized.isin({"true", "1"})


def prepare_inputs(root: Path, feature_directory: Path) -> TrainingInputs:
    config, config_path = load_model_config(root)
    feature_table_path = feature_directory / "feature_table.csv"
    manifest_path = feature_directory / "feature_manifest.json"
    quality_path = feature_directory / "feature_quality_report.json"
    for path in [feature_table_path, manifest_path, quality_path]:
        if not path.is_file():
            raise FileNotFoundError(f"Missing feature input: {path}. Run make features.")

    feature_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    quality_report = json.loads(quality_path.read_text(encoding="utf-8"))
    if quality_report.get("status") != "PASS":
        raise RuntimeError("Feature quality report must pass before model training")
    feature_table = pd.read_csv(feature_table_path)
    feature_table["timestamp"] = pd.to_datetime(
        feature_table["timestamp"], errors="raise"
    )
    for column in [
        "feature_complete",
        "model_training_eligible",
        "model_scoring_eligible",
    ]:
        feature_table[column] = parse_boolean(feature_table[column], column)
    if not feature_table["timestamp"].is_monotonic_increasing:
        raise ValueError("Feature table must be sorted chronologically")

    feature_columns = validate_feature_contract(
        feature_table,
        feature_manifest,
        config,
    )
    split = prepare_training_split(feature_table, config)
    numeric_matrix(split.fit, feature_columns)
    numeric_matrix(split.calibration, feature_columns)
    expected_training_rows = int(feature_manifest["training_row_count"])
    if len(split.fit) + len(split.calibration) != expected_training_rows:
        raise ValueError("Training split does not match the feature manifest")
    return TrainingInputs(
        config=config,
        config_path=config_path,
        feature_table=feature_table,
        feature_manifest=feature_manifest,
        feature_table_path=feature_table_path,
        feature_columns=feature_columns,
        split=split,
    )


def preflight_summary(inputs: TrainingInputs) -> dict[str, int | str]:
    return {
        "status": "READY",
        "model_id": inputs.config.model_id,
        "feature_rows": len(inputs.feature_table),
        "feature_count": len(inputs.feature_columns),
        "fit_rows": len(inputs.split.fit),
        "calibration_rows": len(inputs.split.calibration),
        "scoring_rows": int(inputs.feature_table["model_scoring_eligible"].sum()),
    }


def publish_bundle(
    path: Path,
    bundle: AnomalyModelBundle,
    validation_matrix: np.ndarray,
) -> tuple[str, float]:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    joblib.dump(bundle, temporary, compress=3)
    reloaded = joblib.load(temporary)
    expected = raw_anomaly_scores(
        bundle.estimator,
        bundle.scaler.transform(validation_matrix),
    )
    actual = raw_anomaly_scores(
        reloaded.estimator,
        reloaded.scaler.transform(validation_matrix),
    )
    maximum_difference = float(np.max(np.abs(expected - actual)))
    if tuple(reloaded.feature_columns) != tuple(bundle.feature_columns):
        temporary.unlink(missing_ok=True)
        raise RuntimeError("Reloaded model changed the feature order")
    if maximum_difference > 1e-12:
        temporary.unlink(missing_ok=True)
        raise RuntimeError("Reloaded model predictions do not match")
    temporary.replace(path)
    return sha256_file(path), maximum_difference


def build_scored_timeline(
    feature_table: pd.DataFrame,
    score_output: pd.DataFrame,
    model_id: str,
) -> pd.DataFrame:
    context_columns = [
        "timestamp",
        "scenario_id",
        "scenario_phase",
        "health_state",
        "operating_mode",
        "event_marker",
        "run_status",
        "feature_complete",
        "model_scoring_eligible",
    ]
    timeline = pd.concat(
        [
            feature_table[context_columns].reset_index(drop=True),
            score_output.reset_index(drop=True),
        ],
        axis=1,
    )
    timeline.insert(1, "model_id", model_id)
    numeric_columns = [
        "raw_anomaly_score",
        "anomaly_score",
        "anomaly_threshold",
        "top_driver_1_score",
        "top_driver_2_score",
        "top_driver_3_score",
        *[
            column
            for column in timeline
            if column.startswith("model_impact__")
            or column.startswith("contribution_pct__")
        ],
    ]
    for column in numeric_columns:
        if column in timeline:
            timeline[column] = timeline[column].round(6)
    return timeline


def build_validation_report(
    inputs: TrainingInputs,
    scored_timeline: pd.DataFrame,
    reload_difference: float,
) -> ModelValidationReport:
    scored = scored_timeline.loc[scored_timeline["score_status"] == "SCORED"]
    expected_scored = int(inputs.feature_manifest["scoring_row_count"])
    finite_scores = np.isfinite(scored["anomaly_score"].to_numpy(dtype=float)).all()
    checks = [
        ModelValidationCheck(
            name="feature_count_matches_contract",
            status=(
                "PASS"
                if len(inputs.feature_columns) == inputs.config.expected_feature_count
                else "FAIL"
            ),
            actual=len(inputs.feature_columns),
        ),
        ModelValidationCheck(
            name="chronological_split",
            status="PASS",
            actual=(
                f"{len(inputs.split.fit)} fit rows followed by "
                f"{len(inputs.split.calibration)} calibration rows"
            ),
        ),
        ModelValidationCheck(
            name="scored_row_count",
            status="PASS" if len(scored) == expected_scored else "FAIL",
            actual=len(scored),
        ),
        ModelValidationCheck(
            name="scored_values_are_finite",
            status="PASS" if finite_scores else "FAIL",
            actual=bool(finite_scores),
        ),
        ModelValidationCheck(
            name="artifact_reload_prediction_difference",
            status="PASS" if reload_difference <= 1e-12 else "FAIL",
            actual=reload_difference,
        ),
    ]
    status = "PASS" if all(check.status == "PASS" for check in checks) else "FAIL"
    if status != "PASS":
        failed = [check.name for check in checks if check.status == "FAIL"]
        raise RuntimeError("Model validation failed: " + ", ".join(failed))
    return ModelValidationReport(
        status=status,
        model_id=inputs.config.model_id,
        checks=checks,
    )


def build_manifest(
    inputs: TrainingInputs,
    bundle: AnomalyModelBundle,
    fit_started_at: datetime,
    fit_ended_at: datetime,
    artifact_path: Path,
    artifact_sha256: str,
) -> ModelManifest:
    return ModelManifest(
        model_id=bundle.model_id,
        model_version=bundle.model_version,
        estimator="sklearn.ensemble.IsolationForest",
        scaler="sklearn.preprocessing.RobustScaler",
        input_pipeline_id=bundle.feature_pipeline_id,
        feature_table_sha256=sha256_file(inputs.feature_table_path),
        model_config_sha256=sha256_file(inputs.config_path),
        trained_at=bundle.trained_at,
        fit_started_at=fit_started_at,
        fit_ended_at=fit_ended_at,
        fit_rows=len(inputs.split.fit),
        calibration_rows=len(inputs.split.calibration),
        scoring_rows=int(inputs.feature_table["model_scoring_eligible"].sum()),
        feature_count=len(bundle.feature_columns),
        feature_columns=list(bundle.feature_columns),
        raw_anomaly_threshold=bundle.score_transform.threshold_raw_score,
        normalized_anomaly_threshold=bundle.score_transform.threshold_normalized_score,
        score_transform=bundle.score_transform.as_dict(),
        driver_profiles=[profile.as_dict() for profile in bundle.driver_profiles],
        artifact_file=artifact_path.name,
        artifact_sha256=artifact_sha256,
    )


def write_frame(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    serialized = frame.copy()
    serialized["timestamp"] = serialized["timestamp"].map(
        lambda value: pd.Timestamp(value).isoformat()
    )
    serialized.to_csv(temporary, index=False)
    temporary.replace(path)


def write_json(path: Path, payload: BaseModel | dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    if isinstance(payload, BaseModel):
        content = payload.model_dump(mode="json")
    else:
        content = payload
    temporary.write_text(
        json.dumps(content, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def train(
    inputs: TrainingInputs,
    artifact_directory: Path,
    score_directory: Path,
) -> dict[str, Any]:
    fit_started_at = datetime.now(LOCAL_TIMEZONE)
    bundle, diagnostics = fit_anomaly_model(
        inputs.split,
        inputs.feature_columns,
        inputs.config,
        trained_at=fit_started_at,
    )
    score_output = score_feature_table(
        inputs.feature_table,
        bundle,
        maximum_drivers=inputs.config.drivers.maximum_drivers,
    )
    scored_timeline = build_scored_timeline(
        inputs.feature_table,
        score_output,
        inputs.config.model_id,
    )
    evaluation = evaluate_scored_timeline(scored_timeline, inputs.config)
    evaluation["training"] = diagnostics.as_dict()
    fit_ended_at = datetime.now(LOCAL_TIMEZONE)

    artifact_path = artifact_directory / "model.joblib"
    validation_matrix = numeric_matrix(
        inputs.split.calibration,
        inputs.feature_columns,
    )
    artifact_sha256, reload_difference = publish_bundle(
        artifact_path,
        bundle,
        validation_matrix,
    )
    validation = build_validation_report(inputs, scored_timeline, reload_difference)
    manifest = build_manifest(
        inputs,
        bundle,
        fit_started_at,
        fit_ended_at,
        artifact_path,
        artifact_sha256,
    )
    write_frame(score_directory / "hourly_anomaly_scores.csv", scored_timeline)
    write_json(score_directory / "evaluation_report.json", evaluation)
    write_json(artifact_directory / "model_manifest.json", manifest)
    write_json(artifact_directory / "technical_validation.json", validation)
    return {
        "status": validation.status,
        "model_id": inputs.config.model_id,
        "fit_rows": len(inputs.split.fit),
        "calibration_rows": len(inputs.split.calibration),
        "scoring_rows": int(inputs.feature_table["model_scoring_eligible"].sum()),
        "first_warning": evaluation["first_degradation_anomaly_at"],
        "warning_lead_time_hours": evaluation["warning_lead_time_hours"],
        "artifact": str(artifact_path),
    }


def main() -> None:
    args = parse_args()
    root = args.root.resolve()
    feature_directory = (
        args.features or root / "data/features/ko_3201/v1"
    ).resolve()
    artifact_directory = (
        args.artifacts or root / "artifacts/models/ko_3201/v1"
    ).resolve()
    score_directory = (
        args.scores or root / "data/scored/ko_3201/v1"
    ).resolve()
    inputs = prepare_inputs(root, feature_directory)
    if args.preflight:
        print(json.dumps(preflight_summary(inputs), indent=2))
        return
    report = train(inputs, artifact_directory, score_directory)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
