# Tire monitoring: customer-facing diagnostic card

## What is installed

On a G20 equipped with **direct Tire Pressure Monitor (TPM)**, sensors at the wheel valves measure the pressure in individual tires and may report temperature. Vehicle displays can present four individual pressures. This does not prove an ordinary ELM327 adapter can query the TPM module.

## Input tools

- `read_tpms_pressure`: individual readings with timestamps, device ID and support flags (BMW diagnostic adapter if available).
- `read_vehicle_warnings`: tire pressure warning / system malfunction / reset in progress.
- `collect_photo`: tire sidewall, tread, visible damage; a photograph cannot establish internal damage.
- `ask_driver`: parking duration, speed, temperature change, recent tire swap, whether tire looks visibly flat.

## Reasoning

Check whether values are fresh and correctly matched to wheel position. Compare against the vehicle's current **target pressure** and placard, not a fabricated fixed bar value. Readings may change with heating and ambient conditions. After a wheel change, check tire settings and measurement/reset status, if the owner's manual calls for it.

## Safety classification

A rapidly deflating tire, an obviously flat tire, damaged tire sidewall or a loss of steering stability means stop driving as safely as possible and get roadside help. For minor pressure warnings without visible damage, refer to owner instructions for safe pressure correction and inspection. Do not recommend repairing tire carcass/sidewall damage from a photo.

**References:** S001, S008, S009.
