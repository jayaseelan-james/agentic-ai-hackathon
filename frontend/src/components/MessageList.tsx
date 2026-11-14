import { useEffect, useRef, useState } from 'react';
import { Car } from 'lucide-react';
import Markdown from 'react-markdown';
import InvestigationDetails from './InvestigationDetails';
import {customerError, type ChatMode, type Message, type MechanicReport} from '../api';
import type { SpeechStatus } from '../useSpokenAnswers';

export const BMW_PROMPTS = [
  'My yellow TPMS warning is showing on iDrive.',
  'Coolant loss is recurring in slow traffic.',
  'Clicking without cranking on start — could a BMW 330i starter recall apply?',
  'My engine idles roughly with a check-engine warning.',
];

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
  const text = ['AutoSage mechanic handoff', `Vehicle: ${[report.vehicle.year, report.vehicle.make, report.vehicle.model].filter(Boolean).join(' ') || 'Not provided'}`, `Reported symptoms:\n${report.reported_symptoms.join('\n')}`, `Unconfirmed AI assessment:\n${report.assistant_assessments_unconfirmed.join('\n\n')}`, `Media observations (unconfirmed):\n${(report.media_observations||[]).map(e=>e.quote+(e.value===null?" (uncertain)":"")).join("\n")}`, `Uncertainties:\n${report.uncertainties.join('\n')}`, report.safety || '', `Sources:\n${report.sources.map(s => `${s.title}: ${s.url}`).join('\n')}`, ...(report.simulated_sensor_evidence?.length ? [`Sensor evidence:\n${'Available sensor readings were considered; they do not confirm a mechanical fault.'}`] : [])].join('\n\n');
  return <details className="report"><summary>Mechanic handoff</summary><p>Reported symptoms</p><ul>{report.reported_symptoms.map((s, i) => <li key={i}>{s}</li>)}</ul>{!!report.media_observations?.length&&<><p>Media observations (unconfirmed)</p><ul>{report.media_observations.map(e=><li key={e.id}>{e.quote}{e.value===null?" (uncertain)":""}</li>)}</ul></>}<small>{report.uncertainties.join(' ')}</small>{report.unresolved_questions?.map(question => <p key={question.id}>Unresolved: {question.text}</p>)}<button className="outline" onClick={async () => { try { await navigator.clipboard.writeText(text); setFeedback('Report copied'); } catch { setFeedback('Copy unavailable. Select the report text to copy.'); } }}>Copy report</button><span role="status">{feedback}</span></details>;
}

export default function MessageList({messages, onRetry, busy, mode = 'general', onQuickPrompt, speechStatuses, onPlay, onStop}: {messages: Message[]; onRetry: (id: string) => void; busy: boolean; mode?: ChatMode; onQuickPrompt?: (prompt: string) => void; speechStatuses: Record<string, SpeechStatus>; onPlay: (id: string) => void; onStop: () => void}) {
  const isBmw = mode === 'bmw_g20';
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const list = end.current?.parentElement;
    const latest = list?.querySelector('article:last-of-type');
    if (latest && list && latest.clientHeight > list.clientHeight) latest.scrollIntoView({block:'start'});
    else end.current?.scrollIntoView({block:'end'});
  }, [messages.length, messages.at(-1)?.state]);
  return <div className="messages" role="log" aria-label="Conversation" aria-live="polite">
    {!messages.length && <div className="empty"><Car size={40}/><h2>{isBmw ? 'What’s happening with your BMW 330i (G20)?' : 'What’s happening with your car?'}</h2><p>{isBmw ? 'Describe a Check Control message, iDrive warning, noise, or symptom — or add a photo, voice note, or clip.' : 'Describe it, record it, or add a photo.'}</p><small>{isBmw ? '2019–2024 BMW 330i petrol (B46TU/B48TU) · Uses shared vehicle sensor readings when enabled.' : 'Share what you noticed. We will narrow it down together.'}</small>{isBmw && onQuickPrompt && <div className="quick-prompts" aria-label="BMW 330i G20 starter examples">{BMW_PROMPTS.map(prompt => <button key={prompt} type="button" className="outline quick-prompt" disabled={busy} onClick={() => onQuickPrompt(prompt)}>{prompt}</button>)}</div>}</div>}
    {messages.map((message, index) => <article key={message.id} className={`message ${message.role}`}>
      {message.role === 'assistant' && <span className="avatar"><Car/></span>}<div className="message-content"><div className="bubble">
        {message.text && (message.role === 'user' ? <p>{message.text}</p> : <div className="answer-markdown"><Markdown skipHtml components={{a: ({href, children}) => message.citations.some(c => c.url === href) ? <a href={href} target="_blank" rel="noreferrer">{children}</a> : <span>{children}</span>, img: () => null}}>{annotated(message)}</Markdown></div>)}
        {message.follow_up_question && <p className="diagnostic-question">{message.follow_up_question.text}</p>}
        {message.state === 'failed' && <div className="generation-error"><p role="alert">{customerError(message.error || 'Investigation failed.')}</p>{index === messages.length - 1 && <button className="outline" disabled={busy} onClick={() => onRetry(message.id)}>Retry investigation</button>}</div>}
        {message.attachments.map(file => <div className="sent-media" key={file.id}>{file.kind === 'image' ? <a href={file.url} target="_blank" rel="noreferrer"><img src={file.url} alt={file.filename}/></a> : file.kind === 'audio' ? <audio src={file.url} controls/> : <video src={file.url} controls playsInline/>}<small>{file.filename}</small></div>)}
        {message.role === 'assistant' && message.state === 'processing' && <small>Analyzing the problem…</small>}
        {message.role === 'assistant' && message.provider === 'gemma' && <small className="model-attribution">Gemma 4 26B · Web access blocked</small>}
        {message.role === 'assistant' && message.provider === 'safety_rules' && message.state !== 'processing' && <small>Professional assistance recommended</small>}
      </div>
      {message.role === 'assistant' && message.state === 'complete' && message.text && <div className="speech-controls">
        {speechStatuses[message.id]?.stage === 'loading' || speechStatuses[message.id]?.stage === 'playing'
          ? <button className="outline" onClick={onStop}>{speechStatuses[message.id].stage === 'loading' ? 'Cancel speech' : 'Stop speaking'}</button>
          : <button className="outline" onClick={() => onPlay(message.id)}>{speechStatuses[message.id]?.stage === 'error' ? 'Retry speech' : 'Play answer'}</button>}
        {speechStatuses[message.id]?.stage === 'loading' && <span role="status">Preparing speech…</span>}
        {speechStatuses[message.id]?.error && <span role="status">{speechStatuses[message.id].error}</span>}
        {speechStatuses[message.id]?.text && <details><summary>Spoken summary</summary><p>{speechStatuses[message.id].text}</p></details>}
      </div>}
      {message.role === 'assistant' && <InvestigationDetails message={message}/>}
      {message.report && <Report report={message.report}/>}</div>
    </article>)}<div ref={end}/>
  </div>;
}
