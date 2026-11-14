# Cooling: B46TU/B48TU system notes and triage

## System concept

B46TU/B48TU engine-management literature describes split cooling and an electrically actuated heat-management module. Coolant temperature informs the engine-management system, which commands coolant routing for warm-up and cooling. The engine and cylinder-head temperatures, operating conditions, cooling-fan behavior and coolant flow can all matter.

## Signals

- `coolant_temp` can be a supported OBD Mode 01 PID 05 reading.
- `vehicle_speed` (PID 0D) helps interpret low-speed airflow context.
- `coolant_level` may be a discrete warning, not a calibrated tank-volume readout.
- `fan_rpm`: distinguish the **commanded fan duty/control** from actual fan feedback. Do not make up feedback if the ECU exposes only a command.

## Reasoning examples

High or rising coolant temperature with low road speed can be consistent with insufficient cooling airflow, a fan-control problem, inadequate coolant circulation or other faults. It cannot single out a failed fan without further tests. A loss-of-coolant warning raises concern for leakage or level issues; a temperature sensor itself can also fail.

## Customer safety

If overheating is indicated, the driver should stop safely, switch off the engine as appropriate to the warning and follow the vehicle owner's manual. Never open a hot pressurized cooling system or suggest touching hot hoses. Repeated overheating requires professional assessment. Do not offer a universal temperature cutoff.

**References:** S003, S004, S007, S001.
