"""Verified scope snapshots reach only their designated GM."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from services.api.app.main import create_app
from services.api.app.schemas.coordination import Participant
from services.api.app.services import coordination
from services.api.app.services.file_io import atomic_write_json
from services.api.app.services.scope_verification import load_report, report_path
from services.api.tests.test_backend_api import client as client
from services.api.tests.test_case_packets import PATH as CASES
from services.api.tests.test_case_packets import reports
from services.api.tests.test_equipment_operator import OP, SV, response
from services.api.tests.test_production_delegation import OPERATOR

GM = {'X-Caliber-Person': 'demo-manager'}
PATH = '/api/v1/workflow/gm-reports'


@pytest.mark.parametrize('decision', ['APPROVED', 'RETURNED'])
def test_verified_submission_snapshot_decision_and_restart(client: TestClient, decision, monkeypatch):
    monkeypatch.setattr(coordination, 'PARTICIPANTS', [*coordination.PARTICIPANTS, Participant(person_id='other-manager', display_name='Other manager', role='MANAGER')])
    other_manager = {'X-Caliber-Person': 'other-manager'}
    equipment, production = reports(client)
    packet = client.post(CASES, headers=SV, json={'request_id': str(uuid4()), 'equipment_report_id': equipment['report_id'], 'production_report_id': production['report_id']}).json()
    submit_url = f"{CASES}/{packet['case_id']}/submit-to-gm"
    submission = {'recipient_id': 'demo-manager', 'note': 'Review the verified equipment and production case.'}
    assert client.post(submit_url, headers=SV, json={**submission, 'note': '  '}).status_code == 422
    assert client.post(submit_url, headers=SV, json=submission).status_code == 409
    assert client.post(submit_url, headers=OP, json=submission).status_code == 403
    assert client.post(submit_url, headers={'X-Caliber-Person': 'demo-reviewer'}, json=submission).status_code == 403
    for scope, report in [('equipment', equipment), ('production', production)]:
        client.post(f"/api/v1/workflow/{scope}-reports/{report['report_id']}/send", headers=SV, json={'expected_revision': 0})
    client.post(f"/api/v1/workflow/equipment-reports/{equipment['report_id']}/response", headers=OP, json=response())
    client.post(f"/api/v1/workflow/production-reports/{production['report_id']}/response", headers=OPERATOR, json={'expected_revision': 1, 'decision': 'APPROVED', 'attested': True, 'note': 'Checked against production log'})
    assert client.post(submit_url, headers=SV, json={**submission, 'recipient_id': 'demo-reviewer'}).status_code == 409
    submitted = client.post(submit_url, headers=SV, json=submission)
    assert submitted.status_code == 201, submitted.text
    report = submitted.json()
    assert report['status'] == 'PENDING_REVIEW'
    assert report['equipment_report']['status'] == report['production_report']['status'] == 'APPROVED'
    assert report['rca'] is not None and report['action_plans']
    url = f"{PATH}/{report['report_id']}"
    assert client.post(submit_url, headers=SV, json=submission).json() == report
    assert client.post(submit_url, headers=SV, json={**submission, 'note': 'Different report'}).status_code == 409
    for actor in (OP, {'X-Caliber-Person': 'demo-reviewer'}, other_manager):
        assert client.get(url, headers=actor).status_code == 403
        assert client.get(PATH, headers=actor).json() == []
    assert client.get(PATH, headers=GM).json() == [report]
    source = load_report(client.app.state.backend.root, equipment['report_id'])
    atomic_write_json(report_path(client.app.state.backend.root, equipment['report_id']), source.model_copy(update={'note': 'Later change'}))
    assert client.get(url, headers=GM).json()['equipment_report']['note'] == equipment['note']
    decision_data = {'expected_revision': 0, 'decision': decision, 'note': 'Reviewed verified evidence and proposed actions'}
    assert client.post(f'{url}/decision', headers=SV, json=decision_data).status_code == 403
    assert client.post(f'{url}/decision', headers=other_manager, json=decision_data).status_code == 403
    assert client.post(f'{url}/decision', headers=GM, json={**decision_data, 'note': '  '}).status_code == 422
    assert client.post(f'{url}/decision', headers=GM, json={**decision_data, 'expected_revision': 9}).status_code == 409
    saved = client.post(f'{url}/decision', headers=GM, json=decision_data)
    assert saved.status_code == 200, saved.text
    assert saved.json()['status'] == decision
    assert saved.json()['revision'] == 1
    assert saved.json()['decision']['actor_id'] == 'demo-manager'
    assert client.post(f'{url}/decision', headers=GM, json=decision_data).status_code == 409
    restarted = TestClient(create_app(client.app.state.backend.root))
    assert restarted.get(url, headers=SV).json() == saved.json()
    assert restarted.post(submit_url, headers=SV, json=submission).json() == saved.json()
