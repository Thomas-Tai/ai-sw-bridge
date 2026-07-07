# DFM/DFA Checklist

> Copy this file to `<project>/intake/` and fill it in. Delete guidance lines as you go.

Manufacturing and assembly thinking before modeling details harden.

## Manufacturing process candidates

*(Per custom part family: 3D print, laser-cut plate, CNC, sheet-metal fold…)*

## Process fit at the target production quantity

*(Check each candidate process against the quantity in `requirements.md` —
what is right at qty 1 is wrong at qty 1000.)*

## Material/process fit

*(Does the chosen material suit the process — printable, laser-cuttable,
machinable?)*

## Tolerance and fit strategy

*(Which fits are clearance-by-default; where the tolerance stack-up from
`calculations.md` demands tighter.)*

## Tool access and minimum feature limits

*(Minimum wall, minimum hole, internal corners, tool reach.)*

## 3D print or CNC constraints

*(Overhang angles, support strategy, workholding — where applicable.)*

## Assembly order

*(The sequence a human (or fixture) assembles the machine in; flag any
impossible-to-reach fastener now.)*

## Service access

*(What must be replaceable without tearing the machine down.)*

## Inspection method

*(How each critical dimension gets checked — calipers, gauge, CMM, or a bridge
observe check.)*
