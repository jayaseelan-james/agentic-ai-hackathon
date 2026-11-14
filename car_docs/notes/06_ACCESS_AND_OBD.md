# Reading the data: safe OBD acquisition design

## Three data tiers

1. **Generic emissions OBD:** Mode 01 supported PIDs, engine DTCs, freeze frame. Vehicle-specific coverage varies.
2. **BMW-specific diagnostic reads:** control units such as braking/TPM/engine with ISTA/AOS or suitable permitted diagnostic tooling; not universally exposed to a basic ELM327 adapter.
3. **Simulated and user-supplied channels:** clearly tagged `source_type = simulated` or `user_report`; never misrepresent as live values.

## Potential standard Mode 01 PIDs

| Request | Quantity | Important limitation |
|---|---|---|
| 0105 | Engine coolant temperature | Only if ECU supports |
| 010C | Engine RPM | Cranking samples may be missed |
| 010D | Vehicle speed | May vary by system / speed source |
| 0110 | Air mass flow | PID may be unsupported or estimated |
| 010A | Fuel pressure | Not equal to high-pressure rail automatically |
| 0142 | Control module voltage | Not the same as battery terminal measurement |

For BMW TPMS and brake pressure, use OEM-supported diagnostic access if available and ensure proper authorization. Avoid control-unit writes, coding, actuator tests or DTC clearing in the demo. **Read only** is the safest baseline.

## Provenance contract

Every value should include `timestamp_utc`, `vehicle_id` (pseudonymous), `signal_id`, `value`, `unit`, `source_type`, `data_origin`, `confidence`, `is_supported`, and `is_stale`. A missing PID is `null` and `is_supported=false`, not a manufactured zero.

**References:** S016, S017, S029, S030.
