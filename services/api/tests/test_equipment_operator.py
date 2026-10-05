"""Asset-scoped equipment monitoring and persisted evidence verification."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from services.api.app.main import create_app
from services.api.tests.test_backend_api import ALERT_ID
from services.api.tests.test_backend_api import client as client

SV = {"X-Caliber-Person": "demo-supervisor"}
OP = {"X-Caliber-Person": "demo-equipment-ko"}
OTHER = {"X-Caliber-Person": "demo-equipment-he"}
PATH = "/api/v1/workflow/equipment-reports"


def payload(**changes):
    return {
        "request_id": str(uuid4()), "asset_id": "asset-ko-3201",
        "alert_id": ALERT_ID, "recipient_id": "demo-equipment-ko",
        "due_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        "note": "Verify the oil, bearing and pressure readings against equipment records.",
        **changes,
    }


def response(decision="APPROVED", result="VERIFIED"):
    return {
        "decision": decision, "expected_revision": 1, "attested": True,
        "note": "Equipment evidence checked", "human_context": "Operating mode checked against shift log",
        "checks": [{"check": check, "result": result, "finding": "Checked against source record", "reference": "shift-log:2026-04-29"} for check in ("DATA_VALIDITY", "OPERATING_CONTEXT", "ABNORMAL_BEHAVIOUR", "SUPPORTING_EVIDENCE")],
    }


def test_monitoring_and_report_scope_persistence(client: TestClient):
    assets = client.get("/api/v1/workflow/equipment-monitoring", headers=OP)
    assert assets.status_code == 200
    assert [item["asset"]["asset_id"] for item in assets.json()] == ["asset-ko-3201"]
    assert "production_impact" not in assets.json()[0]
    evidence = client.get("/api/v1/workflow/equipment-monitoring/asset-ko-3201", headers=OP)
    assert evidence.status_code == 200, evidence.text
    assert client.get("/api/v1/workflow/equipment-monitoring/asset-ko-3201", headers=OTHER).status_code == 403
    assert client.get("/api/v1/workflow/equipment-monitoring", headers={"X-Caliber-Person": "demo-production-zcu"}).status_code == 403
    draft = client.post(PATH, json=payload(), headers=SV)
    assert draft.status_code == 201, draft.text
    report = draft.json()
    assert report["scope"] == "EQUIPMENT"
    assert report["evidence"]["alert"]["alert_id"] == ALERT_ID
    assert not {"closed_at", "status", "last_evidence_at", "duration_hours"} & report["evidence"]["alert"].keys()
    assert len(report["evidence"]["drivers"]["contributions"]) == 4
    assert all("feed_rate_tph" not in point and "plant_rate_tph" not in point for point in report["evidence"]["points"])
    assert all(event["occurred_at"] <= report["evidence"]["as_of"] for event in report["evidence"]["events"])
    cutoff = datetime.fromisoformat(report["evidence"]["as_of"])
    assert all(datetime.fromisoformat(point["timestamp"]) <= cutoff for point in report["evidence"]["points"])
    assert all(datetime.fromisoformat(item["timestamp"]) <= cutoff for item in report["evidence"]["transitions"])
    url = f'{PATH}/{report["report_id"]}'
    assert client.get(PATH, headers=OP).json() == []
    assert client.get(url, headers=OP).status_code == 403
    assert client.post(f"{url}/send", json={"expected_revision": 0}, headers=SV).status_code == 200
    assert client.post(f"{url}/response", json=response(), headers=OTHER).status_code == 403
    assert client.post(f"{url}/response", json={**response(), "checks": []}, headers=OP).status_code == 422
    assert client.post(f"{url}/response", json={**response(), "attested": False}, headers=OP).status_code == 409
    approved = client.post(f"{url}/response", json=response(), headers=OP)
    assert approved.status_code == 200, approved.text
    assert approved.json()["review"]["checks"] == response()["checks"]
    restarted = TestClient(create_app(client.app.state.backend.root))
    saved = restarted.get(url, headers=SV).json()
    assert saved["evidence"] == report["evidence"]
    assert saved["status"] == "APPROVED"
    assert client.post(f"{url}/response", json=response(), headers=OP).status_code == 409


def test_recipient_asset_and_response_checks(client: TestClient):
    assert client.post(PATH, json=payload(), headers=OP).status_code == 403
    for recipient in ("demo-equipment-he", "demo-production-zcu"):
        assert client.post(PATH, json=payload(recipient_id=recipient), headers=SV).status_code == 409
    assert client.post(PATH, json=payload(alert_id="unknown-alert"), headers=SV).status_code == 404
    report = client.post(PATH, json=payload(), headers=SV).json()
    url = f'{PATH}/{report["report_id"]}'
    client.post(f"{url}/send", json={"expected_revision": 0}, headers=SV)
    assert client.post(f"{url}/response", json=response(result="MISSING"), headers=OP).status_code == 422
    correction = response("CHANGES_REQUESTED", "ISSUE")
    assert client.post(f"{url}/response", json=correction, headers=OP).status_code == 200
    assert client.get(url, headers=SV).json()["review"]["decision"] == "CHANGES_REQUESTED"
