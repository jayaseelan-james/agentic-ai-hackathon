from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from .sensors import Simulation
from .diagnostic_types import DiagnosticState, Inference, Question


def uid():
    return uuid4().hex


def now():
    return datetime.now(timezone.utc).isoformat()


class Vehicle(BaseModel):
    model_config = ConfigDict(extra='forbid')
    make: str = Field(default='', max_length=80)
    model: str = Field(default='', max_length=100)
    year: int | None = Field(default=None, ge=1900, le=2100)


class Attachment(BaseModel):
    id: str
    kind: Literal['image', 'audio', 'video']
    filename: str
    mime_type: str
    size: int
    url: str


class Event(BaseModel):
    id: str = Field(default_factory=uid)
    tool: str
    initiator: Literal['model', 'backend']
    status: Literal['running', 'complete', 'failed'] = 'complete'
    timestamp: str = Field(default_factory=now)
    summary: str
    arguments: dict | None = None
    result: dict | None = None


class Citation(BaseModel):
    url: str
    title: str
    start_index: int | None = None
    end_index: int | None = None


class Message(BaseModel):
    id: str = Field(default_factory=uid)
    request_id: str | None = None
    reply_to: str | None = None
    role: Literal['user', 'assistant']
    text: str = ''
    timestamp: str = Field(default_factory=now)
    attachments: list[Attachment] = Field(default_factory=list)
    state: Literal['processing', 'complete', 'failed'] = 'complete'
    activity: list[Event] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    search_suggestions: list[str] = Field(default_factory=list)
    provider: str | None = None
    model: str | None = None
    error: str | None = None
    report: dict | None = None
    diagnostic_inference: list[Inference] = Field(default_factory=list)
    follow_up_question: Question | None = None


class Incident(BaseModel):
    id: str = Field(default_factory=uid)
    title: str = 'New chat'
    vehicle: Vehicle = Field(default_factory=Vehicle)
    messages: list[Message] = Field(default_factory=list)
    safety: str | None = None
    sensor_simulation: Simulation = Field(default_factory=Simulation, exclude=True)
    diagnostic_state: DiagnosticState = Field(default_factory=DiagnosticState, exclude=True)


class CreateIncident(BaseModel):
    vehicle: Vehicle = Field(default_factory=Vehicle)
