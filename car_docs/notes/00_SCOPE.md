# Vehicle applicability, evidence quality and limitations

**Target:** BMW 330i sedan (G20), model years 2019–2024, petrol variants. A model-year label alone does not define production date, engine calibration, region, wheel package or installed monitoring modules.

- Use VIN/production date, market and engine code to choose documentation. BMW training pages can discuss B46TU (US) and B48TU (other markets), and some G20 pages focus on the **330e PHEV**, which is not interchangeable with the 330i.
- Distinguish three concepts: `sensor installed`, `value visible in the car`, and `diagnostic service query available`. These are not equivalent.
- A listed standardized Mode 01 PID indicates a potential readout, **not proof that the 330i exposes it**. Query vehicle-supported PIDs first and log unsupported values as null, never zero.
- Control-module voltage (Mode 01 PID 42) should not be marketed as voltage directly measured at the battery posts.
- Unless measured from an exact vehicle, do not claim actual RPM for the cooling fan, dedicated starter-current sensing, continuous coolant litres, continuous brake-fluid volume or detailed hydraulic pressure.
- Vehicle warnings, documented recalls and present symptoms may override apparent normal readings: a single nominal sensor reading does not clear a safety fault.
- No model-specific numeric safe thresholds are included because they depend on operating state and VIN-specific specifications. This pack does not replace BMW ISTA tests or licensed professional repair information.

### Evidence ranking

1. VIN-matched BMW/AOS repair instructions and safety notices; vehicle-specific owner's manual.
2. Official service recall records applicable to the actual VIN and market.
3. BMW technical training for the correct engine and drivetrain (describes systems, not necessarily the exact vehicle).
4. Third-party transcriptions/catalogues and generic OBD documentation.
5. **Simulated** telemetry and synthetic examples: never present as vehicle evidence.
