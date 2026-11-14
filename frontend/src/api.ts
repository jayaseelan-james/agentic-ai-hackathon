export type Attachment = { id: string; kind: 'image' | 'audio' | 'video'; filename: string; mime_type: string; size: number; url: string };
export type Activity = { id: string; tool: string; initiator: 'model' | 'backend'; status: 'running' | 'complete' | 'failed'; timestamp: string; summary: string; arguments?: Record<string, unknown> | null; result?: Record<string, unknown> | null };
export type Citation = { url: string; title: string; start_index: number | null; end_index: number | null };
export type Vehicle = { make: string; model: string; year: number | null };
export type MechanicReport = { reported_symptoms: string[]; assistant_assessments_unconfirmed: string[]; uncertainties: string[]; safety: string | null; sources: Citation[]; vehicle: Vehicle; created_at: string; simulated_sensor_evidence?: unknown[] };
export type SensorSample = { timestamp: string; value: number | null };
export type SensorChannel = { name: string; label: string; unit: string; value: number | null; available: boolean; scenario: string; lookback_minutes: number; samples: SensorSample[]; limits: {min: number; max: number} };
export type SensorSimulation = { enabled: boolean; source: 'simulated'; fixture_id: string; revision: number; snapshot_time: string; channels: Record<string, SensorChannel> };
export type Message = { id: string; role: 'user' | 'assistant'; text: string; timestamp: string; attachments: Attachment[]; activity: Activity[]; state: 'processing' | 'complete' | 'failed'; error: string | null; provider: string | null; model: string | null; citations: Citation[]; search_suggestions: string[]; report: MechanicReport | null };
export type Incident = { id: string; title: string; vehicle: Vehicle; messages: Message[]; safety: string | null };
export type Health = { configured: boolean; verified: boolean; model: string; provider: string };
export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, { ...init, signal: AbortSignal.timeout(60000) });
  if (!response.ok) { const body = await response.json().catch(() => null); throw new Error(typeof body?.detail === 'string' ? body.detail : 'Request failed. Please try again.'); }
  return response.json();
}
export const formatTime = (seconds: number) => `${Math.floor(seconds / 60).toString().padStart(2, '0')}:${(seconds % 60).toString().padStart(2, '0')}`;
export const vehicleName = (vehicle?: Vehicle) => vehicle ? [vehicle.year, vehicle.make, vehicle.model].filter(Boolean).join(' ') || 'Vehicle details not provided' : 'Vehicle details not provided';
