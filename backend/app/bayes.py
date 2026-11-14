"""Pure local inference. Learned parameters are never supplied by a language model."""
import json
import math
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / 'data'
MODEL_PATH = DATA / 'bayes_model.json'
SYMPTOMS = {
    'tire': ('yellow_tpms_warning', 'low_wheel_pressure'),
    'brake': ('soft_brake_pedal', 'persistent_red_warning'),
    'cooling': ('high_temperature_warning', 'coolant_loss', 'overheating_stationary'),
    'starting_charging': ('slow_cranking', 'clicking_no_crank', 'battery_warning_running'),
    'engine_running': ('rough_idle', 'hesitation', 'check_engine_warning'),
}
FAULTS = {
    'tire': ('tire_pressure_loss', 'tpms_sensor_issue', 'other_or_unmodeled'),
    'brake': ('brake_hydraulic_concern', 'brake_indicator_issue', 'other_or_unmodeled'),
    'cooling': ('coolant_loss_concern', 'coolant_circulation_problem', 'cooling_fan_control_issue', 'other_or_unmodeled'),
    'starting_charging': ('low_battery_charge', 'starter_circuit_issue', 'charging_system_issue', 'other_or_unmodeled'),
    'engine_running': ('ignition_misfire_concern', 'air_fuel_delivery_concern', 'engine_sensor_control_concern', 'other_or_unmodeled'),
}


def load_model(path=None):
    model = json.loads(Path(path or MODEL_PATH).read_text(encoding='utf-8'))
    if not isinstance(model.get('model_version'), str) or not model['model_version']:
        raise ValueError('Missing model version')
    for domain, symptoms in SYMPTOMS.items():
        network = model['domains'][domain]
        if set(network['priors']) != set(FAULTS[domain]) or set(network['likelihoods']) != set(FAULTS[domain]):
            raise ValueError('Invalid fault graph')
        priors = list(network['priors'].values())
        if not all(type(p) in (float, int) and math.isfinite(p) and 0 < p < 1 for p in priors):
            raise ValueError('Invalid priors')
        if not math.isclose(sum(priors), 1, abs_tol=1e-9):
            raise ValueError('Unnormalized priors')
        if network['symptoms'] != list(symptoms):
            raise ValueError('Invalid symptom graph')
        for row in network['likelihoods'].values():
            if set(row) != set(symptoms) or not all(type(p) in (float, int) and math.isfinite(p) and 0 < p < 1 for p in row.values()):
                raise ValueError('Invalid conditional probabilities')
    return model


def posterior(network, observations):
    weights = {}
    for fault, prior in network['priors'].items():
        weight = prior
        for symptom, value in observations.items():
            if value is not None:
                p = network['likelihoods'][fault][symptom]
                weight *= p if value else 1 - p
        weights[fault] = weight
    total = sum(weights.values())
    return {fault: weight / total for fault, weight in weights.items()}


def entropy(distribution):
    return -sum(p * math.log2(p) for p in distribution.values() if p)


def information_gain(network, observations, symptom):
    current = posterior(network, observations)
    yes = sum(p * network['likelihoods'][fault][symptom] for fault, p in current.items())
    expected = sum(prob * entropy(posterior(network, {**observations, symptom: value}))
                   for value, prob in ((True, yes), (False, 1 - yes)))
    return max(0.0, entropy(current) - expected)
