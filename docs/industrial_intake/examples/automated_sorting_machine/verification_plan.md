# Verification Plan — Automated Sorting Machine

## Requirements traceability

| REQ | Method | Concrete check |
|---|---|---|
| REQ-001 | test | 100-object timed run ≥ 30 obj/min |
| REQ-002 | test | same run: ≥ 95 % correct bins |
| REQ-003 | analysis | envelope/mass covered by calculations.md load case |
| REQ-004 | demonstration | one object of each class lands in its bin |
| REQ-005 | inspection | bench tape-measure of footprint |
| REQ-006 | demonstration | e-stop halts motion; guard walk-around |

## CAD checks

- Zero component interference (`ai-sw-observe interference` on the slice
  assembly).
- ≥ 2 mm static clearance belt-path to guards (`ai-sw-observe clearance`).
- Printed-bracket minimum wall ≥ 3 mm (`ai-sw-observe min_wall`).
- Equations in each part match the declared parameters
  (`ai-sw-observe equations` diffed against `cad_ready_summary.json`).
- No feature errors, no mate errors (`feature_errors` / `mate_errors`).

## Simulation or motion checks

Diverter sweep-vs-object clearance in motion — deferred to the diverter slice
(`ai-sw-motion` drives the mate through its travel).

## Physical prototype checks

Timed 100-object run (REQ-001/002/004); belt-tracking observation over 30 min.

## Operator acceptance checks

E-stop function, guards fitted, bins removable tool-free, noise subjectively
acceptable at bench distance.

## Risks requiring manual engineering review

- `safety_guarding` — nip-point and sweep guarding must be reviewed by a
  human before first powered run. No automated check signs this off.
