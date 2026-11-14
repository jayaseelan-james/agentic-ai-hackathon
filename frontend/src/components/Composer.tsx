import { useEffect, useRef, useState } from 'react';
import { Paperclip, Mic, Camera, Image, Video, Send, X } from 'lucide-react';
import Recorder from './Recorder';

type Draft = {id: string; file: File; url: string};
export default function Composer({ onSend, busy }: {onSend: (text: string, files: File[]) => Promise<boolean>; busy: boolean}) {
  const [text, setText] = useState('');
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const latest = useRef(drafts); latest.current = drafts;
  const [menu, setMenu] = useState(false);
  const [error, setError] = useState('');
  const [record, setRecord] = useState<'audio' | 'video' | null>(null);
  const upload = useRef<HTMLInputElement>(null);
  const menuContainer = useRef<HTMLDivElement>(null);
  const [accept, setAccept] = useState('image/*,video/*');
  useEffect(() => () => latest.current.forEach(d => URL.revokeObjectURL(d.url)), []);
  useEffect(() => {
    const close = (e: PointerEvent) => { if (!menuContainer.current?.contains(e.target as Node)) setMenu(false); };
    const escape = (e: KeyboardEvent) => { if (e.key === 'Escape') setMenu(false); };
    document.addEventListener('pointerdown', close); document.addEventListener('keydown', escape);
    return () => { document.removeEventListener('pointerdown', close); document.removeEventListener('keydown', escape); };
  }, []);
  function add(files: File[]) {
    const all = [...drafts.map(d => d.file), ...files];
    if (all.length > 5 || all.some(f => f.size > 25_000_000) || all.reduce((a, f) => a + f.size, 0) > 50_000_000) { setError('Limit: 5 files, 25 MB each, 50 MB total.'); return; }
    if (files.some(f => !/^(image|audio|video)\//.test(f.type) || !f.size)) { setError('Choose a non-empty image, audio, or video file.'); return; }
    setDrafts([...drafts, ...files.map(file => ({file, id: crypto.randomUUID(), url: URL.createObjectURL(file)}))]); setError('');
  }
  function pick(types: string) { setAccept(types); setMenu(false); if (upload.current) { upload.current.accept = types; upload.current.click(); } }
  async function send() {
    if (busy || (!text.trim() && !drafts.length)) return;
    if (await onSend(text, drafts.map(d => d.file))) { drafts.forEach(d => URL.revokeObjectURL(d.url)); setDrafts([]); setText(''); setError(''); }
  }
  return <div className="composer-area">
    {error && <p className="error" role="alert">{error}</p>}
    {drafts.length > 0 && <div className="drafts">{drafts.map(d => <div className="draft" key={d.id}>
      {d.file.type.startsWith('image/') ? <img src={d.url} alt={d.file.name}/> : d.file.type.startsWith('audio/') ? <audio src={d.url} controls/> : <video src={d.url} controls playsInline/>}
      <span title={d.file.name}>{d.file.name}</span><button disabled={busy} aria-label={`Remove ${d.file.name}`} onClick={() => { URL.revokeObjectURL(d.url); setDrafts(drafts.filter(item => item.id !== d.id)); }}><X size={18}/></button>
    </div>)}</div>}
    <div className="composer"><textarea aria-label="Message" placeholder="Describe what’s happening with your car…" maxLength={10000} value={text} disabled={busy} onChange={e => setText(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); void send(); } }}/>
      <div className="toolbar"><div ref={menuContainer} className="attachment-control">
        <button disabled={busy} aria-expanded={menu} aria-label="Attach" className={menu ? 'active' : ''} onClick={() => setMenu(!menu)}><Paperclip/><span>Attach</span></button>
        {menu && <div className="attach-menu"><button onClick={() => pick('image/*')}><Image/>Upload images</button><button onClick={() => pick('video/*')}><Video/>Upload video</button><button onClick={() => { setRecord('audio'); setMenu(false); }}><Mic/>Record audio</button><button onClick={() => { setRecord('video'); setMenu(false); }}><Video/>Record video</button><button onClick={() => pick('audio/*')}><Mic/>Upload audio</button></div>}
      </div><button disabled={busy} onClick={() => setRecord('audio')}><Mic/><span>Voice</span></button><button disabled={busy} onClick={() => setRecord('video')}><Camera/><span>Camera</span></button><button disabled={busy} onClick={() => pick('image/*,video/*')}><Image/><span>Gallery</span></button>
      <button className="send primary" aria-label="Send message" disabled={busy || (!text.trim() && !drafts.length)} onClick={() => void send()}><Send/></button></div>
    </div><p className="composer-hint">{busy ? 'Reviewing the evidence…' : 'Media is sent to Google for analysis. Review before sending.'}</p>
    <input ref={upload} type="file" hidden multiple accept={accept} onChange={e => { add(Array.from(e.target.files || [])); e.target.value = ''; }}/>
    {record && <Recorder kind={record} onClose={() => setRecord(null)} onAttach={file => add([file])}/>}
  </div>;
}
