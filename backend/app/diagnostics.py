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
    'tire_pressure_loss': 'tire pressure loss', 'tpms_sensor_issue': 'a TPMS monitoring issue',
    'brake_hydraulic_concern': 'a brake hydraulic concern', 'brake_indicator_issue': 'a brake indicator issue',
    'other_or_unmodeled': 'an issue outside this limited model',
}
QUESTIONS = {
    'yellow_tpms_warning': 'Is a yellow tire-pressure warning currently showing on the dashboard?',
    'low_wheel_pressure': 'Do you already have a cold-tire gauge reading below the correct pressure on the vehicle label or manual?',
    'soft_brake_pedal': 'Have you already noticed the brake pedal feeling soft or spongy?',
    'persistent_red_warning': 'Is a red brake warning staying on?',
}
PATTERNS = {
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
            item.superseded = True
    elif existing and all(e.value == value for e in existing) and source == 'user_reported':
        return
    bump(state)
    state.evidence.append(Evidence(incident_id=incident.id, symptom=symptom, value=value, source=source,
                                 reference=reference, quote=quote, timestamp=now(), revision=state.revision,
                                 context=context, **metadata))


def set_context(incident, context):
    state = incident.diagnostic_state
    if state.context != context:
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
    hypothetical = bool(re.search(HYPOTHETICAL, text))
    if not hypothetical:
        if re.search(r'\b(?:real (?:car|vehicle)|actual (?:car|vehicle)|my real car|not (?:the )?demo)\b', text):
            set_context(incident, 'real')
        elif re.search(r'\b(?:demo|fictional|simulated|synthetic)\b', text):
            set_context(incident, 'demo')
            state.active = bool(state.domains)
        elif pending and pending.kind == 'context':
            if text.strip(' .!') in ('real', 'my car'):
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
        elif pending.symptom and answered:
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
        for clause in re.split(r'[.;!\n]|\bbut\b', text):
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
        for domain, pattern in [('tire', r'\b(?:tire|tyre|tpms)\b'), ('brake', r'\b(?:brake|brakes|pedal)\b')]:
            if re.search(pattern, text) and domain not in state.domains:
                state.domains.append(domain)
                bump(state)
            if re.search(pattern, text):
                state.active = True
    if pending and pending.symptom and any(e.reference == user.id and e.symptom == pending.symptom for e in state.evidence):
        state.asked[pending.id] = 'answered'
        state.pending = None
    apply_brake_safety(incident)


def sync_sensors(incident):
    state, sim = incident.diagnostic_state, incident.sensor_simulation
    if state.sensor_revision != sim.revision:
        state.sensor_revision = sim.revision
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
        return Inference(**base, status='unsupported_domain', reason='Only tire and brake categories are modeled.')
    observations, conflicts, used, ignored = resolve(incident, domain)
    base.update(evidence_used=used, evidence_ignored=ignored, conflicts=conflicts)
    try:
        model = bayes.load_model()
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return Inference(**base, status='model_error', reason='The trained model is missing or invalid; no probabilities were generated.')
    base['model_version'] = model['model_version']
    # Hash parameters as well as version so a replaced artifact cannot reuse stale results.
    key = json.dumps([state.revision, state.context, domain, model], sort_keys=True)
    if key in state.cache:
        return state.cache[key].model_copy(deep=True)
    if not any(value is not None for value in observations.values()):
        result = Inference(**base, status='inconclusive' if conflicts else 'insufficient_evidence',
                           reason='Conflicting reports require clarification.' if conflicts else 'No supported observations; priors are not findings.')
    else:
        probabilities = bayes.posterior(model['domains'][domain], observations)
        ranking = sorted(probabilities.items(), key=lambda item: -item[1])
        inconclusive = bool(conflicts or ranking[0][0] == 'other_or_unmodeled' or ranking[0][1] < .60 or ranking[0][1] - ranking[1][1] < .15)
        result = Inference(**base, status='inconclusive' if inconclusive else 'ok',
                           ranked_hypotheses=[Hypothesis(fault_id=f, posterior=p) for f, p in ranking],
                           reason='Evidence does not distinguish a supported category reliably within this toy model.' if inconclusive else 'Leading category within the synthetic model; unconfirmed.')
    state.cache[key] = result.model_copy(deep=True)
    return result


def apply_brake_safety(incident):
    # A short answer to a brake question is also a reported safety symptom.
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
        return Question(id='context', kind='context', text='Is this investigation about the fictional demo vehicle or your real vehicle?')
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
    for result in results:
        for symptom in result.conflicts:
            signature = 'conflict:' + symptom + ':' + ','.join(e.id for e in result.evidence_used if e.symptom == symptom)
            if signature not in state.asked:
                return Question(id=signature, domain=result.domain, symptom=symptom, kind='conflict',
                                text='Your reports conflict. ' + QUESTIONS[symptom])
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
        for condition, question in [('parked', 'Were these demo readings recorded while the fictional vehicle was parked?'),
                                    ('cold', 'Were the fictional demo tires cold when these readings were recorded?')]:
            if getattr(state, condition) is None and condition not in state.asked:
                return Question(id=condition, kind='conditions', domain='tire', text=question, information_gain=gain)
        if state.parked is not True or state.cold is not True:
            return None
        # Valid readings must actually be executed through sensor tools, not inferred from presets.
        return None
    text = QUESTIONS[symptom]
    if state.context == 'demo':
        text = 'For the fictional demo vehicle: ' + text[0].lower() + text[1:]
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
                  summary='Backend workflow read current simulated tires for Bayesian evidence')
    answer.activity.append(event)
    record_sensor_result(incident, result, event.id)


def finish(incident, answer):
    if not incident.diagnostic_state.active and not incident.safety:
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
    prefix = 'For the fictional demo vehicle, ' if state.context == 'demo' else ''
    if incident.safety:
        answer.text = SAFETY
    elif question:
        if question.kind == 'conflict':
            answer.text = prefix + 'I need to clarify the conflicting observations before narrowing the issue.'
        elif question.kind == 'context':
            answer.text = 'The simulated readings cannot establish what is happening with your real vehicle.'
        elif question.kind == 'conditions':
            answer.text = 'The synthetic handbook reference applies only to cold, parked demo conditions.'
        else:
            answer.text = prefix + 'The available observations do not yet distinguish the fault category.'
    elif any(r.status == 'model_error' for r in results):
        answer.text = 'The local diagnostic model is unavailable. No diagnostic probabilities were generated. Seek qualified inspection for an unresolved issue.'
    else:
        conclusions = []
        for result in results:
            if result.status == 'ok':
                cause = LABELS[result.ranked_hypotheses[0].fault_id]
                clues = ', '.join(e.symptom.replace('_', ' ') + (' reported' if e.source == 'user_reported' else ' simulated')
                                  for e in result.evidence_used if e.value is True)
                conclusions.append(f'{prefix}the observations support {cause} as the leading unconfirmed category in this synthetic model' + (f' ({clues}).' if clues else '.'))
            else:
                conclusions.append(f'The {result.domain} evidence is inconclusive; this limited model cannot identify a supported cause.')
        answer.text = ' '.join(conclusions) + ' Arrange qualified inspection for confirmation; this does not establish roadworthiness.'
    # Generated-text offsets no longer apply to the backend-owned response.
    answer.citations = [c.model_copy(update={'start_index': None, 'end_index': None}) for c in answer.citations] if not incident.safety else []
    return True


def refresh_current(incident):
    """Latest report state is recalculated; old message snapshots are never rewritten."""
    return [classify(incident, domain).model_dump() for domain in incident.diagnostic_state.domains]
