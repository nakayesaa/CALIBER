"""Persisted production handoff, recipient isolation and immutable evidence."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from services.api.app.main import create_app
from services.api.app.security import WriteAuthorizer, WriteMode
from services.api.tests.test_backend_api import client as client

SUPERVISOR = {"X-Caliber-Person": "demo-supervisor"}
OPERATOR = {"X-Caliber-Person": "demo-production-zcu"}
PATH = "/api/v1/workflow/production-reports"


def draft_payload(**changes: object) -> dict:
    return {
        "request_id": str(uuid4()),
        "asset_id": "asset-ko-3201",
        "recipient_id": "demo-production-zcu",
        "due_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        "note": "Check feed, offline interval and the reference against shift records.",
        **changes,
    }


def test_report_handoff_and_response_survive_restart(client: TestClient) -> None:
    payload = draft_payload()
    draft = client.post(PATH, json=payload, headers=SUPERVISOR)
    assert draft.status_code == 201, draft.text
    report = draft.json()
    assert report["status"] == "DRAFT"
    assert report["impact"]["offline_hours"] == 32
    assert report["points"]
    assert set(report["points"][0]) == {
        "timestamp", "feed_rate_tph", "plant_rate_tph", "run_status", "operating_mode",
    }
    assert client.post(PATH, json=payload, headers=SUPERVISOR).json()["report_id"] == report["report_id"]
    assert client.get(PATH, headers=OPERATOR).json() == []
    url = f'{PATH}/{report["report_id"]}'
    assert client.get(url, headers=OPERATOR).status_code == 403
    sent = client.post(f"{url}/send", json={"expected_revision": 0}, headers=SUPERVISOR)
    assert sent.status_code == 200, sent.text
    assert sent.json()["status"] == "SENT"
    assert sent.json()["points"] == report["points"]
    assert client.post(f"{url}/send", json={"expected_revision": 0}, headers=SUPERVISOR).status_code == 409
    assert len(client.get(PATH, headers=OPERATOR).json()) == 1
    decision = {"decision": "APPROVED", "note": "Checked against shift records", "attested": False, "expected_revision": 1}
    assert client.post(f"{url}/response", json=decision, headers=OPERATOR).status_code == 409
    approved = client.post(f"{url}/response", json={**decision, "attested": True}, headers=OPERATOR)
    assert approved.status_code == 200, approved.text
    assert approved.json()["review"]["actor_id"] == "demo-production-zcu"
    assert client.post(f"{url}/response", json={**decision, "attested": True}, headers=OPERATOR).status_code == 409
    restarted = TestClient(create_app(client.app.state.backend.root))
    saved = restarted.get(url, headers=SUPERVISOR).json()
    assert saved["status"] == "APPROVED"
    assert saved["impact"] == report["impact"]
    assert saved["points"] == report["points"]


def test_roles_recipient_scope_and_invalid_requests(client: TestClient) -> None:
    assert client.post(PATH, json=draft_payload()).status_code == 403
    assert client.post(PATH, json=draft_payload(recipient_id="demo-maintenance"), headers=SUPERVISOR).status_code == 409
    assert client.post(PATH, json=draft_payload(recipient_id="demo-production-arp"), headers=SUPERVISOR).status_code == 409
    assert client.post(PATH, json=draft_payload(note="   "), headers=SUPERVISOR).status_code == 422
    assert client.post(PATH, json=draft_payload(due_at="2020-01-01T00:00:00+07:00"), headers=SUPERVISOR).status_code == 409
    assert client.post(PATH, json=draft_payload(impact={"offline_hours": 0}), headers=SUPERVISOR).status_code == 422
    draft = client.post(PATH, json=draft_payload(), headers=SUPERVISOR).json()
    url = f'{PATH}/{draft["report_id"]}'
    wrong = {"X-Caliber-Person": "demo-production-arp"}
    assert client.get(PATH, headers=wrong).json() == []
    assert client.get(url, headers=wrong).status_code == 403
    assert client.post(f"{url}/send", json={"expected_revision": 0}, headers=OPERATOR).status_code == 403
    assert client.post(f"{url}/send", json={"expected_revision": 0}, headers={"X-Caliber-Person": "demo-reviewer"}).status_code == 403
    assert client.get(f"{PATH}/../source_manifest", headers=SUPERVISOR).status_code in {404, 422}


def test_corrections_missing_evidence_and_protected_reads(client: TestClient, monkeypatch) -> None:
    for decision in ("CHANGES_REQUESTED", "UNABLE_TO_VALIDATE"):
        draft = client.post(PATH, json=draft_payload(), headers=SUPERVISOR).json()
        url = f'{PATH}/{draft["report_id"]}'
        client.post(f"{url}/send", json={"expected_revision": 0}, headers=SUPERVISOR)
        data = {"decision": decision, "note": "Shift reference is missing", "expected_revision": 1}
        assert client.post(f"{url}/response", json=data, headers=SUPERVISOR).status_code == 403
        assert client.post(f"{url}/response", json=data, headers=OPERATOR).status_code == 200
        assert client.get(url, headers=SUPERVISOR).json()["status"] == decision
    monkeypatch.setenv("CALIBER_WORKFLOW_PERSON_ID", "demo-supervisor")
    token = "test-production-secret-with-at-least-32-characters"
    client.app.state.write_authorizer = WriteAuthorizer(WriteMode.BEARER, "Supervisor", token)
    assert client.get(PATH).status_code == 401
    assert client.get(url).status_code == 401
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get(url, headers=headers).status_code == 200
    assert client.get(url, headers={**headers, **OPERATOR}).status_code == 403
    client.app.state.write_authorizer = WriteAuthorizer(WriteMode.READ_ONLY, "Supervisor")
    assert client.get(url).status_code == 200
    assert client.post(PATH, json=draft_payload()).status_code == 403
