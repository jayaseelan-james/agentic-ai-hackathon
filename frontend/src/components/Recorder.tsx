import { useEffect, useRef, useState } from 'react';
import { Mic, Video, X, Square, Circle, RotateCw } from 'lucide-react';
import { formatTime } from '../api';

export default function Recorder({ kind, onClose, onAttach }: {kind: 'audio' | 'video'; onClose: () => void; onAttach: (file: File) => void}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const video = useRef<HTMLVideoElement>(null);
  const stream = useRef<MediaStream | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const [state, setState] = useState<'loading' | 'ready' | 'recording' | 'review' | 'error'>('loading');
  const [error, setError] = useState('');
  const [seconds, setSeconds] = useState(0);
  const [file, setFile] = useState<File>();
  const [url, setUrl] = useState('');
  const [facing, setFacing] = useState('environment');
  const stopTracks = () => stream.current?.getTracks().forEach(track => track.stop());

  useEffect(() => { const element = dialog.current!; element.showModal(); return () => element.close(); }, []);
  useEffect(() => {
    let cancelled = false;
    setState('loading');
    async function open() {
      try {
        if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) throw new Error('Recording is unavailable. Use localhost or HTTPS, or upload a file instead.');
        const next = await navigator.mediaDevices.getUserMedia({audio: true, video: kind === 'video' ? {facingMode: {ideal: facing}} : false});
        if (cancelled) { next.getTracks().forEach(t => t.stop()); return; }
        stream.current = next;
        if (video.current) video.current.srcObject = next;
        setState('ready');
      } catch (e) { if (!cancelled) { setError(e instanceof Error ? e.message : 'Cannot access device. You can upload a file instead.'); setState('error'); } }
    }
    void open();
    return () => { cancelled = true; if (recorder.current?.state === 'recording') { recorder.current.onstop = null; recorder.current.stop(); } stopTracks(); };
  }, [kind, facing]);
  useEffect(() => () => { if (url) URL.revokeObjectURL(url); }, [url]);
  useEffect(() => {
    if (state !== 'recording') return;
    const started = Date.now();
    const timer = window.setInterval(() => {
      const elapsed = Math.floor((Date.now() - started) / 1000);
      setSeconds(elapsed);
      if (elapsed >= (kind === 'audio' ? 120 : 60) && recorder.current?.state === 'recording') recorder.current.stop();
    }, 200);
    return () => clearInterval(timer);
  }, [state, kind]);
  function start() {
    try {
      const types = kind === 'video' ? ['video/webm;codecs=vp8,opus', 'video/mp4', 'video/webm'] : ['audio/webm;codecs=opus', 'audio/mp4', 'audio/ogg;codecs=opus'];
      const mimeType = types.find(type => MediaRecorder.isTypeSupported(type));
      if (!mimeType) throw new Error('No supported recording format. Please upload a file instead.');
      const next = new MediaRecorder(stream.current!, {mimeType});
      recorder.current = next;
      const chunks: Blob[] = [];
      let size = 0;
      next.ondataavailable = event => { if (event.data.size) { chunks.push(event.data); size += event.data.size; if (size > 25_000_000 && next.state === 'recording') next.stop(); } };
      next.onerror = () => { stopTracks(); setError('Recording failed. Please try uploading a file.'); setState('error'); };
      next.onstop = () => {
        stopTracks();
        const blob = new Blob(chunks, {type: mimeType});
        if (!blob.size || blob.size > 25_000_000) { setError('Recording was empty or exceeded 25 MB. Please try a shorter clip.'); setState('error'); return; }
        const extension = mimeType.includes('mp4') ? 'mp4' : mimeType.includes('ogg') ? 'ogg' : 'webm';
        setFile(new File([blob], `${kind === 'audio' ? 'Voice-note' : 'Camera-video'}-${Date.now()}.${extension}`, {type: mimeType}));
        setUrl(URL.createObjectURL(blob)); setState('review');
      };
      next.start(250); setSeconds(0); setState('recording');
    } catch (e) { stopTracks(); setError(e instanceof Error ? e.message : 'Recording failed.'); setState('error'); }
  }
  return <dialog ref={dialog} className="recorder" onCancel={onClose} aria-labelledby="record-title">
    <div className="sheet-handle"/><header><h2 id="record-title">{state === 'review' ? 'Review' : 'Record'} {kind === 'audio' ? 'audio' : 'video'}</h2><button aria-label="Close recorder" onClick={onClose}><X/></button></header>
    <p className="record-help">Only record while safely parked.</p>
    {state === 'error' ? <p role="alert" className="error">{error}</p> : <>
      <div className={`record-preview ${kind}`}>
        {kind === 'video' ? (state === 'review' ? <video src={url} controls playsInline/> : <video ref={video} autoPlay muted playsInline/>) : (state === 'review' ? <audio src={url} controls/> : <Mic size={56}/>)}
        {state === 'recording' && <span className="timer"><i/>{formatTime(seconds)}</span>}
        {state === 'loading' && <span className="device-loading">Opening {kind === 'audio' ? 'microphone' : 'camera'}…</span>}
      </div>
      <p className="device-status">{kind === 'video' ? <Video size={22}/> : null}<Mic size={22}/>{state === 'review' ? 'Recording complete · devices are off' : state === 'loading' ? 'Waiting for device permission' : `${kind === 'video' ? 'Camera and microphone are' : 'Microphone is'} on`}</p>
    </>}
    <div className="record-actions"><button className="outline" onClick={onClose}>Cancel</button>
      {state === 'recording' ? <button className="stop-action" onClick={() => recorder.current?.stop()}><span><Square fill="currentColor"/></span>Stop recording</button> : state === 'review' ? <button className="primary" onClick={() => { if (file) onAttach(file); onClose(); }}>Use {kind === 'audio' ? 'audio' : 'clip'}</button> : <button className="primary" disabled={state !== 'ready'} onClick={start}><Circle size={18}/>Start recording</button>}
      {kind === 'video' && state !== 'review' && <button className="outline flip" disabled={state !== 'ready'} onClick={() => setFacing(v => v === 'environment' ? 'user' : 'environment')}><RotateCw size={22}/>Flip</button>}
    </div><p className="review-hint">Review your {kind === 'audio' ? 'audio' : 'clip'} before sending.</p>
  </dialog>;
}
