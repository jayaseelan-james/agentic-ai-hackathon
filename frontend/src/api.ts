export type Attachment = { id: string; kind: 'image' | 'audio' | 'video'; filename: string; mime_type: string; size: number; url: string };
export type Message = { id: string; role: 'user' | 'assistant'; text: string; timestamp: string; attachments: Attachment[]; activity: string[] };
export type Incident = { id: string; title: string; vehicle_id: string; messages: Message[]; safety: string | null };
export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, { ...init, signal: AbortSignal.timeout(60000) });
  if (!response.ok) { const body = await response.json().catch(() => null); throw new Error(typeof body?.detail === 'string' ? body.detail : 'Request failed. Please try again.'); }
  return response.json();
}
export const formatTime = (seconds: number) => `${Math.floor(seconds / 60).toString().padStart(2, '0')}:${(seconds % 60).toString().padStart(2, '0')}`;
