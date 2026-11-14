"""Explicit offline training: python -m backend.train_bayes [--output-dir PATH]."""
import argparse
import hashlib
import json
import random
from collections import Counter
from pathlib import Path

from .app.bayes import DATA, SYMPTOMS, posterior

GENERATOR_VERSION = 'autosage-synthetic-v2'
MODEL_VERSION = 'autosage-trained-v2'
# Hand-authored toy generator, PROJECT_PLAN.md section 6.2. These are not automotive statistics.
GENERATORS = {
    'tire': {'tire_pressure_loss': (0.35, 0.90, 0.80), 'tpms_sensor_issue': (0.20, 0.80, 0.15),
             'other_or_unmodeled': (0.45, 0.10, 0.20)},
    'brake': {'brake_hydraulic_concern': (0.15, 0.90, 0.85), 'brake_indicator_issue': (0.25, 0.08, 0.90),
              'other_or_unmodeled': (0.60, 0.03, 0.05)},
    # Additional hand-authored synthetic assumptions, not measured automotive rates.
    'cooling': {'coolant_loss_concern': (.30,.85,.90,.40), 'coolant_circulation_problem': (.25,.90,.15,.60), 'cooling_fan_control_issue': (.20,.80,.10,.90), 'other_or_unmodeled': (.25,.10,.10,.15)},
    'starting_charging': {'low_battery_charge': (.35,.90,.65,.15), 'starter_circuit_issue': (.20,.15,.90,.05), 'charging_system_issue': (.20,.60,.35,.90), 'other_or_unmodeled': (.25,.10,.10,.10)},
    'engine_running': {'ignition_misfire_concern': (.30,.90,.65,.85), 'air_fuel_delivery_concern': (.25,.60,.90,.60), 'engine_sensor_control_concern': (.20,.35,.40,.90), 'other_or_unmodeled': (.25,.10,.15,.10)},
}


def generate(domain, count, seed):
    rng = random.Random(seed)
    generator = GENERATORS[domain]
    faults = list(generator)
    rows = []
    for _ in range(count):
        fault = rng.choices(faults, weights=[generator[f][0] for f in faults])[0]
        rows.append({'fault': fault, 'symptoms': {s: rng.random() < p for s, p in zip(SYMPTOMS[domain], generator[fault][1:])}})
    return rows


def encode(rows):
    return ''.join(json.dumps(row, sort_keys=True, separators=(',', ':')) + '\n' for row in rows).encode('utf-8')


def fit(domain, rows):
    counts = Counter(row['fault'] for row in rows)
    true_counts = {fault: {s: sum(row['fault'] == fault and row['symptoms'][s] for row in rows)
                           for s in SYMPTOMS[domain]} for fault in GENERATORS[domain]}
    return {
        'symptoms': list(SYMPTOMS[domain]), 'class_counts': dict(counts), 'true_counts': true_counts,
        'priors': {f: (counts[f] + 1) / (len(rows) + len(GENERATORS[domain])) for f in GENERATORS[domain]},
        'likelihoods': {f: {s: (true_counts[f][s] + 1) / (counts[f] + 2) for s in SYMPTOMS[domain]} for f in GENERATORS[domain]},
    }


def train(output_dir=DATA):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    model = {'model_version': MODEL_VERSION, 'generator_version': GENERATOR_VERSION, 'alpha': 1,
             'training_source': 'synthetic_only', 'calibration': 'not_validated', 'domains': {}}
    for index, domain in enumerate(SYMPTOMS):
        train_seed, validation_seed = 42 + index, 1042 + index
        training = generate(domain, 10000, train_seed)
        validation = generate(domain, 2000, validation_seed)
        network = fit(domain, training)
        datasets = {}
        for split, rows, seed in [('train', training, train_seed), ('validation', validation, validation_seed)]:
            payload = encode(rows)
            filename = f'{domain}_{split}.jsonl'
            (output_dir / filename).write_bytes(payload)
            datasets[split] = {'file': filename, 'count': len(rows), 'seed': seed, 'sha256': hashlib.sha256(payload).hexdigest()}
        correct = sum(max(posterior(network, row['symptoms']), key=posterior(network, row['symptoms']).get) == row['fault'] for row in validation)
        network.update(datasets=datasets, validation={'synthetic_agreement': correct / len(validation),
                        'note': 'Agreement with toy-generator labels only; not real diagnostic accuracy.'})
        model['domains'][domain] = network
    (output_dir / 'bayes_model.json').write_text(json.dumps(model, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return model


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=DATA)
    args = parser.parse_args()
    trained = train(args.output_dir)
    print(f"Trained {trained['model_version']} on 10,000 synthetic examples per domain; saved to {args.output_dir}")
