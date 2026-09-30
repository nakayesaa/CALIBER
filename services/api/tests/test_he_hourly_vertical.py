"""Exercise the promoted HE model through evidence, RCA and controlled actions."""

import shutil

import joblib
import pandas as pd
import pytest

from scripts.build_ko_3201_alerts import load_policy
from scripts.build_ko_3201_features import load_config
from scripts.train_ko_3201_anomaly import build_scored_timeline
from services.api.app.services.alerts.decision_engine import build_alert_decisions
from services.api.app.services.analytics.anomaly_model import score_feature_table
from services.api.app.services.analytics.feature_pipeline import build_features
from services.api.tests.test_backend_api import ROOT
from services.api.tests.test_backend_api import client as client
from services.api.tests.test_he_3301_api import exercise_he_action_lifecycle
from services.api.tests.test_he_3301_api import he_client as he_client


@pytest.fixture
def hourly_client(he_client):
    source = ROOT / "data/alerts/he_3301"
    if not (source / "active.json").is_file():
        pytest.skip("Run make he-train and make he-alerts first")
    root = he_client.app.state.backend.root
    shutil.copytree(source, root / "data/alerts/he_3301")
    return he_client


def test_promoted_model_drives_dated_evidence_and_isolated_rca(hourly_client):
    client = hourly_client
    response = client.get("/api/v1/assets/asset-he-3301/investigation")
    assert response.status_code == 200, response.text
    bundle = response.json()
    analytics = bundle["analytics"]
    assert len(analytics["assessments"]) == 4368
    assert len(analytics["signals"]) == 4
    assert analytics["assessments"][0]["score"] is None
    assert "terminal normal block" in analytics["validation_note"]
    alert = analytics["alert"]
    alert_id = alert["alert_id"]
    assert analytics["version"] in alert_id
    drivers = client.get(f"/api/v1/alerts/{alert_id}/driver-analysis", params={"timestamp": alert["peak_score_at"]})
    assert drivers.status_code == 200, drivers.text
    assert len(drivers.json()["contributions"]) == 4
    assert pd.Timestamp(drivers.json()["as_of"]) == pd.Timestamp(alert["peak_score_at"])
    package = client.get(f"/api/v1/alerts/{alert_id}")
    assert package.status_code == 200, package.text
    assert package.json()["opening_snapshot"]["analytics_version"] == analytics["version"]
    assert all("he_performance:Condition History:row:" in value["source_reference"]
               for value in package.json()["opening_snapshot"]["condition_values"].values())
    generated = client.post(f"/api/v1/alerts/{alert_id}/rca", json={"mode": "prepared"})
    assert generated.status_code == 200, generated.text
    record = generated.json()
    root = client.app.state.backend.root
    assert (root / f"data/rca/he_3301/v1/records/{alert_id}.json").is_file()
    assert not (root / "data/rca/he_3301/v1/rca_record.json").exists()
    assert record["alert_id"] == alert_id
    assert client.get("/api/v1/alerts/alert-asset-he-3301-0001").status_code == 200
    assert client.get("/api/v1/alerts/alert-asset-ko-3201-0001").json()["rca"] is None


def test_model_alert_executes_full_governed_capa_lifecycle(hourly_client):
    bundle = hourly_client.get("/api/v1/assets/asset-he-3301/investigation").json()
    exercise_he_action_lifecycle(hourly_client, bundle["analytics"]["alert"]["alert_id"])


def test_fitted_model_spike_does_not_open_persistent_alert():
    model_path = ROOT / "artifacts/models/he_3301/v1/model.joblib"
    if not model_path.is_file():
        pytest.skip("Run make he-train first")
    frame = pd.read_csv(ROOT / "data/synthetic/he_3301/v1/hourly_scenario.csv")
    frame.timestamp = pd.to_datetime(frame.timestamp)
    frame = frame.loc[frame.timestamp.lt(pd.Timestamp("2026-02-26T00:00:00+07:00"))].copy()
    config = load_config(ROOT, ROOT / "data/catalog/he_3301_feature_config.yaml")
    pulse = frame.timestamp.between("2026-01-14T12:00:00+07:00", "2026-01-14T13:00:00+07:00")
    for key, signal in config.condition_signals.items():
        frame.loc[pulse, key] = (signal.alarm_limit + signal.trip_limit) / 2
    features = build_features(frame, config).feature_table
    model = joblib.load(model_path)
    scores = score_feature_table(features, model, 4)
    timeline = build_scored_timeline(features, scores, model.model_id)
    policy, _ = load_policy(ROOT, "he_3301")
    result = build_alert_decisions(timeline, features, policy)
    assert scores.loc[pulse, "is_anomaly"].any()
    assert not result.events
    assert not result.hourly_decisions.decision_state.isin(["WARNING", "HIGH", "CRITICAL"]).any()
