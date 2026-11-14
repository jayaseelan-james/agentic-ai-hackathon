from .schemas import Incident, Vehicle, now
from .config import WEB_TOOLS
from .bayes import SYMPTOMS
from .bmw import BMW_MAKE, BMW_MODEL, BMW_TOOL_SPECS, annotate_sensors, check_recalls, search_knowledge
from .sensors import CATALOG, ReadHistory, ReadSensors, expand, history, list_sensors, read
from .diagnostics import classify, record_sensor_result, refresh_current, unresolved_questions
from .observations import OBSERVATION_TOOL, record

SENSOR_NAMES = {'type': 'array', 'items': {'type': 'string'}, 'minItems': 1, 'maxItems': len(CATALOG),
                'description': 'Channel names from list_available_sensors. tpms_per_wheel_pressure_bar expands to all four tires.'}

TOOLS = [
    OBSERVATION_TOOL,
    {'type': 'function', 'name': 'update_vehicle_profile', 'description': 'Save vehicle details explicitly supplied in a user chat message. Copy make/model/year exactly; omit fields not provided. Never infer from media or search.', 'parameters': {'type': 'object', 'properties': {'message_id': {'type':'string'}, 'make': {'type':'string'}, 'model': {'type':'string'}, 'year': {'type':'integer','minimum':1900,'maximum':2100}}, 'required':['message_id'], 'additionalProperties':False}},
    {'type': 'function', 'name': 'classify_diagnosis', 'description': 'Compute synthetic-trained Bayesian fault categories from accepted incident evidence only. Unknown observations are marginalized. Do not invent probabilities or expose competing causes in ordinary chat.', 'parameters': {'type': 'object', 'properties': {'domain': {'type': 'string', 'enum': list(SYMPTOMS)}}, 'required': ['domain'], 'additionalProperties': False}},
    {'type': 'function', 'name': 'list_available_sensors', 'description': 'Discover optional demo sensor channels, units, availability and suggested history windows. No hardware connection. Simulation may be disabled.', 'parameters': {'type': 'object', 'properties': {}, 'additionalProperties': False}},
    {'type': 'function', 'name': 'read_vehicle_sensors', 'description': 'Read requested current simulated sensor values for this chat. Retrieval success does not mean the vehicle is healthy. No mutation.', 'parameters': {'type': 'object', 'properties': {'sensor_names': SENSOR_NAMES}, 'required': ['sensor_names'], 'additionalProperties': False}},
    {'type': 'function', 'name': 'read_sensor_history', 'description': 'Read frozen timestamped simulated history. Use for trends, gradual changes or recurring problems. Omit lookback_minutes for each channel scenario window; choose a different window when relevant. Windows end at snapshot_time, not wall-clock now. Missing coverage is explicit.', 'parameters': {'type': 'object', 'properties': {'sensor_names': SENSOR_NAMES, 'lookback_minutes': {'type': 'integer', 'minimum': 1, 'maximum': 10080}, 'max_points': {'type': 'integer', 'minimum': 2, 'maximum': 200}}, 'required': ['sensor_names'], 'additionalProperties': False}},
    {'type': 'google_search'}, {'type': 'url_context'},
    {'type': 'function', 'name': 'get_vehicle_profile', 'description': 'Read confirmed user-entered vehicle details and missing fields. Always use before giving vehicle-specific guidance.', 'parameters': {'type': 'object', 'properties': {}, 'additionalProperties': False}},
    {'type': 'function', 'name': 'create_mechanic_report', 'description': 'Create a factual handoff when the user requests a report or a supported leading cause warrants professional handoff. Do not call merely to ask a routine follow-up question.', 'parameters': {'type': 'object', 'properties': {}, 'additionalProperties': False}},
]


def mechanic_report(incident: Incident):
    return {
        'created_at': now(), 'vehicle': incident.vehicle.model_dump(),
        'reported_symptoms': [m.text for m in incident.messages if m.role == 'user' and m.text],
        'media': [{'filename': a.filename, 'kind': a.kind} for m in incident.messages for a in m.attachments],
        'assistant_assessments_unconfirmed': [m.text for m in incident.messages if m.role == 'assistant' and m.state == 'complete' and m.text],
        'media_observations': [e.model_dump() for e in incident.diagnostic_state.evidence if e.source == 'media_observed' and not e.superseded],
        'sources': list({c.url: c.model_dump() for m in incident.messages for c in m.citations}.values()),
        'diagnostic_inference': refresh_current(incident),
        'diagnostic_history': [{'message_id': m.id, 'results': [r.model_dump() for r in m.diagnostic_inference]} for m in incident.messages if m.diagnostic_inference],
        'unresolved_questions': unresolved_questions(incident),
        'simulated_sensor_evidence': [{'tool': event.tool, 'timestamp': event.timestamp, 'arguments': event.arguments, 'result': event.result}
                                      for message in incident.messages for event in message.activity
                                      if event.tool in ('read_vehicle_sensors', 'read_sensor_history') and event.result],
        'safety': incident.safety, 'uncertainties': ['No physical inspection has been performed. Sensor readings are observations, not confirmation of a mechanical fault. AI assessments remain unconfirmed.'],
    }


def tools_for(incident: Incident):
    tools = TOOLS + BMW_TOOL_SPECS if incident.mode == 'bmw_g20' else TOOLS
    if incident.sensor_simulation.internet_blocked:
        return [tool for tool in tools if tool['type'] == 'function' and tool['name'] not in WEB_TOOLS]
    return tools


def dispatch(name: str, arguments: dict, incident: Incident):
    if incident.sensor_simulation.internet_blocked and name in WEB_TOOLS:
        raise ValueError('Web access is blocked in remote breakdown mode. Use sensor readings and bundled references only.')
    if not isinstance(arguments, dict):
        raise ValueError('Tool arguments must be an object.')
    if name == 'update_vehicle_profile':
        if set(arguments) - {'message_id', 'make', 'model', 'year'} or len(arguments) < 2:
            raise ValueError('Provide a source message and at least one vehicle detail.')
        message = next((m for m in incident.messages if m.role == 'user' and m.id == arguments.get('message_id')), None)
        updates = {k: v for k, v in arguments.items() if k != 'message_id'}
        if incident.mode == 'bmw_g20':
            preset = {'make': BMW_MAKE, 'model': BMW_MODEL}
            updates = {
                k: v for k, v in updates.items()
                if not (k in preset and str(v).strip().casefold() in {preset[k].casefold(), '330i', '330i g20', 'g20'} and str(v).casefold() not in (message.text.casefold() if message else ''))
            }
            if not updates:
                return {'vehicle': incident.vehicle.model_dump(), 'source': 'bmw_g20_workspace'}
        if not message or any(not str(v).strip() or str(v).casefold() not in message.text.casefold() for v in updates.values()):
            raise ValueError('Vehicle details must appear explicitly in the referenced user message.')
        incident.vehicle = Vehicle.model_validate({**incident.vehicle.model_dump(), **updates})
        return {'vehicle': incident.vehicle.model_dump(), 'source': 'user_provided'}
    if name == 'record_observations':
        return record(incident, arguments)
    if name in ('search_bmw_knowledge', 'check_bmw_recalls'):
        if incident.mode != 'bmw_g20':
            raise ValueError('Unknown tool. Only declared read-only tools are allowed.')
        return search_knowledge(arguments) if name == 'search_bmw_knowledge' else check_recalls(arguments, incident.vehicle.year)
    if name in ('list_available_sensors', 'read_vehicle_sensors', 'read_sensor_history') and not incident.sensor_simulation.enabled:
        raise ValueError('Simulation is disabled for this investigation. Sensor tools are unavailable.')
    if name == 'classify_diagnosis':
        if set(arguments) != {'domain'} or arguments['domain'] not in SYMPTOMS:
            raise ValueError('Provide only a supported domain; evidence is resolved by the server.')
        return classify(incident, arguments['domain']).model_dump()
    if name in ('read_vehicle_sensors', 'read_sensor_history'):
        try:
            query = (ReadHistory if name == 'read_sensor_history' else ReadSensors).model_validate(arguments)
        except ValueError:
            raise ValueError('Invalid sensor query. Provide sensor_names and bounded integer history options only.') from None
        result = history(incident.sensor_simulation, query) if name == 'read_sensor_history' else read(incident.sensor_simulation, query)
        if name == 'read_vehicle_sensors':
            record_sensor_result(incident, result, 'sensor-tool:' + str(result['revision']) + ':' + ','.join(query.sensor_names))
        return annotate_sensors(result, expand(query.sensor_names)) if incident.mode == 'bmw_g20' else result
    if arguments:
        raise ValueError('This tool accepts no arguments; incident context is resolved by the server.')
    if name == 'list_available_sensors':
        result = list_sensors(incident.sensor_simulation)
        return annotate_sensors(result) if incident.mode == 'bmw_g20' else result
    if name == 'get_vehicle_profile':
        profile = incident.vehicle.model_dump()
        base = {'vehicle': profile, 'source': 'bmw_g20_workspace' if incident.mode == 'bmw_g20' else 'user_provided',
                'missing': [k for k, v in profile.items() if not v], 'sensor_connection': False,
                'simulation': {'enabled': incident.sensor_simulation.enabled, 'revision': incident.sensor_simulation.revision,
                               'note': 'Demo telemetry belongs to a fictional vehicle, not these user-entered details.'}}
        if incident.mode == 'bmw_g20':
            base['variant_scope'] = 'BMW 330i (G20) 2019–2024 petrol (B46TU/B48TU); excludes 330e PHEV'
        return base
    if name == 'create_mechanic_report':
        return mechanic_report(incident)
    raise ValueError('Unknown tool. Only declared read-only tools are allowed.')
