"""Local, ephemeral UI demo. No model, sensor or transcription calls."""
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

app = FastAPI(title="AutoSage Mock API")
MAX_FILE = 25_000_000
MAX_TOTAL = 50_000_000
VEHICLE = "DEMO_DIRECT_TPMS_01"
SAFETY = "If you are driving, stop safely as soon as possible. Do not continue driving. Arrange qualified roadside or workshop assistance."


def uid():
    return uuid4().hex


def now():
    return datetime.now(timezone.utc).isoformat()


class Attachment(BaseModel):
    id: str
    kind: Literal["image", "audio", "video"]
    filename: str
    mime_type: str
    size: int
    url: str


class Message(BaseModel):
    id: str = Field(default_factory=uid)
    role: Literal["user", "assistant"]
    text: str
    timestamp: str = Field(default_factory=now)
    attachments: list[Attachment] = Field(default_factory=list)
    activity: list[str] = Field(default_factory=list)


class Incident(BaseModel):
    id: str = Field(default_factory=uid)
    title: str = "New chat"
    vehicle_id: str = VEHICLE
    messages: list[Message] = Field(default_factory=list)
    safety: str | None = None


class CreateIncident(BaseModel):
    vehicle_id: str = VEHICLE


incidents: dict[str, Incident] = {}
media: dict[str, tuple[bytes, str]] = {}


def get_incident(incident_id: str):
    if incident_id not in incidents:
        raise HTTPException(404, "Chat not found. Start a new chat after a server restart.")
    return incidents[incident_id]


def reply(text: str):
    text = text.lower()
    if any(cue in text for cue in ("brake", "smoke", "fuel leak", "steering failure", "overheating", "flat tire")):
        return SAFETY
    if any(cue in text for cue in ("tire", "tyre", "pressure", "yellow")):
        return "A tire-pressure warning needs a closer look.\nWhile safely parked, check whether any tire looks flat or damaged.\nAre you safely parked now?"
    if any(cue in text for cue in ("engine", "noise", "rattle")):
        return "An unfamiliar engine noise needs more context.\nPlease describe when you notice it, while safely parked with the engine off.\nA recording alone cannot confirm the cause."
    if not text.strip():
        return "Your attachments were received. This mock demo does not analyze or transcribe media.\nDescribe what you noticed and whether you are safely parked."
    return "Let’s understand what you noticed.\nDescribe the warning, sound, or change in behavior, and when it started.\nAre you safely parked now?"


def seed():
    for title, prompt in [("Tire pressure warning", "My car shows a yellow tire warning. What does it mean?"), ("Engine noise", "I noticed an engine noise."), ("Dashboard light", "A dashboard light appeared.")]:
        incident = Incident(title=title, messages=[Message(role="user", text=prompt), Message(role="assistant", text=reply(prompt), activity=["Simulated symptom review — example only", "Simulated follow-up selection — no tools executed"])])
        incidents[incident.id] = incident


seed()


@app.get("/api/health")
def health():
    return {"status": "ok", "mode": "mock", "provider": None}


@app.get("/api/vehicles")
def vehicles():
    return [{"id": VEHICLE, "display_name": "Synthetic Demo Sedan", "source": "demo_fixture"}]


@app.get("/api/incidents", response_model=list[Incident])
def list_incidents():
    return list(incidents.values())


@app.post("/api/incidents", response_model=Incident, status_code=201)
def create_incident(body: CreateIncident):
    if body.vehicle_id != VEHICLE:
        raise HTTPException(422, "Select the supported synthetic demo vehicle.")
    incident = Incident(vehicle_id=body.vehicle_id)
    incidents[incident.id] = incident
    return incident


@app.get("/api/incidents/{incident_id}", response_model=Incident)
def read_incident(incident_id: str):
    return get_incident(incident_id)


ALLOWED = {"image/jpeg", "image/png", "image/webp", "image/gif", "audio/webm", "audio/ogg", "audio/wav", "audio/x-wav", "audio/mp4", "audio/mpeg", "audio/aac", "video/webm", "video/mp4", "video/quicktime", "video/ogg"}


@app.post("/api/incidents/{incident_id}/messages", response_model=Incident)
async def send_message(incident_id: str, text: str = Form(""), files: list[UploadFile] = File(default=[])):
    incident = get_incident(incident_id)
    pending = []
    total = 0
    try:
        if len(files) > 5 or len(text) > 10000 or (not text.strip() and not files):
            raise HTTPException(422, "Provide text (up to 10,000 characters) or 1–5 attachments.")
        for file in files:
            mime = (file.content_type or "").split(";")[0].lower()
            if mime not in ALLOWED:
                raise HTTPException(415, "Unsupported media type. Use an image, audio, or video file.")
            data = await file.read(MAX_FILE + 1)
            total += len(data)
            if len(data) > MAX_FILE or total > MAX_TOTAL:
                raise HTTPException(413, "Limit: 25 MB per file and 50 MB per message.")
            if not data:
                raise HTTPException(422, "Empty attachments cannot be sent.")
            media_id = uid()
            attachment = Attachment(id=media_id, kind=mime.split("/")[0], filename=(file.filename or "Recording").replace("\\", "/").split("/")[-1], mime_type=mime, size=len(data), url=f"/api/attachments/{media_id}")
            pending.append((attachment, data))
    finally:
        for file in files:
            await file.close()
    # Publish only after all files validate; failed requests leave the chat unchanged.
    for attachment, data in pending:
        media[attachment.id] = (data, attachment.mime_type)
    answer = reply(text)
    if answer == SAFETY:
        incident.safety = SAFETY
    if incident.title == "New chat":
        incident.title = text.strip()[:45] or "Media conversation"
    incident.messages.extend([Message(role="user", text=text.strip(), attachments=[a for a, _ in pending]), Message(role="assistant", text=SAFETY if incident.safety else answer, activity=["Simulated symptom review — example only", "Simulated follow-up selection — no tools executed"])])
    return incident


@app.get("/api/attachments/{attachment_id}")
def attachment(attachment_id: str):
    if attachment_id not in media:
        raise HTTPException(404, "Attachment no longer available.")
    data, mime = media[attachment_id]
    return Response(data, media_type=mime, headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})
