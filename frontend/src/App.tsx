import { useEffect, useRef, useState } from 'react';
import { Car, Plus, Menu, X, TriangleAlert } from 'lucide-react';
import { customerError, request, vehicleName, type Health, type Incident } from './api';
import Composer from './components/Composer';
import MessageList from './components/MessageList';

export default function App() {
  const [chats, setChats] = useState<Incident[]>([]);
  const [selected, setSelected] = useState('');
  const [health, setHealth] = useState<Health>();
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const sending = useRef(false);
  const submission = useRef<{signature: string; id: string} | null>(null);
  const [error, setError] = useState('');
  const [sidebar, setSidebar] = useState(false);
  const [pollEpoch, setPollEpoch] = useState(0);
  const current = chats.find(c => c.id === selected);
  const busy = submitting || !!current?.messages.some(m => m.state === 'processing');
  const processingIds = chats.filter(c => c.messages.some(m => m.state === 'processing')).map(c => c.id).join(',');
  function update(chat: Incident) { setChats(chats => chats.map(c => c.id === chat.id ? chat : c)); }
  async function load() {
    setLoading(true); setError('');
    try { const [list, status] = await Promise.all([request<Incident[]>('/incidents'), request<Health>('/health')]); setChats(list); setHealth(status); setSelected(list[0]?.id || ''); }
    catch { setError('Cannot reach the API. Start the backend, then retry.'); }
    finally { setLoading(false); }
  }
  useEffect(() => { void load(); }, []);
  useEffect(() => {
    if (!processingIds) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const [status, ...list] = await Promise.all([request<Health>('/health'), ...processingIds.split(',').map(id => request<Incident>(`/incidents/${id}`))]);
        if (!cancelled) { setHealth(status); setChats(chats => chats.map(chat => list.find(c => c.id === chat.id) || chat)); timer = setTimeout(() => void poll(), 1000); }
      } catch { if (!cancelled) setError('Status connection interrupted. Your submitted message is saved; resume status to check the result.'); }
    }
    timer = setTimeout(() => void poll(), 700);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [processingIds, pollEpoch]);
  async function newChat() {
    if (sending.current) return;
    sending.current = true; setSubmitting(true);
    try { const chat = await request<Incident>('/incidents', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}'}); setChats(c => [chat, ...c]); setSelected(chat.id); setSidebar(false); setError(''); }
    catch (e) { setError(customerError((e as Error).message)); }
    finally { sending.current = false; setSubmitting(false); }
  }
  async function send(text: string, files: File[]) {
    if (!current || sending.current || busy) return false;
    sending.current = true; setSubmitting(true); setError('');
    const signature = JSON.stringify([current.id, text, files.map(f => [f.name, f.size, f.lastModified])]);
    if (submission.current?.signature !== signature) submission.current = {signature, id: crypto.randomUUID()};
    const form = new FormData(); form.append('request_id', submission.current.id); form.append('text', text); files.forEach(f => form.append('files', f));
    try { update(await request<Incident>(`/incidents/${current.id}/messages`, {method: 'POST', body: form})); submission.current = null; return true; }
    catch (e) { setError(`${customerError((e as Error).message)} Your draft is preserved.`); return false; }
    finally { sending.current = false; setSubmitting(false); }
  }
  async function retry(id: string) {
    if (!current || busy || sending.current) return;
    sending.current = true; setSubmitting(true); setError('');
    try { update(await request<Incident>(`/incidents/${current.id}/messages/${id}/retry`, {method: 'POST'})); }
    catch (e) { setError(customerError((e as Error).message)); }
    finally { sending.current = false; setSubmitting(false); }
  }
  return <div className="app-shell">
    {sidebar && <button className="sidebar-backdrop" aria-label="Close navigation" onClick={() => setSidebar(false)}/>}
    <aside className={`sidebar ${sidebar ? 'open' : ''}`} aria-label="Chat navigation"><div className="brand"><Car/><span>AutoSage</span><button className="mobile-only" aria-label="Close navigation" onClick={() => setSidebar(false)}><X/></button></div>
      <button className="new-chat outline" aria-label="Start new chat" onClick={() => void newChat()} disabled={submitting || loading}><Plus/>New chat</button><h2>Recent chats</h2><nav>{chats.map(chat => <button key={chat.id} disabled={submitting} className={chat.id === selected ? 'selected' : ''} onClick={() => { setSelected(chat.id); setSidebar(false); setError(''); }}>{chat.title}</button>)}</nav>
      <div className="vehicle"><Car/><div><strong>Your vehicle</strong><p>{vehicleName(current?.vehicle)}</p></div></div>
    </aside>
    <main><div className="mobile-bar"><button aria-label="Open navigation" onClick={() => setSidebar(true)}><Menu/></button><Car/><strong>AutoSage</strong></div><header className="chat-header"><div><div className="title-row"><h1>{current?.title || 'AutoSage'}</h1></div></div></header>

      {current?.safety && <div className="safety" role="alert"><TriangleAlert/><div><strong>Do not continue driving</strong><p>{current.safety}</p></div></div>}
      {error && <div className="error app-error" role="alert">{error}{processingIds ? <button className="outline" onClick={() => {setError(''); setPollEpoch(v => v + 1);}}>Resume status</button> : !current && <button className="outline" onClick={() => void load()}>Retry connection</button>}</div>}
      {loading ? <div className="empty" role="status">Connecting to API…</div> : current ? <><MessageList messages={current.messages} onRetry={id => void retry(id)} busy={busy}/><Composer key={current.id} onSend={send} busy={busy}/></> : !error && <div className="empty"><Car size={40}/><h2>What’s happening with your car?</h2><p>Start a conversation to share text, photos, audio or video with the assistant.</p><button className="primary" onClick={() => void newChat()}>Start a conversation</button></div>}
    </main>
  </div>;
}
