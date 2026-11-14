import json
import time

import pytest
from fastapi.testclient import TestClient

from backend.app import main
from backend.app.sensors import CATALOG
from backend.tests.fakes import FakeProvider


PROMPT = 'Check what is wrong with my car using the available sensor readings and recorded history.'


@pytest.fixture
def setup(monkeypatch):
    main.incidents.clear()
    main.media.clear()
    main.requests.clear()
    main.locks.clear()
    fake = FakeProvider(responses=[{
        'id': 'sensor-review', 'status': 'completed',
        'steps': [{'type': 'model_output', 'content': [{'type': 'text', 'text': 'The rear-left reading is 1.8 bar and has fallen in the recorded history. Compare with the vehicle reference while safely parked; the cause is unconfirmed.'}]}],
    }])
    monkeypatch.setattr(main, 'get_provider', lambda: fake)
    with TestClient(main.app) as client:
        yield client, fake


def complete(client, incident_id):
    for _ in range(400):
        incident = client.get(f'/api/incidents/{incident_id}').json()
        if incident['messages'][-1]['state'] != 'processing':
            return incident
        time.sleep(.01)
    raise AssertionError('Sensor review did not finish')


def scenario(client, name):
    revision = client.get('/api/simulator').json()['revision']
    response = client.post('/api/simulator/scenario', json={'scenario': name}, headers={'If-Match': str(revision)})
    assert response.status_code == 200
    return response.json()


def submit(client, incident_id, request_id='sensor-check'):
    return client.post(f'/api/incidents/{incident_id}/messages', data={
        'request_id': request_id, 'text': PROMPT, 'sensor_check': 'true',
    })


@pytest.mark.parametrize('mode', ['general', 'bmw_g20'])
def test_automatic_review_reads_every_channel_and_history_before_model_reply(setup, mode):
    client, fake = setup
    snapshot = scenario(client, 'tire_pressure_loss')
    incident_id = client.post('/api/incidents', json={'mode': mode}).json()['id']
    assert submit(client, incident_id).status_code == 202
    incident = complete(client, incident_id)
    answer = incident['messages'][-1]
    assert answer['state'] == 'complete'
    assert '1.8 bar' in answer['text']
    events = {e['tool']: e for e in answer['activity'] if e['initiator'] == 'backend'}
    readings = events['read_vehicle_sensors']['result']
    assert set(events['read_vehicle_sensors']['arguments']['sensor_names']) == set(CATALOG)
    assert set(readings['readings']) | set(readings['unavailable']) == set(CATALOG)
    assert readings['revision'] == snapshot['revision']
    assert readings['readings']['tpms_rear_left_bar']['value'] == 1.8
    histories = events['read_sensor_history']['result']['history']
    assert set(histories) == set(CATALOG)
    assert len(histories['tpms_rear_left_bar']['samples']) == 8
    assert histories['tpms_rear_left_bar']['samples'][0]['value'] == 2.3
    assert histories['tpms_rear_left_bar']['samples'][-1]['value'] == 1.8
    assert bool(readings.get('bmw_g20_catalog')) == (mode == 'bmw_g20')
    model_input = json.dumps(fake.inputs[0]['input'])
    assert 'Automatic sensor check results' in model_input
    assert 'tpms_rear_left_bar' in model_input and '1.8' in model_input
    assert 'First summarize noteworthy readings' in fake.inputs[0]['system_instruction']
    # Repeated transport submissions must not start another review.
    assert submit(client, incident_id).status_code == 202
    assert len(client.get(f'/api/incidents/{incident_id}').json()['messages']) == 2
    conflict = client.post(f'/api/incidents/{incident_id}/messages', data={'request_id': 'sensor-check', 'text': PROMPT})
    assert conflict.status_code == 409


def test_disabled_sensor_review_returns_status_without_calling_provider(setup):
    client, fake = setup
    incident_id = client.post('/api/incidents', json={}).json()['id']
    answer = submit(client, incident_id).json()['messages'][-1]
    assert answer['state'] == 'complete'
    assert answer['provider'] == 'sensor_status'
    assert 'not enabled' in answer['text']
    assert not fake.inputs


def test_missing_reading_stays_unknown_in_automatic_review(setup):
    client, fake = setup
    snapshot = scenario(client, 'tire_pressure_loss')
    client.patch('/api/simulator/sensors/battery_voltage_v', json={'kind': 'unavailable'}, headers={'If-Match': str(snapshot['revision'])})
    incident_id = client.post('/api/incidents', json={}).json()['id']
    submit(client, incident_id)
    answer = complete(client, incident_id)['messages'][-1]
    readings = next(e['result'] for e in answer['activity'] if e['tool'] == 'read_vehicle_sensors')
    assert readings['status'] == 'partial'
    assert 'battery_voltage_v' in readings['unavailable']
    assert 'battery_voltage_v' not in readings['readings']
    assert 'unavailable' in json.dumps(fake.inputs[0]['input'])


def test_retry_retains_automatic_review_and_original_sensor_snapshot(setup):
    client, fake = setup
    original = scenario(client, 'tire_pressure_loss')
    incident_id = client.post('/api/incidents', json={}).json()['id']
    fake.fail = True
    submit(client, incident_id)
    failed = complete(client, incident_id)['messages'][-1]
    assert failed['state'] == 'failed'
    scenario(client, 'battery_drop')
    fake.fail = False
    assert client.post(f"/api/incidents/{incident_id}/messages/{failed['id']}/retry").status_code == 202
    answer = complete(client, incident_id)['messages'][-1]
    assert answer['state'] == 'complete'
    readings = next(e['result'] for e in answer['activity'] if e['tool'] == 'read_vehicle_sensors')
    assert readings['revision'] == original['revision']
    assert readings['readings']['tpms_rear_left_bar']['value'] == 1.8
    assert 'battery_voltage_v' in readings['unavailable']
