# DFM/DFA Checklist — Automated Sorting Machine

## Manufacturing process candidates

Side plates + slider bed: laser-cut 3 mm 5052. Motor bracket + camera mount:
FDM PETG. Bins: FDM or folded sheet. Rollers/motor/belt: purchased.

## Process fit at the target production quantity

Quantity from `requirements.md` = 1 prototype + ≤ 5 pilots: laser-cut plate
and FDM are right; no tooling, no castings. Revisit only if pilots become a
production run.

## Material/process fit

5052 laser-cuts cleanly; PETG prints the bracket's 3 mm walls without
supports if the overhang rule below holds.

## Tolerance and fit strategy

`prototype_clearance` policy: ±0.2 mm laser parts, clearance holes Ø5.5 for
M5. Only the roller bearing seats need a fit class (H7) — deferred to the
roller-detail slice.

## Tool access and minimum feature limits

Minimum printed wall 3 mm (verified by observe `min_wall` in the verification
plan); laser internal corners get R1 relief; all fasteners reachable with a
straight hex key.

## 3D print or CNC constraints

PETG bracket: ≤ 45° overhangs, no supports in the bore, print flat side down.

## Assembly order

frame → slider bed → side plates → rollers → belt (manual stretch over
rollers) → motor + bracket → tension via slots → guards → camera → bins.

## Service access

Belt swap: loosen tensioner slots, no frame disassembly (requirements.md).
Bins lift out tool-free.

## Inspection method

Roller-center distance ±0.2 mm by calipers; printed-bracket walls by the
`min_wall` observe check; assembly clearances by the bridge clearance check
(see verification_plan.md).
