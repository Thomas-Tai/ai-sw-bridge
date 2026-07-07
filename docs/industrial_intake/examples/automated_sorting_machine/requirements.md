# Requirements — Automated Sorting Machine

## Functional requirements

| ID | Requirement | Priority | Verification |
|---|---|---|---|
| REQ-001 | Convey objects one at a time through a sensing zone at ≥ 30 objects/min | must | test |
| REQ-002 | Classify each object into one of ≥ 3 visual classes with ≥ 95 % accuracy on the target set | must | test |
| REQ-004 | Divert each classified object into its matching bin (≥ 3 bins) | must | demonstration |

## Performance requirements

- REQ-001 sets the pace: 30 objects/min at 200 mm object pitch (pitch assumed).
- REQ-002 sets sensing dwell: the camera needs ≥ 100 ms unobstructed view per
  object (assumed until the vision stack is chosen).

## Environmental requirements

Indoor workshop, 10–35 °C, dust typical of a workshop; no washdown.

## Physical constraints

| ID | Requirement | Priority | Verification |
|---|---|---|---|
| REQ-003 | Handle objects up to 100 × 100 × 100 mm and 0.5 kg | must | analysis |
| REQ-005 | Whole machine fits 1200 × 800 mm bench footprint | should | inspection |

## Production quantity, unit-cost target, and timeline

- Quantity: **1 prototype now, up to 5 pilot units later** — DFM targets
  laser-cut plate + FDM printing, not tooling.
- Unit-cost target: prototype bill of materials ≤ the cost of a mid-range
  hobby 3D printer (assumed ceiling; refine after COTS quotes).
- Timeline: first buildable slice (infeed conveyor) modeled first; whole
  machine follows slice by slice.

## Safety and compliance constraints

Machine-safety risk scan (in the spirit of ISO 12100):

| ID | Requirement | Priority | Verification |
|---|---|---|---|
| REQ-006 | An e-stop cuts all motion; belt nip points and the diverter sweep are guarded | must | demonstration |

- Hazards identified: belt/roller nip points (guard strips), diverter sweep
  (side guards), mains wiring (enclosed in the controls module).
- Guarding design is flagged `safety_guarding` for manual engineering review —
  no automated check signs this off.

## Maintenance and serviceability requirements

- Belt replaceable without disassembling the frame (slotted tensioner).
- Bins removable without tools.

## Acceptance criteria

- 100-object mixed run sorts ≥ 95 % correctly (covers REQ-001, REQ-002, REQ-004).
- Bench check confirms footprint and object-envelope limits (REQ-003, REQ-005).
- E-stop and guard inspection passes (REQ-006).
