"""Opt-in billable Gemini rehearsal: python -m backend.tests.live_sensors."""
import asyncio
import json

from backend.app.schemas import Incident, Message
from backend.app.sensors import SensorChange, change_sensor
from backend.app import main
from backend.app.config import settings


async def turn(incident, text, required):
    user = Message(role='user', text=text)
    answer = Message(role='assistant', state='processing')
    incident.messages.extend([user, answer])
    await main.run(incident, user, answer)
    calls = {event.tool for event in answer.activity if event.initiator == 'model'}
    print(json.dumps({'state': answer.state, 'model': answer.model, 'tools': sorted(calls),
                      'sensor_results': [{'tool': event.tool, 'revision': event.result['revision']} for event in answer.activity if event.result and event.result.get('source') == 'simulated'],
                      'answer': answer.text, 'error': answer.error}), flush=True)
    assert answer.state == 'complete', answer.error
    assert required <= calls, f'Missing model calls: {required - calls}'
    return answer


async def run():
    if not settings()[0]:
        raise RuntimeError('Configure GEMINI_API_KEY before live checks.')
    incident = Incident()
    incident.sensor_simulation.enabled = True
    await turn(incident, 'I am safely parked. Investigate the current status of the fictional demo tire sensors. Read the simulated telemetry; keep your answer brief.', {'list_available_sensors', 'read_vehicle_sensors'})
    change_sensor(incident.sensor_simulation, 'tpms_rear_left_bar', SensorChange(kind='preset', preset='tire_slow_loss'))
    answer = await turn(incident, 'The demo tire warning is recurring and rear-left pressure seems to have gradually decreased. Investigate current readings and history, call classify_diagnosis for the tire domain, and use Google Search to verify official tire-warning guidance with citations. Compare the trend and explain what is observed versus uncertain. This is fictional demo telemetry, not my real vehicle.', {'read_vehicle_sensors', 'read_sensor_history', 'classify_diagnosis', 'google_search'})
    assert any(event.result and event.result.get('revision') == 1 for event in answer.activity if event.tool == 'read_sensor_history')
    print('Live stable baseline and gradual-loss investigation passed.', flush=True)


if __name__ == '__main__':
    asyncio.run(run())
