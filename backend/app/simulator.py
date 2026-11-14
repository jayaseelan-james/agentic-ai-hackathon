"""One shared store; investigations receive deep immutable-by-convention snapshots."""
import asyncio

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict

from .sensors import CATALOG, Channel, Sample, Simulation, baseline, change_sensor, describe, reset, series, timestamp, touch

state = Simulation()
lock = asyncio.Lock()
GROUPS = {
    'Tires': ['tpms_front_left_bar', 'tpms_front_right_bar', 'tpms_rear_left_bar', 'tpms_rear_right_bar'],
    'Brakes': ['brake_fluid_pct', 'brake_pressure_bar'],
    'Cooling': ['coolant_temp_c', 'coolant_level_pct', 'fan_rpm', 'vehicle_speed_kmh'],
    'Starting and charging': ['battery_voltage_v', 'cranking_rpm', 'starter_current_a'],
    'Engine running': ['engine_rpm', 'misfire_count', 'fuel_pressure_kpa', 'mass_airflow_gps'],
}
SCENARIOS = {
    'tire_pressure_loss': ('Tire pressure loss', 'Rear-left falls from 2.3 to 1.8 bar over 24 hours.'),
    'low_brake_fluid': ('Low brake fluid', 'Brake-fluid level at a fictional 25%; no brake-pressure measurement.'),
    'temperature_rise': ('Temperature rise', 'Coolant rises from 22 to 110°C over ten minutes while stationary.'),
    'battery_drop': ('Battery voltage drop', 'Voltage falls from 12.6 to 10.8 V over 24 hours.'),
    'unstable_idle': ('Unstable idle', 'RPM alternates from 650 to 1,250; 12 misfires in 60 seconds.'),
}


class Scenario(BaseModel):
    model_config = ConfigDict(extra='forbid')
    scenario: str


def check_revision(value, required=True):
    if value is None:
        if required:
            raise HTTPException(428, 'Refresh the simulator before editing; an If-Match revision is required.')
        return
    try:
        revision = int(value.strip('"'))
    except (ValueError, AttributeError):
        raise HTTPException(422, 'Invalid simulator revision.') from None
    if revision != state.revision:
        raise HTTPException(409, 'Simulator changed in another tab. Reload readings before applying this edit.')


def describe_state():
    result = describe(state)
    result['groups'] = GROUPS
    result['scenarios'] = [{'id': key, 'label': label, 'description': description} for key, (label, description) in SCENARIOS.items()]
    for name, channel in result['channels'].items():
        channel['step'] = 1 if name.endswith('_rpm') or name == 'misfire_count' else .01
        channel['group'] = next(group for group, names in GROUPS.items() if name in names)
        channel['presets'] = ([{'id': 'tire_slow_loss', 'label': 'Slow loss · 24 hours'}, {'id': 'tire_fast_loss', 'label': 'Fast loss · 1 hour'}] if name.startswith('tpms_') else
                              [{'id': 'coolant_rise', 'label': 'Temperature rise · 10 minutes'}] if name == 'coolant_temp_c' else
                              [{'id': 'rpm_rise', 'label': 'RPM rise · 2 minutes'}] if name == 'engine_rpm' else [])
    return result


def apply_scenario(name):
    if name not in SCENARIOS:
        raise HTTPException(422, 'Unknown prepared scenario.')
    at = timestamp()
    channels = {key: Channel(value=None, available=False, scenario=name, lookback_minutes=CATALOG[key][3], samples=[Sample(timestamp=at, value=None)]) for key in CATALOG}
    def constant(key, value):
        channels[key] = Channel(value=value, available=True, scenario=name, lookback_minutes=CATALOG[key][3], samples=series(value, value, CATALOG[key][3], at))
    def trend(key, start, end, minutes):
        channels[key] = Channel(value=end, available=True, scenario=name, lookback_minutes=minutes, samples=series(start, end, minutes, at))
    if name == 'tire_pressure_loss':
        for key in GROUPS['Tires']:
            constant(key, 2.3)
        trend('tpms_rear_left_bar', 2.3, 1.8, 1440)
        constant('vehicle_speed_kmh', 0)
    elif name == 'low_brake_fluid':
        constant('brake_fluid_pct', 25)
    elif name == 'temperature_rise':
        trend('coolant_temp_c', 22, 110, 10)
        for key, value in [('engine_rpm', 900), ('fan_rpm', 0), ('vehicle_speed_kmh', 0)]:
            constant(key, value)
    elif name == 'battery_drop':
        trend('battery_voltage_v', 12.6, 10.8, 1440)
        constant('engine_rpm', 0); constant('cranking_rpm', 0)
    else:
        samples = series(650, 1250, 2, at)
        for index, sample in enumerate(samples):
            sample.value = 650 if index % 2 == 0 else 1250
        channels['engine_rpm'] = Channel(value=samples[-1].value, available=True, scenario=name, lookback_minutes=2, samples=samples)
        constant('misfire_count', 12); constant('vehicle_speed_kmh', 0)
    state.channels = channels
    state.enabled = True
    state.snapshot_time = at
    state.revision += 1
