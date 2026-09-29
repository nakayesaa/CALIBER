"""Exercise HE routing and controlled writes without touching local case records."""

import shutil

import pytest

from services.api.tests.test_backend_api import ROOT
from services.api.tests.test_backend_api import client as client

HE = "asset-he-3301"
ALERT = "alert-asset-he-3301-0001"
SUPERVISOR = {"X-Caliber-Person": "demo-supervisor"}


@pytest.fixture
def he_client(client):
    root = client.app.state.backend.root
    source = ROOT / "data/normalized/he_3301"
    if not source.is_dir():
        pytest.skip("HE canonical artifacts are unavailable")
    shutil.copytree(source, root / "data/normalized/he_3301")
    for path in (ROOT / "data/catalog").glob("he_3301_*.yaml"):
        shutil.copy2(path, root / "data/catalog" / path.name)
    return client


def test_he_read_models_preserve_source_cadence_and_asset_scope(he_client):
    client = he_client
    assets = client.get("/api/v1/assets").json()
    assert {asset["asset_id"] for asset in assets} == {HE, "asset-ko-3201"}
    bundle = client.get(f"/api/v1/assets/{HE}/investigation").json()
    assert len(bundle["assessments"]) == 26
    assert {len(signal["points"]) for signal in bundle["signals"]} == {26, 720}
    assert bundle["reported_downtime_hours"] == 12
    assert client.get(f"/api/v1/assets/{HE}/production-rate").json()["source_rows"] == 720
    assert client.get(f"/api/v1/assets/{HE}/telemetry").status_code == 404
    assert client.get(f"/api/v1/alerts/{ALERT}/driver-analysis").status_code == 422
    assert client.get("/api/v1/assets/unknown/investigation").status_code == 404
    for key in ["he_performance", "he_production", "he_rca"]:
        assert client.get(f"/api/v1/data-sources/{key}").status_code == 200
    recovery = client.get(f"/api/v1/assets/{HE}/effectiveness").json()
    assert not recovery["closure_eligible"]
    assert recovery["approval_status"] == "PENDING_REVIEW"


def test_he_review_and_action_plan_persist_in_separate_namespace(he_client):
    client = he_client
    generated = client.post(f"/api/v1/alerts/{ALERT}/rca", json={"mode": "prepared"})
    assert generated.status_code == 200, generated.text
    rca = generated.json()
    path = f"/api/v1/alerts/{ALERT}/cross-check"
    submitted = client.post(path, json={
        "note": "Cross-checked weekly condition records",
        "references": ["he_performance:Condition History:row:12"],
        "expected_revision": 0,
    })
    assert submitted.status_code == 200, submitted.text
    verified = client.post(f"{path}/review", headers=SUPERVISOR, json={
        "decision": "VERIFIED", "note": "Source comparison reviewed", "expected_revision": 1,
    })
    assert verified.status_code == 200, verified.text
    for state in ["UNDER_REVIEW", "APPROVED"]:
        response = client.patch(f"/api/v1/rca/{rca['rca_id']}/status", headers=SUPERVISOR,
                                json={"status": state, "note": "Evidence and limitations reviewed"})
        assert response.status_code == 200, response.text
    response = client.post(f"/api/v1/rca/{rca['rca_id']}/action-plans", headers=SUPERVISOR,
                           json={"hypothesis_id": rca["generation"]["hypotheses"][0]["hypothesis_id"]})
    assert response.status_code == 200, response.text
    plan = response.json()
    assert plan["alert_id"] == ALERT
    assert plan["selected_cause_category"] == "FOULING"
    assert len(plan["actions"]) == 3
    assert client.get(f"/api/v1/action-plans/{plan['plan_id']}").status_code == 200
    action = next(item for item in plan["actions"] if item["action_type"] == "CORRECTIVE")
    action_path = f"/api/v1/actions/{action['action_id']}"

    def transition(state, person, evidence=None):
        current = client.get(f"/api/v1/action-plans/{plan['plan_id']}").json()
        record = next(item for item in current["actions"] if item["action_id"] == action["action_id"])
        payload = {"status": state, "note": "Reviewed HE execution record",
                   "expected_revision": record["revision"]}
        if evidence is not None:
            payload["evidence"] = evidence
        return client.patch(f"{action_path}/status", json=payload,
                            headers={"X-Caliber-Person": person})

    approved = transition("APPROVED", "demo-supervisor")
    assert approved.status_code == 200, approved.text
    assigned = client.post(f"{action_path}/assignment", headers=SUPERVISOR, json={
        "person_id": "demo-static", "due_date": "2026-10-01",
        "expected_status": "APPROVED", "note": "Assign static equipment review",
    })
    assert assigned.status_code == 200, assigned.text
    accepted = client.post(f"{action_path}/assignment/response",
                           headers={"X-Caliber-Person": "demo-static"}, json={
        "decision": "ACCEPT", "note": "Scope and access reviewed", "expected_revision": 1,
    })
    assert accepted.status_code == 200, accepted.text
    requirements = [{"requirement": key, "disposition": "CONFIRMED",
                     "reference": "he:approved-maintenance", "note": "Reviewed prerequisite"}
                    for key in ["PROCEDURE", "AUTHORIZATION", "CHANGE_CONTROL"]]
    started = transition("IN_PROGRESS", "demo-static", {"requirements": requirements})
    assert started.status_code == 200, started.text
    evidence = {"reference": "he:inspection-and-cleaning", "finding": "Repair acceptance documented"}
    completed = transition("EFFECTIVENESS_REVIEW", "demo-static", evidence)
    assert completed.status_code == 200, completed.text
    assert transition("CLOSED", "demo-static", evidence).status_code == 403
    closed = transition("CLOSED", "demo-reviewer", evidence)
    assert closed.status_code == 200, closed.text
    ko = client.get("/api/v1/alerts/alert-asset-ko-3201-0001").json()
    assert ko["rca"] is None and not ko["action_plans"]
    root = client.app.state.backend.root
    assert (root / "data/rca/he_3301/v1/rca_record.json").is_file()
    assert not (root / "data/rca/ko_3201/v1/rca_record.json").exists()
