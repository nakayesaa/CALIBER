"""Promoted analytics must remain source-bound and must not cross-load KO artifacts."""

import json
from pathlib import Path

import pandas as pd
import pytest

from services.api.app.services.data.he_3301 import load_he_3301
from services.api.app.services.file_io import atomic_write_json, file_sha256
from services.api.app.services.he_analytics import (
    active_snapshot,
    hourly_analytics,
    snapshot_alerts,
)


def snapshot(root: Path):
    source = root / "data/normalized/he_3301/equipment.json"
    atomic_write_json(source, {"source": "he"})
    directory = root / "data/alerts/he_3301/bundles/test-v1"
    atomic_write_json(directory / "events.json", {"events": []})
    atomic_write_json(directory / "manifest.json", {
        "canonical_sha256": file_sha256(source),
        "files": {"events.json": file_sha256(directory / "events.json")},
    })
    atomic_write_json(root / "data/alerts/he_3301/active.json", {
        "version": "test-v1", "manifest_sha256": file_sha256(directory / "manifest.json"),
    })
    return directory, source


def test_absent_model_has_explicit_engineering_fallback(tmp_path):
    assert active_snapshot(tmp_path) is None


def test_changed_promoted_artifact_is_rejected(tmp_path):
    directory, source = snapshot(tmp_path)
    assert active_snapshot(tmp_path) == directory
    atomic_write_json(directory / "events.json", {"events": ["modified"]})
    with pytest.raises(ValueError, match="artifact changed"):
        active_snapshot(tmp_path)
    directory, source = snapshot(tmp_path)
    atomic_write_json(source, {"source": "different-version"})
    with pytest.raises(ValueError, match="source changed"):
        active_snapshot(tmp_path)


def test_pointer_cannot_select_another_asset_directory(tmp_path):
    snapshot(tmp_path)
    atomic_write_json(tmp_path / "data/alerts/he_3301/active.json", {
        "version": "../../ko_3201/v1", "manifest_sha256": "unused",
    })
    with pytest.raises(ValueError, match="Invalid HE analytics version"):
        active_snapshot(tmp_path)


def test_retired_snapshot_rejects_changed_evidence_without_using_current_source(tmp_path):
    directory, source = snapshot(tmp_path)
    atomic_write_json(source, {"source": "new-canonical"})
    assert snapshot_alerts(directory) == []
    atomic_write_json(directory / "events.json", {"events": ["changed"]})
    with pytest.raises(ValueError, match="artifact changed"):
        snapshot_alerts(directory)


def test_hourly_read_model_keeps_null_scores_and_separate_recovery(tmp_path):
    root = Path(__file__).parents[3]
    bundle = load_he_3301(root)
    directory, source = snapshot(tmp_path)
    timestamps = ["2026-05-23T00:00:00+07:00", "2026-05-23T01:00:00+07:00", "2026-05-23T02:00:00+07:00"]
    condition = [signal for signal in bundle.signals if signal.direction]
    pd.DataFrame({
        "timestamp": timestamps, "scenario_phase": "STABLE_RECOVERY",
        **{signal.key: [signal.points[-1].value] * 3 for signal in condition},
    }).to_csv(directory / "hourly_scenario.csv", index=False)
    pd.DataFrame({
        "timestamp": timestamps, "anomaly_score": [None, 40.0, 60.0], "anomaly_threshold": 50.0,
    }).to_csv(directory / "hourly_anomaly_scores.csv", index=False)
    pd.DataFrame({
        "timestamp": timestamps, "decision_state": ["SUPPRESSED", "NORMAL", "WATCH"],
        "decision_reason": "Contract fixture", "breached_signals": "",
    }).to_csv(directory / "hourly_alert_decisions.csv", index=False)
    atomic_write_json(directory / "events.json", {
        "events": [bundle.alert.model_dump(mode="json")], "transitions": [],
    })
    manifest = json.loads((directory / "manifest.json").read_text())
    manifest.update(version="test-v1", model_id="he-contract-fixture", row_count=3,
                    files={path.name: file_sha256(path) for path in directory.iterdir() if path.name != "manifest.json"})
    atomic_write_json(directory / "manifest.json", manifest)
    atomic_write_json(tmp_path / "data/alerts/he_3301/active.json", {
        "version": "test-v1", "manifest_sha256": file_sha256(directory / "manifest.json"),
    })
    analytics = hourly_analytics(tmp_path, bundle)
    assert analytics.assessments[0].score is None
    assert {signal.key for signal in analytics.signals} == {signal.key for signal in condition}
    assert analytics.recovery.eligible_hours == 2
    assert analytics.recovery.anomalous_hours == 1
    assert analytics.recovery.anomaly_rate == 0.5
