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
| `center` | no | object | `{x, y}` offset in sketch-local mm. Default `{"x": 0, "y": 0}` (part origin). |

**Axis mapping:**
- Front Plane: X = width, Y = height, extrude direction = +Z
- Top Plane: X = width, Y = height, extrude direction = -Y (downward)
- Right Plane: X = width, Y = height, extrude direction = +X

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
| `center` | no | object | `{x, y}` offset in sketch-local mm. Default `{0, 0}` (part origin). |

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

1. **Schema** — shape, types, required fields, `additionalProperties: false` (after stripping `_comment` fields)
2. **References** — every `sketch` and `of_feature` must name an earlier feature of the correct type
3. **Locals** — every `{rhs}` variable must be declared in the specified `locals` file

The validator does NOT check geometric validity (e.g. whether a fillet radius exceeds the smallest adjacent edge, or whether a circle lands on material). These surface as runtime errors during the build.

## Examples

| Example | Features | Primitives used |
|---|---|---|
| [`filleted_box`](../examples/filleted_box/) | 3 | `sketch_rectangle_on_plane`, `boss_extrude_blind`, `fillet_constant_radius` |
| [`minimal_cylinder_v2`](../examples/minimal_cylinder_v2/) | 2 | `sketch_circle_on_plane`, `boss_extrude_blind` |
| [`motor_mount_plate`](../examples/motor_mount_plate/) | 10 | All sketch types, all extrude types |
| [`tension_bracket`](../examples/tension_bracket/) | 8 | `sketch_rectangle_on_plane`, `sketch_rectangle_on_face`, `sketch_circle_on_face`, `boss_extrude_blind`, `cut_extrude_through_all` |
