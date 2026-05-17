# mirrored_holes

A 30×20×4 mm plate with one off-center hole, mirrored about the Right Plane to produce a symmetric pair.

## Run

```powershell
ai-sw-build examples\mirrored_holes\spec.json
```

## What it builds

| # | Feature | Primitive | Notes |
|---|---|---|---|
| 1 | `SK_Plate` | `sketch_rectangle_on_plane` | 30×20 mm on Front Plane |
| 2 | `EX_Plate` | `boss_extrude_blind` | 4 mm thick |
| 3 | `SK_HoleSeed` | `sketch_circle_on_face` | Ø3 mm at u = −10, v = 5 on the +z face |
| 4 | `Hole_Seed` | `cut_extrude_through_all` | Through-hole using the seed sketch |
| 5 | `Mir_Hole` | `mirror_feature` | Mirrors `Hole_Seed` about the Right Plane |

## Mirror plane semantics

`plane` is one of `"Front"`, `"Top"`, `"Right"` — the three default reference planes:

| Plane | What it is | Mirror effect |
|---|---|---|
| `Front` | XY plane (z=0) | Flips Z |
| `Top` | XZ plane (y=0) | Flips Y |
| `Right` | YZ plane (x=0) | Flips X |

For this plate (centered on origin), mirroring about Right Plane takes the hole at u=−10 to u=+10. The Y position (v=5) is unchanged.

## When mirroring won't help

Mirror is symmetry-driven. If the geometry you want isn't a mirror image of an existing feature, use `linear_pattern` instead.

## Things to try

- Move the seed hole to v = 0 (centered on origin) and mirror about Top Plane — the mirror is a no-op because the hole is already on the mirror plane.
- Use Front Plane to mirror across z = 0 — for this 4 mm plate, the mirrored hole appears at z = −4. (The mirror produces geometry below the plate; if the plate doesn't extend there, the cut might be a no-op.)
- Mirror a non-hole feature (e.g. a boss instead of a cut) by changing `Hole_Seed`'s type. The mirror primitive doesn't care what kind of feature it's replicating.

## v1 limits

- Only the three default reference planes are accepted as `plane`. Custom reference planes and planar faces are deferred to a later version.
- Single-seed only. Multi-seed mirror would need a list field.
- Feature mirror only, not body mirror. Setting up body mirror would flip multiple boolean args; deferred until a clear need.

## Selection-marked API surface

Like `linear_pattern`, mirror needs marked selection:

- mark **2** — mirror plane
- mark **1** — seed feature

`doc.Extension.SelectByID2` (the marked-selection variant) fails on this build with a Callout marshalling error under pywin32 late-binding. The bridge works around it via plain `SelectByID('Front Plane', 'PLANE', 0, 0, 0)` + `SelectionMgr.SetSelectedObjectMark` for the plane, then `seed.Select2(append=True, mark=1)` for the seed feature. See `spikes/v0_3/spike_s_mirror.py` and the v0.3 spikes README for the full diagnosis.
