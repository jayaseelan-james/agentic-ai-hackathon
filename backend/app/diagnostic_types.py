"""Shared contracts for auditable, synthetic Bayesian decision support."""
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

Domain = Literal['tire', 'brake', 'cooling', 'starting_charging', 'engine_running']
Context = Literal['real', 'demo', 'unspecified']
Symptom = Literal['yellow_tpms_warning', 'low_wheel_pressure', 'soft_brake_pedal', 'persistent_red_warning', 'high_temperature_warning', 'coolant_loss', 'overheating_stationary', 'slow_cranking', 'clicking_no_crank', 'battery_warning_running', 'rough_idle', 'hesitation', 'check_engine_warning']


class Evidence(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    incident_id: str
    symptom: Symptom
    value: bool | None
    source: Literal['user_reported', 'simulated_sensor', 'media_observed']
    attachment_id: str | None = None
    timestamp_seconds: float | None = None
    observation_kind: Literal['text', 'spoken', 'visible'] | None = None
    uncertain: bool = False
    reference: str
    quote: str = ''
    timestamp: str
    revision: int
    context: Context
    sensor_revision: int | None = None
    fixture_id: str | None = None
    superseded: bool = False


class Hypothesis(BaseModel):
    fault_id: str
    posterior: float


class Inference(BaseModel):
    domain: str
    status: Literal['ok', 'insufficient_evidence', 'inconclusive', 'unsupported_domain', 'invalid_evidence', 'model_error']
    context: Context
    evidence_revision: int
    model_version: str | None = None
    method: str = 'exact_enumeration'
    parameter_source: str = 'synthetic_training'
    calibration: str = 'not_validated'
    demo_only: bool = True
    evidence_used: list[Evidence] = Field(default_factory=list)
    evidence_ignored: list[Evidence] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    ranked_hypotheses: list[Hypothesis] = Field(default_factory=list)
    reason: str = ''
    disclaimer: str = 'Trained on synthetic examples; probabilities are not real-world diagnostic confidence.'


class Question(BaseModel):
    id: str
    text: str
    domain: Domain | None = None
    symptom: Symptom | None = None
    kind: Literal['symptom', 'conflict', 'context', 'conditions'] = 'symptom'
    information_gain: float | None = None


class DiagnosticState(BaseModel):
    active: bool = False
    revision: int = 0
    context: Context = 'unspecified'
    domains: list[Domain] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    processed_messages: list[str] = Field(default_factory=list)
    pending: Question | None = None
    asked: dict[str, str] = Field(default_factory=dict)
    stopped: bool = False
    parked: bool | None = None
    cold: bool | None = None
    sensor_revision: int = -1
    cache: dict[str, Inference] = Field(default_factory=dict)
