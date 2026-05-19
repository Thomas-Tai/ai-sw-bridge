# revolved_ring

A hollow cylindrical ring built from a rectangular profile + embedded centerline + 360° revolve. Demonstrates the v0.5 `revolve_boss` primitive and the `centerline` field on plane-based sketches.

## Run

```powershell
ai-sw-build examples\revolved_ring\spec.json --no-dim
```

## What it builds

| # | Feature | Primitive | Notes |
|---|---|---|---|
| 1 | `SK_Profile` | `sketch_rectangle_on_plane` | 30×6 mm rectangle on Front Plane centered at (35, 5); **plus** an embedded centerline along the x-axis (from −60 to +60). |
| 2 | `REV_Ring` | `revolve_boss` | Revolves `SK_Profile` 360° about the centerline. |

## Result

A hollow cylindrical tube along the x-axis:

- Outer radius **8 mm** (rectangle top edge at y = +8)
- Inner radius **2 mm** (rectangle bottom edge at y = +2)
- Axial length **30 mm** (rectangle spans x = 20 to x = 50)
- Body bbox: `x = [20, 50] mm, y = [−8, 8] mm, z = [−8, 8] mm`

Four faces total: outer cylindrical surface, inner cylindrical surface, and two annular caps at the x=20 and x=50 ends.

## How the centerline becomes the axis

SOLIDWORKS' native `Insert → Revolved Boss/Base` command auto-detects a centerline (construction line) inside the profile sketch and uses it as the axis of revolution. This bridge follows that workflow: the `centerline` field on `sketch_rectangle_on_plane` / `sketch_circle_on_plane` adds a `CreateCenterLine` call inside the sketch. The `revolve_boss` handler then just selects the sketch by name and calls `FeatureRevolve2` — SW finds the centerline.

Two consequences:
- The centerline lives **inside** the profile sketch, not as a separate top-level feature. One sketch → one revolve.
- The axis is fully decided by the centerline's start/end points in sketch-local coords. To revolve about a different axis, change the `centerline` field — no need for a separate axis sketch.

## v1 limitations

- **Solid revolves only.** No thin-wall, no surface revolve (use a CSG approach: revolve outer + cut-revolve inner — though `revolve_cut` isn't shipped yet either).
- **Single direction only.** Two-direction / mid-plane revolves are deferred.
- **Boss only.** `revolve_cut` is a v1.1 candidate (mirrors the `cut_extrude_*` family).
- **Angle is literal degrees.** No `{rhs}` parametric binding on angle in v1 (parametric *lengths* still work — `width`/`height`/`diameter` of the profile can use `{rhs}` against `locals.txt`).
- **One centerline per sketch.** Multiple centerlines would be ambiguous as a revolve axis. Schema permits one `centerline` object per sketch.
- **Profile must not cross the centerline.** SW will reject the revolve at build time with a cryptic error. Keep the entire profile on one side of the centerline.

## Things to try

- Change `angle` to `180.0` for a half-revolution (creates a half-pipe trough).
- Change `center.y` of the profile to `0` so the profile *straddles* the centerline — SW will reject the revolve (expected; documents the v1 limitation).
- Change `centerline` to a vertical line (`start: {x:0,y:-60}, end: {x:0,y:60}`) and adjust the rectangle `center.x` to be offset from x=0 — produces a ring oriented about the y-axis instead.
- Swap `sketch_rectangle_on_plane` for `sketch_circle_on_plane` (with a centerline offset from the circle center) to produce a torus.
