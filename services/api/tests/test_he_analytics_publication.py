"""Promotion rejects mixed candidate files and preserves the active pointer."""

import json

import pytest

from scripts import publish_he_3301_analytics as publisher
from services.api.app.services.file_io import atomic_write_json, file_sha256


@pytest.fixture
def candidate(tmp_path):
    files = {
        "feature_table_sha256": "data/features/he_3301/v1/feature_table.csv",
        "model_config_sha256": "data/catalog/he_3301_anomaly_model.yaml",
        "artifact_sha256": "artifacts/models/he_3301/v1/model.joblib",
        "scored_timeline_sha256": "data/scored/he_3301/v1/hourly_anomaly_scores.csv",
        "feature_config_sha256": "data/catalog/he_3301_feature_config.yaml",
    }
    for relative in [*files.values(), "data/synthetic/he_3301/v1/hourly_scenario.csv"]:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("contract-fixture")
    source = tmp_path / "data/normalized/he_3301/equipment.json"
    atomic_write_json(source, {"source": "he"})
    feature_path = tmp_path / "data/features/he_3301/v1/feature_manifest.json"
    atomic_write_json(feature_path, {
        "input_sha256": file_sha256(tmp_path / "data/synthetic/he_3301/v1/hourly_scenario.csv"),
    })
    files["feature_manifest_sha256"] = str(feature_path.relative_to(tmp_path))
    atomic_write_json(tmp_path / "data/synthetic/he_3301/v1/scenario_manifest.json", {
        "source_sha256": file_sha256(source),
    })
    atomic_write_json(tmp_path / "artifacts/models/he_3301/v1/model_manifest.json", {
        key: file_sha256(tmp_path / relative) for key, relative in files.items()
    })
    pointer = tmp_path / "data/alerts/he_3301/active.json"
    atomic_write_json(pointer, {"version": "previous-approved"})
    return tmp_path, files, pointer


@pytest.mark.parametrize("key", ["scored_timeline_sha256", "feature_config_sha256", "feature_manifest_sha256"])
def test_mixed_candidate_is_rejected_before_alert_generation(candidate, key, monkeypatch):
    root, files, pointer = candidate
    path = root / files[key]
    if path.suffix == ".json":
        atomic_write_json(path, {**json.loads(path.read_text()), "changed": True})
    else:
        path.write_text("changed")
    monkeypatch.setattr(publisher, "run", lambda *_args, **_kwargs: pytest.fail("must reject before alert generation"))
    with pytest.raises(ValueError, match="changed"):
        publisher.publish(root)
    assert json.loads(pointer.read_text())["version"] == "previous-approved"


def test_failed_alert_validation_does_not_replace_active_snapshot(candidate, monkeypatch):
    root, _, pointer = candidate
    monkeypatch.setattr(publisher, "run", lambda *_args, **_kwargs: {"status": "FAIL"})
    with pytest.raises(ValueError, match="alert validation failed"):
        publisher.publish(root)
    assert json.loads(pointer.read_text())["version"] == "previous-approved"
