"""Declarative feature-primitive descriptors (X3, FR-X-03).

Single, cycle-free source of truth for each primitive's JSON-Schema shape.
``schema.py`` *assembles* its per-feature fragments from the ``FieldSpec``
lists here (``assemble_feature_schema``) instead of hand-written dict literals,
and ``builder.py`` attaches handlers to the matching descriptors. So adding a
primitive is one entry here + a handler, not five hand-synced files.

Import layering (no cycles): this module imports only ``_build_context``
(for ``FieldSpec``). ``schema.py`` and ``builder.py`` both import *from* here;
neither is imported *by* here.

The shared sub-schemas (``LENGTH_SCHEMA`` etc.) live here too; ``schema.py``
re-exports them for back-compat with existing importers.
"""

from __future__ import annotations

from typing import Any

from ._build_context import FieldSpec

# ---------------------------------------------------------------------------
# Shared sub-schemas (moved here from schema.py; re-exported there).
# ---------------------------------------------------------------------------

# The common feature `name` property: a valid identifier.
NAME_PATTERN: dict[str, Any] = {
    "type": "string",
    "pattern": "^[A-Za-z_][A-Za-z0-9_]*$",
}


# A length value: literal mm or a SW-equation expression to bind via Add2.
LENGTH_SCHEMA: dict[str, Any] = {
    "oneOf": [
        {"type": "number", "description": "Literal length in millimetres."},
        {
            "type": "object",
            "additionalProperties": False,
            "required": ["rhs"],
            "properties": {
                "rhs": {
                    "type": "string",
                    "description": (
                        "Right-hand side of an Equation Manager binding. "
                        "Pasted verbatim into EquationMgr.Add2. Quote variable "
                        "references yourself, e.g. '\"S1B_W\"' for a bare var."
                    ),
                }
            },
        },
    ]
}


# A centerline (construction line) embedded in a plane-based sketch.
CENTERLINE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["start", "end"],
    "properties": {
        "start": {
            "type": "object",
            "additionalProperties": False,
            "required": ["x", "y"],
            "properties": {
                "x": {"type": "number"},
                "y": {"type": "number"},
                "z": {"type": "number"},
            },
            "description": (
                "Centerline start point in sketch-local coords (mm). "
                "Optional z is the part-frame z offset of the sketch plane "
                "(default 0). Used when the parent sketch's center.z is "
                "non-zero (e.g. Top Plane sketch positioned at part-Z != 0)."
            ),
        },
        "end": {
            "type": "object",
            "additionalProperties": False,
            "required": ["x", "y"],
            "properties": {
                "x": {"type": "number"},
                "y": {"type": "number"},
                "z": {"type": "number"},
            },
            "description": (
                "Centerline end point in sketch-local coords (mm). "
                "Optional z is the part-frame z offset of the sketch plane "
                "(default 0)."
            ),
        },
    },
    "description": (
        "Construction line embedded in the sketch. Consumed by `revolve_boss` "
        "as the axis of revolution (SW auto-detects). No driving dim; "
        "coordinates are literal mm."
    ),
}


# Per-feature postcondition expectation (the `_expect` block). The validator
# checks these on the raw spec before _strip_comments removes _-prefixed keys.
EXPECT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["mass_delta_mm3"],
    "properties": {
        "mass_delta_mm3": {
            "type": "number",
            "description": (
                "Expected change in part mass in mm³ after this feature. "
                "Positive for bosses, negative for cuts."
            ),
        },
        "tolerance_mm3": {
            "type": "number",
            "minimum": 0,
            "default": 1.0,
            "description": (
                "Acceptable deviation from mass_delta_mm3. Defaults to 1.0 "
                "if omitted. Must be non-negative."
            ),
        },
    },
    "description": (
        "Per-feature postcondition expectation. The validator checks these "
        "before _strip_comments removes _-prefixed keys. The builder's "
        "--verify-mass mode compares actual volume deltas against these "
        "values after each feature."
    ),
}


# W39 — geometric relations between sketch entities. Optional field on every
# sketch-type feature. Each entry declares a relation type and the segment
# indices it operates on. Arity is enforced by the validator per type
# (coincident=2, symmetric=3, horizontal/vertical=1). The builder applies
# relations via ISketchManager.SketchAddConstraints after geometry draw.
_RELATION_TYPE_ENUM = [
    "horizontal",
    "vertical",
    "parallel",
    "perpendicular",
    "equal",
    "concentric",
]

RELATIONS_SCHEMA: dict[str, Any] = {
    "type": "array",
    "items": {
        "type": "object",
        "additionalProperties": False,
        "required": ["type", "entities"],
        "properties": {
            "type": {
                "enum": _RELATION_TYPE_ENUM,
                "description": (
                    "Geometric relation type. horizontal/vertical take 1 "
                    "entity; parallel/perpendicular/equal/concentric take 2. "
                    "collinear/coincident/symmetric are deferred (tokens "
                    "unproven on seat — see docs/DEFERRED.md)."
                ),
            },
            "entities": {
                "type": "array",
                "items": {"type": "integer", "minimum": 0},
                "minItems": 1,
                "maxItems": 3,
                "description": (
                    "0-based segment indices within the sketch (creation "
                    "order, including construction segments). Arity must "
                    "match the relation type."
                ),
            },
        },
    },
    "description": (
        "Geometric relations between sketch entities. Applied after geometry "
        "draw via ISketchManager.SketchAddConstraints. ⚠️ Token names are "
        "seat-gated (W21 radians lesson)."
    ),
}


# Face-direction enum, shared by all face-bound primitives.
_FACE_ENUM = ["+x", "-x", "+y", "-y", "+z", "-z"]


def _xyz_point(*, required: bool, description: str) -> dict[str, Any]:
    """An {x, y, z} number-object property. ``required`` toggles the x/y/z
    required list (used by pattern direction/axis and edge-point items)."""
    out: dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
    }
    if required:
        out["required"] = ["x", "y", "z"]
    out["properties"] = {
        "x": {"type": "number"},
        "y": {"type": "number"},
        "z": {"type": "number"},
    }
    out["description"] = description
    return out


# ---------------------------------------------------------------------------
# Per-primitive field lists. Field ORDER matters: assemble_feature_schema
# derives the `required` list from `["type", "name"] + required fields in
# this order`, so it must match the hand-written fragments' required order.
# ---------------------------------------------------------------------------

_SKETCH_PLANE_CENTER = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "x": {"type": "number"},
        "y": {"type": "number"},
        "z": {"type": "number"},
    },
}

_RECT_ON_PLANE_CENTER = {
    **_SKETCH_PLANE_CENTER,
    "description": (
        "Sketch-local center (mm). Default (0, 0, 0). The optional "
        "z offsets the sketch geometry along the part-frame Z axis "
        "and is required when sketching on Top Plane (XZ) at "
        "part-Z != 0, e.g. an O-ring groove at the mid-length of "
        "a +Z-extruded shaft. For Front (XY) and Right (YZ) planes "
        "leave z=0; only Top Plane's normal aligns with part-Z."
    ),
}

_CIRCLE_ON_PLANE_CENTER = {
    **_SKETCH_PLANE_CENTER,
    "description": (
        "Sketch-local center (mm). Default (0, 0, 0). See "
        "SKETCH_RECTANGLE_ON_PLANE for when the optional z is needed "
        "(Top Plane sketches positioned at part-Z != 0)."
    ),
}

_UV_CENTER_RECT_FACE = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"u": {"type": "number"}, "v": {"type": "number"}},
    "description": (
        "In-face center offset (mm) from the FACE SKETCH ORIGIN, "
        "which empirically is the projection of the part origin onto "
        "the face (NOT the face's geometric center). For a feature "
        "whose base sketch was a center-rectangle on origin these "
        "happen to coincide; for one shifted off origin (e.g. "
        "TensionBracket cap with Y span [0,15]) they don't, and "
        "child sketches need a u/v offset to land on the bracket "
        "centroid instead of the part origin. Default (0, 0)."
    ),
}

_UV_CENTER_CIRCLE_FACE = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"u": {"type": "number"}, "v": {"type": "number"}},
    "description": (
        "In-face center offset (mm) from the face SKETCH ORIGIN, "
        "which is the projection of the part origin onto the face "
        "(NOT the face's geometric center -- see SKETCH_RECTANGLE_ON_FACE). "
        "Default (0, 0)."
    ),
}

_UV_CENTER_HOLE = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"u": {"type": "number"}, "v": {"type": "number"}},
    "description": (
        "In-face center (mm) of the hole from the face SKETCH ORIGIN "
        "(= part-origin projection onto the face plane, NOT the face "
        "centroid -- see SKETCH_CIRCLE_ON_FACE for the gotcha). "
        "Default (0, 0)."
    ),
}

_ANGLE_DEG = {
    "type": "number",
    "exclusiveMinimum": 0,
    "maximum": 360,
    "default": 360.0,
    "description": (
        "Sweep angle in DEGREES (builder converts to radians). "
        "Default 360 = full revolution."
    ),
}

_EDGE_POINT_ITEM_FILLET = {
    "type": "array",
    "minItems": 1,
    "items": _xyz_point(
        required=True,
        description=(
            "A point on the target edge in part coordinates (mm). "
            "The builder converts to meters and calls SelectByID "
            "with type='EDGE'. Each edge entry adds one to the "
            "selection set before CreateFeature runs."
        ),
    ),
}

_EDGE_POINT_ITEM_CHAMFER = {
    "type": "array",
    "minItems": 1,
    "items": _xyz_point(
        required=True,
        description=(
            "A point on the target edge in part coordinates (mm). "
            "Builder converts to meters and calls SelectByID('EDGE')."
        ),
    ),
}


# ---------------------------------------------------------------------------
# P1.7s — shared sub-schemas for the seven sketch primitives below.
#
# All sketch primitives operate in sketch-local coordinates (millimetres from
# the sketch origin). ``_SKETCH_POINT_2D`` is the in-plane position (x, y);
# ``_SKETCH_POINT_3D`` adds an optional out-of-plane z for the rare 3D-sketch
# case. The ``z`` field is optional on the schema — when absent the handler
# defaults to 0 and calls the 2D COM path. Spline's ``_SKETCH_SPLINE_POINTS``
# is the variadic sequence version (minItems=2) used by the SAFEARRAY arg.
# ---------------------------------------------------------------------------

_SKETCH_POINT_2D: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["x", "y"],
    "properties": {
        "x": {"type": "number", "description": "X (mm) in sketch-local frame."},
        "y": {"type": "number", "description": "Y (mm) in sketch-local frame."},
    },
}

_SKETCH_POINT_3D: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["x", "y"],
    "properties": {
        "x": {"type": "number", "description": "X (mm) in sketch-local frame."},
        "y": {"type": "number", "description": "Y (mm) in sketch-local frame."},
        "z": {
            "type": "number",
            "default": 0.0,
            "description": "Out-of-plane Z (mm). Non-zero triggers the 3D-sketch COM path.",
        },
    },
}

_SKETCH_SPLINE_POINTS: dict[str, Any] = {
    "type": "array",
    "minItems": 2,
    "description": (
        "Control points in sketch-local coordinates (mm). At least 2 required. "
        "🔴 SEAT (P1.7-seat/W0): the live call packs these into a SAFEARRAY of "
        "doubles for ISketchManager.CreateSpline2 — the exact marshaling shape "
        "([x0,y0,x1,y1,...] vs [x0,y0,z0,x1,y1,z1,...]) and the b3D flag "
        "autoselect rule must be confirmed on the seat."
    ),
    "items": _SKETCH_POINT_3D,
}

_SLOT_TYPE_ENUM: dict[str, Any] = {
    "enum": ["arc"],
    "default": "arc",
    "description": (
        "End shape of the slot. Only 'arc' (rounded ends) is supported — the "
        "SOLIDWORKS CreateSketchSlot kernel call produces inherently rounded "
        "slots (there is no flat-ended creation type). For a flat-ended "
        "rectangular slot, use sketch_rectangle_on_plane instead."
    ),
}


FEATURE_FIELDS: dict[str, list[FieldSpec]] = {
    "sketch_rectangle_on_plane": [
        FieldSpec("plane", {"enum": ["Front", "Top", "Right"]}, True),
        FieldSpec("width", LENGTH_SCHEMA, True),
        FieldSpec("height", LENGTH_SCHEMA, True),
        FieldSpec("center", _RECT_ON_PLANE_CENTER, False),
        FieldSpec("centerline", CENTERLINE_SCHEMA, False),
        FieldSpec("relations", RELATIONS_SCHEMA, False),
    ],
    "sketch_rectangle_on_face": [
        FieldSpec(
            "of_feature",
            {"type": "string", "description": "Name of an earlier extrusion feature."},
            True,
        ),
        FieldSpec(
            "face",
            {
                "enum": _FACE_ENUM,
                "description": "Outward normal direction of the face in the feature's local frame.",
            },
            True,
        ),
        FieldSpec("width", LENGTH_SCHEMA, True),
        FieldSpec("height", LENGTH_SCHEMA, True),
        FieldSpec("center", _UV_CENTER_RECT_FACE, False),
        FieldSpec("relations", RELATIONS_SCHEMA, False),
    ],
    "sketch_circle_on_plane": [
        FieldSpec("plane", {"enum": ["Front", "Top", "Right"]}, True),
        FieldSpec("diameter", LENGTH_SCHEMA, True),
        FieldSpec("center", _CIRCLE_ON_PLANE_CENTER, False),
        FieldSpec("centerline", CENTERLINE_SCHEMA, False),
        FieldSpec("relations", RELATIONS_SCHEMA, False),
    ],
    "sketch_circle_on_face": [
        FieldSpec(
            "of_feature",
            {"type": "string", "description": "Name of an earlier extrusion feature."},
            True,
        ),
        FieldSpec(
            "face",
            {
                "enum": _FACE_ENUM,
                "description": "Outward normal direction of the face in the feature's local frame.",
            },
            True,
        ),
        FieldSpec("diameter", LENGTH_SCHEMA, True),
        FieldSpec("center", _UV_CENTER_CIRCLE_FACE, False),
        FieldSpec("relations", RELATIONS_SCHEMA, False),
    ],
    "sketch_circles_on_face": [
        FieldSpec("of_feature", {"type": "string"}, True),
        FieldSpec("face", {"enum": _FACE_ENUM}, True),
        FieldSpec(
            "circles",
            {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["u", "v", "diameter"],
                    "properties": {
                        "u": {
                            "type": "number",
                            "description": (
                                "Center u-offset (mm) from the face SKETCH ORIGIN "
                                "(= part-origin projection onto the face, NOT face "
                                "centroid -- see SKETCH_RECTANGLE_ON_FACE for the gotcha)."
                            ),
                        },
                        "v": {"type": "number"},
                        "diameter": LENGTH_SCHEMA,
                    },
                },
            },
            True,
        ),
        FieldSpec("relations", RELATIONS_SCHEMA, False),
    ],
    "boss_extrude_blind": [
        FieldSpec(
            "sketch",
            {"type": "string", "description": "Name of an earlier sketch feature to extrude."},
            True,
        ),
        FieldSpec("depth", LENGTH_SCHEMA, True),
        FieldSpec(
            "flip",
            {
                "type": "boolean",
                "default": False,
                "description": "Extrude in -normal instead of +normal direction.",
            },
            False,
        ),
    ],
    "cut_extrude_through_all": [
        FieldSpec(
            "sketch",
            {"type": "string", "description": "Name of an earlier sketch to cut along."},
            True,
        ),
        FieldSpec(
            "flip",
            {
                "type": "boolean",
                "default": False,
                "description": "Cut in -normal instead of +normal direction.",
            },
            False,
        ),
    ],
    "cut_extrude_blind": [
        FieldSpec("sketch", {"type": "string"}, True),
        FieldSpec("depth", LENGTH_SCHEMA, True),
        FieldSpec("flip", {"type": "boolean", "default": False}, False),
    ],
    "cut_extrude_midplane": [
        FieldSpec("sketch", {"type": "string"}, True),
        FieldSpec(
            "depth",
            LENGTH_SCHEMA,
            True,
        ),
        FieldSpec("flip", {"type": "boolean", "default": False}, False),
    ],
    "cut_extrude_two_direction": [
        FieldSpec("sketch", {"type": "string"}, True),
        FieldSpec("depth", LENGTH_SCHEMA, True),
        FieldSpec("depth2", LENGTH_SCHEMA, True),
        FieldSpec("flip", {"type": "boolean", "default": False}, False),
    ],
    "revolve_boss": [
        FieldSpec(
            "sketch",
            {
                "type": "string",
                "description": (
                    "Name of an earlier plane-based sketch that contains "
                    "both a closed profile and an embedded centerline. "
                    "SW auto-picks the centerline as the axis of revolution."
                ),
            },
            True,
        ),
        FieldSpec("angle", _ANGLE_DEG, False),
        FieldSpec(
            "flip",
            {"type": "boolean", "default": False, "description": "Reverse the revolve direction."},
            False,
        ),
    ],
    "revolve_cut": [
        FieldSpec(
            "sketch",
            {
                "type": "string",
                "description": (
                    "Name of an earlier plane-based sketch that contains "
                    "both a closed profile and an embedded centerline. "
                    "SW auto-picks the centerline as the axis of revolution. "
                    "The profile, when revolved, must intersect existing body "
                    "material -- otherwise SW silently produces no geometry."
                ),
            },
            True,
        ),
        FieldSpec("angle", _ANGLE_DEG, False),
        FieldSpec(
            "flip",
            {"type": "boolean", "default": False, "description": "Reverse the revolve direction."},
            False,
        ),
    ],
    "simple_hole": [
        FieldSpec(
            "of_feature",
            {"type": "string", "description": "Name of an earlier extrusion feature."},
            True,
        ),
        FieldSpec(
            "face",
            {
                "enum": _FACE_ENUM,
                "description": "Outward normal of the face the hole drills into.",
            },
            True,
        ),
        FieldSpec("center", _UV_CENTER_HOLE, False),
        FieldSpec("diameter", LENGTH_SCHEMA, True),
        FieldSpec(
            "end_condition",
            {
                "enum": ["blind", "through_all"],
                "default": "blind",
                "description": (
                    "Hole depth termination. 'blind' uses `depth`; 'through_all' "
                    "drills all the way through and ignores `depth`."
                ),
            },
            False,
        ),
        FieldSpec("depth", LENGTH_SCHEMA, False),
    ],
    "fillet_constant_radius": [
        FieldSpec("radius", LENGTH_SCHEMA, True),
        FieldSpec("edges", _EDGE_POINT_ITEM_FILLET, True),
    ],
    "chamfer_edge": [
        FieldSpec(
            "mode",
            {
                "enum": ["equal_distance", "distance_angle"],
                "description": (
                    "Chamfer geometry mode. 'equal_distance' takes a single "
                    "distance and applies it to both sides. 'distance_angle' "
                    "takes a distance plus an angle in degrees, measured from "
                    "one face of the chamfered edge."
                ),
            },
            True,
        ),
        FieldSpec(
            "distance",
            {
                **LENGTH_SCHEMA,
                "description": "Chamfer distance from edge (mm). Required for both modes.",
            },
            False,
        ),
        FieldSpec(
            "angle",
            {
                **LENGTH_SCHEMA,
                "description": (
                    "Chamfer angle in DEGREES. Required for mode "
                    "'distance_angle', forbidden for mode 'equal_distance'. "
                    "Despite reusing LENGTH_SCHEMA for parametric support, this "
                    "is an angle in degrees -- the spec author is responsible "
                    "for not passing a length-typed locals var here."
                ),
            },
            False,
        ),
        FieldSpec(
            "flip",
            {
                "type": "boolean",
                "default": False,
                "description": (
                    "Reverse the chamfer asymmetry direction. Only meaningful "
                    "for 'distance_angle' (the equal-distance case is symmetric)."
                ),
            },
            False,
        ),
        FieldSpec("edges", _EDGE_POINT_ITEM_CHAMFER, True),
    ],
    "linear_pattern": [
        FieldSpec(
            "seed",
            {
                "type": "string",
                "description": (
                    "Name of an earlier feature to pattern. The seed itself "
                    "counts as instance 1; `count` includes it."
                ),
            },
            True,
        ),
        FieldSpec(
            "direction",
            _xyz_point(
                required=True,
                description=(
                    "A point on a model edge whose direction defines the pattern "
                    "axis. The builder selects the edge with SelectByID and uses "
                    "its tangent at that point."
                ),
            ),
            True,
        ),
        FieldSpec(
            "count",
            {
                "type": "integer",
                "minimum": 2,
                "description": (
                    "Total number of instances along Direction 1 (includes the "
                    "seed). Must be >= 2 -- a count of 1 would be a no-op."
                ),
            },
            True,
        ),
        FieldSpec(
            "spacing",
            {**LENGTH_SCHEMA, "description": "Distance between consecutive instances (mm)."},
            True,
        ),
        FieldSpec(
            "flip",
            {
                "type": "boolean",
                "default": False,
                "description": "Reverse pattern direction relative to the selected edge's tangent.",
            },
            False,
        ),
    ],
    "circular_pattern": [
        FieldSpec(
            "seed",
            {
                "type": "string",
                "description": (
                    "Name of an earlier feature to pattern. The seed itself "
                    "counts as instance 1; `count` includes it."
                ),
            },
            True,
        ),
        FieldSpec(
            "axis",
            _xyz_point(
                required=True,
                description=(
                    "A point on the rotation-axis reference -- either a circular "
                    "EDGE (e.g. the rim of a cylindrical face) or a cylindrical "
                    "FACE. The builder tries EDGE first, then FACE on fallback. "
                    "SW infers the axis of revolution from the selected entity."
                ),
            ),
            True,
        ),
        FieldSpec(
            "count",
            {
                "type": "integer",
                "minimum": 2,
                "description": (
                    "Total number of instances around the axis (includes the "
                    "seed). Must be >= 2 -- a count of 1 would be a no-op."
                ),
            },
            True,
        ),
        FieldSpec(
            "total_angle",
            {
                "type": "number",
                "exclusiveMinimum": 0,
                "maximum": 360,
                "default": 360.0,
                "description": (
                    "Total sweep angle in DEGREES (builder converts to radians). "
                    "Default 360 = full circle, equally spaced. For a half-fan "
                    "of 4 instances over 180 degrees, set total_angle=180."
                ),
            },
            False,
        ),
        FieldSpec(
            "flip",
            {"type": "boolean", "default": False, "description": "Reverse the rotation direction."},
            False,
        ),
    ],
    "mirror_feature": [
        FieldSpec(
            "seed",
            {"type": "string", "description": "Name of an earlier feature to mirror."},
            True,
        ),
        FieldSpec(
            "plane",
            {
                "enum": ["Front", "Top", "Right"],
                "description": (
                    "Default reference plane to mirror about. Front = XY (mirrors "
                    "Z), Top = XZ (mirrors Y), Right = YZ (mirrors X)."
                ),
            },
            True,
        ),
    ],
    # ---------------------------------------------------------------------------
    # P1.7s — sketch primitives (line / arc / spline / slot / polygon / ellipse /
    # text). Each is a single sketch-feature entry; all seven are live + seat-
    # validated (SW 2024, rev 32.1.0). Full-fidelity flags are constrained to
    # what the seat's API genuinely supports: `construction` ships on every
    # segment primitive EXCEPT slot (CreateSketchSlot's return is a read-only
    # slot object, not a settable segment); text carries `height`+`font` (via
    # ISketchText.GetTextFormat/SetTextFormat). Fields with no out-of-process
    # API on this seat are intentionally absent so a request fails cleanly at
    # validation rather than being silently faked: spline `closed` (yields a C0
    # cusp, not a periodic spline — no MakeClosed/CreateClosedSpline exists),
    # text `angle_deg` (no angle on InsertSketchText/ITextFormat) and text/slot
    # `construction`. Parametric `{rhs}` bindings are supported on every
    # LENGTH_SCHEMA field via the standard Equation Manager pathway.
    # ---------------------------------------------------------------------------
    "sketch_line": [
        FieldSpec(
            "plane",
            {
                "enum": ["Front", "Top", "Right"],
                "description": "Default reference plane to host the sketch.",
            },
            True,
        ),
        FieldSpec("start", _SKETCH_POINT_2D, True),
        FieldSpec("end", _SKETCH_POINT_2D, True),
        FieldSpec(
            "construction",
            {
                "type": "boolean",
                "default": False,
                "description": "If true, mark the segment as a construction (centerline) entity.",
            },
            False,
        ),
        FieldSpec("relations", RELATIONS_SCHEMA, False),
    ],
    "sketch_arc": [
        FieldSpec(
            "plane",
            {
                "enum": ["Front", "Top", "Right"],
                "description": "Default reference plane to host the sketch.",
            },
            True,
        ),
        FieldSpec("center", _SKETCH_POINT_2D, True),
        FieldSpec("start", _SKETCH_POINT_2D, True),
        FieldSpec("end", _SKETCH_POINT_2D, True),
        FieldSpec(
            "direction",
            {
                "enum": ["cw", "ccw"],
                "default": "ccw",
                "description": "Arc direction from start to end about the center.",
            },
            False,
        ),
        FieldSpec(
            "construction",
            {"type": "boolean", "default": False},
            False,
        ),
        FieldSpec("relations", RELATIONS_SCHEMA, False),
    ],
    "sketch_spline": [
        FieldSpec(
            "plane",
            {
                "enum": ["Front", "Top", "Right"],
                "description": "Default reference plane to host the sketch.",
            },
            True,
        ),
        FieldSpec("points", _SKETCH_SPLINE_POINTS, True),
        FieldSpec(
            "construction",
            {
                "type": "boolean",
                "default": False,
                "description": "If true, mark the spline as a construction entity.",
            },
            False,
        ),
        # NOTE: no `closed` field. A point-based periodic (C2) closed spline has
        # no out-of-process API on this seat — ISketchSpline.MakeClosed and
        # ISketchManager.CreateClosedSpline do not exist (verified via
        # GetIDsOfNames -> DISP_E_UNKNOWNNAME and a full typelib scan), and
        # appending the first point yields a C0 cusp, not a periodic spline.
        # Requesting `closed` therefore fails validation rather than faking it.
        FieldSpec("relations", RELATIONS_SCHEMA, False),
    ],
    "sketch_slot": [
        FieldSpec(
            "plane",
            {
                "enum": ["Front", "Top", "Right"],
                "description": "Default reference plane to host the sketch.",
            },
            True,
        ),
        FieldSpec("center", _SKETCH_POINT_2D, True),
        FieldSpec("width", LENGTH_SCHEMA, True),
        FieldSpec("length", LENGTH_SCHEMA, True),
        FieldSpec("slot_type", _SLOT_TYPE_ENUM, False),
        FieldSpec(
            "angle_deg",
            {
                "type": "number",
                "default": 0.0,
                "description": "Rotation of the slot's major axis from the sketch X axis (degrees).",
            },
            False,
        ),
        # NOTE: no `construction` field. CreateSketchSlot returns a read-only
        # slot object (not a settable ISketchSegment): `ConstructionGeometry
        # can not be set` on the seat. Unpacking the macro-feature's underlying
        # segment array to mutate each is COM-index fragile, so construction is
        # rejected for slots rather than faked.
        FieldSpec("relations", RELATIONS_SCHEMA, False),
    ],
    "sketch_polygon": [
        FieldSpec(
            "plane",
            {
                "enum": ["Front", "Top", "Right"],
                "description": "Default reference plane to host the sketch.",
            },
            True,
        ),
        FieldSpec("center", _SKETCH_POINT_2D, True),
        FieldSpec(
            "sides",
            {
                "type": "integer",
                "minimum": 3,
                "maximum": 40,
                "description": "Number of polygon sides (3..40).",
            },
            True,
        ),
        FieldSpec("radius", LENGTH_SCHEMA, True),
        FieldSpec(
            "inscribed",
            {
                "type": "boolean",
                "default": True,
                "description": (
                    "If true, `radius` is the inscribed (apothem) radius — polygon "
                    "edges are tangent to the circle. If false, `radius` is the "
                    "circumscribed radius — polygon vertices lie on the circle."
                ),
            },
            False,
        ),
        FieldSpec(
            "angle_deg",
            {
                "type": "number",
                "default": 0.0,
                "description": "Rotation of the polygon's first vertex from the sketch X axis (degrees).",
            },
            False,
        ),
        FieldSpec(
            "construction",
            {"type": "boolean", "default": False},
            False,
        ),
        FieldSpec("relations", RELATIONS_SCHEMA, False),
    ],
    "sketch_ellipse": [
        FieldSpec(
            "plane",
            {
                "enum": ["Front", "Top", "Right"],
                "description": "Default reference plane to host the sketch.",
            },
            True,
        ),
        FieldSpec("center", _SKETCH_POINT_2D, True),
        FieldSpec("major_radius", LENGTH_SCHEMA, True),
        FieldSpec("minor_radius", LENGTH_SCHEMA, True),
        FieldSpec(
            "angle_deg",
            {
                "type": "number",
                "default": 0.0,
                "description": "Rotation of the major axis from the sketch X axis (degrees).",
            },
            False,
        ),
        FieldSpec(
            "construction",
            {"type": "boolean", "default": False},
            False,
        ),
        FieldSpec("relations", RELATIONS_SCHEMA, False),
    ],
    "sketch_text": [
        FieldSpec(
            "plane",
            {
                "enum": ["Front", "Top", "Right"],
                "description": "Default reference plane to host the sketch.",
            },
            True,
        ),
        FieldSpec("position", _SKETCH_POINT_2D, True),
        FieldSpec(
            "content",
            {
                "type": "string",
                "minLength": 1,
                "description": "Text content. Plain ASCII; no rich formatting.",
            },
            True,
        ),
        FieldSpec("height", LENGTH_SCHEMA, True),
        FieldSpec(
            "font",
            {
                "type": "string",
                "description": (
                    "Font family name (e.g. 'Arial'). Applied via the inserted "
                    "ISketchText's text format (GetTextFormat -> TypeFaceName -> "
                    "SetTextFormat); `height` sets CharHeight in the same call."
                ),
            },
            False,
        ),
        # NOTE: no `angle_deg` or `construction` field for text. InsertSketchText
        # exposes no angle parameter and ITextFormat carries no rotation, so text
        # baseline rotation has no out-of-process API on this seat; and text is
        # not a sketch segment, so ConstructionGeometry does not apply. Both are
        # rejected at validation rather than silently ignored.
        FieldSpec("relations", RELATIONS_SCHEMA, False),
    ],
}


# Per-primitive coverage metadata (X3, FR-X-03). Read by the doc-coverage test
# (tests/test_descriptor_doc_coverage.py) so docs/examples can't silently drift
# from the shipped primitives. `doc` is a one-line human summary; `example_ref`
# names the canonical examples/<dir> that exercises the primitive. `sw_min` is
# the proven SW version (all handlers are GREEN on 2024 SP1); `spike_id` cites
# the spike that GREEN-gated the COM signature where one is on record.
FEATURE_META: dict[str, dict[str, Any]] = {
    "sketch_rectangle_on_plane": {
        "doc": "Rectangular profile sketch on a default reference plane (Front/Top/Right).",
        "example_ref": "chamfered_box",
        "risk_tier": "safe",
        "sw_min": "2024 SP1",
        "spike_id": None,
    },
    "sketch_rectangle_on_face": {
        "doc": "Rectangular profile sketch on an existing feature's orthogonal face.",
        "example_ref": "tension_bracket",
        "risk_tier": "safe",
        "sw_min": "2024 SP1",
        "spike_id": None,
    },
    "sketch_circle_on_plane": {
        "doc": "Circular profile sketch on a default reference plane.",
        "example_ref": "drive_roller",
        "risk_tier": "safe",
        "sw_min": "2024 SP1",
        "spike_id": None,
    },
    "sketch_circle_on_face": {
        "doc": "Circular profile sketch on an existing feature's face.",
        "example_ref": "drive_roller",
        "risk_tier": "safe",
        "sw_min": "2024 SP1",
        "spike_id": None,
    },
    "sketch_circles_on_face": {
        "doc": "Multiple circles in one sketch on a face (e.g. a hole pattern).",
        "example_ref": "motor_mount_plate",
        "risk_tier": "safe",
        "sw_min": "2024 SP1",
        "spike_id": None,
    },
    "boss_extrude_blind": {
        "doc": "Blind boss extrusion of a sketch to a given depth.",
        "example_ref": "chamfered_box",
        "risk_tier": "safe",
        "sw_min": "2024 SP1",
        "spike_id": None,
    },
    "cut_extrude_through_all": {
        "doc": "Through-all cut extrusion along a sketch.",
        "example_ref": "drive_roller",
        "risk_tier": "safe",
        "sw_min": "2024 SP1",
        "spike_id": None,
    },
    "cut_extrude_blind": {
        "doc": "Blind cut extrusion of a sketch to a given depth.",
        "example_ref": "drive_roller",
        "risk_tier": "safe",
        "sw_min": "2024 SP1",
        "spike_id": None,
    },
    "cut_extrude_midplane": {
        "doc": "Mid-plane cut extrusion: removes `depth` of material centred on "
        "the sketch plane (depth/2 each side).",
        "example_ref": "end_condition_cuts",
        "risk_tier": "safe",
        "sw_min": "2024 SP1",
        "spike_id": "spike_cut_endcond",
    },
    "cut_extrude_two_direction": {
        "doc": "Two-direction blind cut: `depth` into +normal and `depth2` into "
        "-normal from the sketch plane.",
        "example_ref": "end_condition_cuts",
        "risk_tier": "safe",
        "sw_min": "2024 SP1",
        "spike_id": "spike_cut_endcond",
    },
    "revolve_boss": {
        "doc": "Solid revolve of a profile about its embedded centerline.",
        "example_ref": "grooved_shaft",
        "risk_tier": "safe",
        "sw_min": "2024 SP1",
        "spike_id": "Spike ZP/ZQ",
    },
    "revolve_cut": {
        "doc": "Subtractive revolve of a profile about its embedded centerline.",
        "example_ref": "drive_roller",
        "risk_tier": "safe",
        "sw_min": "2024 SP1",
        "spike_id": "Spike ZP/ZQ",
    },
    "simple_hole": {
        "doc": "Single straight-bore hole drilled into a face (blind or through-all).",
        "example_ref": "drilled_plate",
        "risk_tier": "safe",
        "sw_min": "2024 SP1",
        "spike_id": None,
    },
    "fillet_constant_radius": {
        "doc": "Constant-radius fillet on selected edges.",
        "example_ref": "filleted_box",
        "risk_tier": "safe",
        "sw_min": "2024 SP1",
        "spike_id": "Spike P",
    },
    "chamfer_edge": {
        "doc": "Edge chamfer (equal-distance or distance-angle).",
        "example_ref": "chamfered_box",
        "risk_tier": "safe",
        "sw_min": "2024 SP1",
        "spike_id": "Spike Q",
    },
    "linear_pattern": {
        "doc": "Linear pattern of a seed feature along a model-edge direction.",
        "example_ref": "patterned_plate",
        "risk_tier": "safe",
        "sw_min": "2024 SP1",
        "spike_id": None,
    },
    "circular_pattern": {
        "doc": "Circular pattern of a seed feature about an axis reference.",
        "example_ref": "patterned_disc",
        "risk_tier": "safe",
        "sw_min": "2024 SP1",
        "spike_id": "Spike T",
    },
    "mirror_feature": {
        "doc": "Mirror of a seed feature about a default reference plane.",
        "example_ref": "mirrored_holes",
        "risk_tier": "safe",
        "sw_min": "2024 SP1",
        "spike_id": None,
    },
    # ---------------------------------------------------------------------------
    # P1.7s — sketch primitives. Handlers are SW-free stubs that assemble the
    # arg tuple and flag the live ISketchManager.Create* call 🔴 SEAT for the
    # P1.7-seat/W0 pass. The single consolidated example `sketch_primitives`
    # exercises all seven types in one spec.
    # ---------------------------------------------------------------------------
    "sketch_line": {
        "doc": "Single line segment on a reference plane (start → end).",
        "example_ref": "sketch_primitives",
        "risk_tier": "seat_stub",
        "sw_min": "2024 SP1",
        "spike_id": "P1.7s (stub)",
    },
    "sketch_arc": {
        "doc": "Circular arc on a reference plane (center + start + end).",
        "example_ref": "sketch_primitives",
        "risk_tier": "seat_stub",
        "sw_min": "2024 SP1",
        "spike_id": "P1.7s (stub)",
    },
    "sketch_spline": {
        "doc": "Freeform spline through a sequence of control points.",
        "example_ref": "sketch_primitives",
        "risk_tier": "seat_stub",
        "sw_min": "2024 SP1",
        "spike_id": "P1.7s (stub, SAFEARRAY 🔴 SEAT)",
    },
    "sketch_slot": {
        "doc": "Rectangular or arc-ended slot on a reference plane.",
        "example_ref": "sketch_primitives",
        "risk_tier": "seat_stub",
        "sw_min": "2024 SP1",
        "spike_id": "P1.7s (stub)",
    },
    "sketch_polygon": {
        "doc": "Regular N-sided polygon on a reference plane.",
        "example_ref": "sketch_primitives",
        "risk_tier": "seat_stub",
        "sw_min": "2024 SP1",
        "spike_id": "P1.7s (stub)",
    },
    "sketch_ellipse": {
        "doc": "Ellipse with major/minor radii on a reference plane.",
        "example_ref": "sketch_primitives",
        "risk_tier": "seat_stub",
        "sw_min": "2024 SP1",
        "spike_id": "P1.7s (stub)",
    },
    "sketch_text": {
        "doc": "Plain-text annotation sketch on a reference plane.",
        "example_ref": "sketch_primitives",
        "risk_tier": "seat_stub",
        "sw_min": "2024 SP1",
        "spike_id": "P1.7s (stub, font bitfield 🔴 SEAT)",
    },
}


# The oneOf order in the top-level SCHEMA (preserved from the hand-written
# list so the assembled schema is identical, not just equivalent).
FEATURE_ORDER: list[str] = [
    "sketch_rectangle_on_plane",
    "sketch_rectangle_on_face",
    "sketch_circle_on_plane",
    "sketch_circle_on_face",
    "sketch_circles_on_face",
    "boss_extrude_blind",
    "cut_extrude_through_all",
    "cut_extrude_blind",
    "cut_extrude_midplane",
    "cut_extrude_two_direction",
    "revolve_boss",
    "revolve_cut",
    "simple_hole",
    "fillet_constant_radius",
    "chamfer_edge",
    "linear_pattern",
    "circular_pattern",
    "mirror_feature",
    # P1.7s — sketch primitives (stub handlers, flagged 🔴 SEAT for P1.7-seat/W0).
    "sketch_line",
    "sketch_arc",
    "sketch_spline",
    "sketch_slot",
    "sketch_polygon",
    "sketch_ellipse",
    "sketch_text",
]


def assemble_feature_schema(name: str) -> dict[str, Any]:
    """Assemble one primitive's JSON-Schema fragment from its FieldSpec list.

    Wraps the declarative fields in the common object envelope: the shared
    ``type`` const + ``name`` pattern, ``additionalProperties: False``, and a
    ``required`` list of ``["type", "name"]`` followed by the required fields
    in declared order.
    """
    fields = FEATURE_FIELDS[name]
    properties: dict[str, Any] = {
        "type": {"const": name},
        "name": NAME_PATTERN,
    }
    required: list[str] = ["type", "name"]
    for f in fields:
        properties[f.name] = f.schema
        if f.required:
            required.append(f.name)
    return {
        "type": "object",
        "additionalProperties": False,
        "required": required,
        "properties": properties,
    }


def assemble_all() -> list[dict[str, Any]]:
    """The full list of feature fragments, in FEATURE_ORDER (for SCHEMA's oneOf)."""
    return [assemble_feature_schema(name) for name in FEATURE_ORDER]
