"""HE shares overview contracts without inventing absent compressor observations."""

import shutil

import pandas as pd
import pytest

from services.api.app.services.he_repository import HE3301ArtifactRepository
from services.api.app.services.production_impact import (
    calculate_production_impact,
    load_production_impact_policy,
)
from services.api.tests.test_backend_api import client as client
from services.api.tests.test_he_3301_api import HE, ROOT
from services.api.tests.test_he_3301_api import he_client as he_client


def test_he_engineering_telemetry_and_effectiveness_contract(he_client):
    response = he_client.get(f"/api/v1/assets/{HE}/telemetry?max_points=10")
    assert response.status_code == 200, response.text
    series = response.json()
    assert series["total_points"] == 26
    assert series["returned_points"] == 10
    assert series["points"][0]["tube_dp"] is not None
    assert series["points"][0]["radial_vibration_micron"] is None
    check = he_client.app.state.backend.he_repository.effectiveness_check(HE)
    assert check is not None
    assert {"tube_dp", "heat_duty", "cold_outlet_temp", "heavy_ends"} <= set(check.comparison_metrics)
    assert check.approved_by is None
    assert check.result == "INITIAL_EFFECTIVE"


def test_he_hourly_telemetry_preserves_may_only_operation_and_dated_impact(he_client):
    source = ROOT / "data/alerts/he_3301"
    if not (source / "active.json").is_file():
        pytest.skip("Promoted HE snapshot unavailable")
    root = he_client.app.state.backend.root
    shutil.copytree(source, root / "data/alerts/he_3301")
    response = he_client.get(f"/api/v1/assets/{HE}/telemetry?max_points=5000")
    assert response.status_code == 200, response.text
    series = response.json()
    assert series["total_points"] == 4368
    assert "Forward-only reference: FAIL" in series["validation_note"]
    assert series["points"][0]["anomaly_score"] is None
    assert series["points"][0]["feed_rate_tph"] is None
    may = [point for point in series["points"] if point["timestamp"].startswith("2026-05-")]
    assert len(may) == 744
    observed = [point for point in may if point["feed_rate_tph"] is not None]
    assert len(observed) == 720
    assert all(point["radial_vibration_micron"] is None for point in may)
    narrowed = he_client.get(f"/api/v1/assets/{HE}/telemetry?start=2026-05-21T00:00:00%2B07:00&end=2026-05-21T23:00:00%2B07:00&max_points=10").json()
    assert narrowed["total_points"] == 24 and narrowed["returned_points"] == 10
    impact = he_client.get(f"/api/v1/assets/{HE}/overview").json()["production_impact"]
    assert impact["offline_hours"] == 13
    assert impact["reported_downtime_hours"] == 12
    assert impact["reported_production_loss_tonnes"] == 216
    assert impact["baseline"]["method"] == "PRE_OUTAGE_OPERATING_MEDIAN"
    assert impact["baseline"]["reference_end"] < impact["window_start"]
    assert impact["estimated_shortfall_tonnes"] > 0


def test_he_baseline_responds_to_pre_outage_observations_not_recovery_data():
    repository = HE3301ArtifactRepository(ROOT)
    operation = repository._operation_frame()
    operation["operating_mode"] = "RUNNING_STEADY"
    operation["event_marker"] = None
    decisions = operation[["timestamp"]].assign(decision_state="HIGH")
    alert = repository.equipment().alert
    policy = load_production_impact_policy(ROOT / "data/catalog/he_3301_production_impact.yaml")
    original = calculate_production_impact(operation, decisions, alert, policy)
    assert original is not None
    assert pd.Timestamp(original.baseline.reference_start) > pd.Timestamp(alert.first_signal_at)
    # May ON data is an operating counterfactual, not evidence of February health.
    recovery = operation.copy()
    recovery.loc[recovery.timestamp.gt(original.window_end), "feed_rate_tph"] *= 10
    assert calculate_production_impact(recovery, decisions, alert, policy) == original
    changed = operation.copy()
    changed.loc[changed.timestamp.lt(original.window_start), "feed_rate_tph"] *= 2
    revised = calculate_production_impact(changed, decisions, alert, policy)
    assert revised.baseline.expected_feed_tph == original.baseline.expected_feed_tph * 2
    assert revised.estimated_shortfall_tonnes > original.estimated_shortfall_tonnes
