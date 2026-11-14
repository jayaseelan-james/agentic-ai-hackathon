import { useState } from 'react';
import type { Vehicle } from '../api';

export default function VehicleEditor({vehicle, disabled, onSave}: {vehicle: Vehicle; disabled: boolean; onSave: (vehicle: Vehicle) => Promise<void>}) {
  const [make, setMake] = useState(vehicle.make);
  const [model, setModel] = useState(vehicle.model);
  const [year, setYear] = useState(vehicle.year?.toString() || '');
  const [error, setError] = useState('');
  return <details className="vehicle-editor"><summary>Edit vehicle details</summary><form onSubmit={async e => { e.preventDefault(); setError(''); try { await onSave({make: make.trim(), model: model.trim(), year: year ? Number(year) : null}); } catch (e) { setError((e as Error).message); } }}>
    <label>Make<input value={make} maxLength={80} onChange={e => setMake(e.target.value)} placeholder="e.g. Toyota" disabled={disabled}/></label>
    <label>Model<input value={model} maxLength={100} onChange={e => setModel(e.target.value)} placeholder="e.g. Corolla" disabled={disabled}/></label>
    <label>Year<input type="number" value={year} min={1900} max={2100} onChange={e => setYear(e.target.value)} placeholder="e.g. 2020" disabled={disabled}/></label>
    <button className="primary" disabled={disabled}>Save vehicle</button>{error && <p className="error" role="alert">{error}</p>}
  </form></details>;
}
