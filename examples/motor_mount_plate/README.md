# Example: motor mount plate (MMP)

The most complete v0.2 example — 10 features, 7 parametric bindings, exercises 6 of the 8 available primitives.

Builds the S1b conveyor's motor mount plate: a 50×50×3 mm plate with a concentric Ø12 coupler hole, Ø20.5 flange recess, 2× motor mounting holes (Ø3.2 at ±12.5 mm), and 2× frame mounting holes (Ø3.4 at ±15 mm).

## Run it

Open SOLIDWORKS, then:

```powershell
ai-sw-build examples/motor_mount_plate/spec.json --no-dim
```

**Note:** This spec references a `locals` path that is specific to the author's machine. To run it, either:

1. Update the `locals` path in `spec.json` to point to your own copy of `s1b_conveyor_locals.txt`, or
2. Replace all `{rhs}` expressions with literal mm values (see the `_comment` fields for the target values)

## What it builds (10 features)

| # | Feature | Type | What it does |
|---|---|---|---|
| 1 | `SK_PlateSlab` | `sketch_rectangle_on_plane` | 50×50 mm rectangle on Front Plane |
| 2 | `Extrude_Plate` | `boss_extrude_blind` | 3 mm thick plate |
| 3 | `SK_CouplerHole` | `sketch_circle_on_face` | Ø12 circle on `-z` face |
| 4 | `Cut_CouplerHole` | `cut_extrude_through_all` | Through-all cut for coupler |
| 5 | `SK_FlangeRecess` | `sketch_circle_on_face` | Ø20.5 circle on `+z` face |
| 6 | `Cut_FlangeRecess` | `cut_extrude_blind` | 1 mm deep blind cut for flange recess |
| 7 | `SK_MotorHoles` | `sketch_circles_on_face` | 2× Ø3.2 circles at X = ±12.5 mm |
| 8 | `Cut_MotorHoles` | `cut_extrude_through_all` | Through-all cut for motor bolts |
| 9 | `SK_FrameHoles` | `sketch_circles_on_face` | 2× Ø3.4 circles at X = ±15 mm |
| 10 | `Cut_FrameHoles` | `cut_extrude_through_all` | Through-all cut for frame bolts |

## Primitives exercised

| Primitive | Used by |
|---|---|
| `sketch_rectangle_on_plane` | `SK_PlateSlab` |
| `sketch_circle_on_face` | `SK_CouplerHole`, `SK_FlangeRecess` |
| `sketch_circles_on_face` | `SK_MotorHoles`, `SK_FrameHoles` |
| `boss_extrude_blind` | `Extrude_Plate` |
| `cut_extrude_through_all` | `Cut_CouplerHole`, `Cut_MotorHoles`, `Cut_FrameHoles` |
| `cut_extrude_blind` | `Cut_FlangeRecess` |

## Key patterns demonstrated

- **Face-based sketches on both `+z` and `-z` faces** of the same extrusion
- **Multi-circle sketch** (`sketch_circles_on_face`) for hole patterns
- **Mixed literal and parametric dimensions** — flange recess depth is literal (1.0 mm), most others are `{rhs}`-bound
- **Geometry verified centered** — all features are symmetric around the part origin

## Things to try

- Change the motor hole pitch: update `u` values in `SK_MotorHoles` from ±12.5 to ±15
- Change plate thickness: edit `S1B_MMP_T` in the locals file, re-run
- Add a fillet: append a `fillet_constant_radius` feature at the end (you'll need to calculate edge coordinates from the plate geometry)
