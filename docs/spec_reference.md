# Spec reference

Complete reference for the JSON spec format consumed by `ai-sw-build`. The authoritative schema lives in [`src/ai_sw_bridge/spec/schema.py`](../src/ai_sw_bridge/spec/schema.py); this document is the human-readable version.

## Editor autocomplete (JSON Schema)

A standalone JSON Schema for the spec format is published at
[`schema/ai-sw-bridge.spec.schema.json`](../schema/ai-sw-bridge.spec.schema.json).
Point your editor at it — via a **workspace mapping**, not a key inside the
spec — to get autocomplete, enum hints, and inline validation while authoring a
`spec.json`, with no `ai-sw-build` run required.

- **VS Code** — map a glob to the file in `.vscode/settings.json`; every
  matching spec then picks it up automatically:

  ```json
  {
    "json.schemas": [
      { "fileMatch": ["**/spec.json"], "url": "./schema/ai-sw-bridge.spec.schema.json" }
    ]
  }
  ```

  Use the raw URL
  (`https://raw.githubusercontent.com/Thomas-Tai/ai-sw-bridge/master/schema/ai-sw-bridge.spec.schema.json`)
  instead of the local path if your specs live outside this repo.

- **JetBrains IDEs** — *Settings → Languages & Frameworks → Schemas and DTDs →
  JSON Schema Mappings*: add the file (or URL) and a `*/spec.json` file pattern.

> **Do not add a `$schema` key inside the spec.** The v1 grammar is strict
> (`additionalProperties: false`), so an inline `$schema` — or any other
> unknown top-level key — is rejected by `ai-sw-build` validation (exit `3`).
> Associate the schema through the editor's workspace mapping instead. (The one
> exception is keys beginning with `_`, e.g. `_comment`: they are stripped as
> annotations and allowed anywhere, and the published schema permits them too.)

The published file is a serialization of `schema.py` (the v1 stable surface),
kept in lockstep by `tools/emit_spec_schema.py` and its CI sync gate — after any
intentional schema change, regenerate it with `python tools/emit_spec_schema.py`.
The per-feature field tables below are generated from that schema by
`tools/emit_spec_reference.py` (delimited by `<!-- BEGIN GENERATED: <type> -->`
markers so surrounding hand-written prose survives) and gated the same way —
regenerate with `python tools/emit_spec_reference.py`.

**Installed outside a repo clone?** The same schema ships inside the wheel, so a
`pip`/`pipx`/installer install can locate it without the source tree:

```python
from ai_sw_bridge.spec import published_schema_path
print(published_schema_path())   # absolute path to the packaged .json
```

Point your editor's workspace mapping at that path (or keep using the raw URL
above). The packaged copy is byte-identical to the repo-root
`schema/` file — both are generated from one `render()` and gated in sync.

## Top-level structure

```json
{
  "schema_version": 1,
  "name": "PartName",
  "locals": "C:\\path\\to\\globals_locals.txt",
  "features": [ ... ]
}
```

| Field | Required | Type | Description |
|---|---|---|---|
| `schema_version` | yes | integer | Must be `1`. |
| `name` | yes | string | Part name. Becomes the SLDPRT filename if saved. |
| `locals` | no | string | Absolute path to a `*_locals.txt` equation file. Required if any feature uses `{rhs}` expressions. |
| `features` | yes | array | Ordered list of features to build. Minimum 1 item. |

## Length values

Any field marked as "length" accepts one of two forms:

| Form | Example | Description |
|---|---|---|
| Literal | `20.0` | Millimetres. Passed directly to SW (converted to meters internally). |
| RHS expression | `{"rhs": "\"S1B_MMP_W\""}` | Equation Manager expression. Pasted verbatim into `EquationMgr.Add2`. Quote variable names yourself. |

RHS expressions also support arithmetic:

```json
{"rhs": "\"S1B_MOTOR_FLANGE_OD\" + 0.5"}
```

In `--no-dim` mode, the builder resolves these to literal mm values in Python before any SW call. In parametric mode, they become live equation links.

## Feature naming

Feature names must match `^[A-Za-z_][A-Za-z0-9_]*$` and be unique within the spec. Names are used for cross-feature references (e.g. `sketch: "SK_Box"`).

## Sketch primitives

### `sketch_rectangle_on_plane`

Creates a centered rectangle on one of the three default reference planes.

```json
{
  "type": "sketch_rectangle_on_plane",
  "name": "SK_Box",
  "plane": "Front",
  "width": 20.0,
  "height": 10.0,
  "center": {"x": 0.0, "y": 0.0}
}
```

<!-- BEGIN GENERATED: sketch_rectangle_on_plane -->
| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `type` | const `"sketch_rectangle_on_plane"` | yes |  | Rectangular profile sketch on a default reference plane (Front/Top/Right). |
| `name` | string | yes |  | Unique identifier for this feature within the spec. Later features refer back to it by name (e.g. via `sketch`, `of_feature`, `seed`, or `target_ref.of_feature`). |
| `plane` | enum (`"Front"` / `"Top"` / `"Right"`) | yes |  | Default reference plane to host the sketch. |
| `width` | length | yes |  | Rectangle width (mm). |
| `height` | length | yes |  | Rectangle height (mm). |
| `center` | object | no |  | Sketch-local center (mm). Default (0, 0, 0). The optional z offsets the sketch geometry along the part-frame Z axis and is required when sketching on Top Plane (XZ) at part-Z != 0, e.g. an O-ring groove at the mid-length of a +Z-extruded shaft. For Front (XY) and Right (YZ) planes leave z=0; only Top Plane's normal aligns with part-Z. |
| `centerline` | object | no |  | Construction line embedded in the sketch. Consumed by `revolve_boss` as the axis of revolution (SW auto-detects). No driving dim; coordinates are literal mm. |
| `relations` | array | no |  | Geometric relations between sketch entities. Applied after geometry draw via ISketchManager.SketchAddConstraints. ⚠️ Token names are seat-gated (W21 radians lesson). |
<!-- END GENERATED -->

**center.z** (Top/Right Plane sketches): The optional `z` field offsets the sketch geometry along the part-frame Z axis. On Front Plane, `z` is redundant (the plane already lies at Z=0). On Top Plane, `center.z` positions the rectangle at the given part-Z — the builder applies a sign flip (`sketch_Y = -part_Z`) internally. On Right Plane, `center.z` positions along part-Z similarly. This is essential when a Top/Right Plane sketch must land at a non-zero Z position (e.g. a groove at mid-length of a cylinder). See the **Sketch axes reference** section below for the full axis-mapping reference.

**Axis mapping:**
- Front Plane: X = width, Y = height, extrude direction = +Z
- Top Plane: X = width, Y = height, extrude direction = -Y (downward)
- Right Plane: X = width, Y = height, extrude direction = +X

**centerline** (optional): Adds a construction line to the sketch, consumed by `revolve_boss` / `revolve_cut` as the axis of revolution. SW auto-detects the centerline when the sketch is selected for a revolve operation.

```json
"centerline": {
  "start": {"x": 0.0, "y": 0.0, "z": -5.0},
  "end":   {"x": 0.0, "y": 0.0, "z": 85.0}
}
```

| Field | Required | Type | Description |
|---|---|---|---|
| `centerline` | no | object | `{start, end}` — each endpoint has `{x, y}` (required) and optional `z` (same meaning as `center.z`). One centerline per sketch. Coordinates are literal mm; no `{rhs}` bindings. |

The centerline `start`/`end` use the same projection as `center`: on Top Plane, the `y` component maps to part-Z (with sign flip) and the optional `z` provides an additional part-frame Z offset. See the **Sketch axes reference** section below for details.

**Lint warning:** A Top Plane sketch with a `centerline` but no `center.z` triggers a lint finding — the centerline will default to part Z=0, which is almost never what you want for a revolved feature. Run `--lint` to catch this.

### `sketch_rectangle_on_face`

Creates a rectangle on the face of an earlier extrusion.

```json
{
  "type": "sketch_rectangle_on_face",
  "name": "SK_Layer",
  "of_feature": "Extrude_Box",
  "face": "+z",
  "width": 15.0,
  "height": 10.0,
  "center": {"u": 0.0, "v": 0.0}
}
```

<!-- BEGIN GENERATED: sketch_rectangle_on_face -->
| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `type` | const `"sketch_rectangle_on_face"` | yes |  | Rectangular profile sketch on an existing feature's orthogonal face. |
| `name` | string | yes |  | Unique identifier for this feature within the spec. Later features refer back to it by name (e.g. via `sketch`, `of_feature`, `seed`, or `target_ref.of_feature`). |
| `of_feature` | string | yes |  | Name of an earlier extrusion feature. |
| `face` | enum (`"+x"` / `"-x"` / `"+y"` / `"-y"` / `"+z"` / `"-z"`) | yes |  | Outward normal direction of the face in the feature's local frame. |
| `width` | length | yes |  | Rectangle width (mm). |
| `height` | length | yes |  | Rectangle height (mm). |
| `center` | object | no |  | In-face center offset (mm) from the FACE SKETCH ORIGIN, which empirically is the projection of the part origin onto the face (NOT the face's geometric center). For a feature whose base sketch was a center-rectangle on origin these happen to coincide; for one shifted off origin (e.g. TensionBracket cap with Y span [0,15]) they don't, and child sketches need a u/v offset to land on the bracket centroid instead of the part origin. Default (0, 0). |
| `relations` | array | no |  | Geometric relations between sketch entities. Applied after geometry draw via ISketchManager.SketchAddConstraints. ⚠️ Token names are seat-gated (W21 radians lesson). |
<!-- END GENERATED -->

**Face-sketch origin gotcha:** The origin is the part-origin *projection* onto the face, NOT the face's geometric center. If the parent extrusion is centered on the part origin (like a `CreateCenterRectangle` at `(0,0)`), these coincide. If the parent is shifted, you need a `center` offset. See [known_limitations.md](known_limitations.md) section 1.

**Side-face limitation:** All six faces are supported, but the side faces `+x`/`-x`/`+y`/`-y` require the parent extrusion to be built on the **Front Plane** (`±z` axis) with a **rectangular** profile. See [known_limitations.md](known_limitations.md) section 2.

### `sketch_circle_on_plane`

Creates a circle on one of the three default reference planes.

```json
{
  "type": "sketch_circle_on_plane",
  "name": "SK_Bore",
  "plane": "Front",
  "diameter": 12.0,
  "center": {"x": 0.0, "y": 0.0}
}
```

<!-- BEGIN GENERATED: sketch_circle_on_plane -->
| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `type` | const `"sketch_circle_on_plane"` | yes |  | Circular profile sketch on a default reference plane. |
| `name` | string | yes |  | Unique identifier for this feature within the spec. Later features refer back to it by name (e.g. via `sketch`, `of_feature`, `seed`, or `target_ref.of_feature`). |
| `plane` | enum (`"Front"` / `"Top"` / `"Right"`) | yes |  | Default reference plane to host the sketch. |
| `diameter` | length | yes |  | Circle diameter (mm). |
| `center` | object | no |  | Sketch-local center (mm). Default (0, 0, 0). See SKETCH_RECTANGLE_ON_PLANE for when the optional z is needed (Top Plane sketches positioned at part-Z != 0). |
| `centerline` | object | no |  | Construction line embedded in the sketch. Consumed by `revolve_boss` as the axis of revolution (SW auto-detects). No driving dim; coordinates are literal mm. |
| `relations` | array | no |  | Geometric relations between sketch entities. Applied after geometry draw via ISketchManager.SketchAddConstraints. ⚠️ Token names are seat-gated (W21 radians lesson). |
<!-- END GENERATED -->

### `sketch_circle_on_face`

Creates a circle on the face of an earlier extrusion.

```json
{
  "type": "sketch_circle_on_face",
  "name": "SK_Hole",
  "of_feature": "Extrude_Box",
  "face": "-z",
  "diameter": 5.0,
  "center": {"u": 0.0, "v": 0.0}
}
```

<!-- BEGIN GENERATED: sketch_circle_on_face -->
| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `type` | const `"sketch_circle_on_face"` | yes |  | Circular profile sketch on an existing feature's face. |
| `name` | string | yes |  | Unique identifier for this feature within the spec. Later features refer back to it by name (e.g. via `sketch`, `of_feature`, `seed`, or `target_ref.of_feature`). |
| `of_feature` | string | yes |  | Name of an earlier extrusion feature. |
| `face` | enum (`"+x"` / `"-x"` / `"+y"` / `"-y"` / `"+z"` / `"-z"`) | yes |  | Outward normal direction of the face in the feature's local frame. |
| `diameter` | length | yes |  | Circle diameter (mm). |
| `center` | object | no |  | In-face center offset (mm) from the face SKETCH ORIGIN, which is the projection of the part origin onto the face (NOT the face's geometric center -- see SKETCH_RECTANGLE_ON_FACE). Default (0, 0). |
| `relations` | array | no |  | Geometric relations between sketch entities. Applied after geometry draw via ISketchManager.SketchAddConstraints. ⚠️ Token names are seat-gated (W21 radians lesson). |
<!-- END GENERATED -->

Same face-sketch-origin gotcha as `sketch_rectangle_on_face`.

### `sketch_circles_on_face`

Creates multiple circles in a single sketch on the face of an earlier extrusion. Used for hole patterns.

```json
{
  "type": "sketch_circles_on_face",
  "name": "SK_HolePattern",
  "of_feature": "Extrude_Plate",
  "face": "+z",
  "circles": [
    {"u": 12.5, "v": 0.0, "diameter": 3.2},
    {"u": -12.5, "v": 0.0, "diameter": 3.2}
  ]
}
```

<!-- BEGIN GENERATED: sketch_circles_on_face -->
| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `type` | const `"sketch_circles_on_face"` | yes |  | Multiple circles in one sketch on a face (e.g. a hole pattern). |
| `name` | string | yes |  | Unique identifier for this feature within the spec. Later features refer back to it by name (e.g. via `sketch`, `of_feature`, `seed`, or `target_ref.of_feature`). |
| `of_feature` | string | yes |  | Name of an earlier extrusion feature. |
| `face` | enum (`"+x"` / `"-x"` / `"+y"` / `"-y"` / `"+z"` / `"-z"`) | yes |  | Outward normal direction of the face in the feature's local frame. |
| `circles` | array (min 1) | yes |  | One or more circles sketched together on the face, each with its own center offset and diameter. |
| `relations` | array | no |  | Geometric relations between sketch entities. Applied after geometry draw via ISketchManager.SketchAddConstraints. ⚠️ Token names are seat-gated (W21 radians lesson). |
<!-- END GENERATED -->

Circle positions are literal mm only — no `{rhs}` on `u` or `v`.

## General-purpose sketch primitives

Seven general-purpose sketch entities that host on one of the three default
reference planes (Front / Top / Right). All seven are **seat-validated on
SW 2024 (rev 32.1.0, 2026-05-31)** — each builds literal-size geometry via its
proven `ISketchManager.Create*` (or `IModelDoc2.InsertSketchText`) call. The
`x`/`y` coordinates are interpreted **sketch-local** (the plane's own 2D frame),
so no part-frame projection is applied. `LENGTH_SCHEMA` fields accept a plain
millimetre number or a `{rhs: "..."}` object, but **parametric dimensioning is
not yet wired** for these primitives (geometry is always built at literal size,
as in `--no-dim`). The `construction` flag **is** applied on line/arc/spline/
polygon/ellipse, and text `height`/`font` **are** applied. Three things have no
out-of-process API on this seat and are therefore **rejected at validation**
(never silently faked): spline `closed` (a point-based periodic C2 spline; only
a C0 cusp is achievable, so it is refused), `construction` on **slot** (the
`CreateSketchSlot` return is read-only) and on **text** (text is not a segment),
and text `angle_deg` (no angle on `InsertSketchText`/`ITextFormat`).

### `sketch_line`

A single line segment.

```json
{
  "type": "sketch_line",
  "name": "SK_Line_Diagonal",
  "plane": "Front",
  "start": {"x": 0.0, "y": 0.0},
  "end":   {"x": 20.0, "y": 20.0},
  "construction": false
}
```

<!-- BEGIN GENERATED: sketch_line -->
| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `type` | const `"sketch_line"` | yes |  | Single line segment on a reference plane (start → end). |
| `name` | string | yes |  | Unique identifier for this feature within the spec. Later features refer back to it by name (e.g. via `sketch`, `of_feature`, `seed`, or `target_ref.of_feature`). |
| `plane` | enum (`"Front"` / `"Top"` / `"Right"`) | yes |  | Default reference plane to host the sketch. |
| `start` | object | yes |  | Line start point (sketch-local mm). |
| `end` | object | yes |  | Line end point (sketch-local mm). |
| `construction` | boolean | no | `false` | If true, mark the segment as a construction (centerline) entity. |
| `relations` | array | no |  | Geometric relations between sketch entities. Applied after geometry draw via ISketchManager.SketchAddConstraints. ⚠️ Token names are seat-gated (W21 radians lesson). |
<!-- END GENERATED -->

### `sketch_arc`

A circular arc (center + start + end).

```json
{
  "type": "sketch_arc",
  "name": "SK_Arc_Quarter",
  "plane": "Front",
  "center": {"x": 30.0, "y": 0.0},
  "start":  {"x": 40.0, "y": 0.0},
  "end":    {"x": 30.0, "y": 10.0},
  "direction": "ccw"
}
```

<!-- BEGIN GENERATED: sketch_arc -->
| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `type` | const `"sketch_arc"` | yes |  | Circular arc on a reference plane (center + start + end). |
| `name` | string | yes |  | Unique identifier for this feature within the spec. Later features refer back to it by name (e.g. via `sketch`, `of_feature`, `seed`, or `target_ref.of_feature`). |
| `plane` | enum (`"Front"` / `"Top"` / `"Right"`) | yes |  | Default reference plane to host the sketch. |
| `center` | object | yes |  | Arc center point (sketch-local mm). |
| `start` | object | yes |  | Arc start point (sketch-local mm). |
| `end` | object | yes |  | Arc end point (sketch-local mm). |
| `direction` | enum (`"cw"` / `"ccw"`) | no | `"ccw"` | Arc direction from start to end about the center. |
| `construction` | boolean | no | `false` | If true, mark the arc as a construction entity. |
| `relations` | array | no |  | Geometric relations between sketch entities. Applied after geometry draw via ISketchManager.SketchAddConstraints. ⚠️ Token names are seat-gated (W21 radians lesson). |
<!-- END GENERATED -->

### `sketch_spline`

A freeform spline through a sequence of control points (min 2).

```json
{
  "type": "sketch_spline",
  "name": "SK_Spline_Curve",
  "plane": "Front",
  "points": [
    {"x": 0.0, "y": 30.0},
    {"x": 10.0, "y": 35.0},
    {"x": 20.0, "y": 30.0}
  ],
  "construction": false
}
```

<!-- BEGIN GENERATED: sketch_spline -->
| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `type` | const `"sketch_spline"` | yes |  | Freeform spline through a sequence of control points. |
| `name` | string | yes |  | Unique identifier for this feature within the spec. Later features refer back to it by name (e.g. via `sketch`, `of_feature`, `seed`, or `target_ref.of_feature`). |
| `plane` | enum (`"Front"` / `"Top"` / `"Right"`) | yes |  | Default reference plane to host the sketch. |
| `points` | array (min 2) | yes |  | Control points in sketch-local coordinates (mm). At least 2 required. 🔴 SEAT (P1.7-seat/W0): the live call packs these into a SAFEARRAY of doubles for ISketchManager.CreateSpline2 — the exact marshaling shape ([x0,y0,x1,y1,...] vs [x0,y0,z0,x1,y1,z1,...]) and the b3D flag autoselect rule must be confirmed on the seat. |
| `construction` | boolean | no | `false` | If true, mark the spline as a construction entity. |
| `relations` | array | no |  | Geometric relations between sketch entities. Applied after geometry draw via ISketchManager.SketchAddConstraints. ⚠️ Token names are seat-gated (W21 radians lesson). |
<!-- END GENERATED -->

> **✅ Seat-proven (2026-05-31):** `ISketchManager.CreateSpline2(pointBuffer, b3D=False)` where `pointBuffer` is a `VT_ARRAY|VT_R8` VARIANT SAFEARRAY of flat `x,y,z` triples (z=0 on a plane). **Open splines only.** There is no `closed` field: a point-based periodic (C2) closed spline has no out-of-process API on this seat — `ISketchSpline.MakeClosed` and `ISketchManager.CreateClosedSpline` do not exist (the live object answered `GetIDsOfNames("MakeClosed")` with `DISP_E_UNKNOWNNAME`, and a full typelib scan found neither), and appending the first point yields a C0 cusp, not a periodic spline. A `closed` request is rejected at validation rather than faked.

### `sketch_slot`

A rounded-end (arc) slot on a reference plane. SOLIDWORKS slots are inherently
rounded-ended — for a flat-ended rectangular slot use `sketch_rectangle_on_plane`.

```json
{
  "type": "sketch_slot",
  "name": "SK_Slot_Horizontal",
  "plane": "Front",
  "center":    {"x": 30.0, "y": 30.0},
  "width":     6.0,
  "length":   20.0,
  "slot_type": "arc",
  "angle_deg":  0.0
}
```

<!-- BEGIN GENERATED: sketch_slot -->
| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `type` | const `"sketch_slot"` | yes |  | Rectangular or arc-ended slot on a reference plane. |
| `name` | string | yes |  | Unique identifier for this feature within the spec. Later features refer back to it by name (e.g. via `sketch`, `of_feature`, `seed`, or `target_ref.of_feature`). |
| `plane` | enum (`"Front"` / `"Top"` / `"Right"`) | yes |  | Default reference plane to host the sketch. |
| `center` | object | yes |  | Slot center point (sketch-local mm). |
| `width` | length | yes |  | Slot width (mm) -- the diameter of the two rounded end caps. |
| `length` | length | yes |  | Slot length (mm) -- the center-to-center distance between the two rounded ends, along the slot's major axis. |
| `slot_type` | enum (`"arc"`) | no | `"arc"` | End shape of the slot. Only 'arc' (rounded ends) is supported — the SOLIDWORKS CreateSketchSlot kernel call produces inherently rounded slots (there is no flat-ended creation type). For a flat-ended rectangular slot, use sketch_rectangle_on_plane instead. |
| `angle_deg` | number | no | `0.0` | Rotation of the slot's major axis from the sketch X axis (degrees). |
| `relations` | array | no |  | Geometric relations between sketch entities. Applied after geometry draw via ISketchManager.SketchAddConstraints. ⚠️ Token names are seat-gated (W21 radians lesson). |
<!-- END GENERATED -->

> **No `construction` field.** `CreateSketchSlot` returns a read-only slot object whose `ConstructionGeometry` cannot be set via the API, so a `construction` request on a slot is rejected at validation rather than faked.

### `sketch_polygon`

A regular N-sided polygon.

```json
{
  "type": "sketch_polygon",
  "name": "SK_Polygon_Hex",
  "plane": "Front",
  "center":    {"x": 50.0, "y": 30.0},
  "sides":     6,
  "radius":    8.0,
  "inscribed": true,
  "angle_deg":  0.0
}
```

<!-- BEGIN GENERATED: sketch_polygon -->
| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `type` | const `"sketch_polygon"` | yes |  | Regular N-sided polygon on a reference plane. |
| `name` | string | yes |  | Unique identifier for this feature within the spec. Later features refer back to it by name (e.g. via `sketch`, `of_feature`, `seed`, or `target_ref.of_feature`). |
| `plane` | enum (`"Front"` / `"Top"` / `"Right"`) | yes |  | Default reference plane to host the sketch. |
| `center` | object | yes |  | Polygon center point (sketch-local mm). |
| `sides` | integer (≥ 3) | yes |  | Number of polygon sides (3..40). |
| `radius` | length | yes |  | Polygon radius (mm); see `inscribed` for whether this is the apothem (inscribed) or circumscribed radius. |
| `inscribed` | boolean | no | `true` | If true, `radius` is the inscribed (apothem) radius — polygon edges are tangent to the circle. If false, `radius` is the circumscribed radius — polygon vertices lie on the circle. |
| `angle_deg` | number | no | `0.0` | Rotation of the polygon's first vertex from the sketch X axis (degrees). |
| `construction` | boolean | no | `false` | If true, mark the polygon as a construction entity. |
| `relations` | array | no |  | Geometric relations between sketch entities. Applied after geometry draw via ISketchManager.SketchAddConstraints. ⚠️ Token names are seat-gated (W21 radians lesson). |
<!-- END GENERATED -->

### `sketch_ellipse`

An ellipse on a reference plane.

```json
{
  "type": "sketch_ellipse",
  "name": "SK_Ellipse_Oval",
  "plane": "Front",
  "center":       {"x": 70.0, "y": 30.0},
  "major_radius": 10.0,
  "minor_radius":  5.0,
  "angle_deg":     0.0
}
```

<!-- BEGIN GENERATED: sketch_ellipse -->
| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `type` | const `"sketch_ellipse"` | yes |  | Ellipse with major/minor radii on a reference plane. |
| `name` | string | yes |  | Unique identifier for this feature within the spec. Later features refer back to it by name (e.g. via `sketch`, `of_feature`, `seed`, or `target_ref.of_feature`). |
| `plane` | enum (`"Front"` / `"Top"` / `"Right"`) | yes |  | Default reference plane to host the sketch. |
| `center` | object | yes |  | Ellipse center point (sketch-local mm). |
| `major_radius` | length | yes |  | Semi-major axis length (mm). |
| `minor_radius` | length | yes |  | Semi-minor axis length (mm). |
| `angle_deg` | number | no | `0.0` | Rotation of the major axis from the sketch X axis (degrees). |
| `construction` | boolean | no | `false` | If true, mark the ellipse as a construction entity. |
| `relations` | array | no |  | Geometric relations between sketch entities. Applied after geometry draw via ISketchManager.SketchAddConstraints. ⚠️ Token names are seat-gated (W21 radians lesson). |
<!-- END GENERATED -->

### `sketch_text`

A plain-text annotation sketch.

```json
{
  "type": "sketch_text",
  "name": "SK_Text_Label",
  "plane": "Front",
  "position": {"x": 0.0, "y": 50.0},
  "content":  "ai-sw-bridge",
  "height":    3.0,
  "font":      "Arial"
}
```

<!-- BEGIN GENERATED: sketch_text -->
| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `type` | const `"sketch_text"` | yes |  | Plain-text annotation sketch on a reference plane. |
| `name` | string | yes |  | Unique identifier for this feature within the spec. Later features refer back to it by name (e.g. via `sketch`, `of_feature`, `seed`, or `target_ref.of_feature`). |
| `plane` | enum (`"Front"` / `"Top"` / `"Right"`) | yes |  | Default reference plane to host the sketch. |
| `position` | object | yes |  | Text insertion point (sketch-local mm). |
| `content` | string | yes |  | Text content. Plain ASCII; no rich formatting. |
| `height` | length | yes |  | Text cap height (mm), applied as CharHeight. |
| `font` | string | no |  | Font family name (e.g. 'Arial'). Applied via the inserted ISketchText's text format (GetTextFormat -> TypeFaceName -> SetTextFormat); `height` sets CharHeight in the same call. |
| `relations` | array | no |  | Geometric relations between sketch entities. Applied after geometry draw via ISketchManager.SketchAddConstraints. ⚠️ Token names are seat-gated (W21 radians lesson). |
<!-- END GENERATED -->

> **✅ Seat-proven (2026-05-31):** Text is a document-level op — `IModelDoc2.InsertSketchText(Ptx, Pty, Ptz, Text, Alignment, FlipDirection, HorizontalMirror, WidthFactor, SpaceBetweenChars)` (NOT on `ISketchManager`; the trailing args are ints and there is **no angle parameter**). `height` (CharHeight, metres) and `font` (TypeFaceName) are applied through the returned `ISketchText` via the early-bind hatch: `typed(raw, "ISketchText").GetTextFormat()` → mutate → `SetTextFormat(0, tf)` (late binding alone hits "Member not found" on `GetTextFormat`). There is **no `angle_deg` or `construction` field**: text baseline rotation has no out-of-process API on this seat (`InsertSketchText`/`ITextFormat` expose no angle), and text is not a sketch segment — both are rejected at validation rather than faked.

### `sketch_3d_sketch`

A 3D polyline sketch through a sequence of 3D points. Unlike on-plane sketch primitives, a 3D sketch is **not** constrained to a reference plane — it uses `ISketchManager.Insert3DSketch(True)` (one BOOL `UpdateEditRebuild` arg; parameterless raises 'Parameter not optional') to enter/exit sketch mode, and `CreateLine` carries real X/Y/Z coordinates. This is the prerequisite that unblocks weldments and swept/lofted surfaces.

```json
{
  "type": "sketch_3d_sketch",
  "name": "SK3D_NonPlanarPath",
  "points": [
    {"x": 0.0,   "y": 0.0,  "z": 0.0},
    {"x": 100.0, "y": 0.0,  "z": 0.0},
    {"x": 100.0, "y": 50.0, "z": 30.0},
    {"x": 0.0,   "y": 50.0, "z": 60.0}
  ]
}
```

<!-- BEGIN GENERATED: sketch_3d_sketch -->
| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `type` | const `"sketch_3d_sketch"` | yes |  | 3D polyline sketch through a sequence of 3D points (non-planar path). |
| `name` | string | yes |  | Unique identifier for this feature within the spec. Later features refer back to it by name (e.g. via `sketch`, `of_feature`, `seed`, or `target_ref.of_feature`). |
| `points` | array (min 2) | yes |  | Ordered 3D control points of the polyline. Consecutive points are connected by line segments. All three axes (x, y, z) are required — use a non-zero z extent to create a non-planar path (weldment / sweep prerequisite). |
<!-- END GENERATED -->

> **✅ Seat-proven:** `Insert3DSketch(True)` + `CreateLine(x1,y1,z1, x2,y2,z2)` — verified on SW 2024 SP1 (3 segments, 0.06 m Z-extent). Same toggle opens and closes the 3D sketch.

### `sketch_polyline_on_plane`

A composite closed polyline — several connected line segments in **one** plane sketch — forming a closed profile a boss/cut extrude can consume. This is the primitive for non-axis-aligned closed profiles (e.g. the 45° parallelograms of SM-HW-S1b-009 BeltEndChute) that `sketch_rectangle_on_plane` (axis-aligned) and `sketch_polygon` (regular N-gon) cannot express, and that `sketch_line` cannot either (it closes its sketch after a single segment). Coordinates are sketch-local 2D (mm), same convention as `sketch_line`.

Because it lives on a standard reference plane, a child extrude runs **along that plane's normal** (a Top-plane profile extrudes ±Y, mid-plane works). This is the key difference from `sketch_3d_sketch`, whose extrude only ever runs +Z regardless of the loop's own plane (verified live 2026-08-05).

```json
{
  "type": "sketch_polyline_on_plane",
  "name": "SK_FloorParallelogram",
  "plane": "Top",
  "points": [
    {"x": 0.0,    "y": 0.0},
    {"x": 8.0,    "y": 8.0},
    {"x": 6.586,  "y": 9.414},
    {"x": -1.414, "y": 1.414}
  ]
}
```

<!-- BEGIN GENERATED: sketch_polyline_on_plane -->
| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `type` | const `"sketch_polyline_on_plane"` | yes |  | Composite closed polyline (multi-segment profile) on a default reference plane; extrudes along the plane normal. |
| `name` | string | yes |  | Unique identifier for this feature within the spec. Later features refer back to it by name (e.g. via `sketch`, `of_feature`, `seed`, or `target_ref.of_feature`). |
| `plane` | enum (`"Front"` / `"Top"` / `"Right"`) | yes |  | Default reference plane to host the sketch. |
| `points` | array (min 3) | yes |  | Ordered vertices of the profile in sketch-local 2D (mm). Consecutive points are joined by line segments; when `closed` is true (default) a final segment joins the last point back to the first. At least 3 points for a closed profile. |
| `closed` | boolean | no | `true` | If true (default) auto-close the loop (last→first) so the profile is extrudable. Set false for an open polyline. |
| `construction` | boolean | no | `false` | If true, mark the segments as construction entities. |
<!-- END GENERATED -->

> **✅ Seat-proven:** multi-segment `CreateLine` on a Top-plane 2D sketch, extruded mid-plane 40 mm → ±Y — verified on SW 2024 SP1 (spike_polyline_on_plane, 2026-08-05).

## Extrude primitives

### `boss_extrude_blind`

Adds material by extruding a sketch in the normal direction.

```json
{
  "type": "boss_extrude_blind",
  "name": "Extrude_Box",
  "sketch": "SK_Box",
  "depth": 10.0,
  "flip": false
}
```

<!-- BEGIN GENERATED: boss_extrude_blind -->
| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `type` | const `"boss_extrude_blind"` | yes |  | Blind boss extrusion of a sketch to a given depth. |
| `name` | string | yes |  | Unique identifier for this feature within the spec. Later features refer back to it by name (e.g. via `sketch`, `of_feature`, `seed`, or `target_ref.of_feature`). |
| `sketch` | string | yes |  | Name of an earlier sketch feature to extrude. |
| `depth` | length | yes |  | Extrusion depth (mm). |
| `flip` | boolean | no | `false` | Extrude in -normal instead of +normal direction. |
| `merge` | boolean | no | `true` | true (default) = fuse this boss into the existing solid body it overlaps (modeling-time boolean UNION). false = keep it as a separate solid body (multi-body). Express unions HERE, at the extrusion phase: there is no post-hoc 'combine' feature. |
| `start_offset` | length | no |  | Optional. Begin the extrude this many mm from the sketch plane (SW start condition swStartOffset) instead of on it; the blind `depth` is then measured from that offset start. OMIT for the normal start-on-sketch-plane behaviour (byte-identical to before). Lets a boss build offset from a standard plane -- e.g. a side plate sketched on Top Plane but extruded to begin at part-Y=+40. Pair with `flip_start_offset` to choose the offset direction. |
| `flip_start_offset` | boolean | no | `false` | Offset toward -normal instead of +normal (SW FlipStartOffset). Only meaningful when `start_offset` is set. |
<!-- END GENERATED -->

### `boss_extrude_midplane`

Adds material extruded symmetrically about the sketch plane — `depth/2` of
material each side.

```json
{
  "type": "boss_extrude_midplane",
  "name": "MidBoss",
  "sketch": "SK_Mid",
  "depth": 16.0
}
```

<!-- BEGIN GENERATED: boss_extrude_midplane -->
| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `type` | const `"boss_extrude_midplane"` | yes |  | Mid-plane boss extrusion: adds `depth` of material centred on the sketch plane (depth/2 each side). |
| `name` | string | yes |  | Unique identifier for this feature within the spec. Later features refer back to it by name (e.g. via `sketch`, `of_feature`, `seed`, or `target_ref.of_feature`). |
| `sketch` | string | yes |  | Name of an earlier sketch feature to extrude. |
| `depth` | length | yes |  | Total extrusion depth (mm), centred on the sketch plane (depth/2 of material added each side). |
| `flip` | boolean | no | `false` | Reserved; a mid-plane extrude is symmetric about the sketch plane, so the direction is immaterial. |
| `merge` | boolean | no | `true` | true (default) = fuse this boss into the existing solid body it overlaps (modeling-time boolean UNION). false = keep it as a separate solid body (multi-body). Express unions HERE, at the extrusion phase: there is no post-hoc 'combine' feature. |
<!-- END GENERATED -->

### `boss_extrude_through_all`

Adds material until it terminates against existing geometry. Requires a prior
solid body — SW errors on a through-all boss with no existing solid (the lint
warns if none precedes it).

```json
{
  "type": "boss_extrude_through_all",
  "name": "ThruBoss",
  "sketch": "SK_Thru",
  "flip": false
}
```

<!-- BEGIN GENERATED: boss_extrude_through_all -->
| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `type` | const `"boss_extrude_through_all"` | yes |  | Through-all boss extrusion: adds material until it terminates against existing geometry. Requires a prior solid body (SW errors without one). |
| `name` | string | yes |  | Unique identifier for this feature within the spec. Later features refer back to it by name (e.g. via `sketch`, `of_feature`, `seed`, or `target_ref.of_feature`). |
| `sketch` | string | yes |  | Name of an earlier sketch feature to extrude. |
| `flip` | boolean | no | `false` | Extrude in -normal instead of +normal direction. |
| `merge` | boolean | no | `true` | true (default) = fuse this boss into the existing solid body it overlaps (modeling-time boolean UNION). false = keep it as a separate solid body (multi-body). Express unions HERE, at the extrusion phase: there is no post-hoc 'combine' feature. |
<!-- END GENERATED -->

No `depth` — the boss runs until it terminates against existing geometry.

### `boss_extrude_two_direction`

Adds material in both normal directions from the sketch plane: `depth` into
+normal and `depth2` into -normal.

```json
{
  "type": "boss_extrude_two_direction",
  "name": "TwoDirBoss",
  "sketch": "SK_Two",
  "depth": 12.0,
  "depth2": 6.0
}
```

<!-- BEGIN GENERATED: boss_extrude_two_direction -->
| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `type` | const `"boss_extrude_two_direction"` | yes |  | Two-direction boss: `depth` into +normal and `depth2` into -normal from the sketch plane. |
| `name` | string | yes |  | Unique identifier for this feature within the spec. Later features refer back to it by name (e.g. via `sketch`, `of_feature`, `seed`, or `target_ref.of_feature`). |
| `sketch` | string | yes |  | Name of an earlier sketch feature to extrude. |
| `depth` | length | yes |  | Extrusion depth into +normal (mm). |
| `depth2` | length | yes |  | Extrusion depth into -normal (mm). |
| `flip` | boolean | no | `false` | Swap which side `depth` (+normal) vs `depth2` (-normal) extrudes into. |
| `merge` | boolean | no | `true` | true (default) = fuse this boss into the existing solid body it overlaps (modeling-time boolean UNION). false = keep it as a separate solid body (multi-body). Express unions HERE, at the extrusion phase: there is no post-hoc 'combine' feature. |
<!-- END GENERATED -->

### `boss_extrude_up_to_surface`

Adds material until the boss terminates on a **durable reference surface** (a
face of an earlier extrusion) — no fixed depth.

```json
{
  "type": "boss_extrude_up_to_surface",
  "name": "PostBoss",
  "sketch": "SK_Post",
  "target_ref": { "of_feature": "EX_Wall", "face": "+z" }
}
```

<!-- BEGIN GENERATED: boss_extrude_up_to_surface -->
| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `type` | const `"boss_extrude_up_to_surface"` | yes |  | Up-to-surface boss: extrudes the sketch until it terminates on `target_ref` (a face of an earlier extrusion). No `depth`. |
| `name` | string | yes |  | Unique identifier for this feature within the spec. Later features refer back to it by name (e.g. via `sketch`, `of_feature`, `seed`, or `target_ref.of_feature`). |
| `sketch` | string | yes |  | Name of an earlier sketch to extrude. |
| `target_ref` | object | yes |  | Durable reference to the up-to termination surface (a face of an earlier extrusion). Required — the boss has no fixed depth. |
| `flip` | boolean | no | `false` | Extrude in -normal instead of +normal direction. |
| `merge` | boolean | no | `true` | true (default) = fuse this boss into the existing solid body it overlaps (modeling-time boolean UNION). false = keep it as a separate solid body (multi-body). Express unions HERE, at the extrusion phase: there is no post-hoc 'combine' feature. |
<!-- END GENERATED -->

No `depth` — the boss runs until it terminates on `target_ref`.

> **OOP end-condition trap (seat-proven):** the handler hardcodes
> `T1 = swEndCondUpToSurface = 4`. The "modern" `swEndCondUpToSelection = 10`
> that the SOLIDWORKS API docs recommend **silently no-ops out-of-process** — the
> formally-deprecated `UpToSurface` is the only functional COM path. Do not
> "modernise" the constant. See `docs/DEFERRED.md`.

### `cut_extrude_through_all`

Removes material through the entire part in both directions.

A one-directional cut sketched on a **reference plane** (any sketch type
that takes a `plane` field, not just the `*_on_plane` three) sweeps
**+normal** (the builder sets FeatureCut4 `Dir=True`). A **face-sketched** cut
keeps `Dir=False` and sweeps **−normal** (into the body). See
[coordinate_conventions.md](coordinate_conventions.md) §4.

```json
{
  "type": "cut_extrude_through_all",
  "name": "Cut_Hole",
  "sketch": "SK_Hole",
  "flip": false
}
```

<!-- BEGIN GENERATED: cut_extrude_through_all -->
| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `type` | const `"cut_extrude_through_all"` | yes |  | Through-all cut extrusion along a sketch. |
| `name` | string | yes |  | Unique identifier for this feature within the spec. Later features refer back to it by name (e.g. via `sketch`, `of_feature`, `seed`, or `target_ref.of_feature`). |
| `sketch` | string | yes |  | Name of an earlier sketch to cut along. |
| `flip` | boolean | no | `false` | Bound to FeatureCut4 arg 2 (`Flip`); proven not to reverse cut direction (issue #40, seat-proven 2026-09-05). The builder sets the real +normal/-normal sweep direction automatically depending on whether the sketch is plane- or face-hosted. |
<!-- END GENERATED -->

No `depth` — cuts go through everything.

### `simple_hole`

Drills a hole on a face of an earlier extrusion. Combines sketch + cut into a single feature.

```json
{
  "type": "simple_hole",
  "name": "Hole_Mount",
  "of_feature": "Extrude_Plate",
  "face": "+z",
  "diameter": 3.2,
  "end_condition": "through_all"
}
```

<!-- BEGIN GENERATED: simple_hole -->
| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `type` | const `"simple_hole"` | yes |  | Single straight-bore hole drilled into a face (blind or through-all). |
| `name` | string | yes |  | Unique identifier for this feature within the spec. Later features refer back to it by name (e.g. via `sketch`, `of_feature`, `seed`, or `target_ref.of_feature`). |
| `of_feature` | string | yes |  | Name of an earlier extrusion feature. |
| `face` | enum (`"+x"` / `"-x"` / `"+y"` / `"-y"` / `"+z"` / `"-z"`) | yes |  | Outward normal of the face the hole drills into. |
| `center` | object | no |  | In-face center (mm) of the hole from the face SKETCH ORIGIN (= part-origin projection onto the face plane, NOT the face centroid -- see SKETCH_CIRCLE_ON_FACE for the gotcha). Default (0, 0). |
| `diameter` | length | yes |  | Hole diameter (mm). |
| `end_condition` | enum (`"blind"` / `"through_all"`) | no | `"blind"` | Hole depth termination. 'blind' uses `depth`; 'through_all' drills all the way through and ignores `depth`. |
| `depth` | length | no |  | Hole depth (mm). Required when `end_condition` is 'blind'; ignored (and may be omitted) for 'through_all'. |
<!-- END GENERATED -->

Same face-sketch-origin gotcha as `sketch_rectangle_on_face` — `center` offsets from the part-origin projection, not the face centroid.

### `cut_extrude_blind`

Removes material to a specified depth.

A one-directional cut sketched on a **reference plane** (any sketch type
that takes a `plane` field, not just the `*_on_plane` three) sweeps
**+normal** (the builder sets FeatureCut4 `Dir=True`). A **face-sketched** cut
keeps `Dir=False` and sweeps **−normal** (into the body). See
[coordinate_conventions.md](coordinate_conventions.md) §4.

```json
{
  "type": "cut_extrude_blind",
  "name": "Cut_Pocket",
  "sketch": "SK_Pocket",
  "depth": 2.0,
  "flip": false
}
```

<!-- BEGIN GENERATED: cut_extrude_blind -->
| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `type` | const `"cut_extrude_blind"` | yes |  | Blind cut extrusion of a sketch to a given depth. |
| `name` | string | yes |  | Unique identifier for this feature within the spec. Later features refer back to it by name (e.g. via `sketch`, `of_feature`, `seed`, or `target_ref.of_feature`). |
| `sketch` | string | yes |  | Name of an earlier sketch feature to cut along. |
| `depth` | length | yes |  | Cut depth (mm). |
| `flip` | boolean | no | `false` | Bound to FeatureCut4 arg 2 (`Flip`); proven not to reverse cut direction (issue #40, seat-proven 2026-09-05). The builder sets the real +normal/-normal sweep direction automatically depending on whether the sketch is plane- or face-hosted. |
<!-- END GENERATED -->

### `cut_extrude_midplane`

Removes material symmetrically about the sketch plane — `depth/2` is cut into each side.

A one-directional cut sketched on a **reference plane** (any sketch type
that takes a `plane` field, not just the `*_on_plane` three) sweeps
**+normal** (the builder sets FeatureCut4 `Dir=True`). A **face-sketched** cut
keeps `Dir=False` and sweeps **−normal** (into the body). Mid-plane still
straddles the sketch, so both sides are cut. See
[coordinate_conventions.md](coordinate_conventions.md) §4.

```json
{
  "type": "cut_extrude_midplane",
  "name": "Cut_Slot",
  "sketch": "SK_Slot",
  "depth": 10.0,
  "flip": false
}
```

<!-- BEGIN GENERATED: cut_extrude_midplane -->
| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `type` | const `"cut_extrude_midplane"` | yes |  | Mid-plane cut extrusion: removes `depth` of material centred on the sketch plane (depth/2 each side). |
| `name` | string | yes |  | Unique identifier for this feature within the spec. Later features refer back to it by name (e.g. via `sketch`, `of_feature`, `seed`, or `target_ref.of_feature`). |
| `sketch` | string | yes |  | Name of an earlier sketch feature to cut along. |
| `depth` | length | yes |  | Total cut depth (mm), centred on the sketch plane (depth/2 removed each side). |
| `flip` | boolean | no | `false` | Bound to FeatureCut4 arg 2 (`Flip`); proven not to reverse cut direction (issue #40, seat-proven 2026-09-05). The builder sets the real +normal/-normal sweep direction automatically depending on whether the sketch is plane- or face-hosted. |
<!-- END GENERATED -->

### `cut_extrude_two_direction`

Removes material in **both** directions from the sketch plane: `depth` into the +normal side and `depth2` into the -normal side (both blind).

```json
{
  "type": "cut_extrude_two_direction",
  "name": "Cut_Through_Pocket",
  "sketch": "SK_Pocket",
  "depth": 6.0,
  "depth2": 4.0,
  "flip": false
}
```

<!-- BEGIN GENERATED: cut_extrude_two_direction -->
| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `type` | const `"cut_extrude_two_direction"` | yes |  | Two-direction blind cut: `depth` into +normal and `depth2` into -normal from the sketch plane. |
| `name` | string | yes |  | Unique identifier for this feature within the spec. Later features refer back to it by name (e.g. via `sketch`, `of_feature`, `seed`, or `target_ref.of_feature`). |
| `sketch` | string | yes |  | Name of an earlier sketch feature to cut along. |
| `depth` | length | yes |  | Cut depth into the +normal direction (mm). |
| `depth2` | length | yes |  | Cut depth into the -normal direction (mm). |
| `flip` | boolean | no | `false` | Bound to FeatureCut4 arg 2 (`Flip`). The issue #40 seat proof (2026-09-05) only covers one-directional cuts, so this field's effect on a two-direction cut is UNVERIFIED -- `depth`/`depth2` are what determine which side is removed, not `flip`. |
<!-- END GENERATED -->

## Revolve primitives

### `revolve_boss`

Adds material by revolving a sketch profile about its embedded centerline. SW auto-detects the centerline from inside the sketch — no separate axis selection needed.

```json
{
  "type": "revolve_boss",
  "name": "Revolve_Hub",
  "sketch": "SK_Hub",
  "angle": 360.0
}
```

<!-- BEGIN GENERATED: revolve_boss -->
| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `type` | const `"revolve_boss"` | yes |  | Solid revolve of a profile about its embedded centerline. |
| `name` | string | yes |  | Unique identifier for this feature within the spec. Later features refer back to it by name (e.g. via `sketch`, `of_feature`, `seed`, or `target_ref.of_feature`). |
| `sketch` | string | yes |  | Name of an earlier plane-based sketch that contains both a closed profile and an embedded centerline. SW auto-picks the centerline as the axis of revolution. |
| `angle` | number | no | `360.0` | Sweep angle in DEGREES (builder converts to radians). Default 360 = full revolution. |
| `flip` | boolean | no | `false` | Reverse the revolve direction. |
<!-- END GENERATED -->

The referenced sketch must have a `centerline` declared. The profile must not cross the centerline — SW will reject the geometry. Only plane-based sketches support centerlines currently; face-based sketches do not.

**v1 limits:** Single-direction, solid-only, literal-degrees angle. Two-direction / mid-plane revolves deferred.

### `revolve_cut`

Removes material by revolving a sketch profile about its embedded centerline. Same axis detection as `revolve_boss`, but subtractive.

```json
{
  "type": "revolve_cut",
  "name": "Cut_Groove",
  "sketch": "SK_Groove",
  "angle": 360.0
}
```

<!-- BEGIN GENERATED: revolve_cut -->
| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `type` | const `"revolve_cut"` | yes |  | Subtractive revolve of a profile about its embedded centerline. |
| `name` | string | yes |  | Unique identifier for this feature within the spec. Later features refer back to it by name (e.g. via `sketch`, `of_feature`, `seed`, or `target_ref.of_feature`). |
| `sketch` | string | yes |  | Name of an earlier plane-based sketch that contains both a closed profile and an embedded centerline. SW auto-picks the centerline as the axis of revolution. The profile, when revolved, must intersect existing body material -- otherwise SW silently produces no geometry. |
| `angle` | number | no | `360.0` | Sweep angle in DEGREES (builder converts to radians). Default 360 = full revolution. |
| `flip` | boolean | no | `false` | Bound to FeatureRevolve2 arg 5 (`ReverseDir`). Whether this reverses the sweep of a *cut* is UNVERIFIED -- the issue #40 seat proof covers FeatureCut4, not FeatureRevolve2, and issue #46 is open on revolve_cut returning None. Do not rely on it to aim the cut. |
<!-- END GENERATED -->

**Important:** The revolved profile must intersect existing body material. If it doesn't, SW silently returns no geometry — the builder surfaces this as an error. This cannot be validated pre-build; the builder emits a precise diagnostic when it detects the silent-no-op.

**Top Plane center.z:** When using a Top Plane sketch with `centerline`, you must set `center.z` to position the sketch at the correct part-Z. The lint checker (`--lint`) warns if a Top Plane sketch has a centerline but no `center.z`. See the DriveRoller example below for a working Top Plane `revolve_cut`.

**v1 limits:** Same as `revolve_boss`. Additionally, requires existing body to cut from.

## Modify primitives

### `fillet_constant_radius`

Applies a constant-radius fillet to one or more edges.

```json
{
  "type": "fillet_constant_radius",
  "name": "Fillet_Edge",
  "radius": 2.0,
  "edges": [
    {"x": 10.0, "y": 0.0, "z": 10.0},
    {"x": -10.0, "y": 0.0, "z": 10.0}
  ]
}
```

<!-- BEGIN GENERATED: fillet_constant_radius -->
| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `type` | const `"fillet_constant_radius"` | yes |  | Constant-radius fillet on selected edges. |
| `name` | string | yes |  | Unique identifier for this feature within the spec. Later features refer back to it by name (e.g. via `sketch`, `of_feature`, `seed`, or `target_ref.of_feature`). |
| `radius` | length | yes |  | Fillet radius (mm). |
| `edges` | array (min 1) | yes |  | Edges to fillet. At least 1 item; each is a literal {x, y, z} point, or (with the semantic_edges flag) an {of_feature, face} / {of_feature, between_faces} selector -- see docs/spec_reference.md Edge selectors. |
<!-- END GENERATED -->

**How literal edge selection works:** The builder converts each point to meters and finds the nearest actual edge (within 1 µm) of the current geometry. The point must land on (or very near) that edge. Changing upstream dimensions that move the edge will break the selection — update edge coordinates accordingly.

<a id="edge-selectors"></a>
**Edge selectors (`fillet_constant_radius` and `chamfer_edge`):** each `edges[]` item is one of:

| Form | Selects | Survives dim edits? |
|---|---|---|
| `{"x": …, "y": …, "z": …}` | the single edge nearest that part-frame point (mm) | no — coordinate is frozen |
| `{"of_feature": "Box", "face": "+z"}` | ALL edges bounding face `+z` of feature `Box` | yes — re-resolved each build |
| `{"of_feature": "Box", "between_faces": ["+z", "+x"]}` | the ONE edge shared by faces `+z` and `+x` of `Box` | yes — re-resolved each build |

The two semantic forms are governed by the **`semantic_edges`** feature flag, **default ON** since v1.7 (live-seat PAE green); `ai-sw-build --disable-flag semantic_edges` falls back to literal-only edges. Rules:
- `of_feature` must name an **earlier fixed-extent boss extrude** (`boss_extrude_blind` / `_midplane` / `_two_direction`) — the extents whose faces the builder can resolve. Faces use the outward-normal names `+x`/`-x`/`+y`/`-y`/`+z`/`-z`.
- `between_faces` takes exactly two DISTINCT, non-anti-parallel faces; `["+z", "-z"]` (opposite faces, no shared edge) is a validation error, as is a pair whose faces share ≠ 1 edge on the current geometry.
- All three forms may be mixed in one `edges[]` array; an edge reached more than one way (e.g. by `of_face` and by `between_faces`) is filleted once.

**No parent sketch needed.** Fillet operates on existing geometry, not a sketch profile.

### `chamfer_edge`

Applies an edge chamfer in one of two modes.

```json
{
  "type": "chamfer_edge",
  "name": "Ch_TopEdges",
  "mode": "equal_distance",
  "distance": 1.0,
  "edges": [
    {"x":  10.0, "y": 0.0, "z": 10.0},
    {"x": -10.0, "y": 0.0, "z": 10.0}
  ]
}
```

<!-- BEGIN GENERATED: chamfer_edge -->
| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `type` | const `"chamfer_edge"` | yes |  | Edge chamfer (equal-distance or distance-angle). |
| `name` | string | yes |  | Unique identifier for this feature within the spec. Later features refer back to it by name (e.g. via `sketch`, `of_feature`, `seed`, or `target_ref.of_feature`). |
| `mode` | enum (`"equal_distance"` / `"distance_angle"`) | yes |  | Chamfer geometry mode. 'equal_distance' takes a single distance and applies it to both sides. 'distance_angle' takes a distance plus an angle in degrees, measured from one face of the chamfered edge. |
| `distance` | length | no |  | Chamfer distance from edge (mm). Required for both modes. |
| `angle` | length | no |  | Chamfer angle in DEGREES. Required for mode 'distance_angle', forbidden for mode 'equal_distance'. Despite reusing LENGTH_SCHEMA for parametric support, this is an angle in degrees -- the spec author is responsible for not passing a length-typed locals var here. |
| `flip` | boolean | no | `false` | Reverse the chamfer asymmetry direction. Only meaningful for 'distance_angle' (the equal-distance case is symmetric). |
| `edges` | array (min 1) | yes |  | Edges to chamfer. At least 1 item; same three selector forms as fillet_constant_radius -- see docs/spec_reference.md Edge selectors. |
<!-- END GENERATED -->

**Modes:**
- `equal_distance` — symmetric chamfer. One distance applied to both sides of each edge.
- `distance_angle` — asymmetric chamfer. The chamfer leaves one face by `distance` and the other by `distance × tan(angle)`. Use when one face must remain larger than the other (e.g. lead-in chamfer on a press fit).

Same edge-selection rules as `fillet_constant_radius`. No vertex chamfer (would need three distances and adjacent-edge convexity matching).

## Pattern primitives

### `linear_pattern`

Replicates an earlier feature along a direction reference.

```json
{
  "type": "linear_pattern",
  "name": "LP_Holes",
  "seed": "Hole_Seed",
  "direction": {"x": 15.0, "y": 0.0, "z": 4.0},
  "count": 3,
  "spacing": 8.0
}
```

<!-- BEGIN GENERATED: linear_pattern -->
| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `type` | const `"linear_pattern"` | yes |  | Linear pattern of a seed feature along a model-edge direction. |
| `name` | string | yes |  | Unique identifier for this feature within the spec. Later features refer back to it by name (e.g. via `sketch`, `of_feature`, `seed`, or `target_ref.of_feature`). |
| `seed` | string | yes |  | Name of an earlier feature to pattern. The seed itself counts as instance 1; `count` includes it. |
| `direction` | object | yes |  | A point on a model edge whose direction defines the pattern axis. The builder selects the edge with SelectByID and uses its tangent at that point. |
| `count` | integer (≥ 2) | yes |  | Total number of instances along Direction 1 (includes the seed). Must be >= 2 -- a count of 1 would be a no-op. |
| `spacing` | length | yes |  | Distance between consecutive instances (mm). |
| `flip` | boolean | no | `false` | Reverse pattern direction relative to the selected edge's tangent. |
<!-- END GENERATED -->

**How direction selection works:** the builder calls `SelectByID('EDGE', x, y, z)` to pick whichever model edge passes through the given point. The pattern axis is the edge's tangent at that point.

**Watch out:** on a box, the "+X edge" (the edge bounding the +X side) is actually oriented along Y at its midpoint. Pick a point on the edge whose **tangent** is the direction you want, not the edge "in the direction of" the axis you want. If the pattern goes the wrong way, set `"flip": true`.

**v1 limits:**
- Direction 1 only. Rectangular (Direction 2) pattern deferred.
- Single seed by name. Multi-seed deferred.
- Spacing not yet parametric (accepts `{rhs}` syntactically but the binding isn't wired).

### `circular_pattern`

Replicates an earlier feature equally spaced around a rotation axis.

```json
{
  "type": "circular_pattern",
  "name": "CP_Holes",
  "seed": "Hole_Seed",
  "axis": {"x": 0.0, "y": 0.0, "z": 5.0},
  "count": 6,
  "total_angle": 360.0
}
```

<!-- BEGIN GENERATED: circular_pattern -->
| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `type` | const `"circular_pattern"` | yes |  | Circular pattern of a seed feature about an axis reference. |
| `name` | string | yes |  | Unique identifier for this feature within the spec. Later features refer back to it by name (e.g. via `sketch`, `of_feature`, `seed`, or `target_ref.of_feature`). |
| `seed` | string | yes |  | Name of an earlier feature to pattern. The seed itself counts as instance 1; `count` includes it. |
| `axis` | object | yes |  | A point on the rotation-axis reference -- either a circular EDGE (e.g. the rim of a cylindrical face) or a cylindrical FACE. The builder tries EDGE first, then FACE on fallback. SW infers the axis of revolution from the selected entity. |
| `count` | integer (≥ 2) | yes |  | Total number of instances around the axis (includes the seed). Must be >= 2 -- a count of 1 would be a no-op. |
| `total_angle` | number | no | `360.0` | Total sweep angle in DEGREES (builder converts to radians). Default 360 = full circle, equally spaced. For a half-fan of 4 instances over 180 degrees, set total_angle=180. |
| `flip` | boolean | no | `false` | Reverse the rotation direction. |
<!-- END GENERATED -->

**How axis selection works:** The builder calls `SelectByID2('EDGE', x, y, z)` first; if that fails (no circular edge at that point), it tries `SelectByID2('FACE', ...)`. Both paths verified on SW 2024 SP1.

**v1 limits:** Direction 1 only. Equal spacing always on. Single seed by name.

### `mirror_feature`

Mirrors an earlier feature about a default reference plane.

```json
{
  "type": "mirror_feature",
  "name": "Mir_Hole",
  "seed": "Hole_Seed",
  "plane": "Right"
}
```

<!-- BEGIN GENERATED: mirror_feature -->
| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `type` | const `"mirror_feature"` | yes |  | Mirror of a seed feature about a default reference plane. |
| `name` | string | yes |  | Unique identifier for this feature within the spec. Later features refer back to it by name (e.g. via `sketch`, `of_feature`, `seed`, or `target_ref.of_feature`). |
| `seed` | string | yes |  | Name of an earlier feature to mirror. |
| `plane` | enum (`"Front"` / `"Top"` / `"Right"`) | yes |  | Default reference plane to mirror about. Front = XY (mirrors Z), Top = XZ (mirrors Y), Right = YZ (mirrors X). |
<!-- END GENERATED -->

**Mirror plane effect:**

| Plane | What it is | Mirror effect |
|---|---|---|
| `Front` | XY plane (z=0) | Flips Z |
| `Top` | XZ plane (y=0) | Flips Y |
| `Right` | YZ plane (x=0) | Flips X |

**v1 limits:**
- Only the three default reference planes. User-created planes and planar faces deferred.
- Single seed by name.
- Feature-mirror only (not body-mirror).

**Selection-marked API surface (pattern + mirror):** Both primitives use `doc.Extension.SelectByID2` with selection marks (`linear_pattern`: seed=4, direction=1; `mirror_feature`: plane=2, seed=1). If you hit a `SelectByID2 returned False` error, the marked-selection variant may not marshal through pywin32 late-binding on your SW build — see [spikes/v0_3/](../spikes/v0_3/) for probe scripts.

## Comment fields

Any feature or the top-level spec can include a `_comment` field with arbitrary string content. These are stripped by the validator and never sent to SOLIDWORKS. Useful for documenting design intent:

```json
{
  "type": "sketch_rectangle_on_plane",
  "name": "SK_Box",
  "_comment": "Base plate dimensions per §13.4",
  "plane": "Front",
  "width": 50.0,
  "height": 50.0
}
```

## Validation

The validator checks three layers, fail-fast:

1. **Schema** — shape, types, required fields, `additionalProperties: false` (after stripping `_comment` fields). Includes the `chamfer_edge` mode-conditional check for `angle`.
2. **Expect blocks** — validates `_expect` fields (see below) on the raw spec before `_comment` stripping.
3. **References** — every `sketch`, `of_feature`, and `seed` must name an earlier feature of the correct type
4. **Locals** — every `{rhs}` variable must be declared in the specified `locals` file

The validator does NOT check geometric validity (e.g. whether a fillet radius exceeds the smallest adjacent edge, whether a circle lands on material, or whether a pattern's direction edge actually exists at the given point). These surface as runtime errors during the build.

## Postcondition expectations (`_expect`)

Any feature can declare an `_expect` block for post-build verification:

```json
{
  "type": "boss_extrude_blind",
  "name": "Extrude_Box",
  "sketch": "SK_Box",
  "depth": 10.0,
  "_expect": {"mass_delta_mm3": 5000.0, "tolerance_mm3": 50.0}
}
```

| Field | Required | Type | Description |
|---|---|---|---|
| `mass_delta_mm3` | yes | number | Expected change in part volume (mm³). Positive for bosses, negative for cuts. |
| `tolerance_mm3` | no | number | Acceptable deviation. Default `1.0`. Must be ≥ 0. |

The validator checks `_expect` blocks on the raw spec (before `_comment` stripping) to ensure correct shape. The builder's `--verify-mass` flag reads `CreateMassProperty` after each feature and compares the actual volume delta against the declared expectation, fail-fast on mismatch.

## Lint checks

The `--lint` flag runs semantic checks beyond schema validation:

- **Unconsumed sketch** — a sketch not referenced by any downstream extrude/cut
- **Missing center.z on Top Plane centerline** — a Top Plane sketch with `centerline` but no `center.z` will produce incorrect geometry at part Z=0
- **center.z thread-through** — a Top Plane sketch with non-zero `center.z` consumed by `boss_extrude_blind` (known gap, extrude_origin remap ignores center.z)

INFO and WARNING findings never change the exit code. `--lint` exits `6` only
when a geometric ERROR is present; a spec that only produces INFO/WARNING
findings still exits `0`. See [`tools_reference.md`](tools_reference.md).

## Examples

| Example | Features | Primitives used |
|---|---|---|
| [`filleted_box`](../examples/filleted_box/) | 3 | `sketch_rectangle_on_plane`, `boss_extrude_blind`, `fillet_constant_radius` |
| [`minimal_cylinder_v2`](../examples/minimal_cylinder_v2/) | 2 | `sketch_circle_on_plane`, `boss_extrude_blind` |
| [`motor_mount_plate`](../examples/motor_mount_plate/) | 10 | All sketch types, all extrude types |
| [`tension_bracket`](../examples/tension_bracket/) | 8 | `sketch_rectangle_on_plane`, `sketch_rectangle_on_face`, `sketch_circle_on_face`, `boss_extrude_blind`, `cut_extrude_through_all` |
| [`chamfered_box`](../examples/chamfered_box/) | 3 | `sketch_rectangle_on_plane`, `boss_extrude_blind`, `chamfer_edge` (equal_distance) |
| [`patterned_plate`](../examples/patterned_plate/) | 5 | adds `sketch_circle_on_face`, `cut_extrude_through_all`, `linear_pattern` |
| [`mirrored_holes`](../examples/mirrored_holes/) | 5 | same as patterned_plate but `mirror_feature` instead of `linear_pattern` |
| [`drive_roller`](../examples/drive_roller/) | 9 | `sketch_circle_on_plane`, `boss_extrude_blind`, `cut_extrude_through_all`, `cut_extrude_blind`, `sketch_rectangle_on_plane` (Top Plane + center.z + centerline), `revolve_cut` |

---

# Sketch axes reference

_Consolidated from the former `sketch_axes.md`._


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
