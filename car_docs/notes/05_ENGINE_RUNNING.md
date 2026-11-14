# Engine-running checks: RPM, airflow, fuel, misfires

## Engine management

The DME collects engine and vehicle measurements and activates engine actuators. Engine RPM and coolant temperature are common standardized OBD parameters. Airflow information may be available as MAF PID 10 when supported; source documentation also describes fallback model-derived estimates when airflow sensing fails.

## Misfire monitoring

An engine may record misfire-related fault codes or counts. Separate: (a) current shaking and loss of power as reported by driver, (b) DTC status (current/pending/history), (c) snapshot/freeze-frame data and (d) OEM counters. Their absence is not proof of no misfire.

## Fuel pressure

The B46TU/B48TU engine literature describes a high-pressure direct-injection rail with a pressure sensor. Standard OBD 'fuel pressure' PID 0A is not necessarily high-pressure rail data; check both **pressure reference** (low side/rail, absolute/relative) and units before interpreting. Avoid any instruction for DIY work on high-pressure fuel pipes, injectors or pump.

## Safety

Severe engine shaking, flashing engine malfunction light, strong fuel smell, obvious fuel leak or smoke requires stopping safely and urgent professional assistance. Do not encourage extended driving to collect better logs.

**References:** S005, S006, S007, S029.
