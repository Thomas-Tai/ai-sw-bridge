# Calculations

> Copy this file to `<project>/intake/` and fill it in. Delete guidance lines as you go.

First-order sizing between the specs and any component selection. Selecting a
motor without a torque calculation is guesswork — this file holds the numbers
that justify COTS choices. Every input is traceable to `engineering_specs.md`;
every result carries the `derived` status.

## Sizing calculations

*(One block per calc: purpose, formula, inputs (with their statuses), result
(derived), safety factor. Torque, speed, force, inertia, power.)*

## Structural checks

*(Deflection, load paths, bolted-joint sanity — where relevant.)*

## Tolerance stack-up

*(For critical fits, where relevant: chain of dimensions, worst-case sum,
verdict against the fit requirement.)*

## Power and duty-cycle budget

*(Sum of actuator loads vs supply; continuous vs peak.)*

## Open calculations that block COTS selection

*(Anything not yet computed that gates a component choice. Empty when ready.)*
