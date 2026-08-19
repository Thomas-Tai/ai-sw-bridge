# Examples

Worked examples for ai-sw-bridge. Each subfolder is a self-contained workflow you can run end-to-end.

## v0.2 examples (JSON spec → direct-COM build)

Run with `ai-sw-build <path>/spec.json --no-dim`. Recommended order:

| Example | Features | What it demonstrates |
|---|---|---|
| [`filleted_box/`](filleted_box/) | 3 | Simplest example: box + fillet. Start here. |
| [`minimal_cylinder_v2/`](minimal_cylinder_v2/) | 2 | Parametric cylinder with `{rhs}` bindings |
| [`motor_mount_plate/`](motor_mount_plate/) | 10 | Full MMP: 6 primitives, face sketches on both sides, multi-circle hole patterns |
| [`tension_bracket/`](tension_bracket/) | 8 | Stacked extrudes, face-sketch-origin offset workaround |

## v0.3 examples (new primitives)

| Example | Features | What it demonstrates |
|---|---|---|
| [`chamfered_box/`](chamfered_box/) | 3 | `chamfer_edge` in equal-distance mode |
| [`patterned_plate/`](patterned_plate/) | 5 | `linear_pattern` of a hole feature along an edge direction |
| [`mirrored_holes/`](mirrored_holes/) | 5 | `mirror_feature` of a hole about Right Plane |

Each ships with a README that walks through the feature list and the gotchas specific to that primitive. The pattern + mirror primitives depend on `SelectByID2` working under late-binding for marked-selection — if you hit a `SelectByID2 returned False` error, run the corresponding spike under [`../spikes/v0_3/`](../spikes/v0_3/) to diagnose.

## v0.4 examples (side faces + simple_hole)

| Example | Features | What it demonstrates |
|---|---|---|
| [`side_face_bosses/`](side_face_bosses/) | 6 | Boss extrudes on all four side faces (`±x`, `±y`) — verifies sketch-origin handling on non-`±z` faces |
| [`drilled_plate/`](drilled_plate/) | 4 | `simple_hole` primitive: blind + through_all variants side by side |

## v0.5 examples (revolve)

| Example | Features | What it demonstrates |
|---|---|---|
| [`revolved_ring/`](revolved_ring/) | 2 | `revolve_boss` primitive + `centerline` field on plane sketch. Profile rectangle revolved 360° about an embedded centerline → hollow tube. |

## v0.6 examples (end-condition primitives)

Boss/cut extrudes with the non-blind end conditions. See [`../docs/spec_reference.md`](../docs/spec_reference.md) for each primitive.

| Example | Features | What it demonstrates |
|---|---|---|
| [`end_condition_bosses/`](end_condition_bosses/) | 8 | The three boss end-condition primitives: `boss_extrude_midplane`, `boss_extrude_two_direction`, `boss_extrude_through_all` |
| [`end_condition_cuts/`](end_condition_cuts/) | 6 | The cut end-condition primitives: `cut_extrude_midplane`, `cut_extrude_two_direction` |
| [`up_to_surface_boss/`](up_to_surface_boss/) | 6 | `boss_extrude_up_to_surface` — a boss terminated on a named up-to face |
| [`patterned_disc/`](patterned_disc/) | 5 | `circular_pattern` — one off-center boss patterned 6× around the disc axis (the circular sibling of the linear `patterned_plate/`) |

## v0.7 examples (revolve-cut)

| Example | Features | What it demonstrates |
|---|---|---|
| [`grooved_shaft/`](grooved_shaft/) | 4 | `revolve_cut` — the subtractive sibling of `revolve_boss`: an O-ring groove cut into a shaft |
| [`spring_end_cap/`](spring_end_cap/) | 6 | Blind + through-all cuts and `sketch_circles_on_face` (multi-circle face sketch) on a real S1b part |
| [`drive_roller/`](drive_roller/) | 10 | Full S1b roller: centre bore, bearing pockets on each end face, and a mid-length O-ring `revolve_cut` groove |

## Sketch-primitive galleries

Reference specs exercising the individual sketch entities (spec-only — read the `spec.json`).

| Example | Features | What it demonstrates |
|---|---|---|
| [`sketch_primitives/`](sketch_primitives/) | 7 | `sketch_line`, `sketch_arc`, `sketch_spline`, `sketch_slot`, `sketch_polygon`, `sketch_ellipse`, `sketch_text` |
| [`sketch_3d_primitives/`](sketch_3d_primitives/) | 1 | `sketch_3d_sketch` — the 3D-sketch primitive |
| [`sketch_polyline_on_plane/`](sketch_polyline_on_plane/) | 2 | `sketch_polyline_on_plane` — a composite closed polyline (parallelogram) + `boss_extrude_midplane` |

## Demo bundle

| Example | What it demonstrates |
|---|---|
| [`demo_widget/`](demo_widget/) | A purpose-built multi-part product (e.g. `demo_widget/demo_baseplate/spec.json`) driven by `tools/demo_full_system.py` — the full-system tour: parts → assembly → observe → drawing → export. Not a single `ai-sw-build` spec. |

## Path C example (recorded-macro parameterization)

| Example | What it demonstrates |
|---|---|
| [`minimal_cylinder/`](minimal_cylinder/) | Record a cylinder in SW UI, parameterize against `locals.txt`, replay in VBE. Validates full Path C workflow. |

## Running an example

**v0.2 examples** — open SOLIDWORKS, then:

```powershell
ai-sw-build examples/filleted_box/spec.json --no-dim
```

**Path C example** — follow the step-by-step instructions in that folder's `README.md`.

## Notes

- Examples with `{rhs}` bindings reference a `locals.txt` file. Some use a machine-specific absolute path — update the `locals` field in `spec.json` to point to your copy, or replace `{rhs}` expressions with literal mm values.
- Path C expects you to record your own `.swp` macro (recordings are machine- and version-specific — see [docs/known_gotchas.md](../docs/known_gotchas.md)).
