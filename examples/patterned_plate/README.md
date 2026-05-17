# patterned_plate

A 30×20×4 mm plate with a Ø3 mm through-hole near the left edge, linear-patterned 3× along +X at 8 mm spacing.

## Run

```powershell
ai-sw-build examples\patterned_plate\spec.json
```

## What it builds

| # | Feature | Primitive | Notes |
|---|---|---|---|
| 1 | `SK_Plate` | `sketch_rectangle_on_plane` | 30×20 mm on Front Plane |
| 2 | `EX_Plate` | `boss_extrude_blind` | 4 mm thick |
| 3 | `SK_HoleSeed` | `sketch_circle_on_face` | Ø3 mm at u = −10, v = 0 on the +z face |
| 4 | `Hole_Seed` | `cut_extrude_through_all` | Through-hole using the seed sketch |
| 5 | `LP_Holes` | `linear_pattern` | 3 instances, spacing 8 mm, +X direction |

## How direction selection works

`linear_pattern` needs a SW model edge whose tangent direction defines the pattern axis. The spec doesn't name the edge — it gives a 3D point in part coords, and the builder calls `SelectByID('EDGE', x, y, z)` to pick whichever edge passes through that point.

For this plate, the edge along the +X side of the +z face runs from (15, −10, 4) to (15, +10, 4). The midpoint **(15, 0, 4)** is on that edge, so the pattern direction follows its tangent (which is ±Y at that point — see the gotcha below).

> **Gotcha:** The +X edge of the +z face is actually oriented along Y at the midpoint. To pattern along +X, you'd want the +Y edge of the +z face instead, with a point like (0, 10, 4). The spec above picks (15, 0, 4) because it's the +X edge that **runs along Y** — picking the "X-direction edge" means picking an edge that *bounds* the X-extent of the plate, which on a rectangular box is actually a Y-aligned edge.
>
> Easier mental model: think "which edge tangent is the direction I want?" not "which edge is at the location I want."

If the pattern goes the wrong way, set `"flip": true`.

## Things to try

- Change `count` to 4 — the spacing should keep instances at 8 mm intervals, giving total span 24 mm.
- Add `"flip": true` to reverse the pattern direction.
- Change `direction` to a point on a Y-aligned edge (e.g. `{"x": 0, "y": 10, "z": 4}`) to pattern along Y instead.

## Why pattern needs marked selection

Unlike fillet/chamfer (which take edges) or extrude (which takes a sketch), pattern features need two distinct things in their selection set: the seed feature *and* the direction reference. SW disambiguates these by **selection mark**:

- mark **4** — seed feature
- mark **1** — direction reference

The builder uses `doc.Extension.SelectByID2` with these marks. If `SelectByID2` fails under late-binding (we've seen it fail with Callout OUT-param errors on other methods), this primitive will surface a clear error. See `spikes/v0_3/spike_r_linear_pattern.py`.
