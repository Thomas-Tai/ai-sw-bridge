# System Architecture — Automated Sorting Machine

## Subsystems

- **infeed_conveyor** — moves objects through the sensing zone at constant speed.
- **vision_module** — camera + lighting over the belt; classifies each object.
- **diverter_unit** — sweeps a classified object off the belt into its bin lane.
- **bin_array** — three (or more) bins receiving diverted objects.
- **frame** — the structure everything mounts to; carries loads to the bench.
- **controls** — SBC + stepper driver + PSU + e-stop; runs the classify-divert loop.

## Interfaces

| ID | From | To | Type | Contract |
|---|---|---|---|---|
| IF-001 | vision_module | infeed_conveyor | spatial | camera FOV covers the belt sensing zone, unobstructed |
| IF-002 | infeed_conveyor | frame | mechanical | slotted bolt pattern; belt-top height = `INF_FRAME_H` |
| IF-003 | diverter_unit | infeed_conveyor | spatial | paddle sweep envelope clears belt + object by ≥ 2 mm |
| IF-004 | infeed_conveyor | controls | electrical | stepper 4-wire to driver; e-stop in series |
| IF-005 | vision_module | controls | data | USB camera stream |
| IF-006 | diverter_unit | bin_array | spatial | diverted-object trajectory lands inside the bin mouth |

## Data flow

camera frame → controls (classify) → diverter command; belt stepper speed is
open-loop from controls.

## Material flow

operator places object → infeed_conveyor → sensing zone → diverter point →
bin_array (one of ≥ 3 bins).

## Energy and force flow

mains → controls PSU (24 V) → stepper → drive roller → belt → object friction.
Object weight → belt → slider bed → side plates → frame → bench.

## Sensor/actuator/control boundaries

vision_module owns the camera; infeed_conveyor owns the stepper; diverter_unit
owns its actuator; controls owns all decisions and the e-stop circuit.

## Failure modes and safe states

- Stepper stall → objects stop moving; safe (no stored energy). Detect by
  vision (object not advancing).
- Misclassification → wrong bin; tolerated to 5 % (REQ-002).
- E-stop → all motion stops; belt has no overrun mass worth braking.
