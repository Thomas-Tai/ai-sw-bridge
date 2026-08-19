# Coordinate Conventions

Reference for the sketch-plane-to-part-frame mapping the bridge uses, and the
handful of offset/flat-part recipes that trip people up. The geometric
pre-flight (`ai-sw-build <spec> --lint`) checks these mappings before a build
ever reaches SOLIDWORKS — read this doc when it flags an `empty_air_cut`
finding, or when you're debugging a silent-`None` from `FeatureCut4` /
`FeatureExtrusion2` on a live seat.

---

## 1. Plane -> part mapping

Every sketch is authored in sketch-local `(u, v)` coordinates on a plane that
sits at offset `o` along that plane's normal. The plane determines how
`(u, v, o)` maps onto part-frame `(X, Y, Z)`:

| Plane | X | Y | Z |
|-------|---|---|---|
| Front | u | v | o |
| Top   | u | o | -v |
| Right | o | v | -u |

The table is exact, but the two sign-flips are what actually bite. Here is
where a *rightward* sketch move (`+u`) and an *upward* sketch move (`+v`)
really go in the part frame, per plane:

```
             a +u (sketch-right) move goes to →   a +v (sketch-up) move goes to →
  Front               +X                                   +Y
  Top                 +X                                   −Z   ⚠ sketch-up = part −Z
  Right               −Z   ⚠ sketch-right = part −Z        +Y

  Part frame is right-handed:      +Z
                                    │
                                    └──── +X
                                   ╱
                                +Y
```

Only **Front** maps sketch `(u, v)` straight onto part `(X, Y)` with no flip.
On **Top**, `+v` drives geometry into **−Z**; on **Right**, `+u` drives it into
**−Z**. Those are the two rows to sanity-check first when a cut lands in air.

**Traps:**
- **Top plane: sketch `v` maps to `-Z`.** A positive `v` in the sketch moves
  the geometry in the *negative* part-Z direction. This is the single most
  common cause of a cut or hole landing in air instead of on material.
- **Right plane: sketch `u` maps to `-Z`.** Same sign-flip trap, on the other
  axis.

If a cut/hole region doesn't intersect any material, `FeatureCut4` returns
`None` with no error (see §5) — check these two rows first.

## 2. Box-face local mapping (modeled faces only)

For sketching on a face of an already-modeled rectangular body:

| Face | u -> | v -> | face lies at |
|------|------|------|---------------|
| +z / -z | X | Y | Z = zmax / zmin |

Other faces (`±x`, `±y`) are an honest-skip in v0.11 — the pre-flight does not
yet model their local mapping and will not flag findings on them.

## 3. Offset-part recipes

- **`start_offset` always grows in the +normal direction and ignores
  `flip`.** To grow a feature the other way along the plane normal, use
  `flip_start_offset` instead of setting `flip` — `flip` has no effect on
  which side `start_offset` grows toward.
- **Holing a body across an air gap:** use `cut_extrude_two_direction` with
  symmetric blind depths on each side, not a through-all cut. A through-all
  cut sweeps until it *finds* material in one direction; across an air gap
  it finds none and `FeatureCut4` returns `None`.

## 4. Flat-part pattern

Build flat profiles as **Front-plane bosses**, then put any holes on the
resulting **`+z` face**. This is the pattern that keeps the box-face mapping
in §2 in play (holes on `+z`/`-z` are supported; other faces are the
honest-skip from §2).

## 5. Silent-`None` triage

When `FeatureCut4` or `FeatureExtrusion2` returns `None` with no COM error:

1. **Suspect geometry-in-air first** — a plane->part mapping slip (§1) or an
   offset that puts the cut/hole region entirely off the target body.
2. Run `ai-sw-build <spec> --lint` — the seat-free pre-flight catches most of
   these before you ever touch SOLIDWORKS.
3. Only after ruling out geometry-in-air should you suspect the COM API
   itself. The on-seat fallback for confirming real geometry is the
   1 micrometer slug-and-read-bbox spike (extrude a 0.001 mm slug at the
   suspect location and read `GetBox` on it) — see
   [known_gotchas.md](known_gotchas.md) for the API-marshalling gotchas that
   are the *other* class of silent failure.

## 6. Assembly placement (pointer)

One sign convention worth knowing here even though it's an assembly-stage
concern, not a part-stage one: in `ai-sw-assembly` placement, `rpy=0` places
a component by its bounding-box center, while `rpy != 0` places it by its
part-origin.
