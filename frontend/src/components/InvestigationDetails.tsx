import type {Activity, DiagnosticInference, Message} from '../api';

const DOMAINS:Record<string,string>={tire:'Tires',brake:'Brakes',cooling:'Cooling',starting_charging:'Starting and charging',engine_running:'Engine running'};
const CHANNELS:Record<string,[string,string]>={
 tpms_front_left_bar:['tire','Front-left tire'],tpms_front_right_bar:['tire','Front-right tire'],tpms_rear_left_bar:['tire','Rear-left tire'],tpms_rear_right_bar:['tire','Rear-right tire'],
 brake_fluid_pct:['brake','Brake-fluid level'],brake_pressure_bar:['brake','Brake pressure'],coolant_temp_c:['cooling','Coolant temperature'],coolant_level_pct:['cooling','Coolant level'],fan_rpm:['cooling','Cooling fan RPM'],vehicle_speed_kmh:['cooling','Vehicle speed'],battery_voltage_v:['starting_charging','Battery voltage'],cranking_rpm:['starting_charging','Cranking RPM'],starter_current_a:['starting_charging','Starter current'],engine_rpm:['engine_running','Engine RPM'],misfire_count:['engine_running','Misfires in 60 seconds'],fuel_pressure_kpa:['engine_running','Fuel pressure'],mass_airflow_gps:['engine_running','Mass airflow']};
const TOOLS:Record<string,string>={gemini:'Analyzing the problem',google_search:'Searching the web',url_context:'Reading a reference page',process_media:'Analyzing media',record_observations:'Recording observations',get_vehicle_profile:'Checking vehicle details',update_vehicle_profile:'Saving vehicle details',classify_diagnosis:'Updating Bayesian probabilities',read_vehicle_sensors:'Reading vehicle sensors',read_sensor_history:'Checking sensor history',list_available_sensors:'Discovering sensor channels',evaluate_safety:'Checking safety',create_mechanic_report:'Preparing mechanic handoff',tool_validation:'Validating a tool call',delete_provider_file:'Removing temporary media'};
const label=(s:string)=>s.replaceAll('_',' ');
const status=(s:string)=>s==='running'?'In progress':s==='failed'?'Failed':'Complete';

type Channel={name:string;domain:string;label:string;value:number|null;unit:string;history?:string;current:boolean};
function channelsUsed(events:Activity[]) {
 const channels=new Map<string,Channel>();
 for(const event of events){
  if(event.status!=='complete'||!event.result)continue;
  const result=event.result;
  if(event.tool==='read_vehicle_sensors'){
   const readings=(result.readings||{}) as Record<string,{value:number|null;unit:string}>;
   for(const [name,reading] of Object.entries(readings)){const meta=CHANNELS[name];if(meta)channels.set(name,{...channels.get(name),name,domain:meta[0],label:meta[1],value:reading.value,unit:reading.unit,current:true});}
   for(const name of (result.unavailable||[]) as string[]){const meta=CHANNELS[name];if(meta)channels.set(name,{...channels.get(name),name,domain:meta[0],label:meta[1],value:null,unit:'',current:true});}
  }
  if(event.tool==='read_sensor_history'){
   const history=(result.history||{}) as Record<string,{unit:string;samples:{value:number|null}[];lookback_minutes:number}>;
   for(const [name,reading] of Object.entries(history)){const meta=CHANNELS[name];if(!meta)continue;const samples=reading.samples.filter(s=>s.value!==null);const existing=channels.get(name);channels.set(name,{name,domain:meta[0],label:meta[1],value:null,unit:reading.unit,current:false,...existing,history:samples.length?`${samples[0].value} → ${samples.at(-1)!.value} ${reading.unit} · ${reading.lookback_minutes} min`:'No numeric history available'});}
  }
 }
 return [...channels.values()];
}

export default function InvestigationDetails({message}:{message:Message}) {
 const results=new Map<string,DiagnosticInference>();
 for(const e of message.activity){if(e.tool==='classify_diagnosis'&&e.status==='complete'&&e.result&&typeof e.result.domain==='string'&&Array.isArray(e.result.ranked_hypotheses))results.set(e.result.domain,e.result as unknown as DiagnosticInference);}
 for(const result of message.diagnostic_inference||[])results.set(result.domain,result);
 const channels=channelsUsed(message.activity);
 const domains=[...new Set([...results.keys(),...channels.map(c=>c.domain)])];
 return <>
  {!!message.activity.length&&<details className="activity investigation-activity" open><summary>Investigation activity <span>{message.activity.length} events · {message.state==='processing'?'Working':message.state==='failed'?'Needs retry':'Finished'}</span></summary><ol>{message.activity.map(e=><li key={e.id} className={`event-${e.status}`}><div><strong>{TOOLS[e.tool]||label(e.tool)}</strong><span className="event-status">{status(e.status)}</span></div><p>{e.summary}</p><small>{new Date(e.timestamp).toLocaleTimeString()} · {e.initiator==='model'?'Agent':'Backend'}</small></li>)}</ol></details>}
  {!!domains.length&&<section className="bayesian-results" aria-label="Bayesian probabilities"><h3>Bayesian probabilities</h3><p className="probability-note">Model estimates from synthetic training, not validated diagnostic confidence. A high score does not confirm a fault.</p>
   {domains.map(domain=>{const result=results.get(domain);const ranked=(result?.ranked_hypotheses||[]).filter(h=>Number.isFinite(h.posterior)&&h.posterior>=0&&h.posterior<=1);const used=channels.filter(c=>c.domain===domain);return <section className="probability-domain" key={domain} aria-label={`${DOMAINS[domain]||label(domain)} probabilities`}><h4>{DOMAINS[domain]||label(domain)}</h4>{result&&<p className="inference-status">{label(result.status)}{result.conflicts?.length?' · Conflicting observations':''}</p>}
    {ranked.length?<div className="probability-chart" role="img" aria-label={`${DOMAINS[domain]||label(domain)} probability chart: ${ranked.map(h=>`${label(h.fault_id)} ${(h.posterior*100).toFixed(1)}%`).join(', ')}`}><div className="probability-scale"><span>0%</span><span>50%</span><span>100%</span></div>{ranked.map(h=><div className="probability-row" key={h.fault_id}><div className="probability-label"><span>{label(h.fault_id)}</span><strong>{(h.posterior*100).toFixed(1)}%</strong></div><div className="probability-track"><div className="probability-fill" style={{width:`${h.posterior*100}%`}}/></div></div>)}</div>:<p className="muted">Probabilities unavailable for the current evidence.</p>}
    {result?.reason&&<p className="inference-reason">{result.reason}</p>}
    {!!used.length&&<div className="used-channels"><h5>Channels read</h5><ul>{used.map(c=><li key={c.name}><strong>{c.label}</strong>{c.current&&<span>{c.value===null?'Unavailable':`${c.value} ${c.unit}`}</span>}{c.history&&<small>History: {c.history}</small>}</li>)}</ul><small>Channels provide evidence; the model assigns probabilities to fault categories, not individual sensors.</small></div>}
   </section>;})}
  </section>}
 </>;
}
