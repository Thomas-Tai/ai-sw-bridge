# Demo widget: pillow-block shaft assembly

A small, purpose-built product bundled for `tools/demo_full_system.py` (the
chaptered full-system demo). Three parts -- a mounting base plate, a turned
shaft, and a bearing block -- assemble into a pillow-block. It exists to
give the demo a legible, recognizable build with a real feature-tree spread,
not to be an exhaustive catalog of every `ai-sw-build` feature kind (see
`docs/superpowers/specs/2026-08-08-ai-sw-bridge-full-system-demo-design.md`
§5 and its Task-7 correction note for why the widget's family list is
smaller than that design doc's original table).

## Layout

```
demo_widget/
  demo_baseplate/{spec.json, locals.txt}
  demo_shaft/{spec.json, locals.txt}
  demo_bearing_block/{spec.json, locals.txt}
  assembly.json        # component placement (+ mates, once Spike 0 confirms them)
  export.json          # standalone schema-v2 spec exercising the export: block
```

## As-built feature-family list (20 build families total)

Enumerated directly from the committed `spec.json` files -- this is the
authoritative list; the design spec's earlier table (§5) listed some kinds
that turned out not to be declarable in a part spec at all (see that doc's
correction note).

**`demo_baseplate` (9 families):** `sketch_rectangle_on_plane`,
`boss_extrude_blind`, `sketch_circle_on_face`, `cut_extrude_through_all`,
`linear_pattern`, `mirror_feature`, `fillet_constant_radius`,
`chamfer_edge`, `circular_pattern`.

**`demo_shaft` (4 families):** `sketch_rectangle_on_plane`, `revolve_boss`,
`revolve_cut`, `chamfer_edge`.

**`demo_bearing_block` (7 families):** `sketch_rectangle_on_plane`,
`boss_extrude_midplane`, `sketch_circle_on_face`, `cut_extrude_through_all`,
`fillet_constant_radius`, `simple_hole`, `chamfer_edge`.

**= 20 build families total** (9 + 4 + 7). Several families repeat across
parts (`sketch_rectangle_on_plane`, `cut_extrude_through_all`,
`chamfer_edge`, `fillet_constant_radius`) -- the 20 counts each part's
distinct families independently, matching how the demo script's `part`
chapter presents them per-part.

## Trap-avoidance notes (from `known_limitations.md`)

- **Origin-centered parents.** Every part's base sketch (`SK_Plate`,
  `SK_Body`, `SK_Block`) is centered on the part origin, so face-sketch
  children (`sketch_circle_on_face`, `of_feature`/`face: "+z"`) resolve
  correctly (§1). Off-origin child sketches carry an explicit `center:
  {u, v}` offset instead of relying on an off-origin parent.
- **Axis-aligned, non-flipped extrudes.** All extrudes are on `Front` with a
  plain `+z`/`+x` sense (`boss_extrude_blind`, `boss_extrude_midplane`,
  `revolve_boss`) so side-face sketches and edges resolve predictably (§2).
- **Semantic edge selectors for fillet/chamfer.** Where the geometry
  supports it, fillets/chamfers select edges via `of_feature` +
  `between_faces` (e.g. `demo_baseplate`'s `FIL_Corners`, `demo_bearing_
  block`'s `FIL_Block`) rather than literal points, so they survive
  dimension edits (§4). Where the parent has no `of_feature`/face metadata
  to select against (a revolve body's end faces, a cut's circular rim), the
  spec falls back to literal edge points and documents why in that
  feature's `_comment` (`demo_shaft`'s `CHA_Ends`,
  `demo_bearing_block`'s `CHA_BoreLeadIn`).
- **`--save-as` on every part.** Each `ai-sw-build --no-dim` invocation
  produces a new untitled document; `demo_full_system.py`'s `part` chapter
  passes `--save-as demo_out/<PartName>.SLDPRT` for every part so the
  assembly chapter has parts on disk to reference (§5).

## The locals mechanism

Each part directory has a `locals.txt` (`"VAR" = value` lines, e.g.
`demo_baseplate/locals.txt`: `"PLATE_L" = 100.0`, `"PLATE_MOUNT_PITCH" =
40.0`, ...) referenced from its `spec.json` via `"locals": "locals.txt"`.
Dimension-bearing fields in the spec bind to a local by name instead of a
literal number:

```json
{"type": "boss_extrude_blind", "name": "EX_Plate", "sketch": "SK_Plate",
 "depth": {"rhs": "\"PLATE_T\""}}
```

`{"rhs": "\"VAR_NAME\""}` is accepted on scalar dimension fields (`width`,
`height`, `depth`, `diameter`, `radius`, `distance`, ...) and even simple
expressions (`demo_shaft`'s `SK_Body.height` is `{"rhs": "\"SHAFT_DIA\"/2"}`).
**Coordinate/center fields stay literal** -- `center: {x, y}`, `center: {u,
v}`, `direction: {x, y, z}`, `axis: {x, y, z}`, and literal edge-point
selectors all reject `{"rhs": ...}` (the schema rejects it: confirmed
empirically, see the `_comment`/`_comment2`/`_comment3` notes throughout the
three `spec.json` files). Those numbers are kept in sync with `locals.txt`
by hand, and each spec's top-level `_comment` says so. This is the mechanism
`tools/demo_full_system.py`'s headline "resize the bore and rebuild" beat
exercises: it changes `demo_bearing_block/locals.txt`'s `BORE_DIA` (in a
`demo_out/reparam/` scratch copy, never the committed file) and rebuilds.

## `export.json`

A separate, standalone schema-v2 (`"schema_version": 2`) spec -- not part of
the widget assembly -- whose only job is to exercise the `export:` block
(`export/schema.py`, spec.md FR-1-03): a small rectangle-and-extrude solid
declaring STEP AP-214, binary STL, and 3MF outputs into `demo_out/`. See
`docs/demo_full_system.md` for why it needs the `AI_SW_BRIDGE_FLAG_SCHEMA_V2`
environment variable, not the build CLI's `--enable-flag`.
