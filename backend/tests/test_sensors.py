import asyncio
import copy
import json
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app import main
from backend.app.agent import investigate
from backend.app.schemas import Incident, Message, Vehicle
from backend.app.sensors import CATALOG, ReadHistory, SensorChange, change_sensor, describe, reset
from backend.app.tools import dispatch, mechanic_report
from backend.tests.fakes import FakeProvider

TIRE = 'tpms_rear_left_bar'


def enabled():
    incident = Incident(vehicle=Vehicle(make='User make', model='User model', year=2020))
    incident.sensor_simulation.enabled = True
    return incident


def query(incident, name='read_vehicle_sensors', **options):
    return dispatch(name, {'sensor_names': [TIRE], **options}, incident)


def test_stable_current_history_and_disabled_boundary():
    incident = enabled()
    before = query(incident)
    again = query(incident)
    assert before['readings'] == again['readings']
    assert before['snapshot_time'] == again['snapshot_time']
    assert before['source'] == 'simulated'
    assert query(incident, 'read_sensor_history')['history'][TIRE]['samples'][-1]['value'] == before['readings'][TIRE]['value'] == 2.3
    assert query(incident, 'read_sensor_history')['history'] == query(incident, 'read_sensor_history')['history']
    incident.sensor_simulation.enabled = False
    assert query(incident)['readings'] == {}
    assert query(incident, 'read_sensor_history')['history'] == {}
    assert dispatch('list_available_sensors', {}, incident)['available'] == []
    assert dispatch('get_vehicle_profile', {}, incident)['vehicle']['make'] == 'User make'


@pytest.mark.parametrize('preset,minutes', [('tire_slow_loss', 1440), ('tire_fast_loss', 60)])
def test_preset_changes_one_channel_with_real_timestamps_and_downsampling(preset, minutes):
    incident = enabled()
    sim = incident.sensor_simulation
    before = copy.deepcopy(sim.channels)
    change_sensor(sim, TIRE, SensorChange(kind='preset', preset=preset))
    assert all(channel == before[name] for name, channel in sim.channels.items() if name != TIRE)
    result = query(incident, 'read_sensor_history', max_points=7)['history'][TIRE]
    assert result['lookback_minutes'] == minutes and result['coverage_complete']
    samples = result['samples']
    assert len(samples) == 7 and samples[0]['value'] == 2.3 and samples[-1]['value'] == 1.8
    assert datetime.fromisoformat(samples[-1]['timestamp']) - datetime.fromisoformat(samples[0]['timestamp']) == timedelta(minutes=minutes)
    assert all(a['value'] > b['value'] for a, b in zip(samples, samples[1:]))
    assert query(incident)['readings'][TIRE]['value'] == samples[-1]['value']
    assert query(incident, 'read_sensor_history', max_points=2)['history'][TIRE]['samples'] == [samples[0], samples[-1]]
    short = query(incident, 'read_sensor_history', lookback_minutes=30)['history'][TIRE]
    assert short['lookback_minutes'] == 30
    assert all(datetime.fromisoformat(sample['timestamp']) >= datetime.fromisoformat(short['requested_start']) for sample in short['samples'])
    assert not query(incident, 'read_sensor_history', lookback_minutes=10080)['history'][TIRE]['coverage_complete']


def test_custom_trend_unavailable_restore_and_reset():
    incident = enabled()
    sim = incident.sensor_simulation
    change_sensor(sim, TIRE, SensorChange(kind='trend', start_value=2.5, end_value=1.7, duration_minutes=4320, sample_count=200))
    assert len(sim.channels[TIRE].samples) == 200
    assert len(query(incident, 'read_sensor_history')['history'][TIRE]['samples']) == 60
    previous = sim.channels[TIRE].samples[-1].model_dump()
    change_sensor(sim, TIRE, SensorChange(kind='unavailable'))
    assert sim.channels[TIRE].value is None
    assert query(incident)['readings'] == {} and query(incident)['unavailable'] == [TIRE]
    samples = query(incident, 'read_sensor_history', max_points=200)['history'][TIRE]['samples']
    assert previous in samples and samples[-1]['value'] is None
    change_sensor(sim, TIRE, SensorChange(kind='value', value=2.0))
    assert query(incident)['readings'][TIRE]['value'] == 2.0
    assert sim.channels[TIRE].samples[-2].value is None  # No fabricated recovery trend.
    change_sensor(sim, TIRE, SensorChange(kind='restore'))
    assert all(sample.value == 2.3 for sample in sim.channels[TIRE].samples)
    revision = sim.revision
    reset(sim)
    assert sim.enabled and sim.revision == revision + 1
    assert all(channel.value == CATALOG[name][2] for name, channel in sim.channels.items())


def test_precision_and_tool_results_do_not_expose_preset_labels():
    incident = enabled()
    change_sensor(incident.sensor_simulation, TIRE, SensorChange(kind='trend', start_value=2.30000001, end_value=1.80000001, duration_minutes=10080))
    values = query(incident)
    samples = query(incident, 'read_sensor_history')['history'][TIRE]['samples']
    assert samples[0]['value'] == 2.30000001
    assert samples[-1]['value'] == values['readings'][TIRE]['value'] == 1.80000001
    assert 'scenario' not in values['readings'][TIRE]
    assert 'scenario' not in query(incident, 'read_sensor_history')['history'][TIRE]


@pytest.mark.parametrize('payload', [
    {'kind': 'value', 'value': float('nan')}, {'kind': 'value', 'value': float('inf')},
    {'kind': 'value', 'value': True}, {'kind': 'value'},
    {'kind': 'trend', 'start_value': 2.3, 'end_value': 1.8, 'duration_minutes': 0},
    {'kind': 'trend', 'start_value': 2.3, 'end_value': 1.8, 'duration_minutes': 10081},
    {'kind': 'trend', 'start_value': 2.3, 'end_value': 1.8, 'duration_minutes': 1.5},
    {'kind': 'trend', 'start_value': 2.3, 'end_value': 1.8, 'duration_minutes': 1, 'sample_count': 201},
    {'kind': 'unavailable', 'value': 2}, {'kind': 'restore', 'unexpected': 'field'},
])
def test_invalid_changes(payload):
    with pytest.raises(ValidationError):
        SensorChange.model_validate(payload)


def test_validation_unknown_channels_partial_reads_and_no_cross_chat_access():
    incident = enabled()
    sim = incident.sensor_simulation
    before = describe(sim)['channels']
    for name, change in [('invented', SensorChange(kind='restore')), (TIRE, SensorChange(kind='value', value=-1)),
                         ('engine_rpm', SensorChange(kind='preset', preset='tire_slow_loss'))]:
        with pytest.raises(ValueError):
            change_sensor(sim, name, change)
    assert describe(sim)['channels'] == before and sim.revision == 0
    result = dispatch('read_vehicle_sensors', {'sensor_names': ['tpms_per_wheel_pressure_bar', 'brake_fluid_pressure']}, incident)
    assert len(result['readings']) == 4 and result['status'] == 'partial'
    assert result['unavailable'] == ['brake_fluid_pressure']
    assert not query(Incident())['readings']
    for args in [{'sensor_names': []}, {'sensor_names': [TIRE], 'incident_id': 'other'},
                 {'sensor_names': [TIRE], 'max_points': 1}, {'sensor_names': [TIRE], 'lookback_minutes': True}]:
        with pytest.raises(ValueError):
            dispatch('read_sensor_history', args, incident)
    assert ReadHistory(sensor_names=[TIRE], max_points=200, lookback_minutes=10080)


def test_actual_tool_results_continue_to_model_and_remain_in_report():
    incident = enabled()
    change_sensor(incident.sensor_simulation, TIRE, SensorChange(kind='preset', preset='tire_slow_loss'))
    user = Message(role='user', text='Investigate the gradually falling tire pressure.')
    answer = Message(role='assistant', state='processing')
    incident.messages.extend([user, answer])
    fake = FakeProvider([
        {'id': 'discover', 'steps': [{'type': 'function_call', 'id': 'a', 'name': 'list_available_sensors', 'arguments': {}}]},
        {'id': 'read', 'steps': [{'type': 'function_call', 'id': 'b', 'name': 'read_vehicle_sensors', 'arguments': {'sensor_names': [TIRE]}},
                                 {'type': 'function_call', 'id': 'c', 'name': 'read_sensor_history', 'arguments': {'sensor_names': [TIRE], 'max_points': 7}}]},
        {'id': 'done', 'status': 'completed', 'steps': [{'type': 'model_output', 'content': [{'type': 'text', 'text': 'Simulated pressure declined from 2.3 to 1.8 bar over 24 hours. The cause is unconfirmed.'}]}]},
    ])
    asyncio.run(investigate(incident, user, answer, {}, fake))
    outputs = [json.loads(part['result'][0]['text']) for part in fake.inputs[2]['input']]
    assert outputs[0]['readings'][TIRE]['value'] == 1.8
    assert outputs[1]['history'][TIRE]['samples'][0]['value'] == 2.3
    assert fake.inputs[2]['previous_interaction_id'] == 'read'
    assert '"revision": 1' in fake.inputs[0]['system_instruction']
    events = [event for event in answer.activity if event.tool.startswith('read_')]
    assert all(event.initiator == 'model' and event.result['revision'] == 1 for event in events)
    original_results = [event.model_dump() for event in events]
    reset(incident.sensor_simulation)
    assert [event.model_dump() for event in events] == original_results
    report = mechanic_report(incident)
    assert len(report['simulated_sensor_evidence']) == 2
    assert all(item['result']['source'] == 'simulated' for item in report['simulated_sensor_evidence'])


@pytest.fixture
def client(monkeypatch):
    main.incidents.clear(); main.locks.clear(); main.requests.clear()
    fake = FakeProvider()
    monkeypatch.setattr(main, 'get_provider', lambda: fake)
    with TestClient(main.app) as client:
        yield client, fake


def test_sensor_api_isolation_refresh_and_busy_rejection(client):
    client, fake = client
    id = client.post('/api/incidents', json={}).json()['id']
    other = client.post('/api/incidents', json={}).json()['id']
    base = f'/api/incidents/{id}/sensors'
    assert not client.get(base).json()['enabled']
    assert client.patch(base, json={'enabled': 'true'}).status_code == 422
    assert client.patch(base, json={'enabled': True}).status_code == 200
    result = client.patch(f'{base}/{TIRE}', json={'kind': 'preset', 'preset': 'tire_slow_loss'})
    assert result.status_code == 200
    assert client.get(base).json()['channels'][TIRE]['value'] == 1.8
    assert client.get(f'/api/incidents/{other}/sensors').json()['channels'][TIRE]['value'] == 2.3
    assert client.get(f'/api/incidents/{id}').json()['messages'] == [] and not fake.inputs
    main.incidents[id].messages.append(Message(role='assistant', state='processing'))
    for method, path, payload in [('patch', base, {'enabled': False}), ('post', f'{base}/reset', None),
                                   ('patch', f'{base}/{TIRE}', {'kind': 'restore'})]:
        assert getattr(client, method)(path, **({'json': payload} if payload else {})).status_code == 409
    main.incidents[id].messages[-1].state = 'complete'
    assert client.patch(f'{base}/unknown', json={'kind': 'restore'}).status_code == 422
    assert client.patch(f'{base}/{TIRE}', json={'kind': 'value', 'value': -1}).status_code == 422
    assert client.post(f'{base}/reset').json()['channels'][TIRE]['value'] == 2.3
    assert client.patch(base, json={'enabled': False}).status_code == 200
    assert client.patch(f'{base}/{TIRE}', json={'kind': 'restore'}).status_code == 422
    assert client.get('/api/incidents/missing/sensors').status_code == 404
