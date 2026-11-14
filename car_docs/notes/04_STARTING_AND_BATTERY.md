# Starting and charging: measurements and limitations

## Useful telemetry

- Battery-related voltage is an important clue, but **OBD PID 42 reports control-module voltage**, which may differ from battery-terminal voltage.
- RPM during cranking may be visible in OEM data; generic OBD polling often samples too slowly to reliably capture a crank event.
- Genuine starter motor current is **not established** as an exposed 330i channel. Intelligent battery-sensor readings may represent total battery current rather than an isolated starter line.
- Save power-state timestamps, ambient temperature, fault codes, driver symptoms and any instrument warnings.

## Scenarios

A no-crank condition differs from crank-but-no-start. In one, the starter may not turn; in the other, engine speed rises but combustion does not sustain. Possible explanations include electrical supply, control authorization, fuel delivery, mechanical or control faults, but sensor values and DTCs are needed before ranking causes.

## Special warning: recalls

NHTSA's US records for 2021 330i include starter-related campaigns 25V636000 (starter relay corrosion/overheating with a park-outside advisory for affected VINs) and 26V056000 (starter overheating risk). **Never assume every 330i in the model-year range is recalled**; verify the exact VIN and delivery market with BMW. For a VIN affected by the park-outside campaign, follow the official campaign instructions. The US records are not a substitute for German BMW/KBA lookup.

**References:** S010 (scope warning), S011 (PHEV-only), S021–S028, S029.
