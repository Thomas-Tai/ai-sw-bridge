# Example: tension bracket

8 features, stacked extrudes with face-based sketches. Demonstrates the face-sketch-origin gotcha and how to work around it.

Builds the S1b conveyor's tension bracket: a cap-slab-cap sandwich (inboard cap → slot slab → outboard cap) with an axle bore through the center.

## Run it

Open SOLIDWORKS, then:

```powershell
ai-sw-build examples/tension_bracket/spec.json --no-dim
```

**Note:** Like the MMP example, this references a machine-specific `locals` path. Update the `locals` field or replace `{rhs}` with literals.

## What it builds (8 features)

| # | Feature | Type | What it does |
|---|---|---|---|
| 1 | `SK_InboardCap` | `sketch_rectangle_on_plane` | 20×15 mm rectangle on Front Plane, offset Y=7.5 so Y spans [0, 15] |
| 2 | `Extrude_InboardCap` | `boss_extrude_blind` | 3 mm cap |
| 3 | `SK_SlotSlab` | `sketch_rectangle_on_face` | 8.5×15 mm rectangle on inboard cap's `+z` face |
| 4 | `Extrude_SlotSlab` | `boss_extrude_blind` | 5 mm slab |
| 5 | `SK_OutboardCap` | `sketch_rectangle_on_face` | 20×15 mm rectangle on slot slab's `+z` face |
| 6 | `Extrude_OutboardCap` | `boss_extrude_blind` | 3 mm cap |
| 7 | `SK_AxleBore` | `sketch_circle_on_face` | Ø8.2 mm circle on outboard cap's `+z` face |
| 8 | `Cut_AxleBore` | `cut_extrude_through_all` | Through-all cut for the axle |

## The face-sketch-origin gotcha

This example **intentionally exercises** the non-obvious behavior documented in [docs/known_limitations.md](../../docs/known_limitations.md) section 1:

- The inboard cap's rectangle is centered at `(0, 7.5)` in part coordinates, not `(0, 0)`
- When you sketch on the cap's `+z` face, the sketch origin is at the part-origin projection `(0, 0)`, not the face center `(0, 7.5)`
- Every child face-sketch must add `center: {u: 0, v: 7.5}` to compensate

If you remove the `v: 7.5` offsets from `SK_SlotSlab`, `SK_OutboardCap`, or `SK_AxleBore`, the features will shift 7.5 mm in -Y and the bounding box will be wrong (22.5 mm in Y instead of 15 mm).

## Key patterns demonstrated

- **Stacked extrudes** — each boss builds on the `+z` face of the previous one
- **`sketch_rectangle_on_face`** — new in v0.2, required for building on top of earlier extrusions
- **Y-shifted parent with center offset** — the workaround for the face-sketch-origin gotcha
- **`cut_extrude_through_all`** at the end — the bore goes through the entire stack

## Things to try

- Remove `v: 7.5` from `SK_SlotSlab` — observe the slab shifts down and the bounding box grows
- Change `S1B_TB_X` to make the bracket wider
- Add a second bore by appending another `sketch_circle_on_face` + `cut_extrude_through_all` pair
