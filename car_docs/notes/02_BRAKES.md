# Brakes: high-risk domain

## Observables

Brake-fluid level may be represented by a low-level switch/warning rather than continuous numeric volume. Hydraulic pressure is used by braking control systems, but which live values are accessible is OEM- and ECU-dependent; a generic OBD adapter is not sufficient evidence of availability.

## Questions the agent should ask

- Are there brake/ABS/DSC warning indicators or a Check Control message?
- Has pedal travel, braking distance or pedal firmness changed? Are there leaks or unusual noises?
- Is there a burning smell, visible fluid, or wheel-specific heat? Do not request that an untrained driver touch hot components or inspect under a moving car.

## Triage

If the driver reports reduced braking, a sinking pedal, visible hydraulic fluid loss, a brake fluid warning, or severe unusual braking behavior, recommend stopping in a safe place and professional inspection/roadside service. Never declare brakes healthy from a sensor reading; never instruct opening the hydraulic system, bleeding brakes, disabling ABS, or conducting a road test to reproduce a failure.

**References:** S001, S016, S017. Exact G20 petrol 330i brake pressure PID exposure remains unverified.
