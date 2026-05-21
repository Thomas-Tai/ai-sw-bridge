# grooved_shaft

A solid cylindrical shaft with a circumferential O-ring groove cut into its mid-length. Demonstrates the v0.7 `revolve_cut` primitive — the subtractive sibling of `revolve_boss`.

## Run

```powershell
ai-sw-build examples\grooved_shaft\spec.json --no-dim
```

## What it builds

| # | Feature | Primitive | Notes |
|---|---|---|---|
| 1 | `SK_Body` | `sketch_rectangle_on_plane` | 80×12.5 mm half-profile on Front Plane centered at (40, **+6.25**); embedded x-axis centerline. Profile sits on the **+y side** of the centerline. |
| 2 | `REV_Body` | `revolve_boss` | Revolves `SK_Body` 360° about the centerline → solid Ø25 × 80 mm cylinder along x-axis. |
| 3 | `SK_Groove` | `sketch_rectangle_on_plane` | 5×1 mm groove profile on Front Plane centered at (40, **−12.0**); same x-axis centerline. Profile sits on the **−y side** of the centerline — note this is **opposite** to the boss profile's +y side. See "A note on opposite-side cuts" below. |
| 4 | `CUT_Groove` | `revolve_cut` | Revolves `SK_Groove` 360° as a cut → 1 mm-deep × 5 mm-wide circumferential groove at the mid-length. |

## Result

A Ø25 × 80 mm cylindrical shaft along the x-axis with a 5 mm-wide × 1 mm-deep annular groove centered at x = 40 mm:

- Body bbox: `x = [0, 80] mm, y = [-12.5, 12.5] mm, z = [-12.5, 12.5] mm`
- The groove drops the outer radius from 12.5 mm to 11.5 mm over the band x ∈ [37.5, 42.5] mm
- Typical use: seat for a Ø2 mm rubber O-ring on a 3D-printed conveyor drive roller (see Lego Sorter S1b DriveRoller § 13.2 for the inspiring real-world geometry)

## How `revolve_cut` works

Structurally identical to `revolve_boss`: the profile sketch carries an embedded centerline (construction line) that SW auto-detects as the axis of revolution. The handler calls `IFeatureManager.FeatureRevolve2` with `IsCut=True` (arg 4) instead of `False`. Everything else — selection state, the 20-arg call shape, the centerline-must-be-inside-sketch design — matches the boss case verbatim.

## v1 limitations (same as `revolve_boss`, plus one cut-specific)

- **Solid cuts only.** No thin-wall, no surface revolve.
- **Single direction only.** Two-direction / mid-plane revolve-cuts deferred.
- **One centerline per sketch.** Multiple would be ambiguous as a revolve axis.
- **Profile must not cross the centerline.** SW rejects with a cryptic error.
- **Angle is literal degrees.** No `{rhs}` parametric binding.
- **Existing body must intersect the swept profile.** If the profile sweeps through empty space (e.g. radially-outside the body, or axially-past its ends), `FeatureRevolve2` silently returns `None` — no SW error. The handler surfaces this with a diagnostic naming the most common cause, but the validator can't catch it pre-build because it would need to simulate the body sweep.

## A note on plane choice

Both sketches in this example are on **Front Plane** because Front Plane's sketch-local axes map trivially to part-frame axes (`sketch_x = part_x`, `sketch_y = part_y`). Top Plane and Right Plane have non-identity mappings (Right Plane's `sketch_x` actually maps to `-part_z`, per empirical Spike ZP from the v0.6 investigation). The bridge does not currently auto-transform plane-sketch coordinates, so authoring a revolve about, say, the y-axis from a Right Plane sketch requires the human to bake the rotated coordinates into the spec by hand.

For most v1 use cases, picking the right *plane* lets you avoid the mapping issue entirely — choose the plane that puts your intended revolve axis along one of its sketch-local axes, and the spec coordinates are the natural part coordinates.

## A note on opposite-side cuts (the chained-revolve handedness gotcha)

When chaining a `revolve_cut` after a `revolve_boss` that share the **same plane and same centerline direction**, the cut profile must sit on the **opposite side** of the centerline from the boss profile. If both profiles sit on the same side, the cut silently returns `None` (no SW error message).

In this example:
- Boss `SK_Body` rectangle is centered at sketch `y = +6.25` → profile on **+y side** of the x-axis centerline.
- Cut `SK_Groove` rectangle is centered at sketch `y = -12.0` → profile on **-y side**.

If you change the groove `center.y` to `+12.0` (same side as the boss), the build fails with the "FeatureRevolve2(IsCut=True) returned None" diagnostic. Verified empirically in Spike ZS (2026-05-21).

This is not a bridge bug — it reproduces in raw pywin32 spikes calling `FeatureRevolve2` directly. The most plausible explanation is that SW's auto-axis detection plus the `UseAutoSelect=True` body-pick picks the wrong revolved volume to subtract from when the cut profile sits on the boss-revolved side. Geometrically a 360° revolve from either side produces the same swept volume, so the empirical rule should be treated as an SW UX wart, not a deeper invariant.

**Workarounds if your spec naturally wants same-side placement:** flip the cut sketch's centerline direction (swap `start` ↔ `end`), or sketch the cut on a perpendicular plane that still contains the axis. Either approach decouples the chained sweep handedness.

## Things to try

- Change the groove `center.y` from `-12.0` to `+12.0` (move profile to same side as boss). The cut will silently return None — demonstrates the opposite-side rule.
- Change the groove `center.y` to `-12.5` (sit the bottom edge on the surface tangentially): the cut succeeds but with zero depth — degenerate.
- Change the groove `width` to `2.0` (narrower groove) — for a Ø2 mm O-ring you'd want about 1.6 mm wide; 5 mm in this example is for a rubber band, not a tight-fit O-ring.
- Add a second groove at `center.x = 70` (near the +x end) by appending another sketch + revolve_cut pair — exercise feature chaining.
