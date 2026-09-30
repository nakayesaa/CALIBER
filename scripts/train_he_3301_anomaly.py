#!/usr/bin/env python3
"""Train an independent HE model with untouched chronological healthy holdout."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import joblib
import numpy as np
import pandas as pd
import sklearn
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.train_ko_3201_anomaly import build_scored_timeline, parse_boolean, publish_bundle
from services.api.app.schemas.anomaly import AnomalyModelConfig
from services.api.app.services.analytics.anomaly_model import (
    TrainingSplit,
    fit_anomaly_model,
    numeric_matrix,
    score_feature_table,
    validate_feature_contract,
)
from services.api.app.services.file_io import atomic_write_json, file_sha256


def healthy_split(
    frame: pd.DataFrame,
    cutoff: pd.Timestamp,
    gap: int = 24,
    minimum_fit: int = 720,
    minimum_calibration: int = 168,
    minimum_holdout: int = 168,
) -> tuple[TrainingSplit, pd.DataFrame]:
    times = frame.timestamp
    if times.duplicated().any():
        raise ValueError("Feature timestamps must be unique")
    if not times.is_monotonic_increasing:
        raise ValueError("Feature rows must be chronological")
    healthy = frame.loc[frame.model_training_eligible & (times < cutoff)]
    first, second = int(len(healthy) * 0.6), int(len(healthy) * 0.8)
    fit = healthy.iloc[:first].copy()
    if len(fit) < minimum_fit:
        raise ValueError(f"Fit partition has {len(fit)} rows, requires {minimum_fit}")
    calibration = healthy.iloc[first:second].copy()
    calibration = calibration.loc[
        calibration.timestamp > fit.timestamp.max() + pd.Timedelta(hours=gap)
    ]
    if len(calibration) < minimum_calibration:
        raise ValueError(
            f"Calibration partition has {len(calibration)} rows, requires {minimum_calibration}"
        )
    holdout = healthy.iloc[second:].copy()
    holdout = holdout.loc[holdout.timestamp > calibration.timestamp.max() + pd.Timedelta(hours=gap)]
    if len(holdout) < minimum_holdout:
        raise ValueError(f"Healthy holdout has {len(holdout)} rows, requires {minimum_holdout}")
    return TrainingSplit(fit=fit, calibration=calibration), holdout


def validate_scoring_order(expected: list[str], actual: list[str]) -> None:
    if expected != actual:
        raise ValueError("Scoring feature order does not match the fitted model")


def blocked_healthy_split(frame: pd.DataFrame, cutoff: pd.Timestamp) -> tuple[TrainingSplit, pd.DataFrame]:
    """Cover historical normal levels in fixed blocks, never random overlapping rows."""
    times = frame.timestamp
    if times.duplicated().any() or not times.is_monotonic_increasing:
        raise ValueError("Feature timestamps must be unique and chronological")
    hours = (times - times.iloc[0].normalize()) / pd.Timedelta(hours=1)
    # Third gap prevents the next cycle's fit inputs sharing the preceding holdout.
    phase = hours % (18 * 24)
    eligible = frame.model_training_eligible & times.lt(cutoff)
    fit = frame.loc[eligible & phase.lt(240)].copy()
    calibration = frame.loc[eligible & phase.ge(264) & phase.lt(324)].copy()
    holdout = frame.loc[eligible & phase.ge(348) & phase.lt(408)].copy()
    for name, part, minimum in [("Fit", fit, 720), ("Calibration", calibration, 168), ("Holdout", holdout, 168)]:
        if len(part) < minimum:
            raise ValueError(f"{name} partition has {len(part)} rows, requires {minimum}")
    return TrainingSplit(fit, calibration), holdout


def prepare_inputs(root: Path, directory: Path):
    config_path = root / "data/catalog/he_3301_anomaly_model.yaml"
    payload = yaml.safe_load(config_path.read_text())
    validation = payload.pop("validation")
    projection = payload.pop("feature_projection", None)
    config = AnomalyModelConfig.model_validate(payload)
    manifest_path = directory / "feature_manifest.json"
    table_path = directory / "feature_table.csv"
    quality_path = directory / "feature_quality_report.json"
    for path in [manifest_path, table_path, quality_path]:
        if not path.is_file():
            raise FileNotFoundError(f"Missing {path}. Run make he-features.")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("config_sha256") != file_sha256(root / "data/catalog/he_3301_feature_config.yaml"):
        raise ValueError("HE feature configuration changed; run make he-features")
    scenario_path = root / "data/synthetic/he_3301/v1/hourly_scenario.csv"
    scenario_manifest_path = scenario_path.with_name("scenario_manifest.json")
    if file_sha256(scenario_path) != manifest["input_sha256"]:
        raise ValueError("HE features reference a stale scenario; run make he-features")
    scenario_manifest = json.loads(scenario_manifest_path.read_text())
    if pd.Timestamp(scenario_manifest["healthy_cutoff"]) != pd.Timestamp(
        validation["healthy_end_exclusive"]
    ):
        raise ValueError("Model healthy cutoff differs from the scenario policy")
    if json.loads(quality_path.read_text()).get("status") != "PASS":
        raise ValueError("HE feature quality must pass before training")
    frame = pd.read_csv(table_path)
    frame["timestamp"] = pd.to_datetime(frame.timestamp, errors="raise")
    for column in ["model_training_eligible", "model_scoring_eligible", "feature_complete"]:
        frame[column] = parse_boolean(frame[column], column)
    if projection:
        manifest = {
            **manifest,
            "model_feature_columns": [
                name
                for name in manifest["model_feature_columns"]
                if any(name.endswith(suffix) for suffix in projection)
            ],
        }
    columns = validate_feature_contract(frame, manifest, config)
    strategy = validation.get("strategy", "forward_chronological")
    if strategy == "retrospective_blocked":
        split, holdout = blocked_healthy_split(frame, pd.Timestamp(validation["healthy_end_exclusive"]))
    elif strategy == "forward_chronological":
        split, holdout = healthy_split(
            frame, pd.Timestamp(validation["healthy_end_exclusive"]), validation["exclusion_gap_hours"],
            config.split.minimum_fit_rows, config.split.minimum_calibration_rows,
            validation["minimum_holdout_rows"],
        )
    else:
        raise ValueError(f"Unknown HE validation strategy: {strategy}")
    for partition in [split.fit, split.calibration, holdout]:
        numeric_matrix(partition, columns)
    return (
        config,
        validation,
        frame,
        columns,
        split,
        holdout,
        {
            "feature_table_sha256": file_sha256(table_path),
            "feature_manifest_sha256": file_sha256(manifest_path),
            "model_config_sha256": file_sha256(config_path),
            "feature_config_sha256": file_sha256(root / "data/catalog/he_3301_feature_config.yaml"),
            "scenario_input_sha256": manifest["input_sha256"],
            "scenario_manifest_sha256": file_sha256(scenario_manifest_path),
            "canonical_source_sha256": scenario_manifest["source_sha256"],
            "scenario_config_sha256": scenario_manifest["config_sha256"],
            "feature_projection": projection,
            "projection_rationale": "All 28 condition inputs used"
            if not projection
            else "Explicit condition-feature projection; full 28 inputs remain inspectable in the feature table.",
        },
    )


def evaluate(frame, scores, holdout, validation):
    scored = scores.score_status.eq("SCORED")
    anomalous = scored & scores.anomaly_score.ge(scores.anomaly_threshold)
    healthy_fraction = float(anomalous.loc[holdout.index].mean())
    blocks = holdout.timestamp.diff().gt(pd.Timedelta(hours=1)).cumsum()
    terminal = holdout.loc[blocks.eq(blocks.iloc[-1])]
    cutoff = pd.Timestamp(validation["healthy_end_exclusive"])
    isolation = pd.Timestamp(validation["isolation_at"])
    degradation = scored & frame.timestamp.ge(cutoff) & frame.timestamp.lt(isolation)
    recovery = scored & frame.timestamp.ge(pd.Timestamp(validation["recovery_start"]))
    sustained = anomalous & degradation
    rolling = sustained.astype(int).rolling(validation["sustained_hours"]).sum()
    positions = rolling.index[rolling.ge(validation["sustained_hours"])]
    first = frame.loc[positions[0], "timestamp"] if len(positions) else None
    degradation_fraction = float(anomalous.loc[degradation].mean()) if degradation.any() else None
    recovery_fraction = float(anomalous.loc[recovery].mean()) if recovery.any() else None
    checks = {
        "healthy_holdout_exceedance": healthy_fraction <= validation["maximum_healthy_exceedance"],
        "sustained_before_isolation": first is not None,
        "recovery_improved": recovery_fraction is not None
        and degradation_fraction is not None
        and recovery_fraction < degradation_fraction,
        "finite_eligible_scores": bool(np.isfinite(scores.loc[scored, "anomaly_score"]).all()),
    }
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "scope": "Retrospective anchored HE hourly scenario; not independent intraday observations",
        "healthy_holdout_rows": len(holdout),
        "healthy_exceedance": healthy_fraction,
        "terminal_healthy_exceedance": float(anomalous.loc[terminal.index].mean()),
        "validation_strategy": validation.get("strategy", "forward_chronological"),
        "validation_limitations": "Retrospective normal-envelope validation; terminal block is reported separately. WATCH novelty alone cannot open an investigation.",
        "lead_time_basis": "Historical replay interval, not prospectively validated warning lead time",
        "degradation_rows": int(degradation.sum()),
        "degradation_exceedance": degradation_fraction,
        "recovery_rows": int(recovery.sum()),
        "recovery_exceedance": recovery_fraction,
        "first_sustained_model_evidence": first.isoformat() if first is not None else None,
        "model_evidence_lead_time_hours": (isolation - first).total_seconds() / 3600
        if first is not None
        else None,
    }


def train(root: Path, directory: Path, artifacts: Path, score_directory: Path, preflight=False):
    config, validation, frame, columns, split, holdout, hashes = prepare_inputs(root, directory)
    summary = {
        "status": "READY",
        "model_id": config.model_id,
        "fit_rows": len(split.fit),
        "calibration_rows": len(split.calibration),
        "healthy_holdout_rows": len(holdout),
        "feature_count": len(columns),
        "scoring_rows": int(frame.model_scoring_eligible.sum()),
    }
    if preflight:
        return summary
    bundle, diagnostics = fit_anomaly_model(
        split, columns, config, datetime.now(ZoneInfo("Asia/Jakarta"))
    )
    validate_scoring_order(columns, list(bundle.feature_columns))
    scores = score_feature_table(frame, bundle, config.drivers.maximum_drivers)
    evaluation = evaluate(frame, scores, holdout, validation)
    if evaluation["status"] != "PASS":
        atomic_write_json(
            artifacts / "rejection_report.json",
            {
                **summary,
                **hashes,
                "status": "FAIL",
                "evaluation": evaluation,
                "promotion": "REJECTED; existing model and scores unchanged",
            },
        )
        raise ValueError("HE model promotion rejected: " + json.dumps(evaluation))
    timeline = build_scored_timeline(frame, scores, config.model_id)
    if validation.get("strategy") == "retrospective_blocked":
        forward_split, forward_holdout = healthy_split(frame, pd.Timestamp(validation["healthy_end_exclusive"]))
        forward_bundle, _ = fit_anomaly_model(forward_split, columns, config, bundle.trained_at)
        forward_scores = score_feature_table(frame, forward_bundle, config.drivers.maximum_drivers)
        evaluation["forward_reference"] = evaluate(
            frame, forward_scores, forward_holdout, {**validation, "strategy": "forward_chronological"}
        )
    # Stage all candidate files before publication; active analytics is a separate promotion step.
    artifacts.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="he-model-", dir=artifacts.parent) as temporary:
        stage = Path(temporary)
        checksum, difference = publish_bundle(
            stage / "model.joblib", bundle, numeric_matrix(holdout, columns)
        )
        reloaded = joblib.load(stage / "model.joblib")
        replay = score_feature_table(frame, reloaded, config.drivers.maximum_drivers)
        if not np.allclose(
            scores.anomaly_score, replay.anomaly_score, equal_nan=True, atol=1e-12, rtol=0
        ):
            raise ValueError("Reloaded HE model changed predictions")
        timeline.to_csv(stage / "hourly_anomaly_scores.csv", index=False)
        manifest = {
            **hashes,
            "model_id": config.model_id,
            "model_version": config.model_version,
            "input_pipeline_id": config.input_pipeline_id,
            "feature_columns": columns,
            "feature_count": len(columns),
            "random_seed": config.random_seed,
            "trained_at": bundle.trained_at.isoformat(),
            "artifact_file": "model.joblib",
            "artifact_sha256": checksum,
            "scored_timeline_sha256": file_sha256(stage / "hourly_anomaly_scores.csv"),
            "normalized_anomaly_threshold": bundle.score_transform.threshold_normalized_score,
            "raw_anomaly_threshold": bundle.score_transform.threshold_raw_score,
            "score_transform": bundle.score_transform.as_dict(),
            "driver_profiles": [p.as_dict() for p in bundle.driver_profiles],
            "split": {
                name: {
                    "rows": len(part),
                    "start": part.timestamp.min().isoformat(),
                    "end": part.timestamp.max().isoformat(),
                }
                for name, part in [
                    ("fit", split.fit),
                    ("calibration", split.calibration),
                    ("healthy_holdout", holdout),
                ]
            },
            "exclusion_gap_hours": validation["exclusion_gap_hours"],
            "validation_strategy": validation.get("strategy", "forward_chronological"),
            "training": diagnostics.as_dict(),
            "versions": {
                "python": sys.version.split()[0],
                "numpy": np.__version__,
                "pandas": pd.__version__,
                "sklearn": sklearn.__version__,
                "joblib": joblib.__version__,
            },
            "reload_max_difference": difference,
            "evaluation": evaluation,
        }
        atomic_write_json(stage / "model_manifest.json", manifest)
        atomic_write_json(stage / "evaluation_report.json", evaluation)
        atomic_write_json(
            stage / "technical_validation.json",
            {
                "status": "PASS",
                "model_id": config.model_id,
                "checks": [
                    *[
                        {"name": name, "status": "PASS" if passed else "FAIL", "actual": passed}
                        for name, passed in evaluation["checks"].items()
                    ],
                    {"name": "artifact_reload_equivalence", "status": "PASS", "actual": difference},
                ],
            },
        )
        artifacts.mkdir(parents=True, exist_ok=True)
        score_directory.mkdir(parents=True, exist_ok=True)
        for name in [
            "model.joblib",
            "model_manifest.json",
            "evaluation_report.json",
            "technical_validation.json",
        ]:
            (stage / name).replace(artifacts / name)
        (stage / "hourly_anomaly_scores.csv").replace(score_directory / "hourly_anomaly_scores.csv")
        atomic_write_json(score_directory / "evaluation_report.json", evaluation)
    return {
        **summary,
        "status": "PASS",
        "evaluation": evaluation,
        "artifact": str(artifacts / "model.joblib"),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--features", type=Path)
    parser.add_argument("--artifacts", type=Path)
    parser.add_argument("--scores", type=Path)
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        result = train(
            root,
            args.features or root / "data/features/he_3301/v1",
            args.artifacts or root / "artifacts/models/he_3301/v1",
            args.scores or root / "data/scored/he_3301/v1",
            args.preflight,
        )
    except (ValueError, FileNotFoundError, KeyError) as error:
        parser.exit(1, f"HE training failed: {error}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
