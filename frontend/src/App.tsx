import { useEffect, useRef, useState } from 'react';
import { Car, Plus, Info, Menu, X, TriangleAlert } from 'lucide-react';
import { request, type Incident } from './api';
import Composer from './components/Composer';
import MessageList from './components/MessageList';

export default function App() {
  const [chats, setChats] = useState<Incident[]>([]);
  const [selected, setSelected] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const sending = useRef(false);
  const [error, setError] = useState('');
  const [sidebar, setSidebar] = useState(false);
  const current = chats.find(c => c.id === selected);
  async function load() {
    setLoading(true); setError('');
    try { const list = await request<Incident[]>('/incidents'); setChats(list); setSelected(list[0]?.id || ''); }
    catch { setError('Cannot reach the mock API. Start the backend, then retry.'); }
    finally { setLoading(false); }
  }
  useEffect(() => { void load(); }, []);
  async function newChat() {
    if (sending.current) return;
    sending.current = true; setBusy(true);
    try { const chat = await request<Incident>('/incidents', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}'}); setChats(c => [chat, ...c]); setSelected(chat.id); setSidebar(false); setError(''); }
    catch (e) { setError((e as Error).message); }
    finally { sending.current = false; setBusy(false); }
  }
  async function send(text: string, files: File[]) {
    if (!current || sending.current) return false;
    sending.current = true; setBusy(true); setError('');
    const form = new FormData(); form.append('text', text); files.forEach(f => form.append('files', f));
    try { const updated = await request<Incident>(`/incidents/${current.id}/messages`, {method: 'POST', body: form}); setChats(chats => chats.map(c => c.id === updated.id ? updated : c)); return true; }
    catch (e) { setError(`${(e as Error).message} Your draft is preserved.`); return false; }
    finally { sending.current = false; setBusy(false); }
  }
  return <div className="app-shell">
    {sidebar && <button className="sidebar-backdrop" aria-label="Close navigation" onClick={() => setSidebar(false)}/>}
    <aside className={`sidebar ${sidebar ? 'open' : ''}`} aria-label="Chat navigation"><div className="brand"><Car/><span>AutoSage</span><button className="mobile-only" aria-label="Close navigation" onClick={() => setSidebar(false)}><X/></button></div>
      <button className="new-chat outline" aria-label="Start new chat" onClick={() => void newChat()} disabled={busy || loading}><Plus/>New chat</button><h2>Recent chats</h2><nav>{chats.map(chat => <button key={chat.id} disabled={busy} className={chat.id === selected ? 'selected' : ''} onClick={() => { setSelected(chat.id); setSidebar(false); setError(''); }}>{chat.title}</button>)}</nav>
      <div className="vehicle"><Car/><div><strong>Demo vehicle</strong><p>Synthetic Demo Sedan</p></div></div>
    </aside>
    <main><div className="mobile-bar"><button aria-label="Open navigation" onClick={() => setSidebar(true)}><Menu/></button><Car/><strong>AutoSage</strong><span className="mock-badge">Mock demo</span></div><header className="chat-header"><div><div className="title-row"><h1>{current?.title || 'AutoSage'}</h1><span className="mock-badge">Mock demo</span></div><p>Synthetic Demo Sedan</p></div></header>
      <div className="notice"><Info size={21}/><span>Demo responses — no live diagnosis or vehicle connection.</span></div>
      {current?.safety && <div className="safety" role="alert"><TriangleAlert/><div><strong>Do not continue driving</strong><p>{current.safety}</p></div></div>}
      {error && <div className="error app-error" role="alert">{error}{!current && <button className="outline" onClick={() => void load()}>Retry connection</button>}</div>}
      {loading ? <div className="empty" role="status">Connecting to mock API…</div> : current ? <><MessageList messages={current.messages}/><Composer key={current.id} onSend={send} busy={busy}/></> : !error && <div className="empty"><h2>Start a conversation</h2><button className="primary" onClick={() => void newChat()}>New chat</button></div>}
    </main>
  </div>;
}
