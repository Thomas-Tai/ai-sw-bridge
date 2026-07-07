# Idea Brief — Automated Sorting Machine

## Raw idea

> "I want to build an automated sorting machine."

## Intended job-to-be-done

Take a mixed stream of small objects, identify each one visually, and drop it
into the right bin — so a person no longer sorts by hand.

## Target user/operator

A single hobbyist/small-workshop operator; no PLC experience; comfortable with
a PC and basic hand tools. Runs the machine attended, a few hours at a time.

## Target object/material/workpiece

Rigid objects up to 100 × 100 × 100 mm and 0.5 kg (e.g. plastic parts, small
boxed goods). Dry, non-fragile, one object at a time on the belt.

## Desired output

Objects land in one of at least three bins by visual class; a sort log is nice
to have (could).

## Known constraints

- Fits on a workbench: about 1200 × 800 mm footprint.
- Mains 230 V AC available; low-voltage DC preferred inside the machine.
- Prototype budget-sensitive: prefer COTS and laser-cut/printed parts.

## Unknowns blocking engineering decisions

- Exact object mix and the visual classes to separate. **(assumed 3 classes
  for v1 — drives bin count)**
- Required throughput. **(assumed 30 objects/min for v1 — drives belt speed)**
- Whether bins must be operator-swappable during a run. (deferred, not
  blocking the first slice)
