# Example: filleted box

The simplest example that exercises three different feature categories: sketch, extrude, and fillet.

Builds a 20×20×10 mm box with a 2 mm constant-radius fillet on one edge. No `locals.txt` — all dimensions are literal mm values.

## Run it

Open SOLIDWORKS (no part needed — the builder creates one), then:

```powershell
ai-sw-build examples/filleted_box/spec.json --no-dim
```

Expected output (~3 seconds):

```json
{
  "ok": true,
  "features_built": ["SK_Box", "Extrude_Box", "Fillet_TopRightEdge"],
  "bindings_added": [],
  "save_as": null,
  "no_dim": true
}
```

## What it builds (3 features)

| # | Feature | Type | What it does |
|---|---|---|---|
| 1 | `SK_Box` | `sketch_rectangle_on_plane` | 20×20 mm rectangle centered on origin, Front Plane |
| 2 | `Extrude_Box` | `boss_extrude_blind` | Extrude the rectangle 10 mm in +Z |
| 3 | `Fillet_TopRightEdge` | `fillet_constant_radius` | 2 mm fillet on the +X edge of the top face (point at `x=10, y=0, z=10`) |

## Files

| File | Purpose |
|---|---|
| `spec.json` | Literal-dimension spec (no `locals.txt` needed) |
| `spec_parametric.json` | Variant with `{rhs}`-bound radius. Requires a valid `locals` path and running without `--no-dim` to see the equation binding |

## Things to try

- Change `radius` from `2.0` to `5.0` — see the fillet grow until it consumes the entire edge
- Change the box `width` to `30.0` — notice the fillet edge point `(10, 0, 10)` still lands on the edge because it's within the new width
- Change the box `width` to `15.0` — the fillet edge point `(10, 0, 10)` is still on the edge (barely), but at `width: 10.0` it would fall outside and fail
- Add a second edge point to the `edges` array to fillet multiple edges at once
