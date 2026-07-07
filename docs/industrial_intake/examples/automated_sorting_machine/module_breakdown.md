# Module Breakdown — Automated Sorting Machine

## Module list

| ID | Name | cad_intent | build_buy |
|---|---|---|---|
| MOD-001 | infeed_conveyor | assembly | mixed |
| MOD-002 | vision_module | assembly | mixed |
| MOD-003 | diverter_unit | assembly | mixed |
| MOD-004 | bin_array | part | build |
| MOD-005 | frame | assembly | mixed |
| MOD-006 | controls | purchased | buy |

## Module responsibility

- MOD-001 moves objects at `INF_BELT_SPEED` through the sensing zone.
- MOD-002 delivers a class decision per object to controls.
- MOD-003 physically redirects one object per decision.
- MOD-004 receives and holds sorted objects.
- MOD-005 positions every module and carries loads to the bench.
- MOD-006 powers and sequences everything; hosts the e-stop.

## Inputs and outputs

infeed_conveyor: objects in (by hand) / objects out (at diverter point);
step pulses in. vision_module: light + object in view / class decision out.
diverter_unit: actuation command in / lateral push out. bin_array: falling
objects in. frame: static loads. controls: mains in / 24 V + signals out.

## Mechanical interfaces

- MOD-001 ↔ MOD-005 via IF-002 (slotted bolt pattern, M5).
- MOD-002 and MOD-003 mount to MOD-005 rails above/at belt level.
- MOD-004 sits on the bench under the diverter discharge (locates by gravity,
  tool-free per serviceability requirement).

## Electrical/control interfaces

- IF-004 stepper wiring; IF-005 USB camera; e-stop loop through MOD-006.

## Dependencies

frame geometry ← infeed_conveyor envelope ← COTS roller/motor dimensions.
Model order: COTS placeholders → conveyor parts → conveyor assembly → frame.

## Build/buy decision

Buy: motor, rollers, belt, camera, controller, fasteners. Build: side plates,
slider bed, motor bracket, bins. Mixed modules combine both.
