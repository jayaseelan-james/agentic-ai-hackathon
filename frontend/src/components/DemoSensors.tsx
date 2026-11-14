import { useEffect, useRef, useState } from 'react';
import { request, type SensorChannel, type SensorSample, type SensorSimulation } from '../api';

const time = (value: string) => new Date(value).toLocaleString([], {month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit'});

function History({channel}: {channel: SensorChannel}) {
  const samples = channel.samples;
  const values = samples.flatMap(sample => sample.value === null ? [] : [sample.value]);
  const low = Math.min(...values), high = Math.max(...values);
  const start = Date.parse(samples[0]?.timestamp), end = Date.parse(samples.at(-1)?.timestamp || '');
  const point = (sample: SensorSample) => `${20 + (Date.parse(sample.timestamp) - start) / (end - start || 1) * 560},${105 - ((sample.value! - low) / (high - low || 1)) * 80}`;
  const segments: SensorSample[][] = [[]];
  for (const sample of samples) {
    if (sample.value === null) segments.push([]);
    else segments[segments.length - 1].push(sample);
  }
  return <section className="sensor-history" aria-label={`${channel.label} history`}>
    <div className="sensor-history-heading"><strong>{channel.label} history</strong><span>{channel.lookback_minutes} minute window · {samples.length} samples</span></div>
    {values.length > 0 ? <><svg viewBox="0 0 600 130" role="img" aria-label={`${channel.label} history: ${values[0]} to ${values.at(-1)} ${channel.unit}`}>
      <line x1="20" y1="110" x2="580" y2="110" stroke="#ccd9d8"/>
      {segments.filter(segment => segment.length > 0).map((segment, index) => <polyline key={index} fill="none" stroke="#0f766e" strokeWidth="3" points={segment.map(point).join(' ')}/>)}
      <text x="20" y="16">{high} {channel.unit}</text><text x="580" y="126" textAnchor="end">{low} {channel.unit}</text>
    </svg><div className="sensor-chart-times"><span>{time(samples[0].timestamp)}</span><span>{time(samples.at(-1)!.timestamp)}</span></div></> : <p>No numeric history available.</p>}
    <details><summary>Timestamped samples</summary><div className="sensor-table-scroll" tabIndex={0}><table><caption>{channel.label} · simulated</caption><thead><tr><th>Time</th><th>Value ({channel.unit})</th></tr></thead><tbody>{samples.map((sample, index) => <tr key={index}><td><time dateTime={sample.timestamp}>{time(sample.timestamp)}</time></td><td>{sample.value ?? 'Unavailable'}</td></tr>)}</tbody></table></div></details>
  </section>;
}

function SensorEditor({channel, disabled, apply}: {channel: SensorChannel; disabled: boolean; apply: (change: Record<string, unknown>) => void}) {
  const [value, setValue] = useState(String(channel.value ?? ''));
  const [start, setStart] = useState(String(channel.value ?? channel.limits.min));
  const [end, setEnd] = useState(String(channel.name.startsWith('tpms_') ? 1.8 : channel.name === 'engine_rpm' ? 1800 : 110));
  const [duration, setDuration] = useState(String(channel.lookback_minutes));
  const presets = channel.name.startsWith('tpms_') ? [['tire_slow_loss', 'Slow pressure loss · 24 hours'], ['tire_fast_loss', 'Faster pressure loss · 1 hour']]
    : channel.name === 'engine_rpm' ? [['rpm_rise', 'RPM rise · 2 minutes']] : [['coolant_rise', 'Coolant rise · 10 minutes']];
  const [preset, setPreset] = useState(presets[0][0]);
  const bounds = {min: channel.limits.min, max: channel.limits.max, step: 'any', required: true};
  return <fieldset disabled={disabled} className="sensor-editor">
    <legend>Edit {channel.label.toLowerCase()}</legend>
    <form className="sensor-form" onSubmit={event => {event.preventDefault(); apply({kind: 'value', value: Number(value)});}}>
      <label>Current value ({channel.unit})<input type="number" {...bounds} value={value} onChange={event => setValue(event.target.value)}/></label>
      <button className="outline" type="submit">Set value</button><button className="outline" type="button" onClick={() => apply({kind: 'unavailable'})}>Mark unavailable</button>
    </form>
    <form className="sensor-form" onSubmit={event => {event.preventDefault(); apply({kind: 'preset', preset});}}>
      <label>Prepared preset<select value={preset} onChange={event => setPreset(event.target.value)}>{presets.map(([id, label]) => <option key={id} value={id}>{label}</option>)}<option value="healthy">Healthy baseline</option></select></label>
      <button className="outline" type="submit">Apply preset</button>
    </form>
    <details className="sensor-custom"><summary>Custom trend</summary><form className="sensor-form" onSubmit={event => {event.preventDefault(); apply({kind: 'trend', start_value: Number(start), end_value: Number(end), duration_minutes: Number(duration)});}}>
      <label>Starting value ({channel.unit})<input type="number" {...bounds} value={start} onChange={event => setStart(event.target.value)}/></label>
      <label>Ending value ({channel.unit})<input type="number" {...bounds} value={end} onChange={event => setEnd(event.target.value)}/></label>
      <label>Duration (minutes)<input type="number" min="1" max="10080" step="1" required value={duration} onChange={event => setDuration(event.target.value)}/></label>
      <button className="outline" type="submit">Apply custom trend</button>
    </form><small>1 minute to 7 days (10,080 minutes). Applying a trend replaces this sensor’s prepared history.</small></details>
    <button className="sensor-restore" type="button" onClick={() => apply({kind: 'restore'})}>Restore sensor</button>
  </fieldset>;
}

export default function DemoSensors({incidentId, disabled, onBusyChange}: {incidentId: string; disabled: boolean; onBusyChange: (busy: boolean) => void}) {
  const [state, setState] = useState<SensorSimulation>();
  const [selected, setSelected] = useState('tpms_rear_left_bar');
  const [error, setError] = useState('');
  const [feedback, setFeedback] = useState('');
  const [loading, setLoading] = useState(true);
  const saving = useRef(false);
  const base = `/incidents/${incidentId}/sensors`;
  useEffect(() => {
    let cancelled = false;
    request<SensorSimulation>(base).then(data => {if (!cancelled) {if (data.channels) setState(data); else setError('Sensor controls are unavailable. Restart the updated backend.');}})
      .catch((error: Error) => {if (!cancelled) setError(error.message);})
      .finally(() => {if (!cancelled) setLoading(false);});
    return () => {cancelled = true;};
  }, [base]);
  async function mutate(path: string, method: string, body?: Record<string, unknown>) {
    if (disabled || saving.current) return;
    saving.current = true; onBusyChange(true); setError(''); setFeedback('');
    try {
      const updated = await request<SensorSimulation>(path, {method, headers: {'Content-Type': 'application/json'}, body: body ? JSON.stringify(body) : undefined});
      setState(updated); setFeedback(`Demo sensors updated · revision ${updated.revision}. Send a message when you want Gemini to investigate.`);
    } catch (error) {setError((error as Error).message);}
    finally {saving.current = false; onBusyChange(false);}
  }
  const channel = state?.channels[selected];
  return <details className="demo-sensors">
    <summary><strong>Demo sensors</strong><span>{state?.enabled ? 'Simulation enabled' : 'Off'} · fixed values + history</span></summary>
    <div className="demo-sensors-body">
      <p>Fictional telemetry, separate from your vehicle details. Values stay fixed until you edit them. Changes do not send a message.</p>
      {loading && <p role="status">Loading sensor controls…</p>}
      {error && <p className="error" role="alert">{error}</p>}
      {state && <>
        <div className="sensor-controls"><label className="sensor-switch"><input type="checkbox" checked={state.enabled} disabled={disabled} onChange={event => void mutate(base, 'PATCH', {enabled: event.target.checked})}/>Enable demo sensors</label><button className="outline" disabled={disabled || !state.enabled} onClick={() => void mutate(`${base}/reset`, 'POST')}>Reset all</button></div>
        <small className="sensor-snapshot">Snapshot {time(state.snapshot_time)} · revision {state.revision}. Tire baseline: fictional 2.3 bar.</small>
        <div className="sensor-grid" aria-label="Demo sensor readings">{Object.values(state.channels).map(sensor => <button key={sensor.name} aria-pressed={sensor.name === selected} onClick={() => {setSelected(sensor.name); setFeedback('');}}><span>{sensor.label}</span><strong>{sensor.value === null ? 'Unavailable' : `${sensor.value} ${sensor.unit}`}</strong></button>)}</div>
        {!state.enabled && <p className="sensor-off-note">Enable the simulator to expose these prepared readings to Gemini.</p>}
        {channel && <><SensorEditor key={`${selected}-${state.revision}`} channel={channel} disabled={disabled || !state.enabled} apply={change => void mutate(`${base}/${selected}`, 'PATCH', change)}/><History channel={channel}/></>}
      </>}
      <p className="sensor-feedback" role="status">{feedback || (disabled ? 'Sensor changes are locked while processing.' : '')}</p>
    </div>
  </details>;
}
