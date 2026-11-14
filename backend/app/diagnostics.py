"""Evidence validation, synthetic Bayesian ranking and backend-owned dialogue policy."""
import json
import math
import re

from . import bayes
from .diagnostic_types import Evidence, Inference, Hypothesis, Question
from .schemas import Event, now
from .safety import SAFETY
from .sensors import TIRES

LABELS = {
    'coolant_loss_concern': 'coolant loss', 'coolant_circulation_problem': 'a coolant circulation problem', 'cooling_fan_control_issue': 'a cooling fan/control issue',
    'low_battery_charge': 'low battery charge', 'starter_circuit_issue': 'a starter circuit issue', 'charging_system_issue': 'a charging system issue',
    'ignition_misfire_concern': 'an ignition/misfire concern', 'air_fuel_delivery_concern': 'an air/fuel delivery concern', 'engine_sensor_control_concern': 'an engine sensor/control concern',
    'tire_pressure_loss': 'tire pressure loss', 'tpms_sensor_issue': 'a TPMS monitoring issue',
    'brake_hydraulic_concern': 'a brake hydraulic concern', 'brake_indicator_issue': 'a brake indicator issue',
    'other_or_unmodeled': 'an issue outside this limited model',
}
QUESTIONS = {
    'high_temperature_warning': 'Have you already observed a high coolant-temperature warning?',
    'coolant_loss': 'Have you already noticed coolant loss (without opening a hot cooling system)?',
    'overheating_stationary': 'Did the temperature problem occur while the vehicle was stationary?',
    'slow_cranking': 'When you last tried starting, did the engine crank slowly?',
    'clicking_no_crank': 'On your last starting attempt, did you hear clicking without the engine cranking?',
    'battery_warning_running': 'Was the battery warning showing while the engine was running?',
    'rough_idle': 'Have you already noticed the engine idling roughly?',
    'hesitation': 'Have you already noticed hesitation during normal use, without performing a road test?',
    'check_engine_warning': 'Is a check-engine warning showing?',

    'yellow_tpms_warning': 'Is a yellow tire-pressure warning currently showing on the dashboard?',
    'low_wheel_pressure': 'Based on an existing cold-tire gauge measurement against the vehicle label/manual (or answer "I don\'t know" if unavailable), is any tire below its specified pressure?',
    'soft_brake_pedal': 'Have you already noticed the brake pedal feeling soft or spongy?',
    'persistent_red_warning': 'Is a red brake warning staying on?',
}
PATTERNS = {
    'high_temperature_warning': '\\b(?:high (?:coolant[ -])?temperature warning|coolant temperature warning)\\b',
    'coolant_loss': '\\b(?:coolant (?:loss|leak|level (?:is )?dropping)|losing coolant)\\b',
    'overheating_stationary': '\\b(?:overheating (?:while )?(?:stationary|parked|at idle)|temperature (?:rises|rising) (?:while )?(?:stationary|parked|at idle))\\b',
    'slow_cranking': '\\b(?:slow cranking|cranks? slowly|cranking slowly)\\b',
    'clicking_no_crank': '\\b(?:clicking (?:without cranking|but (?:it )?(?:does not|doesn.t) crank)|clicks? without cranking)\\b',
    'battery_warning_running': '\\b(?:battery (?:warning|light) (?:is |stays |showing )?(?:on )?(?:while |with )?(?:the )?engine (?:is )?running)\\b',
    'rough_idle': '\\b(?:rough idle|rough idling|idles? roughly|idling roughly)\\b',
    'hesitation': '\\b(?:engine hesitation|engine hesitates|hesitation (?:when|during|on) acceleration)\\b',
    'check_engine_warning': '\\b(?:check[ -]engine (?:warning|light))\\b',

    'yellow_tpms_warning': r'\b(?:yellow\s+(?:tire|tyre|tpms|tire.pressure|tyre.pressure)\s+(?:warning|light)|(?:tire|tyre|tpms|tire.pressure|tyre.pressure)\s+(?:warning|light))\b',
    'low_wheel_pressure': r'\b(?:(?:low|underinflated)\s+(?:(?:wheel|tire|tyre)\s+)?pressure|(?:tire|tyre|wheel)\s+(?:pressure\s+)?(?:is\s+|are\s+)?(?:low|underinflated)|(?:gauge|reading|pressure).{0,25}below\s+(?:the\s+)?(?:correct|label|manual|recommended))\b',
    'soft_brake_pedal': r'\b(?:(?:soft|spongy)\s+(?:brake\s+)?pedal|(?:brake\s+)?pedal\s+(?:feels?\s+|is\s+|goes?\s+)?(?:soft|spongy|to the floor))\b',
    'persistent_red_warning': r'\b(?:red\s+brake\s+(?:warning|light)|brake\s+(?:warning|light).{0,12}red)\b',
}
UNKNOWN = r"\b(?:unsure|uncertain|maybe|perhaps|might|could|not sure|don't know|do not know|cannot tell|can't tell)\b"
HYPOTHETICAL = r'\b(?:if|hypothetical|suppose|imagine|example|what happens|how does|how do|what is|what are)\b'
NEGATIVE = r"\b(?:no|not|never|without|isn't|is not|aren't|doesn't|do not|don't|hasn't)\b"
STOP = r"\b(?:stop asking|no more questions|stop questioning|end (?:the )?(?:diagnosis|investigation)|stop the investigation)\b"


def bump(state):
    state.revision += 1
    state.cache.clear()


def add_evidence(incident, symptom, value, source, reference, quote='', correction=False, **metadata):
    state = incident.diagnostic_state
    context = metadata.pop('context', state.context)
    existing = [e for e in state.evidence if e.symptom == symptom and e.context == context and not e.superseded]
    # Exact retries and repeated claims never create independent observations.
    if any(e.reference == reference and e.value == value and e.source == source for e in existing):
        return
    if correction:
        for item in existing:
            if item.source == source or (source == 'user_reported' and item.source == 'media_observed'):
                item.superseded = True
    elif any(e.value == value and e.source == 'user_reported' for e in existing) and source == 'user_reported' and all(e.value == value for e in existing if e.source == 'user_reported'):
        return
    bump(state)
    state.evidence.append(Evidence(incident_id=incident.id, symptom=symptom, value=value, source=source,
                                 reference=reference, quote=quote, timestamp=now(), revision=state.revision,
                                 context=context, **metadata))


def set_context(incident, context):
    state = incident.diagnostic_state
    if state.context != context:
        if state.context != 'unspecified':
            state.asked.clear()
            state.parked = state.cold = None
        state.context = context
        state.pending = None
        bump(state)
        # Only explicitly unassigned user reports can acquire the clarified context.
        for item in state.evidence:
            if item.context == 'unspecified' and item.source == 'user_reported':
                item.context = context


def short_answer(text):
    normalized = text.lower().strip(' .!,')
    if normalized in ('yes', 'yes it is', 'yes they are', 'yes it does', 'correct', 'yeah', 'yep'):
        return True
    if normalized in ('no', 'no it is not', "no it isn't", 'no they are not', 'no it does not', 'nope'):
        return False
    return None


def ingest_user(incident, user):
    state = incident.diagnostic_state
    if user.id in state.processed_messages:
        return
    state.processed_messages.append(user.id)
    state.active = False
    text = user.text.lower().replace('’', "'")
    pending = state.pending
    if re.search(STOP, text) or text.strip(' .!') == 'stop':
        state.active = bool(state.domains)
        state.stopped = True
        state.pending = None
        bump(state)
        return
    # Educational questions and quoted/hypothetical examples are not symptom reports.
    hypothetical = bool(re.search(HYPOTHETICAL, text) and not re.search(UNKNOWN, text))
    if not hypothetical:
        if re.search(r'\b(?:real (?:car|vehicle)|actual (?:car|vehicle)|my real car|not (?:the )?demo)\b', text):
            set_context(incident, 'real')
            state.active = bool(state.domains)
        elif re.search(r'\b(?:demo|fictional|simulated|synthetic)\b', text):
            set_context(incident, 'demo')
            state.active = bool(state.domains)
        elif pending and pending.kind == 'context':
            if short_answer(text) is not None:
                set_context(incident, 'demo' if short_answer(text) and incident.sensor_simulation.enabled else 'real')
                state.active = bool(state.domains)
            elif text.strip(' .!') in ('real', 'my car'):
                set_context(incident, 'real')
                state.active = bool(state.domains)
        elif state.context == 'unspecified' and not incident.sensor_simulation.enabled:
            set_context(incident, 'real')
    value = short_answer(text)
    unknown = bool(re.search(UNKNOWN, text) or re.search(r'\b(?:skip|prefer not|decline|cannot answer)\b', text))
    if pending and not hypothetical:
        answered = value is not None or unknown
        if pending.kind == 'conditions' and value is not None:
            setattr(state, pending.id, value)
            bump(state)
        elif pending.symptom and answered and not (pending.kind == 'conflict' and unknown):
            add_evidence(incident, pending.symptom, value, 'user_reported', user.id, user.text,
                         correction=pending.kind == 'conflict')
        if answered:
            state.active = True
            state.asked[pending.id] = 'declined' if unknown else 'answered'
            state.pending = None
    if not hypothetical:
        for condition, positive, negative in [
            ('parked', r'\b(?:safely parked|stationary|parked)\b', r'\b(?:not parked|driving|moving)\b'),
            ('cold', r'\b(?:tires? (?:are |were )?cold|tyres? (?:are |were )?cold|cold tires?|cold tyres?)\b', r'\b(?:not cold|warm tires?|hot tires?|tires? (?:are |were )?(?:hot|warm))\b'),
        ]:
            if re.search(negative, text):
                setattr(state, condition, False)
                bump(state)
                state.active = bool(state.domains)
            elif re.search(positive, text) and not re.search(UNKNOWN, text):
                setattr(state, condition, True)
                bump(state)
                state.active = bool(state.domains)
    correction = bool(re.search(r'\b(?:correction|actually|i meant|i was wrong|to clarify|now|anymore)\b', text))
    for symptom, pattern in PATTERNS.items():
        for clause in re.split(r'[.;!\n]|\b(?:but|and)\b', text):
            match = re.search(pattern, clause)
            if not match:
                continue
            domain = next(d for d, symptoms in bayes.SYMPTOMS.items() if symptom in symptoms)
            if hypothetical:
                continue
            state.active = True
            if domain not in state.domains:
                state.domains.append(domain)
                bump(state)
            ambiguous = bool(re.search(UNKNOWN, clause) or ('?' in clause and not re.search(r'\b(?:my|i|stays|shows|feels)\b', clause)))
            negative = bool(re.search(NEGATIVE, clause) or re.search(r'\b(?:off|gone|normal|disappeared)\b', clause[match.end():]))
            # A generic tire warning need not be the yellow TPMS indicator.
            if symptom == 'yellow_tpms_warning' and not re.search(r'\b(?:yellow|tpms|tire.pressure|tyre.pressure)\b', clause):
                ambiguous = True
            add_evidence(incident, symptom, None if ambiguous else not negative, 'user_reported', user.id,
                         user.text, correction=correction)
    # Topic-only investigations can still ask an initial discriminating question.
    if not hypothetical and re.search(r'\b(?:my|investigate|problem|issue|warning)\b', text):
        for domain, pattern in [('tire', r'\b(?:tire|tyre|tpms)\b'), ('brake', r'\b(?:brake|brakes|pedal)\b'), ('cooling', r'\b(?:coolant|cooling|overheating)\b'), ('starting_charging', r'\b(?:battery|starter|cranking|charging)\b'), ('engine_running', r'\b(?:rough idle|hesitation|misfire|check.engine)\b')]:
            if re.search(pattern, text) and domain not in state.domains:
                state.domains.append(domain)
                bump(state)
            if re.search(pattern, text):
                state.active = True
    if pending and pending.symptom and any(e.reference == user.id and e.symptom == pending.symptom for e in state.evidence):
        state.asked[pending.id] = 'declined' if unknown else 'answered'
        state.pending = None
    if not state.active and state.pending:
        # A digression can introduce a different Gemini question. A later bare
        # yes/no must not silently answer an older diagnostic question.
        if state.asked.get(state.pending.id) == 'pending':
            state.asked.pop(state.pending.id)
        state.pending = None
    apply_brake_safety(incident)


def sync_sensors(incident):
    state, sim = incident.diagnostic_state, incident.sensor_simulation
    if state.sensor_revision != sim.revision:
        state.sensor_revision = sim.revision
        for item in state.evidence:
            if item.source == 'simulated_sensor' and item.sensor_revision != sim.revision:
                item.superseded = True
        bump(state)


def record_sensor_result(incident, result, reference):
    state, sim = incident.diagnostic_state, incident.sensor_simulation
    sync_sensors(incident)
    if (state.context != 'demo' or state.parked is not True or state.cold is not True or not sim.enabled
            or result.get('source') != 'simulated' or result.get('fixture_id') != sim.fixture_id
            or result.get('revision') != sim.revision or result.get('snapshot_time') != sim.snapshot_time):
        return
    try:
        handbook = json.loads((bayes.DATA / 'demo_handbook.json').read_text(encoding='utf-8'))
        ref = handbook['pressure_reference']
        if (handbook['fixture_id'] != sim.fixture_id or handbook['source_type'] != 'synthetic_demo_handbook'
                or handbook['conditions'] != {'parked': True, 'tires_cold': True} or ref['unit'] != 'bar'
                or type(ref['value']) not in (int, float) or not math.isfinite(ref['value']) or ref['value'] <= 0):
            return
    except (OSError, ValueError, KeyError, TypeError):
        return
    readings = result.get('readings', {})
    valid = {}
    for name, reading in readings.items():
        if name not in TIRES or name not in sim.channels:
            continue
        value = reading.get('value')
        channel = sim.channels[name]
        if (channel.available and type(value) in (int, float) and math.isfinite(value)
                and value == channel.value and reading.get('unit') == 'bar'
                and reading.get('sample_time') == channel.samples[-1].timestamp):
            valid[name] = value
    low = any(value < ref['value'] for value in valid.values())
    if not low and set(valid) != set(TIRES):
        return
    if 'tire' not in state.domains:
        state.domains.append('tire')
    add_evidence(incident, 'low_wheel_pressure', low, 'simulated_sensor', reference,
                 json.dumps({'readings': valid, 'handbook': handbook}, sort_keys=True),
                 sensor_revision=sim.revision, fixture_id=sim.fixture_id, context='demo')


def resolve(incident, domain):
    state, sim = incident.diagnostic_state, incident.sensor_simulation
    used, ignored = [], []
    for item in state.evidence:
        valid = (not item.superseded and item.incident_id == incident.id and item.context == state.context
                 and item.symptom in bayes.SYMPTOMS[domain])
        if item.source == 'simulated_sensor':
            valid = valid and state.context == 'demo' and sim.enabled and item.sensor_revision == sim.revision and item.fixture_id == sim.fixture_id and state.parked is True and state.cold is True
        (used if valid else ignored).append(item)
    observations, conflicts = {}, []
    for symptom in bayes.SYMPTOMS[domain]:
        values = {item.value for item in used if item.symptom == symptom and item.value is not None}
        observations[symptom] = next(iter(values)) if len(values) == 1 else None
        if len(values) > 1:
            conflicts.append(symptom)
    return observations, conflicts, used, ignored


def classify(incident, domain):
    sync_sensors(incident)
    state = incident.diagnostic_state
    base = dict(domain=domain, context=state.context, evidence_revision=state.revision)
    if domain not in bayes.SYMPTOMS:
        return Inference(**base, status='unsupported_domain', reason='Only configured synthetic fault domains are modeled.')
    observations, conflicts, used, ignored = resolve(incident, domain)
    # Message snapshots must not share mutable evidence objects with the live store.
    base.update(evidence_used=[e.model_copy(deep=True) for e in used],
                evidence_ignored=[e.model_copy(deep=True) for e in ignored], conflicts=conflicts)
    try:
        model = bayes.load_model()
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return Inference(**base, status='model_error', reason='The trained model is missing or invalid; no probabilities were generated.')
    base['model_version'] = model['model_version']
    # Hash parameters as well as version so a replaced artifact cannot reuse stale results.
    key = json.dumps([state.revision, state.context, domain, model,
                      [e.model_dump() for e in used], [e.model_dump() for e in ignored]], sort_keys=True)
    if key in state.cache:
        return state.cache[key].model_copy(deep=True)
    if not any(value is not None for value in observations.values()):
        result = Inference(**base, status='inconclusive' if conflicts else 'insufficient_evidence',
                           reason='Conflicting reports require clarification.' if conflicts else 'No supported observations; priors are not findings.')
    else:
        probabilities = bayes.posterior(model['domains'][domain], observations)
        ranking = sorted(probabilities.items(), key=lambda item: -item[1])
        inconclusive = bool(state.context == 'unspecified' or conflicts or ranking[0][0] == 'other_or_unmodeled' or ranking[0][1] < .60 or ranking[0][1] - ranking[1][1] < .15)
        result = Inference(**base, status='inconclusive' if inconclusive else 'ok',
                           ranked_hypotheses=[Hypothesis(fault_id=f, posterior=p) for f, p in ranking],
                           reason='Evidence does not distinguish a supported category reliably within this toy model.' if inconclusive else 'Leading category within the synthetic model; unconfirmed.')
    state.cache[key] = result.model_copy(deep=True)
    return result


def apply_brake_safety(incident):
    # A short answer to a brake question is also a reported safety symptom.
    _, _, cooling, _ = resolve(incident, 'cooling')
    if any(e.value is True and e.symptom in ('high_temperature_warning', 'overheating_stationary') for e in cooling):
        incident.safety = SAFETY
    observations, _, used, _ = resolve(incident, 'brake')
    if any(item.value is True for item in used if item.symptom in bayes.SYMPTOMS['brake']):
        incident.safety = SAFETY


def next_question(incident, results):
    state = incident.diagnostic_state
    if incident.safety or state.stopped or not state.domains:
        return None
    if state.context == 'unspecified':
        if state.asked.get('context') == 'declined':
            return None
        return Question(id='context', kind='context', text='Should I use the available sensor readings for this investigation?')
    for result in results:
        for symptom in result.conflicts:
            signature = 'conflict:' + symptom + ':' + ','.join(e.id for e in result.evidence_used if e.symptom == symptom)
            if signature not in state.asked:
                return Question(id=signature, domain=result.domain, symptom=symptom, kind='conflict',
                                text='Your reports conflict. ' + QUESTIONS[symptom])
    # A pending unanswered question remains stable through provider retries.
    if state.pending:
        pending = state.pending
        if pending.symptom:
            observations, conflicts, _, _ = resolve(incident, pending.domain)
            if observations[pending.symptom] is None and (pending.kind != 'conflict' or pending.symptom in conflicts):
                return pending
        elif pending.kind == 'conditions' and getattr(state, pending.id) is None:
            return pending
        state.pending = None
    if any(result.status == 'model_error' for result in results):
        return None
    try:
        model = bayes.load_model()
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None
    choices = []
    for domain in state.domains:
        observations, conflicts, _, _ = resolve(incident, domain)
        for symptom in bayes.SYMPTOMS[domain]:
            if observations[symptom] is not None or symptom in conflicts or symptom in state.asked:
                continue
            gain = bayes.information_gain(model['domains'][domain], observations, symptom)
            if gain > .01:
                choices.append((gain, domain, symptom))
    if not choices:
        return None
    # Stable iteration order breaks equal-gain ties.
    gain, domain, symptom = max(choices, key=lambda item: item[0])
    if symptom == 'low_wheel_pressure' and state.context == 'demo' and incident.sensor_simulation.enabled:
        for condition, question in [('parked', 'Was the vehicle parked when these readings were recorded?'),
                                    ('cold', 'Were the tires cold when these readings were recorded?')]:
            if getattr(state, condition) is None and condition not in state.asked:
                return Question(id=condition, kind='conditions', domain='tire', text=question, information_gain=gain)
        if state.parked is not True or state.cold is not True:
            return None
        # Valid readings must actually be executed through sensor tools, not inferred from presets.
        return None
    text = QUESTIONS[symptom]
    return Question(id=symptom, domain=domain, symptom=symptom, text=text, information_gain=gain)


def snapshot(incident, answer, initiator='backend'):
    results = [classify(incident, domain) for domain in incident.diagnostic_state.domains]
    answer.diagnostic_inference = results
    for result in results:
        payload = result.model_dump()
        if not any(e.tool == 'classify_diagnosis' and e.result == payload for e in answer.activity):
            answer.activity.append(Event(tool='classify_diagnosis', initiator=initiator, arguments={'domain': result.domain},
                                         summary='Synthetic Bayesian classification: ' + result.status, result=payload))
    return results


def complete_sensor_evidence(incident, answer):
    """Disclosed backend completion when the model omitted a needed current read."""
    from .sensors import ReadSensors, read
    state, sim = incident.diagnostic_state, incident.sensor_simulation
    if state.context != 'demo' or 'tire' not in state.domains or not sim.enabled or state.parked is not True or state.cold is not True:
        return
    if any(e.source == 'simulated_sensor' and e.sensor_revision == sim.revision and not e.superseded for e in state.evidence):
        return
    arguments = {'sensor_names': ['tpms_per_wheel_pressure_bar']}
    result = read(sim, ReadSensors(**arguments))
    event = Event(tool='read_vehicle_sensors', initiator='backend', arguments=arguments, result=result,
                  summary='Read current tire pressures for Bayesian evidence')
    answer.activity.append(event)
    record_sensor_result(incident, result, event.id)


def finish(incident, answer, preserve_generated=False):
    if not incident.diagnostic_state.active and not incident.safety:
        if preserve_generated:
            finalize_dialogue(incident, answer, None)
        return False
    complete_sensor_evidence(incident, answer)
    results = snapshot(incident, answer)
    state = incident.diagnostic_state
    if not results:
        return False
    question = next_question(incident, results)
    answer.follow_up_question = question
    state.pending = question
    if question:
        state.asked.setdefault(question.id, 'pending')
    if preserve_generated and answer.text and not incident.safety:
        finalize_dialogue(incident, answer, question)
        return True
    prefix = ''
    if incident.safety:
        answer.text = SAFETY
    elif question:
        if question.kind == 'conflict':
            answer.text = prefix + 'I need to clarify the conflicting observations before narrowing the issue.'
        elif question.kind == 'context':
            answer.text = 'I need to confirm which readings apply to this vehicle before drawing a conclusion.'
        elif question.kind == 'conditions':
            answer.text = 'The pressure comparison requires readings taken with cold tires while parked.'
        else:
            facts = []
            for result in results:
                observations, _, _, _ = resolve(incident, result.domain)
                if observations.get('yellow_tpms_warning') is True:
                    facts.append('A yellow tire-pressure warning is reported.')
                if observations.get('low_wheel_pressure') is True:
                    facts.append('A below-reference tire reading is observed' + ' in the available readings.')
            statement = prefix + (' '.join(facts) if facts else 'The available observations do not yet distinguish the fault category.')
            answer.text = statement[0].upper() + statement[1:]
    elif any(r.status == 'model_error' for r in results):
        answer.text = 'The local diagnostic model is unavailable. No diagnostic probabilities were generated. Seek qualified inspection for an unresolved issue.'
    else:
        conclusions = []
        for result in results:
            if result.status == 'ok':
                cause = LABELS[result.ranked_hypotheses[0].fault_id]
                clues = ', '.join(e.symptom.replace('_', ' ') + (' reported' if e.source == 'user_reported' else ' observed')
                                  for e in result.evidence_used if e.value is True)
                sentence = f'{prefix}the observations support {cause} as the leading unconfirmed category' + (f' ({clues}).' if clues else '.')
                conclusions.append(sentence[0].upper() + sentence[1:])
            else:
                conclusions.append(f'The {result.domain} evidence is inconclusive; this limited model cannot identify a supported cause.')
        answer.text = ' '.join(conclusions) + ' Arrange qualified inspection for confirmation; this does not establish roadworthiness.'
    # Generated-text offsets no longer apply to the backend-owned response.
    answer.citations = [c.model_copy(update={'start_index': None, 'end_index': None}) for c in answer.citations] if not incident.safety else []
    return True


def refresh_current(incident):
    """Latest report state is recalculated; old message snapshots are never rewritten."""
    return [classify(incident, domain).model_dump() for domain in incident.diagnostic_state.domains]


def unresolved_questions(incident):
    state = incident.diagnostic_state
    if incident.safety:
        return []
    questions = [state.pending] if state.pending else []
    for domain in state.domains:
        observations, _, _, _ = resolve(incident, domain)
        for symptom, value in observations.items():
            if value is None and not any(q.symptom == symptom for q in questions):
                questions.append(Question(id=symptom, text=QUESTIONS[symptom], domain=domain, symptom=symptom))
    return [q.model_dump() for q in questions]


def finalize_dialogue(incident, answer, question):
    """Keep source-grounded prose; expose at most one question without duplicate text."""
    original = answer.text
    # Numeric confidence belongs to the computed model inspector, never invented prose.
    paragraphs = original.split('\n\n')
    invalid = lambda p: bool(re.search(r'\b\d+(?:\.\d+)?\s*%.{0,40}(?:certain|confidence|probab|likelihood|sure)|(?:confidence|probab|likelihood|posterior).{0,40}\d+(?:\.\d+)?\s*%|invented causes|confirmed diagnosis', p, re.IGNORECASE))
    if any(invalid(p) for p in paragraphs):
        answer.text = '\n\n'.join(p for p in paragraphs if not invalid(p)).strip() or 'The available evidence does not establish a confirmed cause.'
        answer.citations = [c.model_copy(update={'start_index': None, 'end_index': None}) for c in answer.citations]
        original = answer.text
    questions = list(re.finditer(r'[^.!?\n]*\?', original))
    if questions and (incident.mode != 'bmw_g20' or question is None) and not all(incident.vehicle.model_dump().values()) and re.search(r'\b(make|model|year)\b', questions[0].group(), re.IGNORECASE) and not incident.diagnostic_state.stopped:
        question = Question(id='vehicle:' + answer.id, text=questions[0].group().strip())
    if question is None and questions and not incident.diagnostic_state.stopped:
        question = Question(id='model:' + answer.id, text=questions[0].group().strip())
    if questions:
        pieces = []
        end = 0
        for match in questions:
            pieces.append(original[end:match.start()])
            end = match.end()
        pieces.append(original[end:])
        answer.text = ''.join(pieces).strip()
        answer.citations = [c.model_copy(update={'start_index': None, 'end_index': None}) for c in answer.citations]
    if question and incident.diagnostic_state.context == 'demo':
        question = question.model_copy(update={'text': question.text.replace('For the fictional demo vehicle: ', '').replace('the fictional vehicle', 'the vehicle').replace('demo readings', 'sensor readings').replace('demo conditions', 'recorded conditions')})
    answer.follow_up_question = question
    incident.diagnostic_state.pending = question
    if not answer.text and question:
        answer.text = 'Let us narrow this down using the evidence available.'
