# sketch_polyline_on_plane

A gallery of the `sketch_polyline_on_plane` primitive: a non-axis-aligned closed
4-point parallelogram on the Top plane, extruded into a slab.

- **`SK_FloorParallelogram`** — a closed `sketch_polyline_on_plane` profile (a
  parallelogram, so its edges are not axis-aligned) on the Top plane.
- **`BOSS_FloorSlab`** — a `boss_extrude_midplane` of that profile.

`sketch_polyline_on_plane` is the composite closed-polyline primitive for
profiles a rectangle or circle can't express (45° and other non-axis-aligned
edges). See [../../docs/spec_reference.md](../../docs/spec_reference.md).

Run it:

```bash
ai-sw-build examples/sketch_polyline_on_plane/spec.json --no-dim
```
