"""Local Gemini diagnostic API. Ephemeral conversations; no connected sensors."""
import asyncio
import hashlib
from contextlib import asynccontextmanager
from typing import Annotated, Literal

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response

from .agent import investigate
from .bmw import BMW_MAKE, BMW_MODEL
from .config import RESTRICTED_MODEL, settings
from .provider import GeminiProvider, GemmaProvider, public_error
from .safety import SAFETY, critical
from .schemas import Attachment, CreateIncident, Event, Incident, Message, Vehicle, uid
from .sensors import Simulation, EnableSimulation, ConnectivitySimulation, SensorChange, change_sensor, describe, reset, touch
from .tools import mechanic_report
from . import simulator
from .diagnostics import finish, ingest_user, set_context

MAX_FILE = 25_000_000
MAX_TOTAL = 50_000_000
ALLOWED = {'image/jpeg', 'image/png', 'image/webp', 'image/gif', 'audio/webm', 'audio/ogg', 'audio/wav', 'audio/x-wav', 'audio/mp4', 'audio/mpeg', 'audio/aac', 'video/webm', 'video/mp4', 'video/quicktime', 'video/ogg'}
incidents: dict[str, Incident] = {}
media: dict[str, tuple[bytes, str]] = {}
requests: dict[tuple[str, str], str] = {}
locks: dict[str, asyncio.Lock] = {}
tasks: set[asyncio.Task] = set()
shared_simulation = simulator.state
simulator_lock = simulator.lock
verified_model: str | None = None


@asynccontextmanager
async def lifespan(app):
    yield
    for task in list(tasks):
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


app = FastAPI(title='AutoSage Gemini API', lifespan=lifespan)


@app.middleware('http')
async def local_origin(request, call_next):
    origin = request.headers.get('origin')
    if request.method in ('POST', 'PATCH', 'DELETE') and origin and origin not in {'http://127.0.0.1:5173', 'http://localhost:5173', 'http://127.0.0.1:8000', 'http://localhost:8000'}:
        return JSONResponse({'detail': 'Requests from this browser origin are not allowed.'}, status_code=403)
    return await call_next(request)


def get_provider():
    return GeminiProvider()


def get_restricted_provider():
    return GemmaProvider()


def get_incident(incident_id: str):
    if incident_id not in incidents:
        raise HTTPException(404, 'Chat not found. Start a new chat after a server restart.')
    return incidents[incident_id]


def processing(incident):
    return any(m.state == 'processing' for m in incident.messages)


async def run(incident, user, answer):
    global verified_model
    provider = None
    try:
        provider = get_restricted_provider() if incident.sensor_simulation.internet_blocked else get_provider()
        answer.provider = getattr(provider, 'name', 'gemini')
        answer.model = provider.model
        await investigate(incident, user, answer, media, provider)
        if isinstance(provider, GeminiProvider):
            verified_model = provider.model
        if answer.report:
            answer.report = mechanic_report(incident)
    except asyncio.CancelledError:
        answer.state = 'failed'
        answer.error = 'Backend stopped during processing. Please retry.'
        raise
    except Exception as error:
        answer.state = 'failed'
        answer.error = public_error(error)
        # Local results remain available; provider failure and retry stay visible.
        finish(incident, answer)
    finally:
        if answer.state == 'failed':
            for analysis in answer.media_analysis:
                if analysis['status'] != 'analyzed':
                    analysis['status'] = 'failed'
        for event in answer.activity:
            if event.status == 'running':
                event.status = 'failed'
                event.summary = 'Processing did not complete'
        if provider:
            try:
                await asyncio.wait_for(provider.close(), timeout=5)
            except Exception:
                pass


def enqueue(incident, user, answer):
    task = asyncio.create_task(run(incident, user, answer))
    tasks.add(task)
    task.add_done_callback(tasks.discard)


def complete_or_enqueue(incident, user, answer):
    if answer.simulator_snapshot is None:
        incident.sensor_simulation = shared_simulation.model_copy(deep=True)
        sim = incident.sensor_simulation
        answer.simulator_snapshot = {'enabled': sim.enabled, 'revision': sim.revision, 'fixture_id': sim.fixture_id, 'snapshot_time': sim.snapshot_time, 'internet_blocked': sim.internet_blocked}
    restricted = incident.sensor_simulation.internet_blocked
    answer.provider = 'gemma' if restricted else 'gemini'
    answer.model = RESTRICTED_MODEL if restricted else settings()[1]
    if incident.sensor_simulation.enabled:
        set_context(incident, 'demo')
    elif incident.diagnostic_state.context == 'demo':
        set_context(incident, 'real')
    ingest_user(incident, user)
    if user.sensor_check and not incident.sensor_simulation.enabled and not incident.safety:
        answer.state = 'complete'
        answer.text = 'Sensor readings are not enabled, so I could not check your car. Enable vehicle readings and try again, or describe the warning or symptom in chat.'
        answer.provider = 'sensor_status'
        answer.model = None
        answer.activity.append(Event(tool='list_available_sensors', initiator='backend', summary='Sensor readings are disabled', result={'status': 'disabled'}))
        return
    if incident.safety:
        answer.state = 'complete'
        answer.text = SAFETY
        answer.provider = 'safety_rules'
        answer.model = None
        finish(incident, answer)
        answer.report = mechanic_report(incident)
    else:
        enqueue(incident, user, answer)


@app.get('/api/health')
def health():
    key, model = settings()
    blocked = shared_simulation.internet_blocked
    model = RESTRICTED_MODEL if blocked else model
    return {'status': 'ok', 'mode': 'restricted' if blocked else 'live', 'provider': 'gemma' if blocked else 'gemini', 'model': model, 'configured': bool(key), 'verified': verified_model == model, 'supported_inputs': ['text', 'image', 'audio', 'video'], 'sensor_connection': False, 'internet_blocked': blocked, 'web_search_allowed': not blocked, 'api_connection_allowed': True}


@app.get('/api/vehicles')
def vehicles():
    return []


@app.get('/api/incidents', response_model=list[Incident])
def list_incidents(mode: Literal['general', 'bmw_g20'] | None = None):
    items = list(reversed(incidents.values()))
    return [item for item in items if item.mode == mode] if mode else items


@app.post('/api/incidents', response_model=Incident, status_code=201)
def create_incident(body: CreateIncident):
    vehicle = body.vehicle
    if body.mode == 'bmw_g20' and not vehicle.make and not vehicle.model:
        vehicle = Vehicle(make=BMW_MAKE, model=BMW_MODEL, year=vehicle.year)
    incident = Incident(mode=body.mode, vehicle=vehicle)
    incidents[incident.id] = incident
    locks[incident.id] = asyncio.Lock()
    return incident


@app.get('/api/incidents/{incident_id}', response_model=Incident)
def read_incident(incident_id: str):
    return get_incident(incident_id)


@app.patch('/api/incidents/{incident_id}/vehicle', response_model=Incident)
async def update_vehicle(incident_id: str, body: Vehicle):
    incident = get_incident(incident_id)
    async with locks[incident_id]:
        if processing(incident):
            raise HTTPException(409, 'Wait for the current investigation before changing vehicle details.')
        incident.vehicle = body
    return incident


@app.get('/api/incidents/{incident_id}/report')
def report(incident_id: str):
    return mechanic_report(get_incident(incident_id))


# Compatibility routes intentionally address the global simulator, not per-chat controls.
@app.get('/api/incidents/{incident_id}/sensors')
async def sensor_state(incident_id: str):
    get_incident(incident_id)
    return simulator.describe_state()

@app.patch('/api/incidents/{incident_id}/sensors')
async def enable_sensors(incident_id: str, body: EnableSimulation):
    get_incident(incident_id)
    return await _enable(body, None, False)

@app.post('/api/incidents/{incident_id}/sensors/reset')
async def reset_sensors(incident_id: str):
    get_incident(incident_id)
    return await _reset(None, False)

@app.patch('/api/incidents/{incident_id}/sensors/{sensor_name}')
async def update_sensor(incident_id: str, sensor_name: str, body: SensorChange):
    get_incident(incident_id)
    return await _update(sensor_name, body, None, False)


@app.post('/api/incidents/{incident_id}/messages', response_model=Incident, status_code=202)
async def send_message(incident_id: str, request_id: Annotated[str, Form(min_length=1, max_length=80)], text: str = Form(''), files: list[UploadFile] = File(default=[]), sensor_check: bool = Form(False)):
    incident = get_incident(incident_id)
    pending = []
    total = 0
    fingerprint = hashlib.sha256(text.encode())
    fingerprint.update(b'\x01' if sensor_check else b'\x00')
    try:
        if len(files) > 5 or len(text) > 10000 or (not text.strip() and not files):
            raise HTTPException(422, 'Provide text (up to 10,000 characters) or 1–5 attachments.')
        for file in files:
            mime = (file.content_type or '').split(';')[0].lower()
            if mime not in ALLOWED:
                raise HTTPException(415, 'Unsupported media type. Use an image, audio, or video file.')
            data = await file.read(MAX_FILE + 1)
            total += len(data)
            if len(data) > MAX_FILE or total > MAX_TOTAL:
                raise HTTPException(413, 'Limit: 25 MB per file and 50 MB per message.')
            if not data:
                raise HTTPException(422, 'Empty attachments cannot be sent.')
            fingerprint.update(repr((file.filename, mime, len(data))).encode())
            fingerprint.update(data)
            media_id = uid()
            attachment = Attachment(id=media_id, kind=mime.split('/')[0], filename=(file.filename or 'Recording').replace('\\', '/').split('/')[-1], mime_type=mime, size=len(data), url=f'/api/attachments/{media_id}')
            pending.append((attachment, data))
    finally:
        for file in files:
            await file.close()
    async with locks[incident_id]:
        key = (incident_id, request_id)
        digest = fingerprint.hexdigest()
        if key in requests:
            if requests[key] != digest:
                raise HTTPException(409, 'Request ID already belongs to different content.')
            return incident
        if processing(incident):
            raise HTTPException(409, 'An investigation is already processing. Please wait.')
        user = Message(role='user', text=text.strip(), sensor_check=sensor_check, request_id=request_id, attachments=[a for a, _ in pending])
        if critical(user.text):
            incident.safety = SAFETY
        answer = Message(role='assistant', state='processing', reply_to=user.id, provider='gemini', model=settings()[1], activity=[Event(tool='evaluate_safety', initiator='backend', summary='Critical symptoms detected' if incident.safety else 'Reported-symptom preflight completed; safety not determined')])
        for attachment, data in pending:
            media[attachment.id] = (data, attachment.mime_type)
        requests[key] = digest
        if incident.title == 'New chat':
            title = text.strip()
            incident.title = (title[:45].rsplit(' ', 1)[0] + '…' if len(title) > 45 else title) or 'Media conversation'
        incident.messages.extend([user, answer])
        complete_or_enqueue(incident, user, answer)
    return incident


@app.post('/api/incidents/{incident_id}/messages/{message_id}/retry', response_model=Incident, status_code=202)
async def retry(incident_id: str, message_id: str):
    incident = get_incident(incident_id)
    async with locks[incident_id]:
        answer = next((m for m in incident.messages if m.id == message_id and m.role == 'assistant'), None)
        if not answer:
            raise HTTPException(404, 'Assistant message not found.')
        if answer.state == 'processing':
            return incident
        if answer.state != 'failed' or answer != incident.messages[-1] or processing(incident):
            raise HTTPException(409, 'Only the latest failed investigation can be retried.')
        user = next(m for m in incident.messages if m.id == answer.reply_to)
        answer.state, answer.error = 'processing', None
        answer.text, answer.activity, answer.citations, answer.search_suggestions, answer.report = '', [], [], [], None
        answer.media_analysis = []
        answer.diagnostic_inference, answer.follow_up_question = [], None
        complete_or_enqueue(incident, user, answer)
    return incident


@app.get('/api/attachments/{attachment_id}')
def attachment(attachment_id: str):
    if attachment_id not in media:
        raise HTTPException(404, 'Attachment no longer available.')
    data, mime = media[attachment_id]
    return Response(data, media_type=mime, headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})


@app.get('/api/simulator')
async def shared_state():
    return simulator.describe_state()

async def _enable(body, if_match, required=True):
    async with simulator_lock:
        simulator.check_revision(if_match, required)
        if shared_simulation.enabled != body.enabled:
            shared_simulation.enabled = body.enabled
            touch(shared_simulation)
        return simulator.describe_state()

async def _update(name, body, if_match, required=True):
    async with simulator_lock:
        simulator.check_revision(if_match, required)
        try:
            change_sensor(shared_simulation, name, body)
        except ValueError as error:
            raise HTTPException(422, str(error)) from None
        return simulator.describe_state()

async def _reset(if_match, required=True):
    async with simulator_lock:
        simulator.check_revision(if_match, required)
        reset(shared_simulation)
        return simulator.describe_state()

@app.post('/api/simulator/scenario')
async def shared_scenario(body: simulator.Scenario, if_match: str | None = Header(default=None)):
    async with simulator_lock:
        simulator.check_revision(if_match)
        simulator.apply_scenario(body.scenario)
        return simulator.describe_state()


@app.patch('/api/simulator')
async def shared_enable(body: EnableSimulation, if_match: str | None = Header(default=None)):
    return await _enable(body, if_match)


@app.patch('/api/simulator/connectivity')
async def shared_connectivity(body: ConnectivitySimulation, if_match: str | None = Header(default=None)):
    async with simulator_lock:
        simulator.check_revision(if_match)
        if shared_simulation.internet_blocked != body.internet_blocked:
            shared_simulation.internet_blocked = body.internet_blocked
            touch(shared_simulation)
        return simulator.describe_state()

@app.patch('/api/simulator/sensors/{name}')
async def shared_update(name: str, body: SensorChange, if_match: str | None = Header(default=None)):
    return await _update(name, body, if_match)

@app.post('/api/simulator/reset')
async def shared_reset(if_match: str | None = Header(default=None)):
    return await _reset(if_match)

@app.get('/api/incidents/{incident_id}/inspection')
def inspection(incident_id: str):
    incident = get_incident(incident_id)
    return {'incident': incident.model_dump(), 'evidence': [item.model_dump() for item in incident.diagnostic_state.evidence],
            'diagnostic_state': incident.diagnostic_state.model_dump(exclude={'cache'}),
            'report': mechanic_report(incident), 'provider': health()}
