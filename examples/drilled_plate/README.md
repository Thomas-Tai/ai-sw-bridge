# drilled_plate

A 40×30×10 mm plate with two `simple_hole` features showing both `end_condition` values side by side:

- **Hole_Blind** — Ø5 mm BLIND hole, 6 mm deep, at face-sketch offset (+10, 0)
- **Hole_Through** — Ø3 mm THROUGH_ALL hole at face-sketch offset (-10, 0)

## Run

```powershell
ai-sw-build examples\drilled_plate\spec.json --no-dim
```

## What it builds

| # | Feature | Primitive | Notes |
|---|---|---|---|
| 1 | `SK_Plate` | `sketch_rectangle_on_plane` | 40×30 mm on Front Plane |
| 2 | `EX_Plate` | `boss_extrude_blind` | 10 mm tall |
| 3 | `Hole_Blind` | `simple_hole` | Ø5 mm × 6 mm deep on `+z` face |
| 4 | `Hole_Through` | `simple_hole` | Ø3 mm, drills all the way through on `+z` face |

## End conditions

`simple_hole` supports two `end_condition` values:

- **`blind`** (default) — fixed-depth hole. Requires `depth`. SW's `SimpleHole2` is invoked with `swEndCondBlind`.
- **`through_all`** — runs to the opposite side of the body. `depth` is forbidden in the spec (the validator rejects it as ambiguous, since SW ignores the depth value in this mode anyway).

Schema-level checks catch the missing/forbidden depth before any SW call is made — try removing `"depth"` from `Hole_Blind` and you'll see a validation error before SW opens.

## Hole positioning

`center: {u, v}` is the in-face position of the hole **measured from the face SKETCH ORIGIN** — the part-origin projection onto the face plane — *not* the face centroid. For the `+z` face of a centered rectangle these coincide, but the same gotcha as `sketch_circle_on_face` applies on side faces and offset bodies. See [`docs/known_gotchas.md`](../../docs/known_gotchas.md).

## v1 limitations

- **No parametric diameter in dim mode.** `SimpleHole2` emits the diameter as `D1@<auto-named-child-sketch>` (e.g. `D1@Sketch3`), and the child sketch's index is auto-assigned by SW with no way to predict it from the API. v1 binds only `depth` (`D1@<HoleName>`) parametrically; `diameter` is baked in as a literal at build time. Both fields work as literals in `--no-dim`, which is what this example uses. Parametric diameter is a v1.1 candidate.
- **Straight bores only.** No countersink / counterbore (use `HoleWizard` family — deferred to v1.1).
- **One hole per feature.** For arrays of holes, use `sketch_circles_on_face` + `cut_extrude_*` or wait for a `simple_holes` (plural) primitive.

## Things to try

- Change `end_condition` of `Hole_Blind` to `"through_all"` and remove its `depth`. Both holes should now punch through.
- Move a hole off the centerline by changing `center.v` (e.g. `5.0` to shift one hole up by 5 mm).
- Swap the parent face to `-z` to drill from the bottom — the rest of the spec stays unchanged.
