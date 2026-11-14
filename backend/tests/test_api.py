import time

import pytest
from fastapi.testclient import TestClient

from backend.app import main
from backend.app.safety import SAFETY
from backend.tests.fakes import FakeProvider


@pytest.fixture
def setup(monkeypatch):
    main.incidents.clear(); main.media.clear(); main.requests.clear(); main.locks.clear()
    fake = FakeProvider()
    monkeypatch.setattr(main, 'get_provider', lambda: fake)
    with TestClient(main.app) as client:
        yield client, fake


def chat(client):
    return client.post('/api/incidents', json={}).json()['id']


def post(client, id, text='A yellow tire warning', request_id='test', **kwargs):
    return client.post(f'/api/incidents/{id}/messages', data={'text': text, 'request_id': request_id}, **kwargs)


def finish(client, id):
    for _ in range(300):
        result = client.get(f'/api/incidents/{id}').json()
        if result['messages'][-1]['state'] != 'processing':
            return result
        time.sleep(.01)
    raise AssertionError('Background investigation did not finish')


def test_live_conversation_tools_citations_and_history(setup):
    client, fake = setup
    id = chat(client)
    assert client.patch(f'/api/incidents/{id}/vehicle', json={'make':'Toyota','model':'Corolla','year':2020}).status_code == 200
    assert post(client, id).status_code == 202
    result = finish(client, id)
    answer = result['messages'][-1]
    assert answer['state'] == 'complete'
    assert answer['citations'][0]['title'] == 'Official source'
    assert any(event['tool'] == 'get_vehicle_profile' and event['initiator'] == 'model' for event in answer['activity'])
    assert any(event['tool'] == 'google_search' for event in answer['activity'])
    post(client, id, 'What vehicle did I provide?', 'followup')
    result = finish(client, id)
    assert len(result['messages']) == 4
    history = fake.inputs[-1]['input']
    assert history[0]['type'] == 'user_input' and history[1]['type'] == 'model_output'
    assert 'Toyota' in fake.inputs[-1]['system_instruction']


def test_critical_safety_immediate_persistent_without_model(setup):
    client, fake = setup
    id = chat(client)
    result = post(client, id, 'My brake pedal feels soft and red brake warning stays on').json()
    assert result['safety'] == SAFETY
    assert result['messages'][-1]['text'] == SAFETY
    assert result['messages'][-1]['provider'] == 'safety_rules'
    assert not fake.inputs
    result = post(client, id, 'Can I drive home?', 'follow').json()
    assert result['messages'][-1]['text'] == SAFETY
    assert client.get(f'/api/incidents/{id}/report').json()['safety'] == SAFETY


def test_request_id_deduplicates_and_rejects_different_payload(setup):
    client, _ = setup
    id = chat(client)
    post(client, id)
    finish(client, id)
    assert len(post(client, id).json()['messages']) == 2
    assert post(client, id, 'Different content').status_code == 409


def test_failure_retry_reuses_messages(setup):
    client, fake = setup
    fake.fail = True
    id = chat(client)
    post(client, id)
    failed = finish(client, id)['messages'][-1]
    assert failed['state'] == 'failed'
    assert 'sensitive' not in failed['error']
    fake.fail = False
    assert client.post(f"/api/incidents/{id}/messages/{failed['id']}/retry").status_code == 202
    completed = finish(client, id)
    assert len(completed['messages']) == 2
    assert completed['messages'][-1]['state'] == 'complete'
    assert client.post(f"/api/incidents/{id}/messages/{failed['id']}/retry").status_code == 409


def test_missing_credentials_never_canned_reply(setup, monkeypatch):
    client, _ = setup
    def missing():
        raise ValueError('Gemini is not configured. Set GEMINI_API_KEY in the root .env and restart the backend.')
    monkeypatch.setattr(main, 'get_provider', missing)
    id = chat(client)
    post(client, id)
    message = finish(client, id)['messages'][-1]
    assert message['state'] == 'failed' and 'GEMINI_API_KEY' in message['error']
    assert not message['text']


def test_atomic_validation_and_routes(setup, monkeypatch):
    client, fake = setup
    monkeypatch.setattr(main, 'MAX_FILE', 10)
    monkeypatch.setattr(main, 'MAX_TOTAL', 15)
    id = chat(client)
    assert post(client, id, '').status_code == 422
    assert post(client, id, files={'files':('x.html',b'x','text/html')}).status_code == 415
    assert post(client, id, files={'files':('x.png',b'', 'image/png')}).status_code == 422
    assert post(client, id, files={'files':('x.png',b'x'*11,'image/png')}).status_code == 413
    assert post(client, id, files=[('files',('x.png',b'x'*8,'image/png'))]*2).status_code == 413
    assert post(client, id, files=[('files',('x.png',b'x','image/png'))]*6).status_code == 422
    assert not main.media and not fake.inputs
    assert client.get(f'/api/incidents/{id}').json()['messages'] == []
    assert client.get('/api/health').json()['mode'] == 'live'
    assert client.get('/api/vehicles').json() == []
    assert client.patch(f'/api/incidents/{id}/vehicle', json={'year':2200}).status_code == 422
    assert client.get('/api/incidents/missing').status_code == 404
    assert client.get('/api/attachments/missing').status_code == 404
    assert post(client, id, 'x'*10001).status_code == 422


def test_cross_origin_submission_rejected_without_provider_call(setup):
    client,fake=setup
    id=chat(client)
    assert post(client,id,headers={'Origin':'https://unrelated.example'}).status_code == 403
    assert not fake.inputs
