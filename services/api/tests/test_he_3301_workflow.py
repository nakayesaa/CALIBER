"""Verify opening evidence, workflow policy and recovery at their source dates."""

import json
from datetime import timedelta
from pathlib import Path

import pytest

from services.api.app.services.actions.workflow import load_action_policy
from services.api.app.services.demo.prepared_he_rca import PreparedHERCAProvider
from services.api.app.services.he_repository import HE3301ArtifactRepository
from services.api.app.services.rca.case_assessment import assess_case, load_case_policy
from services.api.app.services.rca.generation import build_rca_prompts, validate_grounding

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def repository():
    required = [
        "data/normalized/he_3301/equipment.json",
        "data/normalized/ko_3201/incidents.csv",
        "data/normalized/ko_3201/incident_labels.csv",
    ]
    if any(not (ROOT / path).is_file() for path in required):
        pytest.skip("Source-backed HE and incident canonical artifacts are unavailable")
    return HE3301ArtifactRepository(ROOT)


def test_prepared_provider_uses_only_supplied_ids_and_policy_validates():
    evidence = ["alert:test", "signal:heavy_ends"]
    incidents = ["incident-test"]
    generation = (
        PreparedHERCAProvider()
        .generate(
            "", json.dumps({"allowed_evidence_ids": evidence, "allowed_incident_ids": incidents})
        )
        .generation
    )
    validate_grounding(generation, evidence, incidents)
    assert generation.hypotheses[0].category == "FOULING"
    policy = load_action_policy(ROOT / "data/catalog/he_3301_action_policy.yaml")
    assert {item.cause_category.value for item in policy.cause_policies} == {
        "FOULING",
        "UNDETERMINED",
    }
    assert load_case_policy(ROOT / "data/catalog/he_3301_rca_case.yaml").stages[0].id == "PROBABLE"


def test_opening_package_excludes_future_findings_and_anchor(repository):
    alert = repository.list_alerts()[0]
    package = repository.get_evidence_package(alert.alert_id)
    assert "he-evidence-3" not in package.model_dump_json()
    assert "hydro-jet" not in package.model_dump_json().lower()
    assert all(item.occurred_at < package.query.as_of for item in package.historical_analogues)
    assert all(item.incident_id != "incident-0004" for item in package.historical_analogues)
    assert all(
        item["timestamp"] <= alert.opened_at
        for item in package.alert_snapshot["condition_values"].values()
    )
    system, user = build_rca_prompts(package)
    generation = PreparedHERCAProvider().generate(system, user).generation
    payload = json.loads(user)
    validate_grounding(generation, payload["allowed_evidence_ids"], payload["allowed_incident_ids"])
    assert generation.hypotheses[0].category == "FOULING"


def test_inspection_and_cleaning_advance_case_only_at_available_time(repository):
    alert = repository.list_alerts()[0]
    events = repository.investigation_events(alert)
    policy = load_case_policy(ROOT / "data/catalog/he_3301_rca_case.yaml")
    inspection = next(event for event in events if event.event_id == "he-evidence-3")
    cleaning = next(event for event in events if event.event_id == "he-evidence-4")
    before = assess_case(
        alert.alert_id, inspection.occurred_at - timedelta(seconds=1), events, set(), policy
    )
    inspected = assess_case(alert.alert_id, inspection.occurred_at, events, set(), policy)
    repaired = assess_case(alert.alert_id, cleaning.occurred_at, events, set(), policy)
    assert before.stage == "PROBABLE"
    assert inspected.stage == "CAUSE_REPORTED"
    assert repaired.stage == "REPAIR_REPORTED"


def test_recovery_directions_and_review_gate(repository):
    recovery = repository.effectiveness_review()
    assert recovery.monitoring_periods == 5
    assert recovery.recovery_confirmed
    assert not recovery.closure_eligible
    assert recovery.approval_status == "PENDING_REVIEW"
    by_key = {metric.signal_key: metric for metric in recovery.metrics}
    assert by_key["tube_dp"].after < by_key["tube_dp"].before
    assert by_key["heat_duty"].after > by_key["heat_duty"].before
    assert by_key["cold_outlet_temp"].direction_of_concern == "LOW"
    policy = load_action_policy(ROOT / "data/catalog/he_3301_action_policy.yaml")
    assert {item.cause_category.value for item in policy.cause_policies} == {
        "FOULING",
        "UNDETERMINED",
    }
    rate = repository.plant_rate_daily("asset-he-3301")
    assert rate.source_rows == 720
    assert sum(point.sample_count for point in rate.points) == 720
