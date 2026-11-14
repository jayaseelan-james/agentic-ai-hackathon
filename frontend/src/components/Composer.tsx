import { useEffect, useRef, useState } from 'react';
import { Paperclip, Mic, Camera, Image, Video, Send, X } from 'lucide-react';
import Recorder from './Recorder';
import { request } from '../api';

type Draft = {id: string; file: File; url: string};
export default function Composer({ onSend, busy, onCapture }: {onSend: (text: string, files: File[]) => Promise<boolean>; busy: boolean; onCapture: () => void}) {
  const [text, setText] = useState('');
  const latestText = useRef(text); latestText.current = text;
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const latest = useRef(drafts); latest.current = drafts;
  const [menu, setMenu] = useState(false);
  const [error, setError] = useState('');
  const [record, setRecord] = useState<'audio' | 'video' | null>(null);
  const [dictation, setDictation] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [voiceFile, setVoiceFile] = useState<File | null>(null);
  const [voiceError, setVoiceError] = useState('');
  const transcription = useRef<AbortController | null>(null);
  useEffect(() => () => transcription.current?.abort(), []);
  function cancelTranscription() {
    transcription.current?.abort(); transcription.current = null;
    setTranscribing(false); setVoiceFile(null); setVoiceError('');
  }
  async function transcribe(file: File) {
    transcription.current?.abort();
    const controller = new AbortController(); transcription.current = controller;
    setVoiceFile(file); setVoiceError(''); setTranscribing(true);
    const form = new FormData(); form.append('file', file);
    try {
      const result = await request<{text: string}>('/speech/transcriptions', {method: 'POST', body: form, signal: controller.signal}, 135000);
      if (controller.signal.aborted) return;
      const combined = [latestText.current.trimEnd(), result.text].filter(Boolean).join('\n');
      if (combined.length > 10000) setVoiceError('The transcript and draft exceed 10,000 characters. Shorten the draft and retry transcription.');
      else { setText(combined); setVoiceFile(null); }
    } catch (e) { if (!controller.signal.aborted) setVoiceError((e as Error).message); }
    finally { if (!controller.signal.aborted) setTranscribing(false); }
  }
  function capture(kind: 'audio' | 'video', asDictation = false) {
    onCapture(); setDictation(asDictation); setRecord(kind); setMenu(false);
  }
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
    if (busy || transcribing || record || (!text.trim() && !drafts.length)) return;
    if (await onSend(text, drafts.map(d => d.file))) { drafts.forEach(d => URL.revokeObjectURL(d.url)); setDrafts([]); setText(''); setError(''); }
  }
  return <div className="composer-area">
    {(transcribing || voiceFile || voiceError) && <div className="dictation-status" role="status">
      <span>{transcribing ? 'Transcribing…' : voiceError || 'Recording ready to transcribe.'}</span>
      {!transcribing && voiceFile && <button className="outline" onClick={() => void transcribe(voiceFile)}>Retry transcription</button>}
      <button className="outline" onClick={cancelTranscription}>Cancel dictation</button>
    </div>}
    {error && <p className="error" role="alert">{error}</p>}
    {drafts.length > 0 && <div className="drafts">{drafts.map(d => <div className="draft" key={d.id}>
      {d.file.type.startsWith('image/') ? <img src={d.url} alt={d.file.name}/> : d.file.type.startsWith('audio/') ? <audio src={d.url} controls/> : <video src={d.url} controls playsInline/>}
      <span title={d.file.name}>{d.file.name}</span><button disabled={busy} aria-label={`Remove ${d.file.name}`} onClick={() => { URL.revokeObjectURL(d.url); setDrafts(drafts.filter(item => item.id !== d.id)); }}><X size={18}/></button>
    </div>)}</div>}
    <div className="composer"><textarea aria-label="Message" placeholder="Describe what’s happening with your car…" maxLength={10000} value={text} disabled={busy} onChange={e => setText(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); void send(); } }}/>
      <div className="toolbar"><div ref={menuContainer} className="attachment-control">
        <button disabled={busy} aria-expanded={menu} aria-label="Attach" className={menu ? 'active' : ''} onClick={() => setMenu(!menu)}><Paperclip/><span>Attach</span></button>
        {menu && <div className="attach-menu"><button onClick={() => pick('image/*')}><Image/>Upload images</button><button onClick={() => pick('video/*')}><Video/>Upload video</button><button disabled={transcribing} onClick={() => capture('audio')}><Mic/>Record audio</button><button disabled={transcribing} onClick={() => capture('video')}><Video/>Record video</button><button onClick={() => pick('audio/*')}><Mic/>Upload audio</button></div>}
      </div><button disabled={busy || transcribing} onClick={() => capture('audio', true)}><Mic/><span>Voice</span></button><button disabled={busy || transcribing} onClick={() => capture('video')}><Camera/><span>Camera</span></button><button disabled={busy} onClick={() => pick('image/*,video/*')}><Image/><span>Gallery</span></button>
      <button className="send primary" aria-label="Send message" disabled={busy || transcribing || !!record || (!text.trim() && !drafts.length)} onClick={() => void send()}><Send/></button></div>
    </div><p className="composer-hint">{busy ? 'Reviewing the evidence…' : 'Voice and media are processed by Google. Speech calls may incur charges. Review before sending.'}</p>
    <input ref={upload} type="file" hidden multiple accept={accept} onChange={e => { add(Array.from(e.target.files || [])); e.target.value = ''; }}/>
    {record && <Recorder kind={record} dictation={dictation} onClose={() => setRecord(null)} onAttach={file => dictation ? void transcribe(file) : add([file])}/>}
  </div>;
}
