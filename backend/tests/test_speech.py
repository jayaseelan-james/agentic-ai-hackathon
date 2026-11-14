import asyncio
import base64
import io
import wave
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from backend.app import main, speech
from backend.app.schemas import Incident, Message
from backend.app.safety import SAFETY


def wav_bytes(seconds=0.1):
    out = io.BytesIO()
    with wave.open(out, 'wb') as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000)
        wav.writeframes(b'\x00\x00' * int(16000 * seconds))
    return out.getvalue()


class FakeSpeech:
    transcript = 'My yellow tire warning is on.'
    calls = 0
    closed = 0
    scripts = []

    async def transcribe(self, data):
        return self.transcript

    async def synthesize(self, text):
        type(self).calls += 1
        type(self).scripts.append(text)
        await asyncio.sleep(0.01)
        return wav_bytes()

    async def close(self):
        type(self).closed += 1


class FakeSummary:
    calls = []
    result = 'The warning needs investigation; the cause is unconfirmed.'

    def __init__(self, model=None):
        self.model = model

    async def create(self, **body):
        type(self).calls.append((self.model, body))
        return {'steps': [{'type': 'model_output', 'content': [{'type': 'text', 'text': self.result}]}]}

    async def close(self):
        pass


@pytest.fixture
def setup(monkeypatch):
    main.incidents.clear(); main.media.clear(); speech.cache.clear(); speech.pending.clear()
    FakeSpeech.calls = FakeSpeech.closed = 0; FakeSpeech.scripts = []
    FakeSpeech.transcript = 'My yellow tire warning is on.'
    FakeSummary.calls = []; FakeSummary.result = 'The warning needs investigation; the cause is unconfirmed.'
    monkeypatch.setattr(speech, 'SpeechProvider', FakeSpeech)
    monkeypatch.setattr(speech, 'GeminiProvider', FakeSummary)
    monkeypatch.setattr(speech, 'GemmaProvider', FakeSummary)
    message = Message(role='assistant', text='An unconfirmed tire warning needs investigation.', model='original-model')
    incident = Incident(messages=[Message(role='user', text='Yellow tire warning'), message])
    main.incidents[incident.id] = incident
    with TestClient(main.app) as client:
        yield client, incident, message


def endpoint(incident, message):
    return f'/api/incidents/{incident.id}/messages/{message.id}/speech'


def test_transcription_normalizes_and_preserves_chat(setup):
    client, incident, _ = setup
    before = incident.model_dump()
    result = client.post('/api/speech/transcriptions', files={'file': ('voice.wav', wav_bytes(), 'audio/wav')})
    assert result.status_code == 200 and result.json()['text'] == FakeSpeech.transcript
    assert incident.model_dump() == before and main.media == {}
    assert FakeSpeech.closed == 1


@pytest.mark.parametrize('data,mime,status', [
    (b'not audio', 'audio/wav', 422), (b'', 'audio/wav', 413),
    (b'not audio', 'text/plain', 415), (wav_bytes(121), 'audio/wav', 422),
])
def test_transcription_validation(setup, data, mime, status):
    client, _, _ = setup
    response = client.post('/api/speech/transcriptions', files={'file': ('voice.wav', data, mime)})
    assert response.status_code == status
    assert FakeSpeech.closed == 0


def test_file_limit_and_empty_transcript(setup, monkeypatch):
    client, _, _ = setup
    FakeSpeech.transcript = '  '
    response = client.post('/api/speech/transcriptions', files={'file': ('voice.wav', wav_bytes(), 'audio/wav')})
    assert response.status_code == 422 and 'No speech' in response.json()['detail']
    monkeypatch.setattr(main, 'MAX_FILE', 5)
    response = client.post('/api/speech/transcriptions', files={'file': ('voice.wav', b'123456', 'audio/wav')})
    assert response.status_code == 413


def test_completed_answer_and_cache(setup):
    client, incident, message = setup
    from backend.app.diagnostic_types import Question
    message.follow_up_question = Question(id='question', text='Is the warning steady?', kind='symptom')
    response = client.post(endpoint(incident, message))
    assert response.status_code == 200
    data = response.json()
    assert data['text'].endswith('Is the warning steady?') and data['text'].count('Is the warning steady?') == 1
    assert client.get(data['audio_url']).content == wav_bytes()
    assert client.post(endpoint(incident, message)).json() == data
    assert FakeSpeech.calls == 1
    assert FakeSummary.calls[0][0] == 'original-model'
    assert FakeSummary.calls[0][1]['tools'] == []
    message.text = 'The latest edited answer is different.'
    assert client.post(endpoint(incident, message)).json()['audio_url'] != data['audio_url']


@pytest.mark.parametrize('state', ['processing', 'failed'])
def test_incomplete_message_rejected(setup, state):
    client, incident, message = setup
    message.state = state
    assert client.post(endpoint(incident, message)).status_code == 409
    assert not FakeSpeech.calls


def test_missing_and_user_message_rejected(setup):
    client, incident, message = setup
    message.role = 'user'
    assert client.post(endpoint(incident, message)).status_code == 404
    assert client.post('/api/incidents/missing/messages/missing/speech').status_code == 404


def test_safety_is_verbatim_without_summary(setup):
    client, incident, message = setup
    message.provider = 'safety_rules'; message.text = SAFETY
    assert client.post(endpoint(incident, message)).json()['text'] == SAFETY
    assert FakeSummary.calls == [] and FakeSpeech.scripts == [SAFETY]


def test_unsafe_summary_does_not_change_written_answer(setup):
    client, incident, message = setup
    FakeSummary.result = 'You can safely drive.'
    original = message.model_dump()
    assert client.post(endpoint(incident, message)).status_code == 422
    assert message.model_dump() == original and not FakeSpeech.calls


def test_restricted_snapshot_selects_original_provider(setup, monkeypatch):
    client, incident, message = setup
    restricted = AsyncMock(return_value='Restricted summary.')
    class Restricted(FakeSummary):
        async def create(self, **body):
            await restricted()
            return await super().create(**body)
    monkeypatch.setattr(speech, 'GemmaProvider', Restricted)
    message.simulator_snapshot = {'internet_blocked': True}
    assert client.post(endpoint(incident, message)).status_code == 200
    restricted.assert_awaited_once()


def test_provider_error_is_recoverable_and_sanitized(setup, monkeypatch):
    client, incident, message = setup
    async def fail(self, text):
        raise RuntimeError('private provider response with credential')
    monkeypatch.setattr(FakeSpeech, 'synthesize', fail)
    result = client.post(endpoint(incident, message))
    assert result.status_code == 502 and 'private' not in result.text
    assert message.state == 'complete' and not speech.cache and not speech.pending


def test_concurrent_requests_deduplicate_and_cancelled_waiter_does_not_cancel_generation(setup):
    _, _, message = setup
    async def run():
        first = asyncio.create_task(speech.spoken_answer(message, main.media))
        await asyncio.sleep(0)
        second = asyncio.create_task(speech.spoken_answer(message, main.media))
        first.cancel()
        await asyncio.gather(first, return_exceptions=True)
        result = await second
        assert result['audio_url'] and FakeSpeech.calls == 1
    asyncio.run(run())


def test_real_adapter_deletes_upload_after_failure(monkeypatch):
    # Exercise the adapter independently of fake providers.
    async def run():
        provider = speech.SpeechProvider.__new__(speech.SpeechProvider)
        provider.upload = AsyncMock(return_value={'name': 'files/test', 'uri': 'provider://test'})
        provider.delete = AsyncMock()
        create = AsyncMock(side_effect=RuntimeError('upstream failed'))
        provider.client = SimpleNamespace(aio=SimpleNamespace(interactions=SimpleNamespace(create=create)))
        with pytest.raises(RuntimeError):
            await provider.transcribe(wav_bytes())
        provider.delete.assert_awaited_once_with('files/test')
        assert create.call_args.kwargs['generation_config']['transcription_config']['mode']['type'] == 'verbatim'
    asyncio.run(run())
