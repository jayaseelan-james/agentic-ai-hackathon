import { useEffect, useRef, useState, type MouseEvent } from 'react';
import { Car, Plus, Menu, X, TriangleAlert, ScanLine } from 'lucide-react';
import { customerError, request, vehicleName, type ChatMode, type Health, type Incident } from './api';
import Composer from './components/Composer';
import MessageList, { BMW_PROMPTS } from './components/MessageList';
import { useSpokenAnswers } from './useSpokenAnswers';

const BMW_DEFAULT_VEHICLE = { make: 'BMW', model: '330i (G20)', year: null };
const SENSOR_CHECK_PROMPT = 'Check what’s wrong with my car using the available sensor readings and recorded history. Summarize what needs attention and the next safe action.';
const chatMode = (chat: Incident): ChatMode => chat.mode ?? (chat.vehicle?.model?.includes('330i') ? 'bmw_g20' : 'general');

function modeFromLocation(): ChatMode {
  const path = location.pathname.replace(/\/+$/, '') || '/';
  return path === '/bmw' || path === '/bmw-330i' || path === '/bmw-330i-g20' ? 'bmw_g20' : 'general';
}

export default function App({ initialMode = 'general' }: { initialMode?: ChatMode }) {
  const [mode, setMode] = useState<ChatMode>(initialMode);
  const [chats, setChats] = useState<Incident[]>([]);
  const [selectedByMode, setSelectedByMode] = useState<Record<ChatMode, string>>({ general: '', bmw_g20: '' });
  const [health, setHealth] = useState<Health>();
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const sending = useRef(false);
  const submission = useRef<{signature: string; id: string} | null>(null);
  const [error, setError] = useState('');
  const [sidebar, setSidebar] = useState(false);
  const [pollEpoch, setPollEpoch] = useState(0);
  const isBmw = mode === 'bmw_g20';
  const modeChats = chats.filter(c => chatMode(c) === mode);
  const selected = (selectedByMode[mode] && modeChats.some(c => c.id === selectedByMode[mode])) ? selectedByMode[mode] : (modeChats[0]?.id || '');
  const current = modeChats.find(c => c.id === selected);
  const speech = useSpokenAnswers(current);
  const busy = submitting || !!current?.messages.some(m => m.state === 'processing');
  const processingIds = chats.filter(c => c.messages.some(m => m.state === 'processing')).map(c => c.id).join(',');
  function selectChat(id: string, targetMode: ChatMode = mode) { setSelectedByMode(prev => ({ ...prev, [targetMode]: id })); }
  function update(chat: Incident, submitted = false) { if (submitted) speech.markSubmitted(chat); setChats(list => list.map(c => c.id === chat.id ? chat : c)); }
  async function load() {
    setLoading(true); setError('');
    try {
      const [list, status] = await Promise.all([request<Incident[]>('/incidents'), request<Health>('/health')]);
      setChats(list); setHealth(status);
      setSelectedByMode({
        general: list.find(c => chatMode(c) === 'general')?.id || '',
        bmw_g20: list.find(c => chatMode(c) === 'bmw_g20')?.id || '',
      });
    } catch { setError('Cannot reach the API. Start the backend, then retry.'); }
    finally { setLoading(false); }
  }
  useEffect(() => { void load(); }, []);
  useEffect(() => {
    if (processingIds) return;
    let cancelled = false;
    const timer = setInterval(async () => {
      if (document.hidden) return;
      try { const status = await request<Health>('/health'); if (!cancelled) setHealth(status); } catch { /* Submission errors remain actionable in the chat. */ }
    }, 2000);
    return () => { cancelled = true; clearInterval(timer); };
  }, [processingIds]);
  useEffect(() => {
    document.title = isBmw ? 'AutoSage · BMW 330i G20' : 'AutoSage';
  }, [isBmw]);
  useEffect(() => {
    const onPopState = () => { setMode(modeFromLocation()); setSidebar(false); setError(''); };
    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);
  useEffect(() => {
    if (!processingIds) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const [status, ...list] = await Promise.all([request<Health>('/health'), ...processingIds.split(',').map(id => request<Incident>(`/incidents/${id}`))]);
        if (!cancelled) { setHealth(status); setChats(prev => prev.map(chat => list.find(c => c.id === chat.id) || chat)); timer = setTimeout(() => void poll(), 1000); }
      } catch { if (!cancelled) setError('Status connection interrupted. Your submitted message is saved; resume status to check the result.'); }
    }
    timer = setTimeout(() => void poll(), 700);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [processingIds, pollEpoch]);
  function switchTab(e: MouseEvent<HTMLAnchorElement>, nextMode: ChatMode) {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
    e.preventDefault();
    if (nextMode === mode) return;
    const nextPath = nextMode === 'bmw_g20' ? '/bmw' : '/';
    if (location.pathname !== nextPath) history.pushState(null, '', nextPath);
    setMode(nextMode); setSidebar(false); setError('');
  }
  async function newChat() {
    if (sending.current) return;
    speech.stop();
    sending.current = true; setSubmitting(true);
    const body = isBmw ? JSON.stringify({ mode: 'bmw_g20', vehicle: BMW_DEFAULT_VEHICLE }) : '{}';
    try {
      const chat = await request<Incident>('/incidents', {method: 'POST', headers: {'Content-Type': 'application/json'}, body});
      setChats(c => [chat, ...c]); selectChat(chat.id, mode); setSidebar(false); setError('');
    } catch (e) { setError(customerError((e as Error).message)); }
    finally { sending.current = false; setSubmitting(false); }
  }
  async function send(text: string, files: File[], sensorCheck = false) {
    if (!current || sending.current || busy) return false;
    speech.stop();
    sending.current = true; setSubmitting(true); setError('');
    const signature = JSON.stringify([current.id, text, sensorCheck, files.map(f => [f.name, f.size, f.lastModified])]);
    if (submission.current?.signature !== signature) submission.current = {signature, id: crypto.randomUUID()};
    const form = new FormData(); form.append('request_id', submission.current.id); form.append('text', text); files.forEach(f => form.append('files', f));
    if (sensorCheck) form.append('sensor_check', 'true');
    try { update(await request<Incident>(`/incidents/${current.id}/messages`, {method: 'POST', body: form}), true); submission.current = null; return true; }
    catch (e) { setError(`${customerError((e as Error).message)} Your draft is preserved.`); return false; }
    finally { sending.current = false; setSubmitting(false); }
  }
  async function sendQuickPrompt(prompt: string, sensorCheck = false) {
    if (sending.current || busy) return;
    speech.stop();
    if (current) { void send(prompt, [], sensorCheck); return; }
    sending.current = true; setSubmitting(true); setError('');
    const createBody = isBmw ? JSON.stringify({ mode: 'bmw_g20', vehicle: BMW_DEFAULT_VEHICLE }) : '{}';
    try {
      const chat = await request<Incident>('/incidents', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: createBody});
      setChats(c => [chat, ...c]); selectChat(chat.id, mode);
      submission.current = {signature: JSON.stringify([chat.id, prompt, sensorCheck, []]), id: crypto.randomUUID()};
      const form = new FormData(); form.append('request_id', submission.current.id); form.append('text', prompt);
      if (sensorCheck) form.append('sensor_check', 'true');
      const updated = await request<Incident>(`/incidents/${chat.id}/messages`, {method: 'POST', body: form});
      speech.markSubmitted(updated);
      submission.current = null;
      setChats(c => c.map(item => item.id === updated.id ? updated : item));
    } catch (e) { setError(customerError((e as Error).message)); }
    finally { sending.current = false; setSubmitting(false); }
  }
  async function retry(id: string) {
    if (!current || busy || sending.current) return;
    speech.stop();
    sending.current = true; setSubmitting(true); setError('');
    try { update(await request<Incident>(`/incidents/${current.id}/messages/${id}/retry`, {method: 'POST'}), true); }
    catch (e) { setError(customerError((e as Error).message)); }
    finally { sending.current = false; setSubmitting(false); }
  }
  return <div className="app-shell">
    {sidebar && <button className="sidebar-backdrop" aria-label="Close navigation" onClick={() => setSidebar(false)}/>}
    <aside className={`sidebar ${sidebar ? 'open' : ''}`} aria-label="Chat navigation"><div className="brand"><Car/><span>AutoSage</span><button className="mobile-only" aria-label="Close navigation" onClick={() => setSidebar(false)}><X/></button></div>
      <button className="new-chat outline" aria-label="Start new chat" onClick={() => void newChat()} disabled={submitting || loading}><Plus/>New chat</button><h2>Recent chats</h2><nav>{modeChats.map(chat => <button key={chat.id} disabled={submitting} className={chat.id === selected ? 'selected' : ''} onClick={() => { selectChat(chat.id); setSidebar(false); setError(''); }}>{chat.title}</button>)}</nav>
      <div className="vehicle"><Car/><div><strong>Your vehicle</strong><p>{vehicleName(current?.vehicle || (isBmw ? BMW_DEFAULT_VEHICLE : undefined))}</p>{isBmw && <small className="vehicle-spec">2019–2024 · B46TU / B48TU Petrol</small>}</div></div>
    </aside>
    <main><div className="mobile-bar"><button aria-label="Open navigation" onClick={() => setSidebar(true)}><Menu/></button><Car/><strong>AutoSage</strong>{isBmw && <span className="mock-badge">BMW 330i</span>}</div><header className="chat-header"><div><div className="title-row"><h1>{current?.title || (isBmw ? 'BMW 330i G20' : 'AutoSage')}</h1>{isBmw && <span className="mock-badge">G20 · 2019–2024 Petrol</span>}</div></div><div className="workspace-tabs" role="tablist" aria-label="Diagnostic mode"><a href="/" role="tab" aria-selected={!isBmw} className={`workspace-tab ${!isBmw ? 'active' : ''}`} onClick={e => switchTab(e, 'general')}>General</a><a href="/bmw" role="tab" aria-selected={isBmw} className={`workspace-tab ${isBmw ? 'active' : ''}`} onClick={e => switchTab(e, 'bmw_g20')}>BMW 330i G20</a></div></header>

      <div className="sensor-check-action"><button type="button" className="primary" disabled={loading || busy} onClick={() => void sendQuickPrompt(SENSOR_CHECK_PROMPT, true)}><ScanLine/>Check what’s wrong with my car</button><p>Automatically review available sensor readings and recorded history.</p></div>
      {health?.internet_blocked && <div className="connectivity-notice" role="status"><strong>Remote breakdown mode · Gemma 4 26B</strong><span>Web access blocked · AI connection remains active</span></div>}
      {current?.safety && <div className="safety" role="alert"><TriangleAlert/><div><strong>Do not continue driving</strong><p>{current.safety}</p></div></div>}
      {error && <div className="error app-error" role="alert">{error}{processingIds ? <button className="outline" onClick={() => {setError(''); setPollEpoch(v => v + 1);}}>Resume status</button> : !current && <button className="outline" onClick={() => void load()}>Retry connection</button>}</div>}
      <div className="voice-preference"><button type="button" className="outline" aria-pressed={!speech.muted} onClick={speech.toggleMute}>{speech.muted ? 'Enable spoken answers' : 'Mute spoken answers'}</button><small>Short spoken summaries · Google AI voice</small></div>
      {loading ? <div className="empty" role="status">Connecting to API…</div> : current ? <><MessageList messages={current.messages} onRetry={id => void retry(id)} busy={busy} mode={mode} onQuickPrompt={prompt => void sendQuickPrompt(prompt)} speechStatuses={speech.statuses} onPlay={id => void speech.play(id)} onStop={speech.stop}/><Composer key={current.id} onSend={send} busy={busy} onCapture={speech.stop}/></> : !error && <div className="empty"><Car size={40}/><h2>{isBmw ? 'What’s happening with your BMW 330i (G20)?' : 'What’s happening with your car?'}</h2><p>{isBmw ? 'Investigate B46TU/B48TU petrol symptoms, Check Control & iDrive TPM warnings, recalls, and shared sensor readings.' : 'Start a conversation to share text, photos, audio or video with the assistant.'}</p><button className="primary" onClick={() => void newChat()}>Start a conversation</button>{isBmw && <div className="quick-prompts" aria-label="BMW 330i G20 starter examples">{BMW_PROMPTS.map(prompt => <button key={prompt} type="button" className="outline quick-prompt" disabled={busy} onClick={() => void sendQuickPrompt(prompt)}>{prompt}</button>)}</div>}</div>}
    </main>
  </div>;
}
