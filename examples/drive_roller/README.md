# DriveRoller (SM-HW-S1b-004)

Cylindrical roller with centre bore, bearing pockets on each end face, and an O-ring groove at mid-length.

## Top-Plane sign-flip walkthrough

The O-ring groove (`SK_BeltGripGroove` → `Cut_BeltGripGroove`) is the key example of a Top Plane sketch with `center.z` and `centerline`. Here is how the coordinates flow from spec to SOLIDWORKS geometry.

### Spec declaration

```json
{
  "type": "sketch_rectangle_on_plane",
  "name": "SK_BeltGripGroove",
  "plane": "Top",
  "width": 1.0,
  "height": 5.0,
  "center": {"x": 12.0, "y": 0.0, "z": 40.0},
  "centerline": {
    "start": {"x": 0.0, "y": 0.0, "z": -5.0},
    "end":   {"x": 0.0, "y": 0.0, "z": 85.0}
  }
}
```

### What the builder does

On Top Plane, the axis mapping is:

| Spec field | Part-frame axis | Sketch-local axis |
|---|---|---|
| `center.x` / `width` | part X | sketch X (= +part X) |
| `center.y` / `height` | part Z (note: not Y) | sketch Y (= **-part Z**) |
| `center.z` | part Z offset | applied as an additional shift |

The builder projects part-frame center to sketch-local 2D:

```
sx = center.x  = 12.0        (sketch_X = +part_X)
sy = -center.z = -40.0       (sketch_Y = -part_Z, the sign flip)
```

Then `CreateCenterRectangle(sx_m, sy_m, 0, ...)` places the rectangle at part Z=+40 (verified by bounding box).

### Why center.z matters

Without `center.z`, the rectangle would land at part Z=0 (the bottom face of the roller), which is wrong. The `center.z` field lifts the geometry to Z=40 (mid-length of the 80mm roller).

### Centerline projection

The centerline uses the same projection. Its `y` values (0.0 and 0.0) are sketch-local Y, which maps to `-part_Z`. But the centerline is at part X=0 (the cylinder axis), so the `y` values in the spec are the sketch-Y positions of the endpoints. The `z` values (-5.0 and 85.0) are additional part-Z offsets:

```
start: sy = -centerline.start.z = -(-5.0) = 5.0    → part Z = -5
end:   sy = -centerline.end.z   = -(85.0) = -85.0   → part Z = 85
```

Wait — actually the centerline `z` is the part-frame Z of the endpoint, same as `center.z`. The builder applies the same sign flip: `sketch_Y_endpoint = -centerline_endpoint.z`. So start at sketch-Y=5.0 (part Z=-5) and end at sketch-Y=-85.0 (part Z=85). This gives a centerline running along part Z from -5 to +85, which is the cylinder's central axis — exactly what a `revolve_cut` needs.

### The revolve_cut

```json
{
  "type": "revolve_cut",
  "name": "Cut_BeltGripGroove",
  "sketch": "SK_BeltGripGroove",
  "angle": 360.0
}
```

SW auto-detects the centerline inside `SK_BeltGripGroove` as the axis of revolution and sweeps the rectangle profile 360 degrees around it, cutting a 1mm-deep × 5mm-wide groove into the cylinder at Z=40.

### Lint catches

Running `--lint` on a spec where a Top Plane sketch has `centerline` but no `center.z` would produce:

```
[warning] features/8/center.z: sketch 'SK_Groove' on Top Plane has a centerline
but no center.z — the centerline will default to part Z=0, which is usually
wrong for revolved features
```

## Building

```bash
ai-sw-build examples/drive_roller/spec.json --no-dim
ai-sw-build examples/drive_roller/spec.json --lint
ai-sw-build examples/drive_roller/spec.json --dry-run --lint
ai-sw-build examples/drive_roller/spec.json --verify-mass
```

## Axis reference

See [docs/sketch_axes.md](../../docs/sketch_axes.md) for the complete verified axis mappings across all three default reference planes.
