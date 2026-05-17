# patterned_plate

A 30×20×4 mm plate with a Ø3 mm through-hole near the left edge, linear-patterned 3× along +X at 8 mm spacing.

## Run

```powershell
ai-sw-build examples\patterned_plate\spec.json --no-dim
```

## What it builds

| # | Feature | Primitive | Notes |
|---|---|---|---|
| 1 | `SK_Plate` | `sketch_rectangle_on_plane` | 30×20 mm on Front Plane |
| 2 | `EX_Plate` | `boss_extrude_blind` | 4 mm thick |
| 3 | `SK_HoleSeed` | `sketch_circle_on_face` | Ø3 mm at u = −10, v = 0 on the +z face |
| 4 | `Hole_Seed` | `cut_extrude_through_all` | Through-hole using the seed sketch |
| 5 | `LP_Holes` | `linear_pattern` | 3 instances, spacing 8 mm, +X direction (flipped) |

Result: three Ø3 mm holes along the centreline of the plate at u = −10, −2, +6 on the +z face.

## How direction selection works

`linear_pattern` needs a SW model edge whose tangent direction defines the pattern axis. The spec doesn't name the edge — it gives a 3D point in part coords, and the builder calls `SelectByID('EDGE', x, y, z)` to pick whichever edge passes through that point.

For this plate, the **top edge of the +z face** runs from (−15, +10, 4) to (+15, +10, 4). It's X-aligned, so its tangent is ±X. Picking the midpoint (0, +10, 4) lands on this edge. Setting `flip: true` selects the −X→+X orientation so the pattern grows toward the right.

> **Mental model:** "which edge tangent is the direction I want?" — pick a point on an edge whose **tangent** is along the desired axis, not an edge that's *located at* the desired axis. On a box, edges PARALLEL to your desired direction are what you want. The 4 X-aligned edges on this plate are at y = ±10, z = 0 or 4; any midpoint on those works.

If the pattern goes the wrong way, toggle `flip`.

## Things to try

- Remove `"flip": true` — the pattern reverses, and 2 of 3 instances fall off the plate (you'll see only the seed hole on the left).
- Change `count` to 4 with `spacing: 6.0` — pattern fits 4 holes in the 30mm-wide plate.
- Change `direction` to `{"x": 15.0, "y": 0.0, "z": 4.0}` (an X=+15 edge, oriented along Y) to pattern down −Y instead. With `flip: false` two of the instances fall off the bottom; with `flip: true` they fall off the top.

## Why pattern needs marked selection

Unlike fillet/chamfer (which take edges) or extrude (which takes a sketch), pattern features need two distinct things in their selection set: the seed feature *and* the direction reference. SW disambiguates these by **selection mark**:

- mark **1** — direction reference
- mark **4** — seed feature

The naive approach is `doc.Extension.SelectByID2(name, type, x, y, z, append, mark, callout, opt)`, which takes a mark arg directly. But its `Callout` (OUT-typed IDispatch) arg fails to marshal through pywin32 late-binding — raises `Type mismatch` even when passed `None`. Verified RED in Spike R (2026-05-17).

The bridge uses a 3-step workaround instead:

1. `SelectByID(name, "EDGE", x, y, z)` — plain 5-arg form, no Callout
2. `SelectionMgr.SetSelectedObjectMark(1, mark=1, action=Set)` — retroactively tag the edge
3. `seed_feature.Select2(append=True, mark=4)` — add the seed via the feature's own method, which takes only `(append, mark)`

Order matters: SelectByID is non-appending, so the edge has to be selected first.

Full COM-call detail: `spikes/v0_3/spike_r_linear_pattern.py`.
