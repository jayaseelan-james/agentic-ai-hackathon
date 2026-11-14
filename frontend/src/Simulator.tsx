import { useEffect, useRef, useState } from 'react';
import { Car, ExternalLink, RotateCcw } from 'lucide-react';
import { ApiError, request, type SensorSimulation, type SensorChannel } from './api';
import InvestigationInspector from './components/InvestigationInspector';

type Save = (name:string,body:object,revision?:number)=>Promise<boolean>;
function Reading({channel,enabled,revision,save,select,selected}:{channel:SensorChannel;enabled:boolean;revision:number;save:Save;select:()=>void;selected:boolean}) {
  const [value,setValue]=useState(String(channel.value??''));
  const dirty=useRef(false);const editRevision=useRef(revision);
  useEffect(()=>{if(!dirty.current)setValue(String(channel.value??''));},[channel.value]);
  async function apply(body:object){if(await save(channel.name,body,dirty.current?editRevision.current:revision)){dirty.current=false;}}
  return <form className="reading-row" onSubmit={e=>{e.preventDefault();void apply({kind:'value',value:Number(value)});}}>
    <label>{channel.label}<span className="reading-unit">{channel.unit}{channel.available?'':' · Unavailable'}</span><input aria-label={channel.label} type="number" min={channel.limits.min} max={channel.limits.max} step={channel.step??'any'} required disabled={!enabled} value={value} onChange={e=>{if(!dirty.current)editRevision.current=revision;dirty.current=true;setValue(e.target.value);}} placeholder="Unavailable"/></label>
    <div className="reading-actions"><button className="primary" disabled={!enabled}>Save</button><button type="button" className="outline" disabled={!enabled} onClick={()=>void apply({kind:'unavailable'})}>Unavailable</button><button type="button" disabled={!enabled} onClick={()=>void apply({kind:'restore'})}>Restore</button><button type="button" aria-pressed={selected} onClick={select}>History & trend</button></div>
  </form>;
}

function HistoryEditor({channel,enabled,save,revision}:{channel:SensorChannel;enabled:boolean;save:Save;revision:number}) {
  const [start,setStart]=useState(String(channel.value??''));const [end,setEnd]=useState(String(channel.value??''));
  const [duration,setDuration]=useState(String(channel.lookback_minutes));const [preset,setPreset]=useState(channel.presets?.[0]?.id||'');
  const editRevision=useRef(revision);const dirty=useRef(false);
  if(!dirty.current)editRevision.current=revision;
  const edit=()=>{if(!dirty.current)editRevision.current=revision;dirty.current=true;};
  async function apply(body:object){if(await save(channel.name,body,editRevision.current))dirty.current=false;}
  const numbers=channel.samples.filter(s=>s.value!==null);const min=Math.min(...numbers.map(s=>s.value!));const max=Math.max(...numbers.map(s=>s.value!));
  const first=Date.parse(channel.samples[0]?.timestamp),last=Date.parse(channel.samples.at(-1)?.timestamp||'');
  const segments:string[][]=[[]];for(const sample of channel.samples){if(sample.value===null)segments.push([]);else segments.at(-1)!.push(`${16+(Date.parse(sample.timestamp)-first)/(last-first||1)*568},${112-(sample.value-min)/(max-min||1)*86}`);}
  return <section className="history-panel" id="sensor-history" aria-label={`${channel.label} history`}><h2>{channel.label} history</h2><p className="muted">Frozen {channel.lookback_minutes}-minute window · {channel.samples.length} samples · {channel.unit}</p>
    {numbers.length?<svg viewBox="0 0 600 130" role="img" aria-label={`${channel.label} history: ${numbers[0].value} to ${numbers.at(-1)!.value} ${channel.unit}`}><line x1="16" y1="115" x2="584" y2="115" stroke="#c9d6d5"/>{segments.filter(s=>s.length).map((points,i)=><polyline key={i} points={points.join(' ')} fill="none" stroke="#0f766e" strokeWidth="3"/>)}<text x="16" y="18">{max} {channel.unit}</text></svg>:<p>No numeric history available.</p>}
    <details><summary>Timestamped samples</summary><div className="inspection-table"><table><thead><tr><th>Time</th><th>Value ({channel.unit})</th></tr></thead><tbody>{channel.samples.map((s,i)=><tr key={i}><td>{new Date(s.timestamp).toLocaleString()}</td><td>{s.value??'Unavailable'}</td></tr>)}</tbody></table></div></details>
    <fieldset disabled={!enabled}><legend>Advanced editing</legend>{!!channel.presets?.length&&<form className="trend-form" onSubmit={e=>{e.preventDefault();void apply({kind:'preset',preset});}}><label>Prepared preset<select value={preset} onChange={e=>{edit();setPreset(e.target.value);}}>{channel.presets.map(p=><option key={p.id} value={p.id}>{p.label}</option>)}</select></label><button className="outline">Apply preset</button></form>}
    <form className="trend-form" onSubmit={e=>{e.preventDefault();void apply({kind:'trend',start_value:Number(start),end_value:Number(end),duration_minutes:Number(duration)});}}><label>Starting value<input aria-label="Starting value" required type="number" step={channel.step??'any'} min={channel.limits.min} max={channel.limits.max} value={start} onChange={e=>{edit();setStart(e.target.value);}}/></label><label>Ending value<input aria-label="Ending value" required type="number" step={channel.step??'any'} min={channel.limits.min} max={channel.limits.max} value={end} onChange={e=>{edit();setEnd(e.target.value);}}/></label><label>Duration (minutes)<input aria-label="Duration (minutes)" required type="number" min={1} max={10080} step={1} value={duration} onChange={e=>{edit();setDuration(e.target.value);}}/></label><button className="outline">Apply custom trend</button></form></fieldset>
  </section>;
}

export default function Simulator() {
  const [state,setState]=useState<SensorSimulation>();const [error,setError]=useState('');const [feedback,setFeedback]=useState('');
  const [busy,setBusy]=useState(false);const [stale,setStale]=useState(false);const [selected,setSelected]=useState('tpms_rear_left_bar');const [epoch,setEpoch]=useState(0);
  const saving=useRef(false);const staleRef=useRef(false);
  async function load(explicit=false){try{const data=await request<SensorSimulation>('/simulator');if(!saving.current){setState(current=>!current||data.revision>=current.revision?data:current);if(explicit){staleRef.current=false;setStale(false);setError('');setEpoch(v=>v+1);}}}catch(e){setError((e as Error).message);}}
  useEffect(()=>{let alive=true;const refresh=()=>{if(alive&&!document.hidden&&!saving.current&&!staleRef.current)void load();};refresh();const timer=setInterval(refresh,2000);window.addEventListener('focus',refresh);return()=>{alive=false;clearInterval(timer);window.removeEventListener('focus',refresh);};},[]);
  async function mutate(path:string,method:string,body?:object,revision=state?.revision):Promise<boolean>{
    if(saving.current||staleRef.current||revision===undefined)return false;
    saving.current=true;setBusy(true);setError('');setFeedback('');
    try{const data=await request<SensorSimulation>(path,{method,headers:{'Content-Type':'application/json','If-Match':String(revision)},body:body?JSON.stringify(body):undefined});setState(data);setFeedback(path.endsWith('/connectivity')?`Remote breakdown mode ${data.internet_blocked?'enabled · Gemma 4 26B only; web access blocked':'disabled · standard Gemini model and web tools restored'}. Applies to new investigations; running checks and retries keep their original settings.`:`Saved shared readings · revision ${data.revision}. The next message in every chat uses this snapshot.`);if(path.endsWith('/scenario')||path.endsWith('/reset'))setEpoch(v=>v+1);return true;}
    catch(e){setError((e as Error).message);if(e instanceof ApiError&&e.status===409){staleRef.current=true;setStale(true);}return false;}
    finally{saving.current=false;setBusy(false);}
  }
  const enabled=!!state?.enabled&&!busy&&!stale;
  const save:Save=(name,body,revision)=>mutate(`/simulator/sensors/${name}`,'PATCH',body,revision);
  return <div className="simulator-page"><header className="simulator-header"><div className="brand"><Car/><span>AutoSage</span></div><div className="simulator-links"><a className="outline operator-chat-link" href="/" target="_blank" rel="noreferrer">Open chat<ExternalLink size={17}/></a><a className="outline operator-chat-link" href="/bmw" target="_blank" rel="noreferrer">BMW 330i G20<ExternalLink size={17}/></a></div></header>
    <div className="simulator-title"><h1>Vehicle simulator</h1><p>One shared fictional vehicle for all chats. Changes apply to the next investigation.</p></div>
    <div className="simulator-disclosure">Simulated values are not measurements from a real vehicle. Scenario values are illustrative, not manufacturer specifications.</div>
    {error&&<div className="error" role="alert">{error}{stale&&<p>Reload readings to discard stale drafts and continue.</p>}</div>}
    <div className="simulator-controls"><label className="simulation-toggle"><input type="checkbox" checked={state?.enabled??false} disabled={!state||busy||stale} onChange={e=>void mutate('/simulator','PATCH',{enabled:e.target.checked})}/>Enable simulated data for all chats</label><div><button className="outline" disabled={!state||busy||stale} onClick={()=>void mutate('/simulator/reset','POST')}><RotateCcw size={17}/>Reset all</button><button disabled={busy} onClick={()=>void load(true)}>Reload readings</button></div><small>{state?`Revision ${state.revision} · Snapshot ${new Date(state.snapshot_time).toLocaleString()}`:'Loading shared simulator…'}</small></div>
    <section className={`connectivity-controls ${state?.internet_blocked?'restricted':''}`} aria-label="Remote breakdown simulation"><label className="simulation-toggle"><input type="checkbox" checked={state?.internet_blocked??false} disabled={!state||busy||stale} onChange={e=>void mutate('/simulator/connectivity','PATCH',{internet_blocked:e.target.checked})}/>Block internet access (remote breakdown)</label><p>{state?.internet_blocked?'Gemma 4 26B only · Web search and external pages blocked.':'Standard mode · Gemini and web tools available.'}</p><small>This simulates restricted connectivity. The Gemini API connection stays allowed for Gemma responses. Sensors and bundled BMW references remain available. New investigations use this setting; running checks and retries retain their original setting.</small></section>
    <p className="simulator-feedback" role="status">{feedback||(!state?.enabled?'Enable simulation or apply a prepared scenario to make readings available to the agent.':'Readings stay fixed until edited. Sensor changes never send a chat message.')}</p>
    <section className="scenario-section"><h2>Prepared scenarios</h2><div className="scenario-buttons">{state?.scenarios?.map(s=><button className="outline" key={s.id} title={s.description} disabled={busy||stale} onClick={()=>void mutate('/simulator/scenario','POST',{scenario:s.id})}>{s.label}</button>)}</div></section>
    {state&&<><nav className="sensor-group-nav" aria-label="Sensor groups">{Object.keys(state.groups||{}).map(group=><a key={group} href={`#group-${group.replaceAll(' ','-')}`}>{group}</a>)}</nav><div className="sensor-groups">{Object.entries(state.groups||{'All sensors':Object.keys(state.channels)}).map(([group,names])=><section className="sensor-group" key={group} id={`group-${group.replaceAll(' ','-')}`}><h2>{group}<span>{names.length} channels</span></h2>{names.map(name=>state.channels[name]&&<Reading key={`${name}:${epoch}`} channel={state.channels[name]} enabled={enabled} revision={state.revision} save={save} selected={selected===name} select={()=>setSelected(name)}/>)}</section>)}</div>{state.channels[selected]&&<HistoryEditor key={`${selected}:${epoch}`} revision={state.revision} channel={state.channels[selected]} enabled={enabled} save={save}/>}</>}
    <InvestigationInspector/>
  </div>;
}
