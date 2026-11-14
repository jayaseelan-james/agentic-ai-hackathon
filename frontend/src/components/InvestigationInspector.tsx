import { useEffect, useState } from 'react';
import { request, type Health, type Incident, type Message, type DiagnosticEvidence } from '../api';

type Inspection = {incident: Incident; evidence: DiagnosticEvidence[]; report: unknown; provider: Health};

export default function InvestigationInspector() {
  const [chats,setChats]=useState<Incident[]>([]);
  const [selected,setSelected]=useState('');
  const [data,setData]=useState<Inspection>();
  const [health,setHealth]=useState<Health>();
  const [error,setError]=useState('');
  useEffect(()=>{
    let cancelled=false;
    async function load(){
      try{
        const [list,status]=await Promise.all([request<Incident[]>('/incidents'),request<Health>('/health')]);
        const detail=selected?await request<Inspection>(`/incidents/${selected}/inspection`):undefined;
        if(!cancelled){setChats(list);setHealth(status);setData(detail);setError('');}
      }catch(e){if(!cancelled)setError((e as Error).message);}
    }
    void load();const timer=setInterval(()=>{if(!document.hidden)void load();},2000);
    return()=>{cancelled=true;clearInterval(timer);};
  },[selected]);
  return <details className="operator-inspector"><summary>Investigation inspector</summary>
    <p className="muted">Technical details for testing. Selecting a chat here does not change the shared readings.</p>
    <div className="provider-status">{health?.configured?'Credentials configured':'Credentials missing'} · {health?.model || 'Loading provider'} · {health?.verified?'Verified in this process':'Not yet verified in this process'}</div>
    <label className="inspector-select">Inspect chat<select value={selected} onChange={e=>{setSelected(e.target.value);setData(undefined);}}><option value="">Choose a conversation</option>{chats.map(c=><option key={c.id} value={c.id}>{c.mode==='bmw_g20'?'[BMW 330i G20] ':''}{c.title} · {c.id.slice(0,8)}</option>)}</select></label>
    {error&&<p className="error" role="alert">{error}</p>}
    {data&&<>
      <section aria-label="Accepted evidence"><h3>Evidence registry</h3>{data.evidence.length?<div className="inspection-table"><table><thead><tr><th>Observation</th><th>Value</th><th>Source</th><th>Context</th><th>State</th></tr></thead><tbody>{data.evidence.map(e=><tr key={e.id}><td>{e.symptom.replaceAll('_',' ')}</td><td>{e.value===null?'Unknown':e.value?'Yes':'No'}</td><td>{e.source.replaceAll('_',' ')}{e.attachment_id?` · ${e.attachment_id.slice(0,8)}`:''}</td><td>{e.context}</td><td>{e.superseded?'Superseded':'Current'}</td></tr>)}</tbody></table></div>:<p>No registered observations yet.</p>}</section>
      {data.incident.messages.filter(m=>m.role==='assistant').map(m=><MessageInspection key={m.id} message={m}/>)}
      <details><summary>Full report and provenance</summary><pre>{JSON.stringify(data.report,null,2)}</pre></details>
    </>}
  </details>;
}

function MessageInspection({message}:{message:Message}) {
  return <section className="inspection-message"><h3>{new Date(message.timestamp).toLocaleTimeString()} · {message.state}</h3>
    <p>{message.provider} · {message.model || 'Deterministic guidance'}</p>{message.error&&<p className="error">{message.error}</p>}
    {message.simulator_snapshot&&<p>Simulator snapshot: revision {message.simulator_snapshot.revision} · {message.simulator_snapshot.enabled?'enabled':'disabled'}</p>}
    {message.simulator_snapshot?.internet_blocked&&<p>Remote breakdown simulation · Gemma 4 26B via Gemini API · Web access blocked</p>}
    {message.media_analysis?.map((a,i)=><p key={i}>{a.kind} · {a.status} · {a.attachment_id}</p>)}
    {message.diagnostic_inference?.map(result=><details key={result.domain}><summary>{result.domain.replaceAll('_',' ')} · {result.status.replaceAll('_',' ')}</summary><p>{result.disclaimer || 'Synthetic-trained model; not real-world confidence.'}</p>{result.ranked_hypotheses.map(h=><p key={h.fault_id}>{h.fault_id.replaceAll('_',' ')}: {(h.posterior*100).toFixed(1)}%</p>)}<pre>{JSON.stringify(result,null,2)}</pre></details>)}
    <details><summary>Tool activity · {message.activity.length} events</summary>{message.activity.map(e=><div className="inspection-event" key={e.id}><strong>{e.tool}</strong> · {e.initiator} · {e.status}<p>{e.summary}</p>{(e.arguments||e.result)&&<pre>{JSON.stringify({arguments:e.arguments,result:e.result},null,2)}</pre>}</div>)}</details>
  </section>;
}
