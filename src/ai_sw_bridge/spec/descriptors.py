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


FEATURE_FIELDS: dict[str, list[FieldSpec]] = {
    "sketch_rectangle_on_plane": [
        FieldSpec("plane", {"enum": ["Front", "Top", "Right"]}, True),
        FieldSpec("width", LENGTH_SCHEMA, True),
        FieldSpec("height", LENGTH_SCHEMA, True),
        FieldSpec("center", _RECT_ON_PLANE_CENTER, False),
        FieldSpec("centerline", CENTERLINE_SCHEMA, False),
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
    ],
    "sketch_circle_on_plane": [
        FieldSpec("plane", {"enum": ["Front", "Top", "Right"]}, True),
        FieldSpec("diameter", LENGTH_SCHEMA, True),
        FieldSpec("center", _CIRCLE_ON_PLANE_CENTER, False),
        FieldSpec("centerline", CENTERLINE_SCHEMA, False),
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
    "revolve_boss",
    "revolve_cut",
    "simple_hole",
    "fillet_constant_radius",
    "chamfer_edge",
    "linear_pattern",
    "circular_pattern",
    "mirror_feature",
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
