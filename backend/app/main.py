"""Local Gemini diagnostic API. Ephemeral conversations; no connected sensors."""
import asyncio
import hashlib
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response

from .agent import investigate
from .config import settings
from .provider import GeminiProvider, public_error
from .safety import SAFETY, critical
from .schemas import Attachment, CreateIncident, Event, Incident, Message, Vehicle, uid
from .sensors import EnableSimulation, SensorChange, change_sensor, describe, reset, touch
from .tools import mechanic_report
from .diagnostics import finish, ingest_user

MAX_FILE = 25_000_000
MAX_TOTAL = 50_000_000
ALLOWED = {'image/jpeg', 'image/png', 'image/webp', 'image/gif', 'audio/webm', 'audio/ogg', 'audio/wav', 'audio/x-wav', 'audio/mp4', 'audio/mpeg', 'audio/aac', 'video/webm', 'video/mp4', 'video/quicktime', 'video/ogg'}
incidents: dict[str, Incident] = {}
media: dict[str, tuple[bytes, str]] = {}
requests: dict[tuple[str, str], str] = {}
locks: dict[str, asyncio.Lock] = {}
tasks: set[asyncio.Task] = set()
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
        provider = get_provider()
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
    ingest_user(incident, user)
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
    return {'status': 'ok', 'mode': 'live', 'provider': 'gemini', 'model': model, 'configured': bool(key), 'verified': verified_model == model, 'supported_inputs': ['text', 'image', 'audio', 'video'], 'sensor_connection': False}


@app.get('/api/vehicles')
def vehicles():
    return []


@app.get('/api/incidents', response_model=list[Incident])
def list_incidents():
    return list(reversed(incidents.values()))


@app.post('/api/incidents', response_model=Incident, status_code=201)
def create_incident(body: CreateIncident):
    incident = Incident(vehicle=body.vehicle)
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


@app.get('/api/incidents/{incident_id}/sensors')
async def sensor_state(incident_id: str):
    return describe(get_incident(incident_id).sensor_simulation)


@app.patch('/api/incidents/{incident_id}/sensors')
async def enable_sensors(incident_id: str, body: EnableSimulation):
    incident = get_incident(incident_id)
    async with locks[incident_id]:
        if processing(incident):
            raise HTTPException(409, 'Wait for the current investigation before changing demo sensors.')
        sim = incident.sensor_simulation
        if sim.enabled != body.enabled:
            sim.enabled = body.enabled
            touch(sim)
        return describe(sim)


@app.post('/api/incidents/{incident_id}/sensors/reset')
async def reset_sensors(incident_id: str):
    incident = get_incident(incident_id)
    async with locks[incident_id]:
        if processing(incident):
            raise HTTPException(409, 'Wait for the current investigation before changing demo sensors.')
        reset(incident.sensor_simulation)
        return describe(incident.sensor_simulation)


@app.patch('/api/incidents/{incident_id}/sensors/{sensor_name}')
async def update_sensor(incident_id: str, sensor_name: str, body: SensorChange):
    incident = get_incident(incident_id)
    async with locks[incident_id]:
        if processing(incident):
            raise HTTPException(409, 'Wait for the current investigation before changing demo sensors.')
        try:
            change_sensor(incident.sensor_simulation, sensor_name, body)
        except ValueError as error:
            raise HTTPException(422, str(error)) from None
        return describe(incident.sensor_simulation)


@app.post('/api/incidents/{incident_id}/messages', response_model=Incident, status_code=202)
async def send_message(incident_id: str, request_id: Annotated[str, Form(min_length=1, max_length=80)], text: str = Form(''), files: list[UploadFile] = File(default=[])):
    incident = get_incident(incident_id)
    pending = []
    total = 0
    fingerprint = hashlib.sha256(text.encode())
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
        user = Message(role='user', text=text.strip(), request_id=request_id, attachments=[a for a, _ in pending])
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
        answer.diagnostic_inference, answer.follow_up_question = [], None
        complete_or_enqueue(incident, user, answer)
    return incident


@app.get('/api/attachments/{attachment_id}')
def attachment(attachment_id: str):
    if attachment_id not in media:
        raise HTTPException(404, 'Attachment no longer available.')
    data, mime = media[attachment_id]
    return Response(data, media_type=mime, headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})
