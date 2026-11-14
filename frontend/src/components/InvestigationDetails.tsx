import {useEffect, useRef} from 'react';
import {ExternalLink} from 'lucide-react';
import type {DiagnosticInference, Message} from '../api';

const DOMAINS:Record<string,string>={tire:'Tires',brake:'Brakes',cooling:'Cooling',starting_charging:'Starting and charging',engine_running:'Engine running'};
const TOOLS:Record<string,string>={gemini:'Analyzing the problem',google_search:'Searching the web',url_context:'Reading a reference page',process_media:'Analyzing media',record_observations:'Recording observations',get_vehicle_profile:'Checking vehicle details',update_vehicle_profile:'Saving vehicle details',classify_diagnosis:'Updating Bayesian probabilities',read_vehicle_sensors:'Reading vehicle sensors',read_sensor_history:'Checking sensor history',list_available_sensors:'Discovering sensor channels',evaluate_safety:'Checking safety',create_mechanic_report:'Preparing mechanic handoff',tool_validation:'Validating a tool call',delete_provider_file:'Removing temporary media'};
const label=(s:string)=>s.replaceAll('_',' ');
const status=(s:string)=>s==='running'?'In progress':s==='failed'?'Failed':'Complete';

export default function InvestigationDetails({message}:{message:Message}) {
 const dropdown=useRef<HTMLDetailsElement>(null);
 useEffect(()=>{if(message.state!=='processing'&&dropdown.current)dropdown.current.open=false;},[message.state]);
 const running=message.state==='processing';
 const current=message.activity.at(-1);
 const currentLabel=current?(TOOLS[current.tool]||label(current.tool)):'Reviewing the evidence';
 const results=new Map<string,DiagnosticInference>();
 for(const e of message.activity){if(e.tool==='classify_diagnosis'&&e.status==='complete'&&e.result&&typeof e.result.domain==='string'&&Array.isArray(e.result.ranked_hypotheses))results.set(e.result.domain,e.result as unknown as DiagnosticInference);}
 for(const result of message.diagnostic_inference||[])results.set(result.domain,result);
 const domains=[...results.keys()];
 if(!running&&!message.activity.length&&!domains.length&&!message.citations.length&&!message.search_suggestions.length)return null;
 return <details ref={dropdown} className="activity investigation-dropdown"><summary><span className={running?'current-event processing':'details-label'}>{running&&<span className="event-spinner" aria-hidden="true"/>}{current?currentLabel:running?'Reviewing the evidence':message.state==='failed'?'Investigation details · Needs retry':'Investigation details'}</span><span className="details-count">{message.activity.length} events</span><span className="details-chevron" aria-hidden="true">⌄</span></summary><div className="investigation-dropdown-body">
  {!!domains.length&&<section className="bayesian-results" aria-label="Bayesian probabilities"><h3>Bayesian probabilities</h3><p className="probability-note">Model estimates, not validated diagnostic confidence.</p>
   {domains.map(domain=>{const result=results.get(domain);const ranked=(result?.ranked_hypotheses||[]).filter(h=>Number.isFinite(h.posterior)&&h.posterior>=0&&h.posterior<=1);return <section className="probability-domain" key={domain} aria-label={`${DOMAINS[domain]||label(domain)} probabilities`}><h4>{DOMAINS[domain]||label(domain)}</h4>{result&&<p className="inference-status">{label(result.status)}{result.conflicts?.length?' · Conflicting observations':''}</p>}
    {ranked.length?<div className="probability-chart" role="img" aria-label={`${DOMAINS[domain]||label(domain)} probability chart: ${ranked.map(h=>`${label(h.fault_id)} ${(h.posterior*100).toFixed(1)}%`).join(', ')}`}><div className="probability-scale"><span>0%</span><span>50%</span><span>100%</span></div>{ranked.map(h=><div className="probability-row" key={h.fault_id}><div className="probability-label"><span>{label(h.fault_id)}</span><strong>{(h.posterior*100).toFixed(1)}%</strong></div><div className="probability-track"><div className="probability-fill" style={{width:`${h.posterior*100}%`}}/></div></div>)}</div>:<p className="muted">Probabilities unavailable for the current evidence.</p>}
   </section>;})}
  </section>}
  {!!message.activity.length&&<section className="investigation-activity" aria-label="Investigation events"><h3>Events</h3><ol>{message.activity.map(e=><li key={e.id} className={`event-${e.status}`}><div><strong>{TOOLS[e.tool]||label(e.tool)}</strong><span className="event-status">{status(e.status)}</span></div><p>{e.summary}</p><small>{new Date(e.timestamp).toLocaleTimeString()} · {e.initiator==='model'?'Agent':'Backend'}</small></li>)}</ol></section>}
      {message.citations.length > 0 && <div className="sources"><strong>Sources</strong>{[...new Map(message.citations.map(source => [source.url, source])).values()].map((source, i) => <a key={source.url} href={source.url} target="_blank" rel="noreferrer">{i + 1}. {source.title}<ExternalLink size={13}/></a>)}</div>}
      {message.search_suggestions.map((html, i) => <iframe key={i} className="search-suggestions" title={`Google Search suggestions ${i + 1}`} sandbox="allow-popups allow-popups-to-escape-sandbox" referrerPolicy="no-referrer" srcDoc={`<!doctype html><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline' https:; img-src https: data:; font-src https:"><base target="_blank">${html}`}/>)}
 </div></details>;
}
