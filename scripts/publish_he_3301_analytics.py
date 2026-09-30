#!/usr/bin/env python3
"""Publish one validated, immutable HE snapshot after model and alert gates pass."""

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.build_ko_3201_alerts import run
from services.api.app.schemas.alerts import AlertEvent, AlertStateTransition
from services.api.app.services.artifacts import KO3201ArtifactRepository
from services.api.app.services.file_io import atomic_write_json, file_sha256


def publish(root: Path) -> dict:
    model = json.loads((root / "artifacts/models/he_3301/v1/model_manifest.json").read_text())
    feature = json.loads((root / "data/features/he_3301/v1/feature_manifest.json").read_text())
    scenario = json.loads((root / "data/synthetic/he_3301/v1/scenario_manifest.json").read_text())
    checks = [
        ("Model features", model["feature_table_sha256"], root / "data/features/he_3301/v1/feature_table.csv"),
        ("Model configuration", model["model_config_sha256"], root / "data/catalog/he_3301_anomaly_model.yaml"),
        ("Fitted artifact", model["artifact_sha256"], root / "artifacts/models/he_3301/v1/model.joblib"),
        ("Model scores", model["scored_timeline_sha256"], root / "data/scored/he_3301/v1/hourly_anomaly_scores.csv"),
        ("Feature configuration", model["feature_config_sha256"], root / "data/catalog/he_3301_feature_config.yaml"),
        ("Feature manifest", model["feature_manifest_sha256"], root / "data/features/he_3301/v1/feature_manifest.json"),
        ("Scenario features", feature["input_sha256"], root / "data/synthetic/he_3301/v1/hourly_scenario.csv"),
        ("Source anchors", scenario["source_sha256"], root / "data/normalized/he_3301/equipment.json"),
    ]
    for label, checksum, path in checks:
        if checksum != file_sha256(path):
            raise ValueError(f"{label} changed; rebuild HE artifacts before promotion")
    result = run(root, asset="he_3301")
    if result["status"] != "PASS":
        raise ValueError("HE alert validation failed; active analytics unchanged")
    sources = {
        "hourly_scenario.csv": "data/synthetic/he_3301/v1/hourly_scenario.csv",
        "scenario_manifest.json": "data/synthetic/he_3301/v1/scenario_manifest.json",
        "hourly_anomaly_scores.csv": "data/scored/he_3301/v1/hourly_anomaly_scores.csv",
        "hourly_alert_decisions.csv": "data/alerts/he_3301/v1/hourly_alert_decisions.csv",
        "feature_config.yaml": "data/catalog/he_3301_feature_config.yaml",
        "model_manifest.json": "artifacts/models/he_3301/v1/model_manifest.json",
        "evaluation_report.json": "data/scored/he_3301/v1/evaluation_report.json",
        "alert_policy.yaml": "data/catalog/he_3301_alert_policy.yaml",
        "model.joblib": "artifacts/models/he_3301/v1/model.joblib",
    }
    evaluation = json.loads((root / sources["evaluation_report.json"]).read_text())
    if evaluation["status"] != "PASS":
        raise ValueError("HE model evaluation failed; active analytics unchanged")
    canonical_hash = file_sha256(root / "data/normalized/he_3301/equipment.json")
    checksums = {name: file_sha256(root / path) for name, path in sources.items()}
    import hashlib

    version = hashlib.sha256(
        json.dumps([canonical_hash, checksums], sort_keys=True).encode()
    ).hexdigest()[:16]
    directory = root / "data/alerts/he_3301/bundles" / version
    directory.mkdir(parents=True, exist_ok=True)
    for name, path in sources.items():
        shutil.copy2(root / path, directory / name)
    repository = KO3201ArtifactRepository(root)
    alerts = repository._read_csv("data/alerts/he_3301/v1/alerts.csv")
    transitions = repository._read_csv("data/alerts/he_3301/v1/alert_state_transitions.csv")
    events = []
    mapped_ids = {}
    for record in alerts.to_dict("records"):
        record["breached_signals"] = json.loads(record["breached_signals"])
        for field in ["closed_at", "closure_reason"]:
            if str(record[field]) == "nan":
                record[field] = None
        alert = AlertEvent.model_validate(record)
        mapped_ids[alert.alert_id] = f"alert-asset-he-3301-{version}-{len(events) + 1:04d}"
        events.append(alert.model_copy(update={"alert_id": mapped_ids[alert.alert_id]}))
    if not events:
        raise ValueError("No HE model investigation event; active analytics unchanged")
    changes = [
        AlertStateTransition.model_validate({**record, "alert_id": mapped_ids[record["alert_id"]]})
        for record in transitions.to_dict("records")
    ]
    atomic_write_json(
        directory / "events.json",
        {
            "events": [item.model_dump() for item in events],
            "transitions": [item.model_dump() for item in changes],
        },
    )
    checksums["events.json"] = file_sha256(directory / "events.json")
    atomic_write_json(
        directory / "manifest.json",
        {
            "version": version,
            "model_id": events[0].model_id,
            "row_count": 4368,
            "canonical_sha256": canonical_hash,
            "files": checksums,
        },
    )
    atomic_write_json(
        root / "data/alerts/he_3301/active.json",
        {
            "version": version,
            "manifest_sha256": file_sha256(directory / "manifest.json"),
        },
    )
    return {"status": "PASS", "version": version, "alert_events": len(events)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    print(json.dumps(publish(parser.parse_args().root.resolve()), indent=2))
