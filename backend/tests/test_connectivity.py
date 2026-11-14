import asyncio
import copy
import json
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from google.genai import types

from backend.app import main, provider
from backend.app.config import RESTRICTED_MODEL, WEB_TOOLS
from backend.app.schemas import Incident
from backend.app.tools import dispatch, tools_for
from backend.tests.fakes import FakeProvider


def completed(text='I checked the available readings. The cause remains unconfirmed.'):
    return {'id': 'reply', 'status': 'completed', 'steps': [{'type': 'model_output', 'content': [{'type': 'text', 'text': text}]}]}


@pytest.fixture
def setup(monkeypatch):
    main.incidents.clear()
    main.media.clear()
    main.requests.clear()
    main.locks.clear()
    fake = FakeProvider([completed()])
    fake.model = RESTRICTED_MODEL
    fake.name = 'gemma'
    monkeypatch.setattr(main, 'get_restricted_provider', lambda: fake)
    def forbidden():
        raise AssertionError('Standard Gemini provider must never be constructed in restricted mode')
    monkeypatch.setattr(main, 'get_provider', forbidden)
    with TestClient(main.app) as client:
        yield client, fake


def headers(client):
    return {'If-Match': str(client.get('/api/simulator').json()['revision'])}


def toggle(client, blocked):
    response = client.patch('/api/simulator/connectivity', json={'internet_blocked': blocked}, headers=headers(client))
    assert response.status_code == 200
    return response.json()


def wait(client, incident_id):
    for _ in range(400):
        answer = client.get(f'/api/incidents/{incident_id}').json()['messages'][-1]
        if answer['state'] != 'processing':
            return answer
        time.sleep(.01)
    raise AssertionError('Investigation did not finish')


@pytest.mark.parametrize('mode', ['general', 'bmw_g20'])
def test_restricted_mode_uses_only_gemma_and_local_tools(setup, mode):
    client, fake = setup
    client.post('/api/simulator/scenario', json={'scenario': 'tire_pressure_loss'}, headers=headers(client))
    toggle(client, True)
    incident_id = client.post('/api/incidents', json={'mode': mode}).json()['id']
    response = client.post(f'/api/incidents/{incident_id}/messages', data={'request_id': 'check', 'text': 'Check the available readings and recorded history.', 'sensor_check': 'true'})
    assert response.status_code == 202
    answer = wait(client, incident_id)
    assert answer['state'] == 'complete'
    assert answer['model'] == RESTRICTED_MODEL and answer['provider'] == 'gemma'
    assert answer['simulator_snapshot']['internet_blocked'] is True
    assert any(e['tool'] == 'gemma' for e in answer['activity'])
    assert any(e['tool'] == 'read_vehicle_sensors' for e in answer['activity'])
    specs = fake.inputs[0]['tools']
    assert all(t['type'] == 'function' and t['name'] not in WEB_TOOLS for t in specs)
    assert {'read_vehicle_sensors', 'read_sensor_history'} <= {t['name'] for t in specs}
    assert ('search_bmw_knowledge' in {t['name'] for t in specs}) == (mode == 'bmw_g20')
    assert 'Use Google Search to verify' not in fake.inputs[0]['system_instruction']
    health = client.get('/api/health').json()
    assert health['model'] == RESTRICTED_MODEL
    assert health['web_search_allowed'] is False and health['api_connection_allowed'] is True


def test_connectivity_requires_revision_preserves_sensors_and_survives_scenario_reset(setup):
    client, _ = setup
    before = client.get('/api/simulator').json()
    assert client.patch('/api/simulator/connectivity', json={'internet_blocked': True}).status_code == 428
    after = toggle(client, True)
    assert after['channels'] == before['channels']
    assert after['enabled'] is False  # Connectivity is independent of sensor enablement.
    assert after['revision'] == before['revision'] + 1
    assert client.patch('/api/simulator/connectivity', json={'internet_blocked': False}, headers={'If-Match': str(before['revision'])}).status_code == 409
    assert client.patch('/api/simulator/connectivity', json={'internet_blocked': 'false'}, headers=headers(client)).status_code == 422
    scenario = client.post('/api/simulator/scenario', json={'scenario': 'battery_drop'}, headers=headers(client)).json()
    assert scenario['internet_blocked'] is True
    assert client.post('/api/simulator/reset', headers=headers(client)).json()['internet_blocked'] is True
    restored = toggle(client, False)
    assert restored['internet_blocked'] is False
    health = client.get('/api/health').json()
    assert health['provider'] == 'gemini' and health['web_search_allowed'] is True


@pytest.mark.parametrize('name', sorted(WEB_TOOLS))
def test_web_dispatch_blocked_even_if_model_requests_it(name):
    incident = Incident()
    incident.sensor_simulation.internet_blocked = True
    with pytest.raises(ValueError, match='Web access is blocked'):
        dispatch(name, {'query': 'please search'}, incident)


def test_wrong_model_fails_without_fallback(setup):
    client, fake = setup
    fake.model = 'gemini-other'
    toggle(client, True)
    incident_id = client.post('/api/incidents', json={}).json()['id']
    client.post(f'/api/incidents/{incident_id}/messages', data={'request_id': 'wrong', 'text': 'Hello'})
    answer = wait(client, incident_id)
    assert answer['state'] == 'failed'
    assert 'Gemma 4 26B strictly' in answer['error']
    assert not fake.inputs


def test_forbidden_provider_web_operation_fails_without_presenting_web_results(setup):
    client, fake = setup
    fake.responses = [{'id': 'bad', 'status': 'completed', 'steps': [{'type': 'google_search_call', 'arguments': {'queries': ['bad']}}, *completed()['steps']]}]
    toggle(client, True)
    incident_id = client.post('/api/incidents', json={}).json()['id']
    client.post(f'/api/incidents/{incident_id}/messages', data={'request_id': 'bad', 'text': 'Hello'})
    answer = wait(client, incident_id)
    assert answer['state'] == 'failed' and 'Web access is blocked' in answer['error']
    assert not answer['citations'] and not answer['search_suggestions']


def test_retry_keeps_restricted_model_after_global_mode_changes(setup):
    client, fake = setup
    toggle(client, True)
    fake.fail = True
    incident_id = client.post('/api/incidents', json={}).json()['id']
    client.post(f'/api/incidents/{incident_id}/messages', data={'request_id': 'retry', 'text': 'Hello'})
    failed = wait(client, incident_id)
    assert failed['state'] == 'failed'
    toggle(client, False)
    fake.fail = False
    client.post(f"/api/incidents/{incident_id}/messages/{failed['id']}/retry")
    answer = wait(client, incident_id)
    assert answer['state'] == 'complete' and answer['model'] == RESTRICTED_MODEL
    assert answer['simulator_snapshot']['internet_blocked'] is True
    assert all(t['type'] == 'function' for t in fake.inputs[-1]['tools'])


def sdk_provider(monkeypatch, responses):
    calls = []
    async def generate_content(**body):
        types.GenerateContentConfig.model_validate(body['config'])
        for content in body['contents']:
            types.Content.model_validate(content)
        calls.append(copy.deepcopy(body))
        raw = responses.pop(0)
        return SimpleNamespace(model_dump=lambda **kwargs: raw)
    client = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content)))
    monkeypatch.setattr(provider, 'settings', lambda: ('test-key', 'gemini-anything'))
    monkeypatch.setattr(provider.genai, 'Client', lambda **kwargs: client)
    return provider.GemmaProvider(), calls


def test_gemma_adapter_pins_generate_content_model_and_continues_local_tool_calls(monkeypatch):
    raw_model = {'role': 'model', 'parts': [{'function_call': {'name': 'get_vehicle_profile', 'args': {}}, 'thought_signature': 'c2ln'}]}
    gemma, calls = sdk_provider(monkeypatch, [
        {'model_version': RESTRICTED_MODEL, 'candidates': [{'finish_reason': 'STOP', 'content': raw_model}]},
        {'model_version': RESTRICTED_MODEL, 'candidates': [{'finish_reason': 'STOP', 'content': {'role': 'model', 'parts': [{'text': 'Please describe the warning.'}]}}]},
    ])
    incident = Incident()
    incident.sensor_simulation.internet_blocked = True
    body = {'input': [{'type': 'user_input', 'content': [{'type': 'text', 'text': 'Hello'}]}], 'system_instruction': 'No web access.', 'tools': tools_for(incident)}
    first = asyncio.run(gemma.create(**body))
    call = first['steps'][0]
    body['input'] = [{'type': 'function_result', 'name': call['name'], 'call_id': call['id'], 'result': [{'type': 'text', 'text': json.dumps({'vehicle': {}})}]}]
    second = asyncio.run(gemma.create(**body, previous_interaction_id=first['id']))
    assert second['steps'][0]['content'][0]['text'] == 'Please describe the warning.'
    assert all(c['model'] == RESTRICTED_MODEL for c in calls)
    assert calls[1]['contents'][1] == raw_model
    assert calls[1]['contents'][2]['parts'][0]['function_response'] == {'name': 'get_vehicle_profile', 'response': {'vehicle': {}}}
    assert calls[0]['config']['automatic_function_calling'] == {'disable': True}
    assert set(calls[0]['config']['tools'][0]) == {'function_declarations'}


@pytest.mark.parametrize('tool', [{'type': 'google_search'}, {'type': 'url_context'}, {'type': 'function', 'name': 'web_search'}])
def test_gemma_adapter_rejects_web_tools_before_any_api_call(monkeypatch, tool):
    gemma, calls = sdk_provider(monkeypatch, [])
    with pytest.raises(ValueError, match='Web access is blocked'):
        asyncio.run(gemma.create(input=[], system_instruction='', tools=[tool]))
    assert not calls


def test_gemma_adapter_rejects_response_from_a_different_model(monkeypatch):
    gemma, _ = sdk_provider(monkeypatch, [{'model_version': 'gemini-other', 'candidates': []}])
    with pytest.raises(ValueError, match='Gemma 4 26B strictly'):
        asyncio.run(gemma.create(input=[], system_instruction='', tools=[]))
