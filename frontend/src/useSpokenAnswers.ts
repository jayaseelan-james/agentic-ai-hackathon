import { useCallback, useEffect, useRef, useState } from 'react';
import { request, type Incident, type SpeechResult } from './api';

export type SpeechStatus = { stage: 'loading' | 'ready' | 'playing' | 'error'; text?: string; error?: string };

export function useSpokenAnswers(chat?: Incident) {
  const [muted, setMuted] = useState(() => {
    try { return localStorage.getItem('autosage-speech-muted') === 'true'; } catch { return false; }
  });
  const [statuses, setStatuses] = useState<Record<string, SpeechStatus>>({});
  const current = useRef(chat); current.current = chat;
  const mutedRef = useRef(muted); mutedRef.current = muted;
  const candidates = useRef(new Map<string, string>());
  const audio = useRef<HTMLAudioElement | null>(null);
  const controller = useRef<AbortController | null>(null);
  const objectUrl = useRef('');
  const activeId = useRef('');
  const epoch = useRef(0);

  const stop = useCallback(() => {
    epoch.current++;
    controller.current?.abort(); controller.current = null;
    if (audio.current) { audio.current.pause(); audio.current.removeAttribute('src'); audio.current.load(); audio.current = null; }
    if (objectUrl.current) { URL.revokeObjectURL(objectUrl.current); objectUrl.current = ''; }
    const id = activeId.current;
    if (id) setStatuses(prev => ({...prev, [id]: {...prev[id], stage: 'ready'}}));
    activeId.current = '';
  }, []);

  const play = useCallback(async (id: string) => {
    const selected = current.current;
    const message = selected?.messages.find(m => m.id === id);
    if (!selected || message?.state !== 'complete') return;
    // A manual tap can reuse preloaded audio without awaiting a network request.
    if (audio.current && activeId.current === id) {
      const player = audio.current;
      try {
        await player.play();
        if (audio.current === player) setStatuses(prev => ({...prev, [id]: {...prev[id], stage: 'playing', error: undefined}}));
      } catch {
        if (audio.current === player) setStatuses(prev => ({...prev, [id]: {...prev[id], stage: 'ready', error: 'Playback needs a tap. Select Play answer.'}}));
      }
      return;
    }
    stop();
    const token = epoch.current;
    const abort = new AbortController(); controller.current = abort;
    activeId.current = id;
    const valid = () => token === epoch.current && current.current?.id === selected.id && !abort.signal.aborted;
    setStatuses(prev => ({...prev, [id]: {stage: 'loading'}}));
    try {
      const result = await request<SpeechResult>(`/incidents/${selected.id}/messages/${id}/speech`, {method: 'POST', signal: abort.signal}, 135000);
      if (!valid()) return;
      setStatuses(prev => ({...prev, [id]: {stage: 'loading', text: result.text}}));
      const response = await fetch(result.audio_url, {signal: AbortSignal.any([abort.signal, AbortSignal.timeout(30000)])});
      if (!response.ok) throw new Error('Speech recording expired. Retry speech.');
      const blob = await response.blob();
      if (!valid()) return;
      objectUrl.current = URL.createObjectURL(blob);
      const player = new Audio(objectUrl.current); audio.current = player;
      player.onended = () => { if (valid()) stop(); };
      player.onerror = () => {
        if (valid()) { stop(); setStatuses(prev => ({...prev, [id]: {text: result.text, stage: 'error', error: 'Audio playback failed. Retry speech.'}})); }
      };
      try {
        await player.play();
        if (valid()) setStatuses(prev => ({...prev, [id]: {stage: 'playing', text: result.text}}));
      } catch {
        if (valid()) setStatuses(prev => ({...prev, [id]: {stage: 'ready', text: result.text, error: 'Playback needs a tap. Select Play answer.'}}));
      }
    } catch (error) {
      if (valid()) { stop(); setStatuses(prev => ({...prev, [id]: {stage: 'error', error: (error as Error).message}})); }
    }
  }, [stop]);

  const markSubmitted = useCallback((incident: Incident) => {
    if (current.current?.id !== incident.id) return;
    const answer = [...incident.messages].reverse().find(m => m.role === 'assistant');
    if (answer) candidates.current.set(answer.id, incident.id);
  }, []);

  useEffect(() => {
    for (const [id, incidentId] of candidates.current) {
      if (incidentId !== chat?.id) candidates.current.delete(id);
    }
    return stop;
  }, [chat?.id, stop]);

  useEffect(() => {
    for (const message of chat?.messages || []) {
      if (candidates.current.get(message.id) !== chat?.id || message.state === 'processing') continue;
      candidates.current.delete(message.id);
      if (message.state === 'complete' && message.text && !mutedRef.current) void play(message.id);
    }
  }, [chat?.messages, chat?.id, play]);

  function toggleMute() {
    const next = !mutedRef.current;
    mutedRef.current = next; setMuted(next);
    if (next) stop();
    try { localStorage.setItem('autosage-speech-muted', String(next)); } catch { /* Session preference still works. */ }
  }
  return {muted, toggleMute, statuses, play, stop, markSubmitted};
}
