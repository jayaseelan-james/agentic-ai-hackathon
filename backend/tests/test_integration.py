import asyncio
import io
import threading
import time

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend.app import main, simulator
from backend.app.agent import investigate
from backend.app.diagnostics import classify, ingest_user, resolve
from backend.app.observations import record
from backend.app.schemas import Attachment, Incident, Message
from backend.app.sensors import CATALOG, ReadSensors, read
from backend.tests.fakes import FakeProvider


def complete(client, id):
    for _ in range(500):
        body=client.get(f'/api/incidents/{id}').json()
        if body['messages'][-1]['state']!='processing': return body
        time.sleep(.01)
    raise AssertionError('Investigation did not finish')


@pytest.fixture
def client(monkeypatch):
    main.incidents.clear(); main.requests.clear(); main.media.clear(); main.locks.clear()
    fake=FakeProvider()
    monkeypatch.setattr(main,'get_provider',lambda:fake)
    with TestClient(main.app) as client:
        yield client,fake


def headers(client):
    return {'If-Match':str(client.get('/api/simulator').json()['revision'])}


def test_global_catalog_revision_conflicts_and_all_channels(client):
    client,_=client
    state=client.get('/api/simulator').json()
    assert len(state['channels'])==17
    assert set(sum(state['groups'].values(),[]))==set(CATALOG)
    assert sum(c['available'] for c in state['channels'].values())==17
    assert all(c['value'] is not None for c in state['channels'].values())
    assert client.patch('/api/simulator',json={'enabled':True}).status_code==428
    assert client.patch('/api/simulator?required=false',json={'enabled':True}).status_code==428
    assert client.patch('/api/simulator',json={'enabled':True},headers={'If-Match':'0'}).status_code==200
    assert client.patch('/api/simulator',json={'enabled':False},headers={'If-Match':'0'}).status_code==409
    for name,channel in state['channels'].items():
        value=channel['value'] if channel['value'] is not None else 1
        result=client.patch(f'/api/simulator/sensors/{name}',json={'kind':'value','value':value},headers=headers(client))
        assert result.status_code==200
        assert result.json()['channels'][name]['value']==value
    assert len(read(main.shared_simulation,ReadSensors(sensor_names=list(CATALOG)))['readings'])==17
    reset=client.post('/api/simulator/reset',headers=headers(client)).json()
    assert all(c['available'] and c['value'] is not None for c in reset['channels'].values())
    for name in CATALOG:
        result=client.patch(f'/api/simulator/sensors/{name}',json={'kind':'unavailable'},headers=headers(client))
        assert result.status_code==200 and result.json()['channels'][name]['value'] is None
        result=client.patch(f'/api/simulator/sensors/{name}',json={'kind':'restore'},headers=headers(client))
        assert result.status_code==200
        assert result.json()['channels'][name]['available'] is (CATALOG[name][2] is not None)


@pytest.mark.parametrize('scenario',list(simulator.SCENARIOS))
def test_scenarios_are_atomic_and_replace_unrelated_values(client,scenario):
    client,_=client
    client.patch('/api/simulator',json={'enabled':True},headers=headers(client))
    client.patch('/api/simulator/sensors/mass_airflow_gps',json={'kind':'value','value':42},headers=headers(client))
    old=client.get('/api/simulator').json()['revision']
    result=client.post('/api/simulator/scenario',json={'scenario':scenario},headers={'If-Match':str(old)})
    state=result.json()
    assert result.status_code==200 and state['revision']==old+1 and state['enabled']
    assert state['channels']['mass_airflow_gps']['value'] is None
    assert client.post('/api/simulator/scenario',json={'scenario':'invented'},headers=headers(client)).status_code==422
    assert client.get('/api/simulator').json()['revision']==old+1


def test_two_chats_get_new_shared_readings_but_running_job_keeps_snapshot(client,monkeypatch):
    client,_=client
    started=threading.Event();release=threading.Event()
    class Blocking(FakeProvider):
        async def create(self,**body):
            if not self.inputs:
                self.inputs.append(body);started.set()
                while not release.is_set(): await asyncio.sleep(.01)
                return {'id':'first','steps':[{'type':'function_call','id':'read','name':'read_vehicle_sensors','arguments':{'sensor_names':['tpms_rear_left_bar']}}]}
            return await super().create(**body)
    provider=Blocking()
    monkeypatch.setattr(main,'get_provider',lambda:provider)
    client.post('/api/simulator/scenario',json={'scenario':'tire_pressure_loss'},headers=headers(client))
    first=client.post('/api/incidents',json={}).json()['id'];second=client.post('/api/incidents',json={}).json()['id']
    client.post(f'/api/incidents/{first}/messages',data={'request_id':'first','text':'Hello'})
    assert started.wait(3)
    client.patch('/api/simulator/sensors/tpms_rear_left_bar',json={'kind':'value','value':2.2},headers=headers(client))
    release.set();one=complete(client,first)['messages'][-1]
    event=next(e for e in one['activity'] if e['tool']=='read_vehicle_sensors')
    assert event['result']['readings']['tpms_rear_left_bar']['value']==1.8
    assert main.incidents[first].sensor_simulation.channels['tpms_rear_left_bar'].value==1.8
    client.post(f'/api/incidents/{second}/messages',data={'request_id':'second','text':'Hello'})
    two=complete(client,second)['messages'][-1]
    assert two['simulator_snapshot']['revision']>one['simulator_snapshot']['revision']
    assert main.incidents[second].sensor_simulation.channels['tpms_rear_left_bar'].value==2.2


def test_disabled_snapshot_omits_sensors_even_when_global_enabled_later(client):
    client,fake=client
    id=client.post('/api/incidents',json={}).json()['id']
    client.post(f'/api/incidents/{id}/messages',data={'request_id':'a','text':'Hi'})
    answer=complete(client,id)['messages'][-1]
    assert not answer['simulator_snapshot']['enabled']
    assert not any(t.get('name') in ('list_available_sensors','read_vehicle_sensors','read_sensor_history') for t in fake.inputs[0]['tools'])


def media_context(kind='image'):
    incident=Incident()
    file=Attachment(id='attachment',kind=kind,filename='test',mime_type=f'{kind}/test',size=1,url='/test')
    user=Message(role='user',text='Please analyze this.',attachments=[file])
    incident.messages.append(user);incident.analyzed_attachment_ids.add(file.id)
    return incident,user


def observation(user,**changes):
    return {'message_id':user.id,'attachment_id':'attachment','symptom':'yellow_tpms_warning','value':True,'source':'visible','quote':'Yellow TPMS warning on the dashboard','certainty':'observed',**changes}


def test_media_evidence_reaches_bayes_and_uncertainty_is_not_false():
    incident,user=media_context()
    record(incident,{'observations':[observation(user)]})
    result=classify(incident,'tire')
    assert result.evidence_used[0].source=='media_observed'
    assert result.evidence_used[0].attachment_id=='attachment'
    assert result.ranked_hypotheses
    record(incident,{'observations':[observation(user,symptom='low_wheel_pressure',certainty='uncertain')]})
    assert resolve(incident,'tire')[0]['low_wheel_pressure'] is None


def test_media_ref_validation_and_spoken_critical_safety():
    incident,user=media_context('audio')
    for changes in [{'message_id':'foreign'}, {'attachment_id':'foreign'}, {'source':'visible'}, {'source':'web'}]:
        with pytest.raises(ValueError): record(incident,{'observations':[observation(user,**changes)]})
    record(incident,{'observations':[observation(user,source='spoken',symptom='soft_brake_pedal',quote='My brake pedal feels soft',timestamp_seconds=1.2)]})
    assert incident.safety and 'Do not continue driving' in incident.safety


def test_multimodal_sensor_bayes_and_search_prose_survive_finalization(client,monkeypatch):
    client,_=client
    client.post('/api/simulator/scenario',json={'scenario':'tire_pressure_loss'},headers=headers(client))
    id=client.post('/api/incidents',json={}).json()['id']
    class Integrated(FakeProvider):
        async def create(self,**body):
            self.inputs.append(body)
            if len(self.inputs)==1:
                user=main.incidents[id].messages[0]
                return {'id':'tools','steps':[
                    {'type':'function_call','id':'obs','name':'record_observations','arguments':{'observations':[observation(user,attachment_id=user.attachments[0].id)]}},
                    {'type':'function_call','id':'read','name':'read_vehicle_sensors','arguments':{'sensor_names':['tpms_per_wheel_pressure_bar']}},
                    {'type':'function_call','id':'history','name':'read_sensor_history','arguments':{'sensor_names':['tpms_rear_left_bar']}},
                    {'type':'function_call','id':'classify','name':'classify_diagnosis','arguments':{'domain':'tire'}},
                ]}
            text='The dashboard image shows a tire warning, and the simulated rear-left reading is below reference. Manufacturer guidance explains the next check. Has it lost pressure again?'
            return {'id':'final','status':'completed','steps':[{'type':'google_search_call','arguments':{'queries':['manufacturer TPMS']}},{'type':'model_output','content':[{'type':'text','text':text,'annotations':[{'type':'url_citation','url':'https://example.com/manual','title':'Manufacturer','start_index':0,'end_index':30}]}]}]}
    fake=Integrated();monkeypatch.setattr(main,'get_provider',lambda:fake)
    image=io.BytesIO();Image.new('RGB',(16,16),'yellow').save(image,'PNG')
    result=client.post(f'/api/incidents/{id}/messages',data={'request_id':'mixed','text':'Investigate the fictional demo yellow TPMS warning. It is safely parked with cold tires.'},files={'files':('dashboard.png',image.getvalue(),'image/png')})
    assert result.status_code==202
    answer=complete(client,id)['messages'][-1]
    assert answer['state']=='complete'
    assert 'dashboard image' in answer['text'] and 'Manufacturer guidance' in answer['text']
    assert answer['follow_up_question']['text'].count('?')==1 and '?' not in answer['text']
    assert answer['citations'] and answer['diagnostic_inference']
    assert any(e['tool']=='classify_diagnosis' for e in answer['activity'])
    assert answer['media_analysis'][0]['status']=='analyzed' and fake.deleted==['files/1']
    registry=client.get(f'/api/incidents/{id}/inspection').json()['evidence']
    assert any(e['source']=='media_observed' for e in registry)
    assert any(e['source']=='simulated_sensor' for e in registry)

def test_vehicle_details_from_chat_and_conversational_question():
    from backend.app.tools import dispatch
    from backend.app.diagnostics import finalize_dialogue
    from backend.app.diagnostic_types import Question
    incident=Incident()
    answer=Message(role='assistant',text='To check the correct manual, what make, model and year is your car?')
    finalize_dialogue(incident,answer,Question(id='symptom',text='Is the warning steady?'))
    assert answer.follow_up_question.id.startswith('vehicle:')
    user=Message(role='user',text='It is a 2020 Toyota Corolla.')
    incident.messages.append(user)
    result=dispatch('update_vehicle_profile',{'message_id':user.id,'make':'Toyota','model':'Corolla','year':2020},incident)
    assert result['vehicle']=={'make':'Toyota','model':'Corolla','year':2020}
    with pytest.raises(ValueError):
        dispatch('update_vehicle_profile',{'message_id':user.id,'make':'Honda'},incident)
    assert incident.vehicle.make=='Toyota'
