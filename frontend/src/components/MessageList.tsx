import { useEffect, useRef } from 'react';
import { Car, ChevronDown } from 'lucide-react';
import type { Message } from '../api';
export default function MessageList({messages}: {messages: Message[]}) {
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { end.current?.scrollIntoView({block: 'end'}); }, [messages]);
  return <div className="messages" role="log" aria-label="Conversation" aria-live="polite">
    {!messages.length && <div className="empty"><Car size={40}/><h2>What’s happening with your car?</h2><p>Describe it, record it, or add a photo.</p><small>Example replies only. No live diagnosis.</small></div>}
    {messages.map(message => <article key={message.id} className={`message ${message.role}`}>
      {message.role === 'assistant' && <span className="avatar"><Car/></span>}<div className="message-content"><div className="bubble">
        {message.text && <p>{message.text}</p>}
        {message.attachments.map(file => <div className="sent-media" key={file.id}>{file.kind === 'image' ? <a href={file.url} target="_blank" rel="noreferrer"><img src={file.url} alt={file.filename}/></a> : file.kind === 'audio' ? <audio src={file.url} controls/> : <video src={file.url} controls playsInline/>}<small>{file.filename}</small></div>)}
        {message.role === 'assistant' && <small>Example response · Not an analysis of your media</small>}
      </div>{message.activity.length > 0 && <details className="activity"><summary><ChevronDown size={18}/><strong>Demo activity</strong><span>{message.activity.length} simulated steps</span></summary><ul>{message.activity.map(item => <li key={item}>{item}</li>)}</ul></details>}</div>
    </article>)}<div ref={end}/>
  </div>;
}
