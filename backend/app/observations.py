"""Validate model-extracted observations against incident-owned sources."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool

from .bayes import SYMPTOMS
from .diagnostic_types import Symptom
from .diagnostics import add_evidence, apply_brake_safety, set_context
from .safety import SAFETY, critical


class Observation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    message_id: str
    symptom: Symptom
    value: StrictBool | None
    source: Literal['text', 'spoken', 'visible']
    quote: str = Field(min_length=1, max_length=1200)
    certainty: Literal['observed', 'uncertain']
    attachment_id: str | None = None
    timestamp_seconds: float | None = Field(default=None, ge=0, le=7200, allow_inf_nan=False)


class ObservationBatch(BaseModel):
    model_config = ConfigDict(extra='forbid')
    observations: list[Observation] = Field(max_length=20)


OBSERVATION_TOOL = {
    'type': 'function', 'name': 'record_observations',
    'description': 'Record directly reported or visible symptoms from incident-owned text/media. For every media turn call this before answering, with an empty observations list if ambiguous. Do not register hidden causes, web statements or acoustic hypotheses as observed facts.',
    'parameters': {'type': 'object', 'properties': {'observations': {'type': 'array', 'maxItems': 20, 'items': {
        'type': 'object', 'properties': {
            'message_id': {'type': 'string'}, 'attachment_id': {'type': 'string'},
            'symptom': {'type': 'string', 'enum': [s for group in SYMPTOMS.values() for s in group]},
            'value': {'type': ['boolean', 'null']}, 'source': {'type': 'string', 'enum': ['text', 'spoken', 'visible']},
            'quote': {'type': 'string'}, 'certainty': {'type': 'string', 'enum': ['observed', 'uncertain']},
            'timestamp_seconds': {'type': 'number', 'minimum': 0, 'maximum': 7200}},
        'required': ['message_id', 'symptom', 'value', 'source', 'quote', 'certainty'], 'additionalProperties': False}}},
        'required': ['observations'], 'additionalProperties': False}}


def record(incident, arguments):
    batch = ObservationBatch.model_validate(arguments)
    validated = []
    for item in batch.observations:
        message = next((m for m in incident.messages if m.id == item.message_id and m.role == 'user'), None)
        if not message:
            raise ValueError('Observation must reference a user message in this incident.')
        attachment = next((a for a in message.attachments if a.id == item.attachment_id), None)
        if item.source == 'text':
            if item.attachment_id or item.timestamp_seconds is not None or item.quote.casefold() not in message.text.casefold():
                raise ValueError('Text observation requires an exact quote from the referenced user message.')
        else:
            if not attachment or attachment.id not in incident.analyzed_attachment_ids:
                raise ValueError('Media observation must reference a processed attachment from this incident.')
            if item.source == 'spoken' and attachment.kind not in ('audio', 'video'):
                raise ValueError('Spoken observations require audio or video.')
            if item.source == 'visible' and attachment.kind not in ('image', 'video'):
                raise ValueError('Visible observations require an image or video.')
            if attachment.kind == 'image' and item.timestamp_seconds is not None:
                raise ValueError('A still image has no timestamp.')
        value = item.value if item.certainty == 'observed' else None
        # A single frame or engine noise cannot prove pressure, persistence or hidden faults.
        if item.source == 'visible' and item.symptom not in ('yellow_tpms_warning', 'high_temperature_warning', 'check_engine_warning'):
            value = None
        validated.append((item, value))
    if incident.diagnostic_state.context == 'unspecified' and not incident.sensor_simulation.enabled:
        set_context(incident, 'real')
    for item, value in validated:
        state = incident.diagnostic_state
        domain = next(d for d, group in SYMPTOMS.items() if item.symptom in group)
        if domain not in state.domains:
            state.domains.append(domain)
        state.active = True
        reference = f'{item.message_id}:{item.attachment_id or "text"}:{item.symptom}'
        add_evidence(incident, item.symptom, value, 'user_reported' if item.source == 'text' else 'media_observed',
                     reference, item.quote, attachment_id=item.attachment_id, timestamp_seconds=item.timestamp_seconds,
                     observation_kind=item.source, uncertain=value is None)
        if value is True and (critical(item.quote) or item.symptom in ('soft_brake_pedal', 'persistent_red_warning', 'high_temperature_warning', 'overheating_stationary')):
            incident.safety = SAFETY
    apply_brake_safety(incident)
    return {'accepted': [{'symptom': item.symptom, 'value': value, 'source': item.source} for item, value in validated],
            'safety': incident.safety, 'note': 'Observations are evidence; faults remain unconfirmed.'}
