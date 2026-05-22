# Sketch Axis Mappings (Empirically Verified)

This document records the mapping between part-frame coordinates and
sketch-local 2D coordinates on each default reference plane. These were
determined by building geometry at known part coordinates and reading
back the resulting body bounding box.

## Verified Mappings (2026-05-22, SW 2024 SP1)

| Plane | sketch_X | sketch_Y | Verification |
|-------|----------|----------|--------------|
| Front (XY) | +part_X | +part_Y | Identity — trivially correct |
| Top (XZ) | +part_X | **-part_Z** | DriveRoller groove at center.z=40 lands at part Z=[37.5, 42.5] via `ai-sw-observe bbox` |
| Right (YZ) | +part_Z | +part_Y | Not exercised by shipped specs; derived from ModelToSketchTransform and geometric consistency |

## How to read this table

Given a spec `center: {"x": 12, "y": 0, "z": 40}` on Top Plane:

1. The builder projects part-frame center to sketch-local 2D:
   - `sx = cx = 12` (sketch_X = +part_X)
   - `sy = -cz = -40` (sketch_Y = -part_Z)
2. The COM call `CreateCenterRectangle(sx_m, sy_m, 0, ...)` receives meters.
3. The resulting geometry lands at part Z=+40 (verified by bounding box).

## ModelToSketchTransform caveat

Reading `ISketch.ModelToSketchTransform.ArrayData` on Top Plane shows a
3x3 rotation matrix with `sketch_Y = +part_Z` (no sign flip). This
appears to contradict the empirical mapping above. The discrepancy is
likely due to SW's internal transform convention differing from the
simple `sketch = R * part + t` interpretation. **The actual geometry
takes precedence over the transform matrix reading.** Do not "fix" the
sign flip based on the transform alone.

## Centerline endpoint projection

Centerline `start`/`end` coordinates use the same projection. For Top
Plane, the `z` component of start/end is negated the same way as
`center.z`:

```python
# _draw_centerline_if_present (in _sketch_primitives.py)
if plane == "Top":
    sz_m = -cz_m  # same sign flip as rectangle/circle center
```

## Code locations

- Rectangle handler: `spec/sketches/rectangle_on_plane.py:73-79`
- Circle handler: `spec/sketches/circle_on_plane.py:44-49`
- Centerline drawing: `spec/_sketch_primitives.py:90`
- Extrude origin remap: `spec/builder.py:420-426`

## When to re-verify

- New SW version (the sign flip may change across builds)
- Adding a new plane type (user-created reference planes)
- Any change to the sketch handler projection logic
