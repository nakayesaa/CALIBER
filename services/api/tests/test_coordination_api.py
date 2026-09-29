"""HTTP roles, optimistic review revisions and persisted evidence references."""

from fastapi.testclient import TestClient

from services.api.app.security import WriteAuthorizer, WriteMode
from services.api.tests.test_backend_api import ALERT_ID
from services.api.tests.test_backend_api import client as client


def test_cross_check_roles_and_persistence(client: TestClient) -> None:
    path = f"/api/v1/alerts/{ALERT_ID}/cross-check"
    assert client.get(path).json()["status"] == "DRAFT"
    payload = {"note": "Reviewed pressure and oil trends", "references": ["signal:water_in_oil"], "expected_revision": 0}
    assert client.post(path, json=payload, headers={"X-Caliber-Person": "demo-maintenance"}).status_code == 403
    submitted = client.post(path, json=payload)
    assert submitted.status_code == 200
    review = {"decision": "VERIFIED", "note": "Source comparison accepted", "expected_revision": 1}
    assert client.post(f"{path}/review", json=review).status_code == 403
    verified = client.post(f"{path}/review", json=review, headers={"X-Caliber-Person": "demo-supervisor"})
    assert verified.status_code == 200
    assert client.get(path).json()["reviewed_by"] == "demo-supervisor"
    assert client.post(f"{path}/review", json=review, headers={"X-Caliber-Person": "demo-supervisor"}).status_code == 409
    assert client.post(path, json={**payload, "actor": "supervisor"}).status_code == 422
    assert client.get("/api/v1/workflow/session", headers={"X-Caliber-Person": "unknown"}).status_code == 403


def test_bearer_mode_cannot_switch_workflow_identity(client: TestClient) -> None:
    token = "test-workflow-secret-with-at-least-32-characters"
    client.app.state.write_authorizer = WriteAuthorizer(WriteMode.BEARER, "Configured user", token)
    response = client.get("/api/v1/workflow/session")
    assert response.json()["can_switch"] is False
    assert client.get("/api/v1/workflow/session", headers={"X-Caliber-Person": "demo-supervisor"}).status_code == 403
    payload = {"note": "Checked source", "references": ["source:oil"], "expected_revision": 0}
    path = f"/api/v1/alerts/{ALERT_ID}/cross-check"
    assert client.post(path, json=payload).status_code == 401
    assert client.post(path, json=payload, headers={"Authorization": f"Bearer {token}", "X-Caliber-Person": "demo-supervisor"}).status_code == 403
    assert client.post(path, json=payload, headers={"Authorization": f"Bearer {token}"}).status_code == 200
