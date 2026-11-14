"""BMW 330i (G20) offline diagnostic reference, recall metadata and sensor caveats."""
from functools import lru_cache
import json
from pathlib import Path
import re

from pydantic import BaseModel, ConfigDict, Field

CAR_DOCS = Path(__file__).resolve().parents[2] / 'car_docs'
BMW_MAKE = 'BMW'
BMW_MODEL = '330i (G20)'

SENSOR_MAP = {
    'tpms_front_left_bar': 'tire_pressure_fl',
    'tpms_front_right_bar': 'tire_pressure_fr',
    'tpms_rear_left_bar': 'tire_pressure_rl',
    'tpms_rear_right_bar': 'tire_pressure_rr',
    'brake_fluid_pct': 'brake_fluid_level',
    'brake_pressure_bar': 'brake_pressure',
    'coolant_temp_c': 'coolant_temp',
    'coolant_level_pct': 'coolant_level',
    'fan_rpm': 'fan_rpm',
    'vehicle_speed_kmh': 'vehicle_speed',
    'battery_voltage_v': 'battery_voltage',
    'cranking_rpm': 'cranking_rpm',
    'starter_current_a': 'starter_current',
    'engine_rpm': 'engine_rpm',
    'misfire_count': 'misfire_count',
    'fuel_pressure_kpa': 'fuel_pressure',
    'mass_airflow_gps': 'mass_airflow',
}

DOMAIN_NOTES = {
    'tire': '01_TIRES.md',
    'brake': '02_BRAKES.md',
    'cooling': '03_COOLING.md',
    'starting_charging': '04_STARTING_AND_BATTERY.md',
    'engine_running': '05_ENGINE_RUNNING.md',
    'obd': '06_ACCESS_AND_OBD.md',
    'recall': '07_RECALL_AND_APPLICABILITY.md',
    'safety': '08_TRIAGE_POLICY.md',
}

BMW_ADDENDUM = '''You are operating in the dedicated BMW 330i (G20) diagnostic workspace for 2019–2024 petrol sedans (B46TU / B48TU 2.0L TwinPower Turbo 4-cylinder, DME engine electronics, iDrive / Check Control).
Make ("BMW") and model ("330i (G20)") are already known. Never ask the user for make or model. Only ask for model year (2019–2024) or market (such as US versus Germany/EU) if needed for recall scope or year-specific guidance, and never override a pending authoritative backend diagnostic next_question. If the user states their model year, pass year to update_vehicle_profile.
Strictly separate the 330i petrol (B46TU/B48TU) from the G20 330e plug-in hybrid (PHEV): never apply 330e auxiliary-battery, high-voltage, or hybrid starter-generator details to the petrol 330i.
Use search_bmw_knowledge to ground subsystem explanations in verified BMW G20 notes (for example: option-dependent direct TPMS and iDrive/placard tire targets without inventing universal BMW pressure specs; B46TU/B48TU split cooling and actuated Heat Management Module; PWM fan command versus unverified actual fan RPM; Mode 01 PID 42 control-module voltage versus IBS or battery-post voltage; DME air-mass substitution and high-pressure direct-injection rail versus generic low-side PID 0A; DSC hydraulic pressure caveats).
Use check_bmw_recalls when investigating starting/no-crank/starter-relay/electrical issues, restraint warnings, or recall questions (including US NHTSA campaigns 25V636000 starter-relay corrosion with park-outside advisory for affected 2019–2021 vehicles, and 26V056000 starter thermal risk). Always state that model-year match is not VIN confirmation and advise official BMW / NHTSA / KBA VIN lookup.
When sensors are enabled, use list_available_sensors, read_vehicle_sensors and read_sensor_history to inspect the shared vehicle readings and recorded history, interpreting each channel alongside its bmw_g20_catalog caveats while keeping customer-facing phrasing natural ("vehicle readings", "sensor readings", "recorded history").'''

BMW_TOOL_SPECS = [
    {
        'type': 'function',
        'name': 'search_bmw_knowledge',
        'description': 'Retrieve curated BMW 330i (G20, 2019–2024 petrol B46TU/B48TU) diagnostic cards, subsystem caveats and verified reference links across tires, brakes, cooling, starting/charging, engine running, OBD access and recalls.',
        'parameters': {
            'type': 'object',
            'properties': {
                'query': {'type': 'string', 'minLength': 1, 'maxLength': 300},
                'domain': {'type': 'string', 'enum': ['tire', 'brake', 'cooling', 'starting_charging', 'engine_running', 'obd', 'recall', 'safety']},
            },
            'required': ['query'],
            'additionalProperties': False,
        },
    },
    {
        'type': 'function',
        'name': 'check_bmw_recalls',
        'description': 'Check verified BMW 330i G20 recall campaign metadata (including 25V636000 starter relay and 26V056000 starter campaigns) and official US/Germany VIN lookup resources. Never confirms VIN applicability.',
        'parameters': {
            'type': 'object',
            'properties': {
                'query': {'type': 'string', 'maxLength': 200},
                'model_year': {'type': 'integer', 'minimum': 2018, 'maximum': 2026},
                'market': {'type': 'string', 'maxLength': 60},
            },
            'additionalProperties': False,
        },
    },
]


class KnowledgeQuery(BaseModel):
    model_config = ConfigDict(extra='forbid')
    query: str = Field(min_length=1, max_length=300)
    domain: str | None = None


class RecallQuery(BaseModel):
    model_config = ConfigDict(extra='forbid')
    query: str = Field(default='', max_length=200)
    model_year: int | None = Field(default=None, ge=2018, le=2026)
    market: str = Field(default='', max_length=60)


@lru_cache(maxsize=1)
def _pack():
    sources_raw = json.loads((CAR_DOCS / 'sources/source_catalog.json').read_text(encoding='utf-8'))
    sources = {item['id']: item for item in sources_raw}
    cards = [
        json.loads(line)
        for line in (CAR_DOCS / 'data/rag_knowledge_cards.jsonl').read_text(encoding='utf-8').splitlines()
        if line.strip()
    ]
    sensor_raw = json.loads((CAR_DOCS / 'data/sensor_catalog.json').read_text(encoding='utf-8'))
    sensors = {item['id']: item for item in sensor_raw}
    recalls = json.loads((CAR_DOCS / 'data/us_2021_330i_recalls_verified.json').read_text(encoding='utf-8'))
    notes = {
        path.name: path.read_text(encoding='utf-8').strip()
        for path in sorted((CAR_DOCS / 'notes').glob('*.md'))
    }
    return {'sources': sources, 'cards': cards, 'sensors': sensors, 'recalls': recalls, 'notes': notes}


def _resolve_sources(source_ids: list[str]) -> list[dict]:
    sources = _pack()['sources']
    resolved = []
    seen = set()
    for sid in source_ids:
        sid = sid.strip()
        if sid in sources and sid not in seen:
            seen.add(sid)
            item = sources[sid]
            resolved.append({
                'id': sid,
                'title': item['title'],
                'url': item['url'],
                'document_type': item['document_type'],
                'applicability': item['applicability'],
            })
    return resolved


def annotate_sensors(payload: dict, requested_names: list[str] | None = None) -> dict:
    sensors = _pack()['sensors']
    names = requested_names if requested_names is not None else list(SENSOR_MAP)
    catalog_notes = {}
    for name in names:
        bmw_id = SENSOR_MAP.get(name)
        if not bmw_id or bmw_id not in sensors:
            continue
        entry = sensors[bmw_id]
        sids = [s.strip() for s in str(entry.get('source_ids', '')).split(',') if s.strip()]
        catalog_notes[name] = {
            'bmw_signal_id': bmw_id,
            'hardware_basis': entry['hardware_basis'],
            'retrieval_path': entry['retrieval_path'],
            'generic_obd_request': entry['generic_obd_request'],
            'support_status': entry['support_status'],
            'caveats': entry['caveats'],
            'sources': _resolve_sources(sids),
        }
    return {**payload, 'vehicle_target': 'BMW 330i (G20) 2019–2024 petrol', 'bmw_g20_catalog': catalog_notes}


def search_knowledge(arguments: dict) -> dict:
    try:
        parsed = KnowledgeQuery.model_validate(arguments)
    except ValueError as error:
        raise ValueError('Invalid BMW knowledge query.') from error
    if parsed.domain is not None and parsed.domain not in DOMAIN_NOTES:
        raise ValueError('Unsupported BMW knowledge domain.')
    pack = _pack()
    tokens = [t for t in re.findall(r'[a-z0-9]+', parsed.query.casefold()) if len(t) > 1]
    domain_aliases = {
        'tire': 'tires',
        'brake': 'brakes',
        'cooling': 'cooling',
        'starting_charging': 'starting/charging',
        'engine_running': 'engine running',
        'obd': 'diagnostics',
        'recall': 'recall',
        'safety': 'diagnostics',
    }
    target_domain = domain_aliases.get(parsed.domain or '', '')
    scored = []
    for card in pack['cards']:
        haystack = f"{card['id']} {card['domain']} {card['title']} {card['content']} {card['applicability']}".casefold()
        score = sum(2 if token in card['title'].casefold() else 1 for token in tokens if token in haystack)
        if target_domain and card['domain'].casefold() == target_domain:
            score += 3
        if score > 0:
            scored.append((score, card))
    scored.sort(key=lambda item: -item[0])
    selected = [card for _, card in scored[:6]] or pack['cards'][:3]
    source_ids: list[str] = []
    formatted_cards = []
    for card in selected:
        source_ids.extend(card.get('source_ids', []))
        formatted_cards.append({
            'id': card['id'],
            'domain': card['domain'],
            'title': card['title'],
            'content': card['content'],
            'applicability': card['applicability'],
            'safety_note': card['safety_note'],
            'source_ids': card['source_ids'],
        })
    note_excerpts = {}
    note_files = ['00_SCOPE.md']
    if parsed.domain and DOMAIN_NOTES.get(parsed.domain):
        note_files.append(DOMAIN_NOTES[parsed.domain])
    else:
        for dom_key, filename in DOMAIN_NOTES.items():
            text = pack['notes'].get(filename, '')
            if any(token in text.casefold() for token in tokens):
                note_files.append(filename)
    for filename in dict.fromkeys(note_files[:3]):
        if filename in pack['notes']:
            note_excerpts[filename] = pack['notes'][filename][:1200]
    return {
        'vehicle_scope': 'BMW 330i (G20) 2019–2024 petrol (B46TU/B48TU); excludes 330e PHEV',
        'cards': formatted_cards,
        'notes': note_excerpts,
        'sources': _resolve_sources(source_ids)[:6],
    }


def check_recalls(arguments: dict, vehicle_year: int | None = None) -> dict:
    try:
        parsed = RecallQuery.model_validate(arguments)
    except ValueError as error:
        raise ValueError('Invalid BMW recall query.') from error
    pack = _pack()
    year = parsed.model_year or vehicle_year
    tokens = [t for t in re.findall(r'[a-z0-9]+', parsed.query.casefold()) if len(t) > 1]
    campaigns = []
    for item in pack['recalls']:
        haystack = f"{item['campaign_id']} {item['component']} {item['short_original_summary']} {item['advice_note']}".casefold()
        matched = not tokens or any(token in haystack for token in tokens)
        if matched:
            campaigns.append(item)
    if not campaigns:
        campaigns = pack['recalls']
    recall_cards = [
        {
            'id': card['id'],
            'title': card['title'],
            'content': card['content'],
            'applicability': card['applicability'],
        }
        for card in pack['cards']
        if card['id'] in ('ELE-04', 'ELE-05', 'RCL-01')
    ]
    source_ids = ['S021', 'S022', 'S023', 'S025', 'S027', 'S028']
    return {
        'vehicle_scope': 'BMW 330i (G20) petrol',
        'queried_model_year': year,
        'queried_market': parsed.market or 'unspecified',
        'vin_verified': False,
        'recall_requires_vin_verification': True,
        'policy': 'Model-year or symptom match is NOT VIN confirmation. Verify exact VIN with official BMW or national authority tools before treating a campaign as active on this vehicle.',
        'observed_us_2021_330i_campaigns': campaigns,
        'campaign_scope_notes': recall_cards,
        'sources': _resolve_sources(source_ids),
    }
