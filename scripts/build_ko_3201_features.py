#!/usr/bin/env python3
"""Build validated model-independent features for the KO-3201 scenario."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml
from pydantic import BaseModel


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from services.api.app.schemas.features import (  # noqa: E402
    FeatureManifest,
    FeaturePipelineConfig,
    FeatureQualityCheck,
    FeatureQualityReport,
)
from services.api.app.services.analytics.feature_pipeline import (  # noqa: E402
    ELIGIBILITY_COLUMNS,
    FeatureBuildResult,
    build_features,
    validate_hourly_input,
)


GENERATED_AT = datetime.fromisoformat("2026-09-10T00:00:00+07:00")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Hourly scenario CSV (default: data/synthetic/ko_3201/v1/hourly_scenario.csv)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Feature output directory (default: data/features/ko_3201/v1)",
    )
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_config(root: Path) -> FeaturePipelineConfig:
    path = root / "data/catalog/ko_3201_feature_config.yaml"
    return FeaturePipelineConfig.model_validate(
        yaml.safe_load(path.read_text(encoding="utf-8"))
    )


def load_scenario_manifest(input_path: Path) -> dict[str, Any]:
    path = input_path.parent / "scenario_manifest.json"
    if not path.is_file():
        raise FileNotFoundError(f"Missing scenario manifest: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def model_to_row(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(mode="json")


def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"Refusing to write an empty CSV: {path}")
    temporary = path.with_suffix(path.suffix + ".tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def write_frame(path: Path, frame: pd.DataFrame) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = frame.copy()
    if pd.api.types.is_datetime64_any_dtype(serialized["timestamp"]):
        serialized["timestamp"] = serialized["timestamp"].map(
            lambda value: value.isoformat()
        )
    serialized.to_csv(temporary, index=False)
    temporary.replace(path)


def write_json(path: Path, model: BaseModel) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary.write_text(
        json.dumps(model.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def build_manifest(
    config: FeaturePipelineConfig,
    result: FeatureBuildResult,
    input_path: Path,
) -> FeatureManifest:
    table = result.feature_table
    return FeatureManifest(
        pipeline_id=config.pipeline_id,
        pipeline_version=config.pipeline_version,
        input_scenario_id=config.input_scenario_id,
        input_sha256=sha256_file(input_path),
        generated_at=GENERATED_AT,
        row_count=len(table),
        complete_row_count=int(table["feature_complete"].sum()),
        training_row_count=int(table["model_training_eligible"].sum()),
        scoring_row_count=int(table["model_scoring_eligible"].sum()),
        lookback_hours=result.lookback_hours,
        model_feature_columns=result.model_feature_columns,
        explanation_feature_columns=result.explanation_feature_columns,
        metadata_columns=config.output.metadata_columns,
        label_columns=config.output.label_columns,
        eligibility_columns=ELIGIBILITY_COLUMNS,
        leakage_policy=(
            "All temporal features use the current row and prior rows only. "
            "Labels and eligibility fields are excluded from the model feature list."
        ),
        training_policy=(
            "Rows must be complete, source-eligible, in an approved operating mode, "
            "running, and below every configured condition alarm limit."
        ),
    )


def build_quality_report(
    config: FeaturePipelineConfig,
    result: FeatureBuildResult,
    expected_rows: int,
) -> FeatureQualityReport:
    table = result.feature_table
    complete = table.loc[table["feature_complete"], result.model_feature_columns]
    excluded = {
        *config.output.metadata_columns,
        *config.output.label_columns,
        *ELIGIBILITY_COLUMNS,
    }
    phase_counts = table["scenario_phase"].value_counts().to_dict()
    expected_model_features = sum(
        int(signal.include_raw)
        + len(signal.delta_periods)
        + 2 * len(signal.rolling_windows)
        + len(signal.trend_periods)
        for signal in config.condition_signals.values()
    ) + sum(
        int(signal.include_raw)
        + len(signal.delta_periods)
        + len(signal.rolling_windows)
        for signal in config.process_signals.values()
    )
    expected_explanation_features = len(config.condition_signals) + 2
    checks = [
        FeatureQualityCheck(
            name="output_row_count",
            status="PASS" if len(table) == expected_rows else "FAIL",
            actual=len(table),
        ),
        FeatureQualityCheck(
            name="model_feature_count",
            status=(
                "PASS"
                if len(result.model_feature_columns) == expected_model_features
                else "FAIL"
            ),
            actual=len(result.model_feature_columns),
        ),
        FeatureQualityCheck(
            name="explanation_feature_count",
            status=(
                "PASS"
                if len(result.explanation_feature_columns)
                == expected_explanation_features
                else "FAIL"
            ),
            actual=len(result.explanation_feature_columns),
        ),
        FeatureQualityCheck(
            name="complete_values_are_finite",
            status=(
                "PASS"
                if np.isfinite(complete.to_numpy(dtype=float)).all()
                else "FAIL"
            ),
            actual=bool(np.isfinite(complete.to_numpy(dtype=float)).all()),
        ),
        FeatureQualityCheck(
            name="labels_excluded_from_model_inputs",
            status=(
                "PASS"
                if not excluded.intersection(result.model_feature_columns)
                else "FAIL"
            ),
            actual=not bool(excluded.intersection(result.model_feature_columns)),
        ),
        FeatureQualityCheck(
            name="all_scenario_phases_retained",
            status="PASS" if len(phase_counts) == 9 else "FAIL",
            actual={str(key): int(value) for key, value in phase_counts.items()},
        ),
    ]
    status = "PASS" if all(check.status == "PASS" for check in checks) else "FAIL"
    if status != "PASS":
        failed = [check.name for check in checks if check.status == "FAIL"]
        raise RuntimeError("Feature quality checks failed: " + ", ".join(failed))
    return FeatureQualityReport(
        status=status,
        pipeline_id=config.pipeline_id,
        checks=checks,
    )


def run(
    root: Path,
    input_path: Path | None = None,
    output: Path | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    input_path = (
        input_path or root / "data/synthetic/ko_3201/v1/hourly_scenario.csv"
    ).resolve()
    output = (output or root / "data/features/ko_3201/v1").resolve()
    if not input_path.is_file():
        raise FileNotFoundError(f"Missing scenario input: {input_path}. Run make scenario.")

    config = load_config(root)
    scenario_manifest = load_scenario_manifest(input_path)
    if scenario_manifest["scenario_id"] != config.input_scenario_id:
        raise ValueError("Feature config and scenario manifest IDs do not match")
    raw = pd.read_csv(input_path)
    validated = validate_hourly_input(raw, config, scenario_manifest["timestamp_count"])
    result = build_features(validated, config)
    manifest = build_manifest(config, result, input_path)
    quality_report = build_quality_report(
        config,
        result,
        expected_rows=scenario_manifest["timestamp_count"],
    )

    complete = result.feature_table["feature_complete"]
    training = result.feature_table["model_training_eligible"]
    matrix_columns = ["timestamp", *result.model_feature_columns]
    write_frame(output / "feature_table.csv", result.feature_table)
    write_frame(
        output / "model_matrix.csv",
        result.feature_table.loc[complete, matrix_columns],
    )
    write_frame(
        output / "training_matrix.csv",
        result.feature_table.loc[training, matrix_columns],
    )
    write_rows(output / "feature_catalog.csv", [model_to_row(row) for row in result.catalog])
    write_json(output / "feature_manifest.json", manifest)
    write_json(output / "feature_quality_report.json", quality_report)
    return {
        "status": quality_report.status,
        "row_count": manifest.row_count,
        "complete_row_count": manifest.complete_row_count,
        "training_row_count": manifest.training_row_count,
        "scoring_row_count": manifest.scoring_row_count,
        "model_feature_count": len(manifest.model_feature_columns),
        "explanation_feature_count": len(manifest.explanation_feature_columns),
    }


def main() -> None:
    args = parse_args()
    report = run(args.root, args.input, args.output)
    print(
        "KO-3201 features built: "
        f"{report['row_count']:,} rows, "
        f"{report['model_feature_count']} model features, "
        f"{report['training_row_count']:,} training rows."
    )


if __name__ == "__main__":
    main()
