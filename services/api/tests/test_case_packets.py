"""Case readiness follows the two bound report versions, not client flags."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from services.api.app.main import create_app
from services.api.app.services.file_io import atomic_write_json
from services.api.app.services.scope_verification import load_report, report_path
from services.api.tests.test_backend_api import client as client
from services.api.tests.test_equipment_operator import OP, SV, payload, response
from services.api.tests.test_production_delegation import OPERATOR, draft_payload

PATH = '/api/v1/workflow/case-packets'


def reports(client):
    equipment = client.post('/api/v1/workflow/equipment-reports', headers=SV, json=payload()).json()
    production = client.post('/api/v1/workflow/production-reports', headers=SV, json=draft_payload()).json()
    return equipment, production


def test_bound_packet_readiness_and_persistence(client: TestClient):
    equipment, production = reports(client)
    data = {'request_id': str(uuid4()), 'equipment_report_id': equipment['report_id'], 'production_report_id': production['report_id']}
    created = client.post(PATH, headers=SV, json=data)
    assert created.status_code == 201, created.text
    packet = created.json()
    url = f"{PATH}/{packet['case_id']}"
    assert packet['verified_scopes'] == 0
    assert not packet['can_escalate']
    assert client.post(f'{url}/readiness', headers=SV).status_code == 409
    assert client.post(PATH, headers=SV, json=data).json()['case_id'] == packet['case_id']
    assert client.get(url, headers=OP).status_code == 403
    assert client.get(url, headers={'X-Caliber-Person': 'demo-reviewer'}).status_code == 403
    for scope, report in [('equipment', equipment), ('production', production)]:
        client.post(f"/api/v1/workflow/{scope}-reports/{report['report_id']}/send", headers=SV, json={'expected_revision': 0})
    client.post(f"/api/v1/workflow/equipment-reports/{equipment['report_id']}/response", headers=OP, json=response())
    waiting = client.get(url, headers=SV).json()
    assert waiting['verified_scopes'] == 1
    assert 'Production' in waiting['summary']
    assert client.post(f'{url}/readiness', headers=SV).status_code == 409
    client.post(f"/api/v1/workflow/production-reports/{production['report_id']}/response", headers=OPERATOR, json={'expected_revision': 1, 'decision': 'APPROVED', 'attested': True, 'note': 'Verified against shift records'})
    ready = client.post(f'{url}/readiness', headers=SV)
    assert ready.status_code == 200, ready.text
    assert ready.json()['state'] == 'READY_FOR_GM'
    assert ready.json()['can_escalate']
    restarted = TestClient(create_app(client.app.state.backend.root))
    assert restarted.get(url, headers=SV).json()['verified_scopes'] == 2
    assert {item['report_id'] for item in ready.json()['scopes']} == {equipment['report_id'], production['report_id']}
    path = report_path(client.app.state.backend.root, equipment['report_id'])
    backup = path.with_suffix('.backup')
    path.rename(backup)
    assert client.get(url, headers=SV).json()['state'] == 'UNAVAILABLE'
    assert client.post(f'{url}/readiness', headers=SV).status_code == 409
    backup.rename(path)
    source = load_report(client.app.state.backend.root, production['report_id'])
    path = report_path(client.app.state.backend.root, production['report_id'])
    atomic_write_json(path, source.model_copy(update={'version': '02'}))
    assert client.get(url, headers=SV).json()['state'] == 'UNAVAILABLE'
    assert client.post(f'{url}/readiness', headers=SV).status_code == 409
    atomic_write_json(path, source)


@pytest.mark.parametrize(('decision', 'result', 'state'), [('CHANGES_REQUESTED', 'ISSUE', 'NEEDS_CORRECTION'), ('UNABLE_TO_VALIDATE', 'MISSING', 'EVIDENCE_REQUIRED')])
def test_correction_and_invalid_packet_cannot_pass(client: TestClient, decision, result, state):
    equipment, production = reports(client)
    data = {'request_id': str(uuid4()), 'equipment_report_id': equipment['report_id'], 'production_report_id': production['report_id']}
    assert client.post(PATH, headers=OP, json=data).status_code == 403
    assert client.post(PATH, headers=SV, json={**data, 'can_escalate': True}).status_code == 422
    source = load_report(client.app.state.backend.root, production['report_id'])
    path = report_path(client.app.state.backend.root, production['report_id'])
    atomic_write_json(path, source.model_copy(update={'alert_id': 'different-alert'}))
    assert client.post(PATH, headers=SV, json=data).status_code == 409
    atomic_write_json(path, source)
    created = client.post(PATH, headers=SV, json=data)
    assert created.status_code == 201, created.text
    url = f"{PATH}/{created.json()['case_id']}"
    client.post(f"/api/v1/workflow/equipment-reports/{equipment['report_id']}/send", headers=SV, json={'expected_revision': 0})
    client.post(f"/api/v1/workflow/equipment-reports/{equipment['report_id']}/response", headers=OP, json=response(decision, result))
    blocked = client.get(url, headers=SV).json()
    assert blocked['state'] == state
    assert blocked['scopes'][0]['note'] == 'Equipment evidence checked'
    assert client.post(f'{url}/readiness', headers=SV).status_code == 409
    assert client.post(PATH, headers=SV, json={**data, 'request_id': str(uuid4())}).status_code == 409
    assert client.post(PATH, headers=SV, json={**data, 'equipment_report_id': production['report_id']}).status_code in {404, 409}
