# patterned_disc

A 30 mm diameter × 5 mm thick disc with one Ø3 mm × 2 mm off-center boss, circular-patterned 6× around the disc's central axis at equal spacing over 360°.

## Run

```powershell
ai-sw-build examples\patterned_disc\spec.json --no-dim
```

## What it builds

| # | Feature | Primitive | Notes |
|---|---|---|---|
| 1 | `SK_Disc` | `sketch_circle_on_plane` | Ø30 mm on Front Plane |
| 2 | `EX_Disc` | `boss_extrude_blind` | 5 mm thick |
| 3 | `SK_BossSeed` | `sketch_circle_on_face` | Ø3 mm at u = 10, v = 0 on the +z face |
| 4 | `Boss_Seed` | `boss_extrude_blind` | 2 mm tall boss using the seed sketch |
| 5 | `CP_Bosses` | `circular_pattern` | 6 instances around +z axis, equal spacing, 360° |

Result: six Ø3 mm × 2 mm bosses arranged in a hexagonal ring on the top face of the disc, at 60° intervals.

## How axis selection works

`circular_pattern` needs an SW entity whose axis-of-revolution defines the rotation axis. The spec gives a 3D point in part coords; the builder tries `SelectByID('EDGE', x, y, z)` first, then falls back to `SelectByID('FACE', ...)` if no edge passes through that point.

For this disc, the **top circular rim edge** lies on the circle `(x² + y² = 15², z = 5)`. Any point on that circle works as the axis reference; `(15, 0, 5)` is the +X-side rim. SW infers the axis of revolution (here, +z through the origin) from the selected circular edge.

> **Mental model:** the axis point names a *reference entity*, not the axis itself. Pick a point on a circular edge or a cylindrical face that revolves around the axis you want. A circular hole's rim works; a cylinder's side face works.

### Alternate axis sources

The builder accepts either:
- a point on a **circular edge** (e.g. the rim of any cylindrical hole or boss) — preferred, less ambiguous
- a point on a **cylindrical face** (e.g. the side wall of a cylindrical hub) — fallback

Both are verified working on SW 2024 SP1.

## v1 limits

- Direction 1 only — no bidirectional / symmetric patterns yet
- Single seed feature — multi-seed circular patterns deferred
- `total_angle` is a plain number, not parametric — `{"rhs": "..."}` form not yet wired for pattern dims
- Equal spacing always on
