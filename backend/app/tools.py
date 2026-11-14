from .schemas import Incident, now
from .sensors import ReadHistory, ReadSensors, history, list_sensors, read
from .diagnostics import classify, record_sensor_result, refresh_current

SENSOR_NAMES = {'type': 'array', 'items': {'type': 'string'}, 'minItems': 1, 'maxItems': 8,
                'description': 'Channel names from list_available_sensors. tpms_per_wheel_pressure_bar expands to all four tires.'}

TOOLS = [
    {'type': 'function', 'name': 'classify_diagnosis', 'description': 'Compute synthetic-trained Bayesian tire/brake categories from accepted incident evidence only. Unknown observations are marginalized. Do not invent probabilities or expose competing causes in ordinary chat.', 'parameters': {'type': 'object', 'properties': {'domain': {'type': 'string', 'enum': ['tire', 'brake']}}, 'required': ['domain'], 'additionalProperties': False}},
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
        'sources': list({c.url: c.model_dump() for m in incident.messages for c in m.citations}.values()),
        'diagnostic_inference': refresh_current(incident),
        'diagnostic_history': [{'message_id': m.id, 'results': [r.model_dump() for r in m.diagnostic_inference]} for m in incident.messages if m.diagnostic_inference],
        'unresolved_questions': [incident.diagnostic_state.pending.model_dump()] if incident.diagnostic_state.pending and not incident.safety else [],
        'simulated_sensor_evidence': [{'tool': event.tool, 'timestamp': event.timestamp, 'arguments': event.arguments, 'result': event.result}
                                      for message in incident.messages for event in message.activity
                                      if event.tool in ('read_vehicle_sensors', 'read_sensor_history') and event.result],
        'safety': incident.safety, 'uncertainties': ['No sensor connection or physical inspection. Demo readings, when enabled, are simulated and separate from user vehicle details. AI observations and possible causes are unconfirmed.'],
    }


def dispatch(name: str, arguments: dict, incident: Incident):
    if not isinstance(arguments, dict):
        raise ValueError('Tool arguments must be an object.')
    if name == 'classify_diagnosis':
        if set(arguments) != {'domain'} or arguments['domain'] not in ('tire', 'brake'):
            raise ValueError('Provide only domain=tire or domain=brake; evidence is resolved by the server.')
        return classify(incident, arguments['domain']).model_dump()
    if name in ('read_vehicle_sensors', 'read_sensor_history'):
        try:
            query = (ReadHistory if name == 'read_sensor_history' else ReadSensors).model_validate(arguments)
        except ValueError:
            raise ValueError('Invalid sensor query. Provide sensor_names and bounded integer history options only.') from None
        result = history(incident.sensor_simulation, query) if name == 'read_sensor_history' else read(incident.sensor_simulation, query)
        if name == 'read_vehicle_sensors':
            record_sensor_result(incident, result, 'sensor-tool:' + str(result['revision']) + ':' + ','.join(query.sensor_names))
        return result
    if arguments:
        raise ValueError('This tool accepts no arguments; incident context is resolved by the server.')
    if name == 'list_available_sensors':
        return list_sensors(incident.sensor_simulation)
    if name == 'get_vehicle_profile':
        profile = incident.vehicle.model_dump()
        return {'vehicle': profile, 'source': 'user_provided', 'missing': [k for k, v in profile.items() if not v], 'sensor_connection': False,
                'simulation': {'enabled': incident.sensor_simulation.enabled, 'revision': incident.sensor_simulation.revision,
                               'note': 'Demo telemetry belongs to a fictional vehicle, not these user-entered details.'}}
    if name == 'create_mechanic_report':
        return mechanic_report(incident)
    raise ValueError('Unknown tool. Only declared read-only tools are allowed.')
