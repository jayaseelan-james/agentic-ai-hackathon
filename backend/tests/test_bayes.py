import asyncio
import copy
import hashlib
import json
import math

import pytest
from fastapi.testclient import TestClient

from backend import train_bayes
from backend.app import bayes, main
from backend.app.agent import investigate
from backend.app.diagnostics import (add_evidence, classify, finish, ingest_user, next_question,
                                     record_sensor_result, resolve)
from backend.app.schemas import Incident, Message
from backend.app.sensors import ReadSensors, SensorChange, change_sensor, read
from backend.app.tools import dispatch, mechanic_report
from backend.tests.fakes import FakeProvider


def turn(incident, text):
    user = Message(role='user', text=text)
    answer = Message(role='assistant', state='complete', reply_to=user.id)
    incident.messages.extend([user, answer])
    ingest_user(incident, user)
    finish(incident, answer)
    return answer


def demo(text='The fictional demo vehicle has a yellow TPMS warning. Safely parked, tires are cold.'):
    incident = Incident()
    incident.sensor_simulation.enabled = True
    change_sensor(incident.sensor_simulation, 'tpms_rear_left_bar', SensorChange(kind='preset', preset='tire_slow_loss'))
    turn(incident, text)
    return incident


def test_training_reproducible_separate_splits_and_learned_counts(tmp_path):
    model = train_bayes.train(tmp_path)
    assert model == train_bayes.train(tmp_path)
    assert model == bayes.load_model()
    for domain, network in model['domains'].items():
        assert network['datasets']['train']['count'] == 10000
        assert network['datasets']['validation']['count'] == 2000
        assert network['datasets']['train']['seed'] != network['datasets']['validation']['seed']
        for split in ('train', 'validation'):
            data = network['datasets'][split]
            payload = (tmp_path / data['file']).read_bytes()
            assert hashlib.sha256(payload).hexdigest() == data['sha256']
            assert len(payload.splitlines()) == data['count']
        for fault, values in train_bayes.GENERATORS[domain].items():
            n = network['class_counts'][fault]
            assert network['priors'][fault] == (n + 1) / (10000 + len(train_bayes.GENERATORS[domain]))
            assert abs(network['priors'][fault] - values[0]) < .02
            for symptom, generating_p in zip(network['symptoms'], values[1:]):
                learned = network['likelihoods'][fault][symptom]
                assert learned == (network['true_counts'][fault][symptom] + 1) / (n + 2)
                assert abs(learned - generating_p) < .04
        assert 0 <= network['validation']['synthetic_agreement'] <= 1


def test_inference_uses_fitted_parameters_and_matches_manual_arithmetic():
    incident = demo()
    result = classify(incident, 'tire')
    network = bayes.load_model()['domains']['tire']
    weights = {f: network['priors'][f] * network['likelihoods'][f]['yellow_tpms_warning'] * network['likelihoods'][f]['low_wheel_pressure'] for f in network['priors']}
    assert result.status == 'ok'
    assert result.ranked_hypotheses[0].fault_id == 'tire_pressure_loss'
    for item in result.ranked_hypotheses:
        assert item.posterior == pytest.approx(weights[item.fault_id] / sum(weights.values()))
    assert sum(item.posterior for item in result.ranked_hypotheses) == pytest.approx(1)
    assert result.ranked_hypotheses[0].posterior == pytest.approx(.8842, abs=.02)
    assert any(e.source == 'simulated_sensor' and 'DEMO_HANDBOOK_V1' in e.quote for e in result.evidence_used)


def test_unknown_marginalized_no_priors_as_findings_and_domain_separation():
    incident = Incident()
    assert classify(incident, 'tire').status == 'insufficient_evidence'
    assert not classify(incident, 'tire').ranked_hypotheses
    answer = turn(incident, 'My yellow TPMS warning is showing.')
    result = answer.diagnostic_inference[0]
    expected = bayes.posterior(bayes.load_model()['domains']['tire'], {'yellow_tpms_warning': True})
    assert {r.fault_id: r.posterior for r in result.ranked_hypotheses} == pytest.approx(expected)
    assert classify(incident, 'brake').status == 'insufficient_evidence'
    assert classify(incident, 'engine').status == 'unsupported_domain'
    assert all(e.symptom != 'low_wheel_pressure' for e in result.evidence_used)


@pytest.mark.parametrize('text', ['Maybe my yellow TPMS warning is showing.', 'I am not sure whether the yellow TPMS warning is on.'])
def test_uncertain_reports_remain_unknown(text):
    incident = Incident()
    turn(incident, text)
    assert classify(incident, 'tire').status == 'insufficient_evidence'


@pytest.mark.parametrize('text', ['If my yellow TPMS warning is on, what should happen?', 'How does a TPMS warning work?', 'Imagine a soft brake pedal.'])
def test_hypothetical_reports_do_not_enter_model(text):
    incident = Incident()
    turn(incident, text)
    assert not incident.diagnostic_state.evidence


def test_duplicates_negatives_conflicts_corrections_and_decline():
    incident = Incident()
    turn(incident, 'My yellow TPMS warning is on.')
    before = classify(incident, 'tire')
    turn(incident, 'My yellow TPMS warning is on.')
    assert len(incident.diagnostic_state.evidence) == 1
    assert classify(incident, 'tire').ranked_hypotheses == before.ranked_hypotheses
    answer = turn(incident, 'No yellow TPMS warning is on.')
    result = answer.diagnostic_inference[0]
    assert result.conflicts == ['yellow_tpms_warning']
    assert result.status == 'inconclusive'
    assert answer.follow_up_question.kind == 'conflict'
    answer = turn(incident, "I don't know")
    assert answer.follow_up_question is None
    assert classify(incident, 'tire').conflicts
    answer = turn(incident, 'Correction: the yellow TPMS warning is not on.')
    assert not answer.diagnostic_inference[0].conflicts
    assert resolve(incident, 'tire')[0]['yellow_tpms_warning'] is False


def test_information_gain_question_and_short_answers_without_repetition():
    incident = Incident()
    answer = turn(incident, 'My yellow TPMS warning is showing.')
    question = answer.follow_up_question
    assert question.symptom == 'low_wheel_pressure'
    assert question.information_gain > .01
    assert question.text.count('?') == 1
    assert not answer.text.endswith('?')  # Question is a separate typed field.
    answer = turn(incident, 'yes')
    assert resolve(incident, 'tire')[0]['low_wheel_pressure'] is True
    assert answer.follow_up_question is None
    assert 'leading unconfirmed category' in answer.text
    assert '%' not in answer.text
    other = Incident()
    turn(other, 'My yellow TPMS warning is showing.')
    assert turn(other, "I don't know").follow_up_question is None
    assert any(q['symptom'] == 'low_wheel_pressure' for q in mechanic_report(other)['unresolved_questions'])
    assert turn(other, 'My yellow TPMS warning is showing.').follow_up_question is None
    standalone = Incident()
    turn(standalone, 'yes')
    assert not standalone.diagnostic_state.evidence


def test_conflicts_take_priority_over_an_existing_question():
    incident = Incident()
    turn(incident, 'My yellow TPMS warning is on.')
    answer = turn(incident, 'The yellow TPMS warning is not on.')
    assert answer.follow_up_question.kind == 'conflict'


def test_sensor_context_is_explicit_and_real_evidence_never_combined():
    incident = Incident()
    incident.sensor_simulation.enabled = True
    answer = turn(incident, 'My yellow TPMS warning is on.')
    assert answer.follow_up_question.kind == 'context'
    assert not any(e.source == 'simulated_sensor' for e in incident.diagnostic_state.evidence)
    turn(incident, 'My real car')
    record_sensor_result(incident, read(incident.sensor_simulation, ReadSensors(sensor_names=list(incident.sensor_simulation.channels))), 'test')
    assert not any(e.source == 'simulated_sensor' for e in classify(incident, 'tire').evidence_used)
    answer = turn(incident, 'Investigate the fictional demo vehicle. Safely parked, tires are cold.')
    assert all(e.context == 'demo' for e in answer.diagnostic_inference[0].evidence_used)
    assert any(e.context == 'real' for e in answer.diagnostic_inference[0].evidence_ignored)


def test_partial_read_false_requires_all_wheels_and_results_are_validated():
    incident = demo('Investigate fictional demo tire sensors. Safely parked, tires are cold.')
    state = incident.diagnostic_state
    state.evidence.clear()
    state.cache.clear()
    change_sensor(incident.sensor_simulation, 'tpms_rear_left_bar', SensorChange(kind='restore'))
    partial = read(incident.sensor_simulation, ReadSensors(sensor_names=['tpms_front_left_bar']))
    record_sensor_result(incident, partial, 'partial')
    assert not state.evidence
    forged = copy.deepcopy(partial)
    forged['readings']['tpms_front_left_bar']['value'] = 1.0
    record_sensor_result(incident, forged, 'forged')
    assert not state.evidence
    full = read(incident.sensor_simulation, ReadSensors(sensor_names=['tpms_per_wheel_pressure_bar']))
    record_sensor_result(incident, full, 'full')
    assert resolve(incident, 'tire')[0]['low_wheel_pressure'] is False


def test_stale_revision_disabling_cross_chat_and_immutable_history():
    incident = demo()
    old = incident.messages[-1].diagnostic_inference[0].model_dump()
    result = read(incident.sensor_simulation, ReadSensors(sensor_names=['tpms_per_wheel_pressure_bar']))
    change_sensor(incident.sensor_simulation, 'tpms_rear_left_bar', SensorChange(kind='restore'))
    record_sensor_result(incident, result, 'stale')
    assert resolve(incident, 'tire')[0]['low_wheel_pressure'] is None
    assert mechanic_report(incident)['diagnostic_inference'][0]['evidence_ignored']
    assert incident.messages[-1].diagnostic_inference[0].model_dump() == old
    turn(incident, 'Investigate the demo tire warning again.')
    assert resolve(incident, 'tire')[0]['low_wheel_pressure'] is False
    incident.sensor_simulation.enabled = False
    assert resolve(incident, 'tire')[0]['low_wheel_pressure'] is None
    other = demo()
    foreign = copy.deepcopy(other.diagnostic_state.evidence[-1])
    incident.diagnostic_state.evidence.append(foreign)
    assert foreign in classify(incident, 'tire').evidence_ignored


def test_conditions_and_missing_handbook_leave_pressure_unknown(monkeypatch, tmp_path):
    incident = demo('The fictional demo vehicle has a yellow TPMS warning.')
    assert not any(e.source == 'simulated_sensor' for e in incident.diagnostic_state.evidence)
    assert incident.messages[-1].follow_up_question.id == 'parked'
    assert turn(incident, 'yes').follow_up_question.id == 'cold'
    monkeypatch.setattr(bayes, 'DATA', tmp_path)
    answer = turn(incident, 'yes')
    assert resolve(incident, 'tire')[0]['low_wheel_pressure'] is None
    assert answer.diagnostic_inference[0].ranked_hypotheses


def test_model_errors_never_fabricate_probabilities_or_weaken_safety(monkeypatch, tmp_path):
    incident = Incident()
    monkeypatch.setattr(bayes, 'MODEL_PATH', tmp_path / 'missing.json')
    answer = turn(incident, 'My yellow TPMS warning is on.')
    assert answer.diagnostic_inference[0].status == 'model_error'
    assert not answer.diagnostic_inference[0].ranked_hypotheses
    assert not answer.follow_up_question
    answer = turn(incident, 'My brake pedal feels soft and red brake warning stays on.')
    assert answer.text == incident.safety
    assert not answer.follow_up_question
    assert all(not r.ranked_hypotheses for r in answer.diagnostic_inference)


@pytest.mark.parametrize('mutation', ['nan', 'priors', 'graph', 'likelihoods'])
def test_malformed_models(mutation, tmp_path):
    model = bayes.load_model()
    network = model['domains']['tire']
    if mutation == 'nan':
        network['priors']['tire_pressure_loss'] = float('nan')
    elif mutation == 'priors':
        network['priors']['tire_pressure_loss'] = .99
    elif mutation == 'graph':
        network['symptoms'] = ['invented']
    else:
        network['likelihoods']['tire_pressure_loss']['yellow_tpms_warning'] = -1
    path = tmp_path / 'bad.json'
    path.write_text(json.dumps(model))
    with pytest.raises(ValueError):
        bayes.load_model(path)


def test_stop_request_and_general_conversation_are_preserved():
    incident = Incident()
    turn(incident, 'My yellow TPMS warning is on.')
    assert not turn(incident, 'Stop asking questions.').follow_up_question
    user = Message(role='user', text='What vehicle details have I provided?')
    ingest_user(incident, user)
    answer = Message(role='assistant', text='Your vehicle details are not provided.')
    assert not finish(incident, answer)
    assert answer.text == 'Your vehicle details are not provided.'


def test_scoped_negation_and_digressions_do_not_misattribute_short_answers():
    incident = Incident()
    turn(incident, 'My yellow TPMS warning is showing and no tire pressure is low.')
    observations = resolve(incident, 'tire')[0]
    assert observations == {'yellow_tpms_warning': True, 'low_wheel_pressure': False}
    other = Incident()
    turn(other, 'My yellow TPMS warning is showing.')
    turn(other, 'What vehicle details have I provided?')
    turn(other, 'yes')
    assert resolve(other, 'tire')[0]['low_wheel_pressure'] is None


def test_unknown_answer_with_if_is_not_misread_as_hypothetical():
    incident = Incident()
    turn(incident, 'My yellow TPMS warning is showing.')
    answer = turn(incident, "I don't know if any tire is low.")
    assert answer.follow_up_question is None
    assert resolve(incident, 'tire')[0]['low_wheel_pressure'] is None


def test_user_correction_cannot_erase_a_current_conflicting_sensor_observation():
    incident = demo()
    answer = turn(incident, 'Correction: no tire pressure is low.')
    assert 'low_wheel_pressure' in answer.diagnostic_inference[0].conflicts
    assert any(e.source == 'simulated_sensor' for e in answer.diagnostic_inference[0].evidence_used)


def test_corrections_and_context_clarification_do_not_rewrite_old_snapshots():
    incident = Incident()
    answer = turn(incident, 'My yellow TPMS warning is showing.')
    old = answer.diagnostic_inference[0].model_dump()
    turn(incident, 'Correction: no yellow TPMS warning is showing.')
    assert answer.diagnostic_inference[0].model_dump() == old
    other = Incident()
    other.sensor_simulation.enabled = True
    answer = turn(other, 'My yellow TPMS warning is showing.')
    old = answer.diagnostic_inference[0].model_dump()
    turn(other, 'The fictional demo vehicle.')
    assert answer.diagnostic_inference[0].model_dump() == old


def test_model_tool_and_backend_ensure_use_same_result_and_retries_deduplicate():
    incident = Incident()
    user = Message(role='user', text='My yellow TPMS warning is showing.')
    answer = Message(role='assistant', state='processing')
    incident.messages.extend([user, answer])
    provider = FakeProvider([
        {'id': '1', 'steps': [{'type': 'function_call', 'name': 'classify_diagnosis', 'arguments': {'domain': 'tire'}, 'id': 'classify'}]},
        {'id': '2', 'status': 'completed', 'steps': [{'type': 'model_output', 'content': [{'type': 'text', 'text': 'Here are five invented causes and 99% certainty.'}]}]},
    ])
    asyncio.run(investigate(incident, user, answer, {}, provider))
    assert 'invented' not in answer.text and '99%' not in answer.text
    assert answer.follow_up_question.symptom == 'low_wheel_pressure'
    events = [e for e in answer.activity if e.tool == 'classify_diagnosis']
    assert len(events) == 1 and events[0].initiator == 'model'
    assert events[0].result == answer.diagnostic_inference[0].model_dump()
    before = copy.deepcopy(incident.diagnostic_state.evidence)
    ingest_user(incident, user)
    finish(incident, answer)
    assert incident.diagnostic_state.evidence == before
    assert len([e for e in answer.activity if e.tool == 'classify_diagnosis']) == 1
    with pytest.raises(ValueError):
        dispatch('classify_diagnosis', {'domain': 'tire', 'posterior': 1, 'incident_id': 'other'}, incident)


def test_api_local_safety_and_inference_without_provider(monkeypatch):
    main.incidents.clear(); main.requests.clear(); main.locks.clear()
    def missing():
        raise ValueError('Gemini is not configured. Set GEMINI_API_KEY.')
    monkeypatch.setattr(main, 'get_provider', missing)
    with TestClient(main.app) as client:
        id = client.post('/api/incidents', json={}).json()['id']
        response = client.post(f'/api/incidents/{id}/messages', data={'text': 'My brake pedal feels soft and red brake warning stays on.', 'request_id': 'brake'}).json()
        answer = response['messages'][-1]
        assert answer['state'] == 'complete'
        assert answer['provider'] == 'safety_rules'
        assert not answer['follow_up_question']
        assert answer['diagnostic_inference'][0]['domain'] == 'brake'
        report = client.get(f'/api/incidents/{id}/report').json()
        assert report['diagnostic_inference'] and report['diagnostic_history']
        assert not report['unresolved_questions']


@pytest.mark.parametrize('domain,text', [
    ('cooling', 'My coolant loss is recurring.'),
    ('starting_charging', 'My engine cranks slowly.'),
    ('engine_running', 'My engine idles roughly.'),
])
def test_expanded_domains_are_trained_and_ask_one_question(domain, text):
    incident = Incident()
    answer = turn(incident, text)
    result = next(r for r in answer.diagnostic_inference if r.domain == domain)
    assert len(result.ranked_hypotheses) == 4
    assert sum(r.posterior for r in result.ranked_hypotheses) == pytest.approx(1)
    assert answer.follow_up_question and answer.follow_up_question.domain == domain
    assert answer.follow_up_question.text.count('?') == 1
    assert not classify(incident, 'tire').ranked_hypotheses
    assert dispatch('classify_diagnosis', {'domain': domain}, incident)['domain'] == domain


def test_expanded_model_counts_and_temperature_safety():
    model = bayes.load_model()
    assert len(model['domains']) == 5
    assert sum(len(n['priors']) for n in model['domains'].values()) == 18
    incident = Incident()
    answer = turn(incident, 'My high temperature warning is showing.')
    assert incident.safety and answer.text == incident.safety
    assert answer.follow_up_question is None


def test_customer_fallback_and_questions_use_plain_vehicle_language():
    incident = demo()
    answer = incident.messages[-1]
    text = answer.text + (' ' + answer.follow_up_question.text if answer.follow_up_question else '')
    assert not any(word in text.lower() for word in ('fictional', 'simulated', 'demo', 'synthetic'))
    assert 'leading unconfirmed category' in answer.text
    assert not any(word in ' '.join(mechanic_report(incident)['uncertainties']).lower() for word in ('fictional', 'simulated', 'demo'))
