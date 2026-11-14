import json
import time

import pytest
from fastapi.testclient import TestClient

from backend.app import main
from backend.app.schemas import Incident
from backend.app.tools import dispatch
from backend.tests.fakes import FakeProvider


def wait_complete(client: TestClient, incident_id: str):
    for _ in range(400):
        body = client.get(f'/api/incidents/{incident_id}').json()
        if body['messages'][-1]['state'] != 'processing':
            return body
        time.sleep(0.01)
    raise AssertionError('BMW investigation did not complete in time')


@pytest.fixture
def setup(monkeypatch):
    main.incidents.clear()
    main.media.clear()
    main.requests.clear()
    main.locks.clear()
    fake = FakeProvider()
    monkeypatch.setattr(main, 'get_provider', lambda: fake)
    with TestClient(main.app) as client:
        yield client, fake


def sim_headers(client: TestClient):
    return {'If-Match': str(client.get('/api/simulator').json()['revision'])}


def test_bmw_mode_vehicle_defaults_and_mode_filtering(setup):
    client, _ = setup
    general = client.post('/api/incidents', json={}).json()
    bmw = client.post('/api/incidents', json={'mode': 'bmw_g20'}).json()
    assert general['mode'] == 'general'
    assert general['vehicle'] == {'make': '', 'model': '', 'year': None}
    assert bmw['mode'] == 'bmw_g20'
    assert bmw['vehicle'] == {'make': 'BMW', 'model': '330i (G20)', 'year': None}
    assert len(client.get('/api/incidents').json()) == 2
    assert [c['id'] for c in client.get('/api/incidents?mode=bmw_g20').json()] == [bmw['id']]
    assert [c['id'] for c in client.get('/api/incidents?mode=general').json()] == [general['id']]


def test_bmw_mode_shares_simulated_sensors_and_adds_g20_catalog_caveats(setup, monkeypatch):
    client, _ = setup
    client.post('/api/simulator/scenario', json={'scenario': 'tire_pressure_loss'}, headers=sim_headers(client))
    general_id = client.post('/api/incidents', json={}).json()['id']
    bmw_id = client.post('/api/incidents', json={'mode': 'bmw_g20'}).json()['id']

    class SensorRecallProvider(FakeProvider):
        async def create(self, **body):
            self.inputs.append(body)
            if len(self.inputs) == 1:
                return {
                    'id': 'bmw-step-1',
                    'steps': [
                        {'type': 'function_call', 'id': 'c1', 'name': 'read_vehicle_sensors', 'arguments': {'sensor_names': ['tpms_per_wheel_pressure_bar']}},
                        {'type': 'function_call', 'id': 'c2', 'name': 'search_bmw_knowledge', 'arguments': {'query': 'TPMS pressure target G20', 'domain': 'tire'}},
                        {'type': 'function_call', 'id': 'c3', 'name': 'check_bmw_recalls', 'arguments': {'query': 'starter relay', 'model_year': 2021, 'market': 'US'}},
                    ],
                }
            return {
                'id': 'bmw-step-2',
                'status': 'completed',
                'steps': [{'type': 'model_output', 'content': [{'type': 'text', 'text': 'The rear-left reading is below reference on your BMW 330i G20. Compare against the iDrive target and door placard while parked.'}]}],
            }

    provider = SensorRecallProvider()
    monkeypatch.setattr(main, 'get_provider', lambda: provider)

    res = client.post(
        f'/api/incidents/{bmw_id}/messages',
        data={'request_id': 'bmw-1', 'text': 'Investigate the demo yellow TPMS warning. Safely parked with cold tires.'},
    )
    assert res.status_code == 202
    bmw_done = wait_complete(client, bmw_id)
    bmw_answer = bmw_done['messages'][-1]
    assert bmw_answer['state'] == 'complete'
    assert 'BMW 330i (G20)' in provider.inputs[0]['system_instruction']

    sensor_event = next(e for e in bmw_answer['activity'] if e['tool'] == 'read_vehicle_sensors')
    assert sensor_event['result']['readings']['tpms_rear_left_bar']['value'] == 1.8
    assert 'bmw_g20_catalog' in sensor_event['result']
    assert sensor_event['result']['bmw_g20_catalog']['tpms_rear_left_bar']['bmw_signal_id'] == 'tire_pressure_rl'

    knowledge_event = next(e for e in bmw_answer['activity'] if e['tool'] == 'search_bmw_knowledge')
    assert any(card['id'].startswith('TIR-') for card in knowledge_event['result']['cards'])

    recall_event = next(e for e in bmw_answer['activity'] if e['tool'] == 'check_bmw_recalls')
    assert recall_event['result']['vin_verified'] is False
    assert recall_event['result']['recall_requires_vin_verification'] is True
    assert any(c['campaign_id'] == '25V636000' for c in recall_event['result']['observed_us_2021_330i_campaigns'])
    assert bmw_answer['citations']
    assert bmw_answer['diagnostic_inference'][0]['ranked_hypotheses'][0]['fault_id'] == 'tire_pressure_loss'

    # Verify General chat reads the exact same shared simulator revision & values
    monkeypatch.setattr(main, 'get_provider', lambda: FakeProvider())
    client.post(f'/api/incidents/{general_id}/messages', data={'request_id': 'gen-1', 'text': 'Investigate the demo yellow TPMS warning. Safely parked with cold tires.'})
    gen_done = wait_complete(client, general_id)
    assert gen_done['messages'][-1]['simulator_snapshot'] == bmw_answer['simulator_snapshot']


def test_bmw_tools_scoped_to_bmw_mode_and_year_update_works():
    general = Incident()
    with pytest.raises(ValueError, match='Unknown tool'):
        dispatch('search_bmw_knowledge', {'query': 'cooling'}, general)
    with pytest.raises(ValueError, match='Unknown tool'):
        dispatch('check_bmw_recalls', {'query': 'starter'}, general)

    bmw = Incident(mode='bmw_g20', vehicle={'make': 'BMW', 'model': '330i (G20)', 'year': None})
    from backend.app.schemas import Message
    msg = Message(role='user', text='It is a 2021 US-market sedan.')
    bmw.messages.append(msg)
    out = dispatch('update_vehicle_profile', {'message_id': msg.id, 'make': 'BMW', 'model': '330i (G20)', 'year': 2021}, bmw)
    assert out['vehicle'] == {'make': 'BMW', 'model': '330i (G20)', 'year': 2021}
