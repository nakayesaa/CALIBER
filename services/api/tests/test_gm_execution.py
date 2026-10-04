"""Management authorization creates separate, recipient-scoped execution work."""

from datetime import date, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from services.api.app.main import create_app
from services.api.app.schemas.actions import ActionPlan, ActionStatus
from services.api.app.services.actions.workflow import update_plan_status
from services.api.tests.test_backend_api import client as client
from services.api.tests.test_case_packets import PATH as CASES
from services.api.tests.test_case_packets import reports
from services.api.tests.test_equipment_operator import OP, SV, response
from services.api.tests.test_gm_review import GM, PATH
from services.api.tests.test_production_delegation import OPERATOR


def submitted(client):
    equipment, production = reports(client)
    packet = client.post(CASES, headers=SV, json={'request_id': str(uuid4()), 'equipment_report_id': equipment['report_id'], 'production_report_id': production['report_id']}).json()
    for scope, report in [('equipment', equipment), ('production', production)]:
        client.post(f"/api/v1/workflow/{scope}-reports/{report['report_id']}/send", headers=SV, json={'expected_revision': 0})
    client.post(f"/api/v1/workflow/equipment-reports/{equipment['report_id']}/response", headers=OP, json=response())
    client.post(f"/api/v1/workflow/production-reports/{production['report_id']}/response", headers=OPERATOR, json={'expected_revision': 1, 'decision': 'APPROVED', 'attested': True, 'note': 'Source checked'})
    return client.post(f"{CASES}/{packet['case_id']}/submit-to-gm", headers=SV, json={'recipient_id': 'demo-manager', 'note': 'Authorize proposed work'}).json()


def test_management_assignment_is_gated_and_separate(client):
    report = submitted(client)
    source = next(action for plan in report['action_plans'] for action in plan['actions'] if action['owner_role'] == 'Rotating Equipment Engineer')
    url = f"{PATH}/{report['report_id']}"
    assignment = {'person_id': 'demo-maintenance', 'due_date': (date.today()+timedelta(days=2)).isoformat(), 'expected_status': 'PROPOSED', 'expected_revision': 0, 'note': 'Perform approved corrective work'}
    endpoint = f"{url}/actions/{source['action_id']}/assignment"
    assert client.post(endpoint, headers=SV, json=assignment).status_code == 409
    client.post(f'{url}/decision', headers=GM, json={'expected_revision': 0, 'decision': 'APPROVED', 'note': 'Work authorized'})
    frozen = client.get(url, headers=SV).json()
    assert client.post(endpoint, headers=GM, json=assignment).status_code == 403
    assert client.post(endpoint, headers=SV, json={**assignment, 'person_id': 'demo-operator'}).status_code == 409
    assert client.post(endpoint, headers=SV, json={**assignment, 'due_date': '2020-01-01'}).status_code == 409
    saved = client.post(endpoint, headers=SV, json=assignment)
    assert saved.status_code == 200, saved.text
    plan = saved.json()
    assert all(item['action_type'] != 'CONTAINMENT' for item in plan['actions'])
    parsed = ActionPlan.model_validate(plan)
    completed = parsed.model_copy(update={'actions': [item.model_copy(update={'status': ActionStatus.CLOSED}) for item in parsed.actions]})
    assert update_plan_status(completed).status == ActionStatus.CLOSED
    action = next(item for item in plan['actions'] if item['source_action_id'] == source['action_id'])
    assert plan['gm_report_id'] == report['report_id']
    assert action['status'] == 'APPROVED' and action['assignment']['person_id'] == 'demo-maintenance'
    assert not action['completion'] and not action['requirements']
    assert client.post(endpoint, headers=SV, json=assignment).status_code == 409
    assert client.get(url, headers=SV).json() == frozen
    inbox = client.get('/api/v1/workflow/assigned-actions', headers={'X-Caliber-Person': 'demo-maintenance'}).json()
    assert [item['action_id'] for item in inbox[0]['actions']] == [action['action_id']]
    assert client.get('/api/v1/workflow/assigned-actions', headers=OP).json() == []
    other_supervisor = {'X-Caliber-Person': 'demo-reviewer'}
    assert client.post(endpoint, headers=other_supervisor, json=assignment).status_code == 403
    engineer = {'X-Caliber-Person': 'demo-maintenance'}
    action_url = f"/api/v1/actions/{action['action_id']}"
    accepted = client.post(f'{action_url}/assignment/response', headers=engineer, json={'expected_revision': 1, 'decision': 'ACCEPT', 'note': 'Accepted work order'})
    assert accepted.status_code == 200, accepted.text
    assert len(accepted.json()['actions']) == 1
    action = next(item for item in accepted.json()['actions'] if item['action_id'] == action['action_id'])
    requirements = [{'requirement': key, 'disposition': 'CONFIRMED', 'reference': f'permit:{key.lower()}', 'note': 'Reviewed by assigned engineer'} for key in ['PROCEDURE', 'AUTHORIZATION', 'CHANGE_CONTROL']]
    for status, actor, evidence in [('IN_PROGRESS', engineer, {'requirements': requirements}), ('EFFECTIVENESS_REVIEW', engineer, {'reference': 'work-order:completed', 'finding': 'Completed and monitored'}), ('CLOSED', SV, {'reference': 'verification:reviewed', 'finding': 'Independent effectiveness check accepted'})]:
        changed = client.patch(f'{action_url}/status', headers=actor, json={'status': status, 'note': 'Execution evidence recorded', 'expected_revision': action['revision'], 'evidence': evidence})
        assert changed.status_code == 200, changed.text
        action = next(item for item in changed.json()['actions'] if item['action_id'] == action['action_id'])
    assert action['status'] == 'CLOSED'
    restarted = TestClient(create_app(client.app.state.backend.root))
    assert restarted.get(f'{url}/actions', headers=SV).json()[0]['actions'] == changed.json()['actions']
    assert client.get(url, headers=SV).json() == frozen


def test_returned_report_cannot_authorize_work(client):
    report = submitted(client)
    url = f"{PATH}/{report['report_id']}"
    client.post(f'{url}/decision', headers=GM, json={'expected_revision': 0, 'decision': 'RETURNED', 'note': 'More evidence required'})
    action = report['action_plans'][0]['actions'][0]
    saved = client.post(f"{url}/actions/{action['action_id']}/assignment", headers=SV, json={'person_id': 'demo-maintenance', 'due_date': (date.today()+timedelta(days=2)).isoformat(), 'expected_status': 'PROPOSED', 'note': 'Cannot execute returned case'})
    assert saved.status_code == 409
    assert client.get(f'{url}/actions', headers=SV).json() == []
