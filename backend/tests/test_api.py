import pytest
from fastapi.testclient import TestClient
from backend.app import main


@pytest.fixture
def client():
    main.incidents.clear()
    main.media.clear()
    with TestClient(main.app) as client:
        yield client


def chat(client):
    return client.post('/api/incidents', json={}).json()['id']


def test_conversation_and_safety_persist(client):
    id = chat(client)
    response = client.post(f'/api/incidents/{id}/messages', data={'text': 'My brake pedal feels soft and the red brake warning stays on.'})
    assert response.status_code == 200
    assert response.json()['safety'] == main.SAFETY
    follow = client.post(f'/api/incidents/{id}/messages', data={'text': 'Can I drive home?'}).json()
    assert len(follow['messages']) == 4
    assert follow['messages'][-1]['text'] == main.SAFETY
    assert client.get(f'/api/incidents/{id}').json() == follow


def test_upload_roundtrip_and_media_only_disclosure(client):
    id = chat(client)
    result = client.post(f'/api/incidents/{id}/messages', files=[('files', ('voice.webm', b'demo-bytes', 'audio/webm'))])
    assert result.status_code == 200
    body = result.json()
    attachment = body['messages'][0]['attachments'][0]
    assert attachment['kind'] == 'audio'
    assert client.get(attachment['url']).content == b'demo-bytes'
    assert 'does not analyze or transcribe' in body['messages'][1]['text']


def test_validation_is_atomic(client, monkeypatch):
    monkeypatch.setattr(main, 'MAX_FILE', 10)
    monkeypatch.setattr(main, 'MAX_TOTAL', 15)
    id = chat(client)
    url = f'/api/incidents/{id}/messages'
    assert client.post(url).status_code == 422
    assert client.post(url, files={'files': ('x.html', b'x', 'text/html')}).status_code == 415
    assert client.post(url, files={'files': ('x.png', b'', 'image/png')}).status_code == 422
    assert client.post(url, files={'files': ('x.png', b'x' * 11, 'image/png')}).status_code == 413
    assert client.post(url, files=[('files', ('x.png', b'x'*8, 'image/png'))]*2).status_code == 413
    assert client.post(url, files=[('files', ('x.png', b'x', 'image/png'))]*6).status_code == 422
    assert not main.media
    assert not client.get(f'/api/incidents/{id}').json()['messages']


def test_routes_and_limits(client):
    assert client.get('/api/health').json()['mode'] == 'mock'
    assert client.get('/api/vehicles').json()[0]['source'] == 'demo_fixture'
    assert client.post('/api/incidents', json={'vehicle_id': 'unknown'}).status_code == 422
    assert client.get('/api/incidents/missing').status_code == 404
    assert client.get('/api/attachments/missing').status_code == 404
    id = chat(client)
    assert client.post(f'/api/incidents/{id}/messages', data={'text': 'x'*10001}).status_code == 422


@pytest.mark.parametrize('text,phrase', [('yellow tire warning', 'tire-pressure'), ('engine rattle', 'engine noise'), ('hello', 'when it started')])
def test_mock_scenarios(client, text, phrase):
    id = chat(client)
    response = client.post(f'/api/incidents/{id}/messages', data={'text': text}).json()
    assert phrase in response['messages'][-1]['text']
    assert all('Simulated' in event for event in response['messages'][-1]['activity'])
