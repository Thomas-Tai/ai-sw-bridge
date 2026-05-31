# Spec reference

Complete reference for the JSON spec format consumed by `ai-sw-build`. The authoritative schema lives in [`src/ai_sw_bridge/spec/schema.py`](../src/ai_sw_bridge/spec/schema.py); this document is the human-readable version.

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

| Field | Required | Type | Description |
|---|---|---|---|
| `type` | yes | const `"sketch_rectangle_on_plane"` | |
| `name` | yes | string | Unique feature name |
| `plane` | yes | enum | `"Front"`, `"Top"`, or `"Right"` |
| `width` | yes | length | Rectangle width (mm) |
| `height` | yes | length | Rectangle height (mm) |
| `center` | no | object | `{x, y, z}` offset in sketch-local mm. Default `{"x": 0, "y": 0}` (part origin). See **center.z** below. |

**center.z** (Top/Right Plane sketches): The optional `z` field offsets the sketch geometry along the part-frame Z axis. On Front Plane, `z` is redundant (the plane already lies at Z=0). On Top Plane, `center.z` positions the rectangle at the given part-Z — the builder applies a sign flip (`sketch_Y = -part_Z`) internally. On Right Plane, `center.z` positions along part-Z similarly. This is essential when a Top/Right Plane sketch must land at a non-zero Z position (e.g. a groove at mid-length of a cylinder). See [sketch_axes.md](sketch_axes.md) for the full axis-mapping reference.

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

The centerline `start`/`end` use the same projection as `center`: on Top Plane, the `y` component maps to part-Z (with sign flip) and the optional `z` provides an additional part-frame Z offset. See [sketch_axes.md](sketch_axes.md) for details.

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

| Field | Required | Type | Description |
|---|---|---|---|
| `type` | yes | const `"sketch_rectangle_on_face"` | |
| `name` | yes | string | Unique feature name |
| `of_feature` | yes | string | Name of an earlier extrusion feature |
| `face` | yes | enum | `"+x"`, `"-x"`, `"+y"`, `"-y"`, `"+z"`, `"-z"` — outward normal direction |
| `width` | yes | length | Rectangle width (mm) |
| `height` | yes | length | Rectangle height (mm) |
| `center` | no | object | `{u, v}` offset from face-sketch origin (mm). Default `{0, 0}`. |

**Face-sketch origin gotcha:** The origin is the part-origin *projection* onto the face, NOT the face's geometric center. If the parent extrusion is centered on the part origin (like a `CreateCenterRectangle` at `(0,0)`), these coincide. If the parent is shifted, you need a `center` offset. See [known_limitations.md](known_limitations.md) section 1.

**Current limitation:** Only `+z` and `-z` faces are implemented. `+x`, `-x`, `+y`, `-y` raise `NotImplementedError`. See [known_limitations.md](known_limitations.md) section 2.

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

| Field | Required | Type | Description |
|---|---|---|---|
| `type` | yes | const `"sketch_circle_on_plane"` | |
| `name` | yes | string | Unique feature name |
| `plane` | yes | enum | `"Front"`, `"Top"`, or `"Right"` |
| `diameter` | yes | length | Circle diameter (mm) |
| `center` | no | object | `{x, y, z}` offset in sketch-local mm. Default `{0, 0}` (part origin). The optional `z` offsets along part-frame Z — see `sketch_rectangle_on_plane` **center.z** for details. |

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

| Field | Required | Type | Description |
|---|---|---|---|
| `type` | yes | const `"sketch_circle_on_face"` | |
| `name` | yes | string | Unique feature name |
| `of_feature` | yes | string | Name of an earlier extrusion feature |
| `face` | yes | enum | `"+x"`, `"-x"`, `"+y"`, `"-y"`, `"+z"`, `"-z"` |
| `diameter` | yes | length | Circle diameter (mm) |
| `center` | no | object | `{u, v}` offset from face-sketch origin (mm). Default `{0, 0}`. |

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

| Field | Required | Type | Description |
|---|---|---|---|
| `type` | yes | const `"sketch_circles_on_face"` | |
| `name` | yes | string | Unique feature name |
| `of_feature` | yes | string | Name of an earlier extrusion feature |
| `face` | yes | enum | `"+x"`, `"-x"`, `"+y"`, `"-y"`, `"+z"`, `"-z"` |
| `circles` | yes | array | Minimum 1 item. Each has `u`, `v` (number, mm), and `diameter` (length). |

Circle positions are literal mm only — no `{rhs}` on `u` or `v`.

## Sketch primitives (P1.7s)

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

| Field | Required | Type | Description |
|---|---|---|---|
| `type` | yes | const `"sketch_line"` | |
| `name` | yes | string | Unique feature name |
| `plane` | yes | enum | `"Front"`, `"Top"`, or `"Right"` |
| `start` | yes | object | `{x, y}` in sketch-local mm |
| `end` | yes | object | `{x, y}` in sketch-local mm |
| `construction` | no | boolean | Mark as construction (centerline) entity. Default `false`. |

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

| Field | Required | Type | Description |
|---|---|---|---|
| `type` | yes | const `"sketch_arc"` | |
| `name` | yes | string | Unique feature name |
| `plane` | yes | enum | `"Front"`, `"Top"`, or `"Right"` |
| `center` | yes | object | `{x, y}` in sketch-local mm |
| `start` | yes | object | `{x, y}` in sketch-local mm |
| `end` | yes | object | `{x, y}` in sketch-local mm |
| `direction` | no | enum | `"cw"` or `"ccw"`. Default `"ccw"`. |
| `construction` | no | boolean | Default `false`. |

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

| Field | Required | Type | Description |
|---|---|---|---|
| `type` | yes | const `"sketch_spline"` | |
| `name` | yes | string | Unique feature name |
| `plane` | yes | enum | `"Front"`, `"Top"`, or `"Right"` |
| `points` | yes | array | Min 2 points; each `{x, y, z?}` in sketch-local mm. If any point has non-zero `z`, the 3D-sketch COM path is selected. |
| `construction` | no | boolean | Mark the spline as a construction entity. Default `false`. |

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

| Field | Required | Type | Description |
|---|---|---|---|
| `type` | yes | const `"sketch_slot"` | |
| `name` | yes | string | Unique feature name |
| `plane` | yes | enum | `"Front"`, `"Top"`, or `"Right"` |
| `center` | yes | object | `{x, y}` in sketch-local mm |
| `width` | yes | length | Slot width (mm) |
| `length` | yes | length | Slot length (mm) |
| `slot_type` | no | enum | Only `"arc"` (rounded ends) is supported. Default `"arc"`. Flat-ended slots → use `sketch_rectangle_on_plane`. |
| `angle_deg` | no | number | Rotation of the slot's major axis from sketch X (degrees). Default `0`. |

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

| Field | Required | Type | Description |
|---|---|---|---|
| `type` | yes | const `"sketch_polygon"` | |
| `name` | yes | string | Unique feature name |
| `plane` | yes | enum | `"Front"`, `"Top"`, or `"Right"` |
| `center` | yes | object | `{x, y}` in sketch-local mm |
| `sides` | yes | integer | Number of sides (3..40) |
| `radius` | yes | length | Radius in mm. Meaning depends on `inscribed`. |
| `inscribed` | no | boolean | If `true` (default), `radius` is the inscribed (apothem) radius — polygon edges are tangent to the circle. If `false`, `radius` is the circumscribed radius — polygon vertices lie on the circle. |
| `angle_deg` | no | number | Rotation of the first vertex from sketch X (degrees). Default `0`. |
| `construction` | no | boolean | Default `false`. |

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

| Field | Required | Type | Description |
|---|---|---|---|
| `type` | yes | const `"sketch_ellipse"` | |
| `name` | yes | string | Unique feature name |
| `plane` | yes | enum | `"Front"`, `"Top"`, or `"Right"` |
| `center` | yes | object | `{x, y}` in sketch-local mm |
| `major_radius` | yes | length | Semi-major axis (mm) |
| `minor_radius` | yes | length | Semi-minor axis (mm) |
| `angle_deg` | no | number | Rotation of the major axis from sketch X (degrees). Default `0`. |
| `construction` | no | boolean | Default `false`. |

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

| Field | Required | Type | Description |
|---|---|---|---|
| `type` | yes | const `"sketch_text"` | |
| `name` | yes | string | Unique feature name |
| `plane` | yes | enum | `"Front"`, `"Top"`, or `"Right"` |
| `position` | yes | object | `{x, y}` in sketch-local mm |
| `content` | yes | string | Plain ASCII text content (non-empty). |
| `height` | yes | length | Text cap height (mm). Applied as `CharHeight`. |
| `font` | no | string | Font family name (e.g. `"Arial"`). Applied as `TypeFaceName`. |

> **✅ Seat-proven (2026-05-31):** Text is a document-level op — `IModelDoc2.InsertSketchText(Ptx, Pty, Ptz, Text, Alignment, FlipDirection, HorizontalMirror, WidthFactor, SpaceBetweenChars)` (NOT on `ISketchManager`; the trailing args are ints and there is **no angle parameter**). `height` (CharHeight, metres) and `font` (TypeFaceName) are applied through the returned `ISketchText` via the early-bind hatch: `typed(raw, "ISketchText").GetTextFormat()` → mutate → `SetTextFormat(0, tf)` (late binding alone hits "Member not found" on `GetTextFormat`). There is **no `angle_deg` or `construction` field**: text baseline rotation has no out-of-process API on this seat (`InsertSketchText`/`ITextFormat` expose no angle), and text is not a sketch segment — both are rejected at validation rather than faked.

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

| Field | Required | Type | Description |
|---|---|---|---|
| `type` | yes | const `"boss_extrude_blind"` | |
| `name` | yes | string | Unique feature name |
| `sketch` | yes | string | Name of an earlier sketch feature |
| `depth` | yes | length | Extrusion depth (mm) |
| `flip` | no | boolean | Extrude in -normal direction. Default `false`. |

### `cut_extrude_through_all`

Removes material through the entire part in both directions.

```json
{
  "type": "cut_extrude_through_all",
  "name": "Cut_Hole",
  "sketch": "SK_Hole",
  "flip": false
}
```

| Field | Required | Type | Description |
|---|---|---|---|
| `type` | yes | const `"cut_extrude_through_all"` | |
| `name` | yes | string | Unique feature name |
| `sketch` | yes | string | Name of an earlier sketch feature |
| `flip` | no | boolean | Cut in -normal direction. Default `false`. |

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

| Field | Required | Type | Description |
|---|---|---|---|
| `type` | yes | const `"simple_hole"` | |
| `name` | yes | string | Unique feature name |
| `of_feature` | yes | string | Name of an earlier extrusion feature |
| `face` | yes | enum | `"+x"`, `"-x"`, `"+y"`, `"-y"`, `"+z"`, `"-z"` — face the hole drills into |
| `diameter` | yes | length | Hole diameter (mm) |
| `center` | no | object | `{u, v}` offset from face-sketch origin (mm). Default `{0, 0}`. |
| `end_condition` | no | enum | `"blind"` (default) or `"through_all"`. |
| `depth` | conditional | length | Required for `"blind"` end condition. Ignored for `"through_all"`. |

Same face-sketch-origin gotcha as `sketch_rectangle_on_face` — `center` offsets from the part-origin projection, not the face centroid.

### `cut_extrude_blind`

Removes material to a specified depth.

```json
{
  "type": "cut_extrude_blind",
  "name": "Cut_Pocket",
  "sketch": "SK_Pocket",
  "depth": 2.0,
  "flip": false
}
```

| Field | Required | Type | Description |
|---|---|---|---|
| `type` | yes | const `"cut_extrude_blind"` | |
| `name` | yes | string | Unique feature name |
| `sketch` | yes | string | Name of an earlier sketch feature |
| `depth` | yes | length | Cut depth (mm) |
| `flip` | no | boolean | Cut in -normal direction. Default `false`. |

### `cut_extrude_midplane`

Removes material symmetrically about the sketch plane — `depth/2` is cut into each side.

```json
{
  "type": "cut_extrude_midplane",
  "name": "Cut_Slot",
  "sketch": "SK_Slot",
  "depth": 10.0,
  "flip": false
}
```

| Field | Required | Type | Description |
|---|---|---|---|
| `type` | yes | const `"cut_extrude_midplane"` | |
| `name` | yes | string | Unique feature name |
| `sketch` | yes | string | Name of an earlier sketch feature |
| `depth` | yes | length | Total cut depth (mm); centred on the sketch plane |
| `flip` | no | boolean | Mirror the asymmetric reference. Default `false`. |

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

| Field | Required | Type | Description |
|---|---|---|---|
| `type` | yes | const `"cut_extrude_two_direction"` | |
| `name` | yes | string | Unique feature name |
| `sketch` | yes | string | Name of an earlier sketch feature |
| `depth` | yes | length | Cut depth in the +normal direction (mm) |
| `depth2` | yes | length | Cut depth in the -normal direction (mm) |
| `flip` | no | boolean | Swap which direction is +normal. Default `false`. |

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

| Field | Required | Type | Description |
|---|---|---|---|
| `type` | yes | const `"revolve_boss"` | |
| `name` | yes | string | Unique feature name |
| `sketch` | yes | string | Name of an earlier plane-based sketch containing a closed profile and a `centerline` |
| `angle` | no | number | Sweep angle in degrees. Default `360.0` (full revolution). Must be > 0 and ≤ 360. |
| `flip` | no | boolean | Reverse the revolve direction. Default `false`. |

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

| Field | Required | Type | Description |
|---|---|---|---|
| `type` | yes | const `"revolve_cut"` | |
| `name` | yes | string | Unique feature name |
| `sketch` | yes | string | Name of an earlier plane-based sketch containing a closed profile and a `centerline` |
| `angle` | no | number | Sweep angle in degrees. Default `360.0` (full revolution). |
| `flip` | no | boolean | Reverse the revolve direction. Default `false`. |

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

| Field | Required | Type | Description |
|---|---|---|---|
| `type` | yes | const `"fillet_constant_radius"` | |
| `name` | yes | string | Unique feature name |
| `radius` | yes | length | Fillet radius (mm) |
| `edges` | yes | array | Minimum 1 item. Each is `{x, y, z}` — a point on the target edge in part coordinates (mm). |

**How edge selection works:** The builder converts each point to meters and calls `SelectByID("EDGE")` with that coordinate. The point must land on (or very near) an actual edge of the current geometry. Changing upstream dimensions that move the edge will break the selection — update edge coordinates accordingly.

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

| Field | Required | Type | Description |
|---|---|---|---|
| `type` | yes | const `"chamfer_edge"` | |
| `name` | yes | string | Unique feature name |
| `mode` | yes | enum | `"equal_distance"` or `"distance_angle"` |
| `distance` | yes | length | Chamfer distance from edge (mm) |
| `angle` | conditional | length | Angle in **degrees**. Required for `distance_angle` mode, forbidden for `equal_distance`. Reuses LENGTH_SCHEMA for parametric support; the spec author is responsible for not passing a length-typed locals var here. |
| `flip` | no | boolean | Reverse asymmetry direction. Only meaningful for `distance_angle`. Default `false`. |
| `edges` | yes | array | Minimum 1 item. Each is `{x, y, z}` — a point on the target edge in part coords (mm). |

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

| Field | Required | Type | Description |
|---|---|---|---|
| `type` | yes | const `"linear_pattern"` | |
| `name` | yes | string | Unique feature name |
| `seed` | yes | string | Name of an earlier feature to pattern |
| `direction` | yes | object | `{x, y, z}` — a point on a model edge whose tangent gives the pattern direction |
| `count` | yes | integer | Total instances (including seed). Must be ≥ 2 |
| `spacing` | yes | length | Distance between consecutive instances (mm) |
| `flip` | no | boolean | Reverse pattern direction. Default `false` |

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

| Field | Required | Type | Description |
|---|---|---|---|
| `type` | yes | const `"circular_pattern"` | |
| `name` | yes | string | Unique feature name |
| `seed` | yes | string | Name of an earlier feature to pattern |
| `axis` | yes | object | `{x, y, z}` — a point on a circular EDGE or cylindrical FACE in part coords. The builder tries EDGE first, then FACE on fallback. SW infers the axis of revolution from the selected entity. |
| `count` | yes | integer | Total instances (including seed). Must be ≥ 2. |
| `total_angle` | no | number | Total sweep angle in degrees. Default `360.0`. Must be > 0 and ≤ 360. |
| `flip` | no | boolean | Reverse rotation direction. Default `false`. |

**How axis selection works:** The builder calls `SelectByID2('EDGE', x, y, z)` first; if that fails (no circular edge at that point), it tries `SelectByID2('FACE', ...)`. Both paths verified on SW 2024 SP1 (Spike T).

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

| Field | Required | Type | Description |
|---|---|---|---|
| `type` | yes | const `"mirror_feature"` | |
| `name` | yes | string | Unique feature name |
| `seed` | yes | string | Name of an earlier feature to mirror |
| `plane` | yes | enum | `"Front"`, `"Top"`, or `"Right"` — the mirror plane |

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

Lint findings are warnings, not errors. The spec is valid but likely buggy. Exit code 6 if any findings.

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
