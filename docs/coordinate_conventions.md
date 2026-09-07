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

### Live face resolution (issue #47)

The table above is the *modelled* face: `_face_frame` computes a centre and
outward normal from the parent extrusion's origin, axis, depth, and (for side
faces) rectangular extents. That mapping is a pure function of the spec.

Selecting the corresponding live `IFace2` is a separate step. The builder
enumerates every solid-body face (`GetBodies2` / `GetFaces`), keeps those
whose outward normal matches the modelled face, and picks the unique winner
of a total order on measured geometry:

1. Euclidean distance from the modelled face centre to
   `IFace2.GetClosestPointOn` of that centre (nearer wins).
2. Face area (larger wins) — so two coplanar leftovers after a cut do not
   race on `GetFaces` order.
3. Bounding-box centroid `(x, y, z)` lexicographic order.

The ranked winner is enacted with `SelectByID` at that face's closest point
— the pick `InsertSketch` is proven to consume — and kept only when the
picked face fingerprints (normal + area + centroid) as the winner. A
view-dependent wrong hit is rejected and the ranked `IFace2` is selected
with `IEntity.Select2` instead. A `SelectByID` spiral without a ranked
winner is last-resort fallback (enumeration raised or nothing selectable);
a `FACE_RESOLVE ... path=select_by_id` line on stderr marks it.
`simple_hole` still uses `SelectByID` at the hole centre for the pick
*point* `SimpleHole2` consumes; that path is residual risk, not the sketch
path.

Every resolve prints one `FACE_RESOLVE` line to stderr (`path`, enumeration
`index`, `dist_mm`, `area_m2`, `centroid_mm`, `normal`) so two seat runs of
the same spec can be diffed rather than guessed at. `index` may shuffle
across runs even when the geometric winner is stable — compare centroid /
area / path, not index.

## 3. Offset-part recipes

- **`start_offset` always grows in the +normal direction and ignores
  `flip`.** To grow a feature the other way along the plane normal, use
  `flip_start_offset` instead of setting `flip` — `flip` has no effect on
  which side `start_offset` grows toward.
- **Holing a body across an air gap:** use `cut_extrude_two_direction` with
  symmetric blind depths on each side, not a through-all cut. A through-all
  cut sweeps until it *finds* material in one direction; across an air gap
  it finds none and `FeatureCut4` returns `None`.

## 4. Cut direction (and the flat-part pattern)

`FeatureCut4` with `Dir=False` (the COM default) sweeps **−(sketch normal)**.
A modeled face's normal points out of the body, so −normal is *into* it — a
face-sketched one-directional cut therefore works without flipping `Dir`. A
reference plane at or below the body has −normal pointing away, so the same
default would sweep empty air and SOLIDWORKS would return `None` with no
error (issue #40).

The builder therefore sets `Dir=True` for a one-directional cut
(`cut_extrude_blind` / `_through_all` / `_midplane`) whose sketch is on a
reference plane — any sketch type whose schema takes a `plane` field, which
is all of them except the three `*_on_face` types and `sketch_3d_sketch` —
so the cut sweeps **+normal**, toward the
material the rest of this doc and the pre-flight already assume. Face-sketched
cuts keep `Dir=False`. `cut_extrude_two_direction` is unchanged: it straddles
the plane and removes material whichever way `Dir` points.

`flip` on a one-directional cut is bound to FeatureCut4 arg 2 (`Flip`) and
**does not reverse the cut direction** (seat-proven 2026-09-05, both `flip`
values build once `Dir` is correct). Do not use it as a "cut the other way"
switch.

The still-useful flat-part pattern: build flat profiles as **Front-plane
bosses**, then put holes on the resulting **`+z` face**. That keeps the
box-face mapping in §2 in play (holes on `+z`/`-z` are supported; other
faces are the honest-skip from §2). It is no longer a workaround for a
kernel constraint — plane-sketched one-directional cuts now build — but it
is still the mapping the pre-flight models exactly.

## 5. Silent-`None` triage

When `FeatureCut4` or `FeatureExtrusion2` returns `None` with no COM error:

1. **Suspect geometry-in-air first** — a plane->part mapping slip (§1) or an
   offset that puts the cut/hole region entirely off the target body.
2. Run `ai-sw-build <spec> --lint` — the seat-free pre-flight catches most of
   these before you ever touch SOLIDWORKS.
3. **If the failing feature consumes a face-referenced sketch**
   (`sketch_*_on_face`, `of_feature` + `face`): grep stderr for
   `FACE_RESOLVE` on that parent/face. Diff the line against a passing run
   of the same spec. A change in `centroid_mm` / `area_m2` / `path` means
   the live face was not the same object; a stable `FACE_RESOLVE` with
   `path=enumeration` means the face identity was stable and the `None` is
   geometry, not resolution. See §2.
4. Only after ruling out geometry-in-air *and* a face-identity slip should
   you suspect the COM API itself. The on-seat fallback for confirming real
   geometry is the 1 micrometer slug-and-read-bbox spike (extrude a
   0.001 mm slug at the suspect location and read `GetBox` on it) — see
   [known_gotchas.md](known_gotchas.md) for the API-marshalling gotchas that
   are the *other* class of silent failure.

## 6. Assembly placement (pointer)

One sign convention worth knowing here even though it's an assembly-stage
concern, not a part-stage one: in `ai-sw-assembly` placement, `rpy=0` places
a component by its bounding-box center, while `rpy != 0` places it by its
part-origin.
