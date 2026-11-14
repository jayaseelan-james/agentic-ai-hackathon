"""Frozen, incident-local demo telemetry. No vehicle hardware or timers."""
from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, model_validator


def timestamp():
    return datetime.now(timezone.utc).isoformat()


CATALOG = {
    'tpms_front_left_bar': ('Front-left tire', 'bar', 2.3, 1440, 0, 10),
    'tpms_front_right_bar': ('Front-right tire', 'bar', 2.3, 1440, 0, 10),
    'tpms_rear_left_bar': ('Rear-left tire', 'bar', 2.3, 1440, 0, 10),
    'tpms_rear_right_bar': ('Rear-right tire', 'bar', 2.3, 1440, 0, 10),
    'engine_rpm': ('Engine RPM', 'RPM', 0, 2, 0, 20000),
    'coolant_temp_c': ('Coolant temperature', '°C', 22, 10, -50, 200),
}
CATALOG.update({
 'brake_fluid_pct': ('Brake-fluid level', '%', 75, 1440, 0, 100),
 'brake_pressure_bar': ('Brake pressure', 'bar', 0, 10, 0, 300),
 'coolant_level_pct': ('Coolant level', '%', 80, 1440, 0, 100),
 'fan_rpm': ('Cooling fan RPM', 'RPM', 0, 10, 0, 20000),
 'vehicle_speed_kmh': ('Vehicle speed', 'km/h', 0, 10, 0, 300),
 'battery_voltage_v': ('Battery voltage', 'V', 12.6, 1440, 0, 30),
 'cranking_rpm': ('Cranking RPM', 'RPM', 0, 2, 0, 3000),
 'starter_current_a': ('Starter current', 'A', 0, 2, 0, 2000),
 'misfire_count': ('Misfires in 60 seconds', 'count', 0, 2, 0, 100000),
 'fuel_pressure_kpa': ('Fuel pressure', 'kPa', 0, 10, 0, 30000),
 'mass_airflow_gps': ('Mass airflow', 'g/s', 0, 10, 0, 1000),
})
TIRES = tuple(name for name in CATALOG if name.startswith('tpms_'))
PRESETS = {
    'healthy': ('Healthy baseline', None, None, None),
    'tire_slow_loss': ('Slow pressure loss · 24 hours', 2.3, 1.8, 1440),
    'tire_fast_loss': ('Faster pressure loss · 1 hour', 2.3, 1.8, 60),
    'coolant_rise': ('Coolant rise · 10 minutes', 22, 110, 10),
    'rpm_rise': ('RPM rise · 2 minutes', 0, 1800, 2),
}


class Sample(BaseModel):
    timestamp: str
    value: float | None


def series(start: float, end: float, minutes: int, at: str, count=61):
    if start is None or end is None:
        return [Sample(timestamp=at, value=None)]
    anchor = datetime.fromisoformat(at)
    return [Sample(timestamp=(anchor - timedelta(minutes=minutes * (1 - i / (count - 1)))).isoformat(),
                   value=start if i == 0 else end if i == count - 1 else start + (end - start) * i / (count - 1)) for i in range(count)]


class Channel(BaseModel):
    value: float | None
    available: bool = True
    scenario: str = 'healthy'
    lookback_minutes: int
    samples: list[Sample]


def baseline(name: str, at: str):
    _, _, value, minutes, _, _ = CATALOG[name]
    return Channel(value=value, available=value is not None, lookback_minutes=minutes, samples=series(value, value, minutes, at) if value is not None else [Sample(timestamp=at, value=None)])


class Simulation(BaseModel):
    enabled: bool = False
    internet_blocked: bool = False
    fixture_id: str = 'demo-sensors-v1'
    revision: int = 0
    snapshot_time: str = Field(default_factory=timestamp)
    channels: dict[str, Channel] = Field(default_factory=dict)

    @model_validator(mode='after')
    def initialize(self):
        if not self.channels:
            self.channels = {name: baseline(name, self.snapshot_time) for name in CATALOG}
        return self


class EnableSimulation(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    enabled: bool


class ConnectivitySimulation(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    internet_blocked: bool


class SensorChange(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['value', 'unavailable', 'trend', 'preset', 'restore']
    value: StrictFloat | None = Field(default=None, allow_inf_nan=False)
    start_value: StrictFloat | None = Field(default=None, allow_inf_nan=False)
    end_value: StrictFloat | None = Field(default=None, allow_inf_nan=False)
    duration_minutes: StrictInt | None = Field(default=None, ge=1, le=10080)
    sample_count: StrictInt = Field(default=61, ge=2, le=200)
    preset: Literal['healthy', 'tire_slow_loss', 'tire_fast_loss', 'coolant_rise', 'rpm_rise'] | None = None

    @model_validator(mode='after')
    def required_fields(self):
        required = {'value': ['value'], 'trend': ['start_value', 'end_value', 'duration_minutes'], 'preset': ['preset']}
        if any(getattr(self, key) is None for key in required.get(self.kind, [])):
            raise ValueError('Provide all fields required for this sensor change.')
        allowed = set(required.get(self.kind, [])) | {'kind'}
        if self.kind == 'trend':
            allowed.add('sample_count')
        if self.model_fields_set - allowed:
            raise ValueError('Unexpected fields for this sensor change.')
        return self


class ReadSensors(BaseModel):
    model_config = ConfigDict(extra='forbid')
    sensor_names: list[str] = Field(min_length=1, max_length=len(CATALOG))


class ReadHistory(ReadSensors):
    lookback_minutes: StrictInt | None = Field(default=None, ge=1, le=10080)
    max_points: StrictInt = Field(default=60, ge=2, le=200)


def metadata(sim: Simulation):
    return {'source': 'simulated', 'fixture_id': sim.fixture_id, 'revision': sim.revision,
            'internet_blocked': sim.internet_blocked,
            'snapshot_time': sim.snapshot_time, 'retrieved_at': timestamp(), 'enabled': sim.enabled,
            'note': 'Fictional demo telemetry, separate from user vehicle details; not a roadworthiness assessment.'}


def describe(sim: Simulation):
    return {**metadata(sim), 'channels': {name: {**channel.model_dump(), 'name': name,
            'label': CATALOG[name][0], 'unit': CATALOG[name][1],
            'limits': {'min': CATALOG[name][4], 'max': CATALOG[name][5]}}
            for name, channel in sim.channels.items()}}


def touch(sim: Simulation):
    sim.revision += 1
    sim.snapshot_time = timestamp()


def change_sensor(sim: Simulation, name: str, change: SensorChange):
    if name not in CATALOG:
        raise ValueError('Unknown sensor.')
    if not sim.enabled:
        raise ValueError('Enable demo sensors before changing a reading.')
    _, _, default, duration, lower, upper = CATALOG[name]
    for value in (change.value, change.start_value, change.end_value):
        if name == 'misfire_count' and value is not None and value != int(value):
            raise ValueError('Misfire counts must be whole numbers.')
        if value is not None and not lower <= value <= upper:
            raise ValueError(f'Demo value must be between {lower} and {upper} {CATALOG[name][1]}.')
    at = timestamp()
    channel = sim.channels[name]
    if change.kind in ('value', 'unavailable'):
        value = change.value if change.kind == 'value' else None
        # Hold the old value until this explicit edit; a step is not a gradual trend.
        if datetime.fromisoformat(at) > datetime.fromisoformat(channel.samples[-1].timestamp):
            channel.samples.append(Sample(timestamp=at, value=channel.value))
        channel.samples.append(Sample(timestamp=at, value=value))
        channel.samples = channel.samples[-200:]
        channel.value, channel.available, channel.scenario = value, value is not None, change.kind
    else:
        start, end, scenario, count = default, default, 'healthy', 61
        if change.kind == 'trend':
            start, end, duration, scenario, count = change.start_value, change.end_value, change.duration_minutes, 'custom_trend', change.sample_count
        elif change.kind == 'preset' and change.preset != 'healthy':
            scenario = change.preset
            if ((scenario.startswith('tire_') and name not in TIRES)
                    or (scenario == 'coolant_rise' and name != 'coolant_temp_c')
                    or (scenario == 'rpm_rise' and name != 'engine_rpm')):
                raise ValueError('This preset does not match the selected sensor.')
            _, start, end, duration = PRESETS[scenario]
        sim.channels[name] = Channel(value=end, available=end is not None, scenario=scenario, lookback_minutes=duration,
                                     samples=series(start, end, duration, at, count))
    if name == 'misfire_count':
        for sample in sim.channels[name].samples:
            if sample.value is not None:
                sample.value = round(sample.value)
    sim.revision += 1
    sim.snapshot_time = at


def reset(sim: Simulation):
    touch(sim)
    sim.channels = {name: baseline(name, sim.snapshot_time) for name in CATALOG}


def list_sensors(sim: Simulation):
    return {**metadata(sim), 'status': 'ok' if sim.enabled else 'disabled',
            'supported': [{'name': name, 'unit': CATALOG[name][1], 'label': CATALOG[name][0],
                           'suggested_lookback_minutes': channel.lookback_minutes,
                           'available': sim.enabled and channel.available} for name, channel in sim.channels.items()],
            'available': [name for name, channel in sim.channels.items() if sim.enabled and channel.available],
            'unavailable': [name for name, channel in sim.channels.items() if not sim.enabled or not channel.available] + ['brake_fluid_pressure', 'airbag_status'],
            'tire_reference': {'value': 2.3, 'unit': 'bar', 'source': 'fictional_demo_reference',
                               'note': 'This is not an OEM specification for the user-entered vehicle.'}}


def expand(names):
    return list(dict.fromkeys(name for requested in names for name in
                (TIRES if requested == 'tpms_per_wheel_pressure_bar' else [requested])))


def read(sim: Simulation, query: ReadSensors):
    readings, unavailable = {}, []
    for name in expand(query.sensor_names):
        channel = sim.channels.get(name)
        if not sim.enabled or not channel or not channel.available:
            unavailable.append(name)
        else:
            readings[name] = {'value': channel.value, 'unit': CATALOG[name][1],
                              'sample_time': channel.samples[-1].timestamp}
    return {**metadata(sim), 'status': ('ok' if not unavailable else 'partial' if readings else 'unavailable'),
            'readings': readings, 'unavailable': unavailable}


def history(sim: Simulation, query: ReadHistory):
    results, unavailable = {}, []
    for name in expand(query.sensor_names):
        channel = sim.channels.get(name)
        if not sim.enabled or not channel:
            unavailable.append(name)
            continue
        minutes = query.lookback_minutes or channel.lookback_minutes
        end = datetime.fromisoformat(sim.snapshot_time)
        start = end - timedelta(minutes=minutes)
        samples = [sample for sample in channel.samples if start <= datetime.fromisoformat(sample.timestamp) <= end]
        # Unchanged sensors are held constant through the snapshot, without moving old samples.
        if channel.samples and channel.samples[-1].timestamp < sim.snapshot_time:
            samples.append(Sample(timestamp=sim.snapshot_time, value=channel.value))
        total = len(samples)
        if total > query.max_points:
            samples = [samples[round(i * (total - 1) / (query.max_points - 1))] for i in range(query.max_points)]
        results[name] = {'unit': CATALOG[name][1],
                         'current_available': channel.available, 'lookback_minutes': minutes,
                         'requested_start': start.isoformat(), 'requested_end': sim.snapshot_time,
                         'coverage_start': samples[0].timestamp if samples else None,
                         'coverage_end': samples[-1].timestamp if samples else None,
                         'coverage_complete': datetime.fromisoformat(channel.samples[0].timestamp) <= start,
                         'downsampled': total > query.max_points,
                         'samples': [sample.model_dump() for sample in samples]}
    return {**metadata(sim), 'status': 'ok' if not unavailable else 'partial' if results else 'unavailable',
            'history': results, 'unavailable': unavailable}
