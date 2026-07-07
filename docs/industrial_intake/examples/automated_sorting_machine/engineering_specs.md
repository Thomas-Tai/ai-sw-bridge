# Engineering Specs — Automated Sorting Machine

Every number carries a status: `required`, `assumed`, `measured`,
`vendor_provided`, or `derived`.

## Throughput, speed, accuracy, repeatability

| Quantity | Value | Status | Source |
|---|---|---|---|
| Throughput | 30 objects/min | required | REQ-001 |
| Object pitch on belt | 200 mm | assumed | one object length + gap |
| Belt speed `INF_BELT_SPEED` | 0.1 m/s | derived | calculations.md §1 |
| Classification accuracy | ≥ 95 % | required | REQ-002 |

## Payload, force, torque, power, duty cycle

| Quantity | Value | Status | Source |
|---|---|---|---|
| Max object mass | 0.5 kg | required | REQ-003 |
| Objects on belt simultaneously | 3 | derived | INF_BELT_L / pitch |
| Belt mass | 0.3 kg | assumed | typical PU flat belt this size |
| Belt-on-bed friction coefficient | 0.35 | assumed | slider bed, conservative |
| Drive torque required | 0.25 N·m (incl. SF 2.0) | derived | calculations.md §2 |
| Duty | continuous while running | required | operating pattern |

## Dimensional envelope and mass

| Quantity | Value | Status | Source |
|---|---|---|---|
| `CONVEYOR_WIDTH` | 120 mm | assumed | 100 mm object + 2 × 10 mm clearance |
| `INF_BELT_L` (roller-center to roller-center) | 600 mm | assumed | sensing zone + a pitch either side |
| `INF_ROLLER_D` | 40 mm | assumed | candidate crowned roller |
| `INF_FRAME_H` (belt top above baseplate) | 150 mm | assumed | bin clearance under discharge |
| Machine envelope | ≤ 1200 × 800 mm | required | REQ-005 |

## Materials and surface constraints

Frame plates 5052 aluminium 3 mm (laser-cut); printed brackets PETG; belt
food-grade PU not required (dry rigid goods).

## Control and signal requirements

One stepper (belt drive), one diverter actuator (later slice), one USB camera,
one e-stop circuit; controller is a single-board computer + stepper driver
(candidate). 24 V DC internal bus (assumed).

## Tolerance policy

`prototype_clearance`: default ±0.2 mm on laser-cut plate; clearance fits
everywhere except roller bearing seats (see calculations.md tolerance
stack-up).

## Applicable standards

- Drawing standard: **ISO 128, third-angle projection, stated on every sheet**
  (assumed — flip to first-angle only if a supplier demands it).
- Threads: ISO metric coarse (M3/M5).
- Fits: ISO 286; bearing seats H7 (deferred to the roller slice detail).

## Units and reference coordinate conventions

mm / kg / deg. X = belt travel direction, Y = across the belt, Z = up.
Machine origin: frame center, front face, bottom
(`machine_origin_at_frame_center_front_bottom`).
