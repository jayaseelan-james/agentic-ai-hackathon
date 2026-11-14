import { useEffect, useRef, useState } from 'react';
import { Car, ChevronDown, ExternalLink } from 'lucide-react';
import Markdown from 'react-markdown';
import type { Message, MechanicReport } from '../api';

function annotated(message: Message) {
  const characters = Array.from(message.text);
  const urls = [...new Set(message.citations.map(c => c.url))];
  const seen = new Set<string>();
  const inserts = message.citations.map(citation => ({...citation, label: urls.indexOf(citation.url) + 1})).filter(c => {const key = `${c.url}:${c.end_index}`; if (seen.has(key)) return false; seen.add(key); return c.end_index !== null && c.end_index <= characters.length;}).sort((a, b) => b.end_index! - a.end_index!);
  for (const item of inserts) characters.splice(item.end_index!, 0, ` [${item.label}](${item.url})`);
  return characters.join('');
}

function Report({report}: {report: MechanicReport}) {
  const [feedback, setFeedback] = useState('');
  const text = ['AutoSage mechanic handoff', `Vehicle: ${[report.vehicle.year, report.vehicle.make, report.vehicle.model].filter(Boolean).join(' ') || 'Not provided'}`, `Reported symptoms:\n${report.reported_symptoms.join('\n')}`, `Unconfirmed AI assessment:\n${report.assistant_assessments_unconfirmed.join('\n\n')}`, `Uncertainties:\n${report.uncertainties.join('\n')}`, report.safety || '', `Sources:\n${report.sources.map(s => `${s.title}: ${s.url}`).join('\n')}`, ...(report.simulated_sensor_evidence?.length ? [`Simulated sensor evidence (not measurements from the user vehicle):\n${JSON.stringify(report.simulated_sensor_evidence, null, 2)}`] : [])].join('\n\n');
  return <details className="report"><summary>Mechanic handoff</summary><p>Reported symptoms</p><ul>{report.reported_symptoms.map((s, i) => <li key={i}>{s}</li>)}</ul><small>{report.uncertainties.join(' ')}</small><button className="outline" onClick={async () => { try { await navigator.clipboard.writeText(text); setFeedback('Report copied'); } catch { setFeedback('Copy unavailable. Select the report text to copy.'); } }}>Copy report</button><span role="status">{feedback}</span></details>;
}

export default function MessageList({messages, onRetry, busy}: {messages: Message[]; onRetry: (id: string) => void; busy: boolean}) {
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const list = end.current?.parentElement;
    const latest = list?.querySelector('article:last-of-type');
    if (latest && list && latest.clientHeight > list.clientHeight) latest.scrollIntoView({block:'start'});
    else end.current?.scrollIntoView({block:'end'});
  }, [messages.length, messages.at(-1)?.state]);
  return <div className="messages" role="log" aria-label="Conversation" aria-live="polite">
    {!messages.length && <div className="empty"><Car size={40}/><h2>What’s happening with your car?</h2><p>Describe it, record it, or add a photo.</p><small>Gemini can investigate the evidence. No vehicle connection.</small></div>}
    {messages.map((message, index) => <article key={message.id} className={`message ${message.role}`}>
      {message.role === 'assistant' && <span className="avatar"><Car/></span>}<div className="message-content"><div className="bubble">
        {message.text && (message.role === 'user' ? <p>{message.text}</p> : <div className="answer-markdown"><Markdown skipHtml components={{a: ({href, children}) => message.citations.some(c => c.url === href) ? <a href={href} target="_blank" rel="noreferrer">{children}</a> : <span>{children}</span>, img: () => null}}>{annotated(message)}</Markdown></div>)}
        {message.state === 'processing' && <p className="processing" role="status">Investigating with Gemini…</p>}
        {message.state === 'failed' && <div className="generation-error"><p role="alert">{message.error || 'Investigation failed.'}</p>{index === messages.length - 1 && <button className="outline" disabled={busy} onClick={() => onRetry(message.id)}>Retry investigation</button>}</div>}
        {message.attachments.map(file => <div className="sent-media" key={file.id}>{file.kind === 'image' ? <a href={file.url} target="_blank" rel="noreferrer"><img src={file.url} alt={file.filename}/></a> : file.kind === 'audio' ? <audio src={file.url} controls/> : <video src={file.url} controls playsInline/>}<small>{file.filename}</small></div>)}
        {message.role === 'assistant' && <small>{message.provider === 'safety_rules' ? 'Safety guidance · Professional assistance recommended' : `Gemini${message.model ? ` · ${message.model}` : ''} · Findings are unconfirmed`}</small>}
      </div>
      {message.citations.length > 0 && <div className="sources"><strong>Sources</strong>{[...new Map(message.citations.map(source => [source.url, source])).values()].map((source, i) => <a key={source.url} href={source.url} target="_blank" rel="noreferrer">{i + 1}. {source.title}<ExternalLink size={13}/></a>)}</div>}
      {message.search_suggestions.map((html, i) => <iframe key={i} className="search-suggestions" title={`Google Search suggestions ${i + 1}`} sandbox="allow-popups allow-popups-to-escape-sandbox" referrerPolicy="no-referrer" srcDoc={`<!doctype html><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline' https:; img-src https: data:; font-src https:"><base target="_blank">${html}`}/>)}
      {message.activity.length > 0 && <details className="activity"><summary><ChevronDown size={18}/><strong>Investigation activity</strong><span>{message.activity.length} events</span></summary><ul>{message.activity.map(event => <li key={event.id}><strong>{event.tool}</strong> · {event.initiator} · {event.status}<p>{event.summary}{event.result?.source === 'simulated' && ` · simulated · revision ${event.result.revision}`}</p>{event.arguments && <details className="tool-data"><summary>Tool arguments</summary><pre>{JSON.stringify(event.arguments, null, 2)}</pre></details>}{event.result && <details className="tool-data"><summary>Tool result</summary><pre>{JSON.stringify(event.result, null, 2)}</pre></details>}</li>)}</ul></details>}
      {message.report && <Report report={message.report}/>}</div>
    </article>)}<div ref={end}/>
  </div>;
}
