# SolidWorks Handoff — Automated Sorting Machine (first slice: infeed conveyor)

This maps the design package onto the existing bridge surfaces and gives the
**ordered build sequence** with a verify point per step. The package readiness
is `cad_ready_with_assumptions` — every `assumed` parameter above is fair game
to change; rebuild from specs, do not hand-edit models.

## What becomes what

| Package item | CAD artifact | Bridge surface |
|---|---|---|
| MOD-001 custom parts (side plates ×2, slider bed, motor bracket) | `INF_*.SLDPRT` | `ai-sw-build` (one spec per part; `ai-sw-batch` for multi-feature slices) |
| COTS-001/002/003 (motor, belt, rollers) | imported or placeholder parts | `ai-sw-import` (STEP/IGES) or placeholder `ai-sw-build` specs |
| MOD-001 assembly | `infeed_conveyor.SLDASM` | `ai-sw-assembly` (placement + mates) |
| Manufacturing drawings (side plate first) | drawing + PDF | `ai-sw-drawing` |
| Part metadata (number, material) | custom properties | `ai-sw-properties` |
| Width variants (future) | separate part files | `ai-sw-configurations` |
| Parameters table | per-part `<part>_locals.txt` | bound in each build spec |

Parameters map to per-part `*_locals.txt` variables: `INF_*` are module-owned;
`CONVEYOR_WIDTH` is machine-global. `cad_ready_summary.json` is the source of
truth if files disagree.

## Ordered build sequence (verify point per step)

1. **COTS assets.** Vendor STEP files are `missing`: build placeholder parts
   from the critical dimensions (roller = Ø40 × 130 cylinder; motor = 42.3 mm
   square block with a Ø5 shaft) via `ai-sw-build`. When vendor STEP arrives,
   swap in via `ai-sw-import` and review the diagnostics it reports (a
   surface-body count > 0 means unstitched geometry).
   **Verify:** `ai-sw-observe volume` > 0 and `ai-sw-observe bounding_box`
   matches the critical dimensions.
2. **Custom parts.** One spec per part, parametric against its
   `<part>_locals.txt` (e.g. `INF_side_plate_locals.txt` carrying
   `INF_BELT_L`, `INF_FRAME_H`, `INF_ROLLER_D`).
   **Verify per part:** `ai-sw-observe volume` and `bounding_box` within the
   expected envelope; `ai-sw-observe feature_errors` empty.
3. **Assemble the slice.** `ai-sw-assembly`: place side plates, slider bed,
   rollers (concentric + distance mates to plate bores), motor on bracket
   (coincident + concentric to the drive roller shaft).
   **Verify:** `ai-sw-observe interference` reports zero interferences;
   `ai-sw-observe clearance` belt-path-to-guard ≥ 2 mm;
   `ai-sw-observe mate_errors` empty.
4. **Drawings + metadata.** `ai-sw-drawing` for the side plate (third-angle,
   ISO, title block per `engineering_specs.md`); `ai-sw-properties` sets part
   number and material (5052).
   **Verify:** the drawing lifecycle commit succeeds and the sheet contains
   the driving dimensions.
5. **Close the loop against the package.** Diff
   `ai-sw-observe equations` output for each part against the `parameters`
   array in `cad_ready_summary.json` — names and values must match. Then run
   the CAD checks in [`verification_plan.md`](verification_plan.md)
   (`min_wall` ≥ 3 mm on the printed bracket).

Checkpoints are recorded automatically during builds; at each step boundary,
`ai-sw-history part <part>` confirms the checkpoint exists, and
`ai-sw-history diff` / rollback is the recovery path if a step regresses.

## Manual-in-GUI items (not bridge-executable)

- Skeleton/layout sketch and any in-context references.
- Physically fitting the belt (and its flexible-body CAD, omitted in v1).
- The `safety_guarding` review flagged in `readiness.manual_review_required`.

## When to return to the build docs

Spec authoring rules, feature-type choice, and worked spec examples live in
[`docs/AGENTS.md`](../../../AGENTS.md) and
[`docs/spec_reference.md`](../../../spec_reference.md). Return there once this
package's readiness is `cad_ready_with_assumptions` or better — that is the
pre-CAD gate.
