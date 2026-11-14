import asyncio
import io
import wave

import pytest
from PIL import Image

from backend.app import agent
from backend.app.agent import investigate, parse_output
from backend.app.media_processing import normalize
from backend.app.provider import public_error
from backend.app.safety import critical, unsafe_answer
from backend.app.schemas import Attachment, Incident, Message
from backend.app.tools import dispatch
from backend.tests.fakes import FakeProvider


def context():
    user = Message(role='user',text='Yellow tire warning')
    answer = Message(role='assistant',state='processing')
    incident = Incident(messages=[user, answer])
    return incident, user, answer


def test_citation_byte_offsets_and_untrusted_links():
    text, citations, _ = parse_output([{'type':'model_output','content':[{'type':'text','text':'é tire','annotations':[{'type':'url_citation','url':'https://example.com','start_index':0,'end_index':2},{'type':'url_citation','url':'javascript:alert(1)'}]}]}])
    assert text == 'é tire' and len(citations) == 1
    assert citations[0].end_index == 1


def test_unknown_tool_rejected_and_can_recover():
    incident, user, answer = context()
    fake = FakeProvider([{'id':'1','steps':[{'type':'function_call','name':'run_shell','arguments':{'cmd':'bad'},'id':'call'}]}, {'id':'2','status':'completed','steps':[{'type':'model_output','content':[{'type':'text','text':'Please provide your vehicle details.'}]}]}])
    asyncio.run(investigate(incident,user,answer,{},fake))
    assert answer.state == 'complete'
    assert any(event.status == 'failed' for event in answer.activity)
    assert 'error' in fake.inputs[1]['input'][0]['result'][0]['text']
    with pytest.raises(ValueError):
        dispatch('get_vehicle_profile', {'vehicle_id':'invented'}, incident)


@pytest.mark.parametrize('count', [1,13])
def test_model_turn_and_tool_limits(count):
    incident,user,answer=context()
    response = {'id':'1','steps':[{'type':'function_call','name':'get_vehicle_profile','arguments':{},'id':str(i)} for i in range(count)]}
    fake=FakeProvider([response]*6)
    with pytest.raises(ValueError,match='Investigation exceeded'):
        asyncio.run(investigate(incident,user,answer,{},fake))
    assert len(fake.inputs) <= 6


def test_media_bytes_used_and_files_deleted_on_failure(monkeypatch):
    incident,user,answer=context()
    user.attachments=[Attachment(id='a',kind='audio',filename='voice.webm',mime_type='audio/webm',size=5,url='/media/a')]
    async def convert(data,mime,kind):
        assert data == b'input'
        return b'converted', 'audio/wav'
    monkeypatch.setattr(agent,'normalize',convert)
    fake=FakeProvider(); fake.fail=True
    with pytest.raises(RuntimeError):
        asyncio.run(investigate(incident,user,answer,{'a':(b'input','audio/webm')},fake))
    assert fake.uploads == [(b'converted','audio/wav')]
    assert fake.deleted == ['files/1']
    assert fake.inputs[0]['input'][0]['content'][-1]['type'] == 'audio'


def test_normalization_decodes_image_and_audio_and_rejects_garbage():
    output=io.BytesIO(); Image.new('RGB',(16,16),'blue').save(output,'PNG')
    image,mime=asyncio.run(normalize(output.getvalue(),'image/png','image'))
    assert mime == 'image/jpeg' and image.startswith(b'\xff\xd8')
    audio=io.BytesIO()
    with wave.open(audio,'wb') as file:
        file.setnchannels(1);file.setsampwidth(2);file.setframerate(16000);file.writeframes(b'\0\0'*1600)
    data,mime=asyncio.run(normalize(audio.getvalue(),'audio/wav','audio'))
    assert mime == 'audio/wav' and data.startswith(b'RIFF')
    for kind in ['image','audio','video']:
        with pytest.raises(ValueError):
            asyncio.run(normalize(b'garbage','application/octet-stream',kind))


@pytest.mark.parametrize('text,expected',[('soft brake pedal',True),('red brake warning stays on',True),('brake pedal goes to the floor',True),('fuel leak',True),('steering has failed',True),('no smoke, but soft brake pedal',True),('No smoke. Yellow tire warning.',False),('How does a brake work?',False)])
def test_safety_preflight(text,expected):
    assert critical(text) is expected


def test_safety_postflight_does_not_reject_disclaimer():
    assert unsafe_answer('Your car is safe to drive.')
    assert not unsafe_answer('I cannot establish whether your car is safe to drive.')
    assert not unsafe_answer('Do not drive if it looks unsafe.')


def test_report_and_missing_vehicle_details():
    incident,user,answer=context()
    assert dispatch('get_vehicle_profile',{},incident)['missing'] == ['make','model','year']
    assert dispatch('create_mechanic_report',{},incident)['reported_symptoms'] == [user.text]
    assert 'sensitive' not in public_error(RuntimeError('sensitive key'))


def test_blocked_and_unsafe_outputs_fail_honestly():
    incident,user,answer=context()
    fake=FakeProvider([{'id':'1','status':'failed','steps':[]}])
    with pytest.raises(ValueError,match='blocked'):
        asyncio.run(investigate(incident,user,answer,{},fake))
    fake=FakeProvider([{'id':'1','status':'completed','steps':[{'type':'model_output','content':[{'type':'text','text':'Your car is safe to drive.'}]}]}])
    asyncio.run(investigate(incident,user,answer,{},fake))
    assert 'could not pass the safety review' in answer.text


def test_critical_media_observation_sets_persistent_safety():
    incident,user,answer=context()
    text='CRITICAL OBSERVATION: The recording reports a soft brake pedal.'
    fake=FakeProvider([{'id':'1','status':'completed','steps':[{'type':'model_output','content':[{'type':'text','text':text}]}]}])
    asyncio.run(investigate(incident,user,answer,{},fake))
    assert incident.safety and answer.text == incident.safety
