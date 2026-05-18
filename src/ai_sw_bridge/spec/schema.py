"""
JSON schema for the v0.2 declarative part spec.

This is the single source of truth for the spec format. Both the AI agent
(when emitting) and the validator/builder (when consuming) reference it.

Design rules:
- All lengths in MILLIMETRES at the spec layer. Builder converts to meters
  (SW's internal unit) before each COM call. The AI doesn't have to know
  SW uses SI.
- A `length` value is either a literal number (mm) or {"rhs": "<expr>"} where
  expr is a SW Equation Manager expression. RHS strings get pasted verbatim
  into EquationMgr.Add2 - the user must quote variable references themselves
  (e.g. `"\"S1B_MMP_W\""` for a bare var, `"\"S1B_X\" + 0.5"` for an expr).
- Features have unique `name` (within the spec) and are built in declared
  order. References to earlier features use that `name`.
- Planes: the three default reference planes are "Front", "Top", "Right"
  (matching SW's English UI). v1 doesn't support custom reference planes.
- Faces: a face is referenced by `of_feature: "<feat_name>", face: "<spec>"`
  where face spec is one of "+x" "-x" "+y" "-y" "+z" "-z" (the local outward
  normal direction of the feature). The builder computes the face center coord
  from the feature's geometry. v1 only supports orthogonal faces of extrusions.
"""

from __future__ import annotations

from typing import Any

SCHEMA_VERSION = 1


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


# Per-feature schemas
SKETCH_RECTANGLE_ON_PLANE: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["type", "name", "plane", "width", "height"],
    "properties": {
        "type": {"const": "sketch_rectangle_on_plane"},
        "name": {"type": "string", "pattern": "^[A-Za-z_][A-Za-z0-9_]*$"},
        "plane": {"enum": ["Front", "Top", "Right"]},
        "width": LENGTH_SCHEMA,
        "height": LENGTH_SCHEMA,
        "center": {
            "type": "object",
            "additionalProperties": False,
            "properties": {"x": {"type": "number"}, "y": {"type": "number"}},
            "description": "Sketch-local center (mm). Default (0, 0).",
        },
    },
}


SKETCH_CIRCLE_ON_PLANE: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["type", "name", "plane", "diameter"],
    "properties": {
        "type": {"const": "sketch_circle_on_plane"},
        "name": {"type": "string", "pattern": "^[A-Za-z_][A-Za-z0-9_]*$"},
        "plane": {"enum": ["Front", "Top", "Right"]},
        "diameter": LENGTH_SCHEMA,
        "center": {
            "type": "object",
            "additionalProperties": False,
            "properties": {"x": {"type": "number"}, "y": {"type": "number"}},
            "description": "Sketch-local center (mm). Default (0, 0).",
        },
    },
}


SKETCH_RECTANGLE_ON_FACE: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["type", "name", "of_feature", "face", "width", "height"],
    "properties": {
        "type": {"const": "sketch_rectangle_on_face"},
        "name": {"type": "string", "pattern": "^[A-Za-z_][A-Za-z0-9_]*$"},
        "of_feature": {
            "type": "string",
            "description": "Name of an earlier extrusion feature.",
        },
        "face": {
            "enum": ["+x", "-x", "+y", "-y", "+z", "-z"],
            "description": "Outward normal direction of the face in the feature's local frame.",
        },
        "width": LENGTH_SCHEMA,
        "height": LENGTH_SCHEMA,
        "center": {
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
        },
    },
}


SKETCH_CIRCLE_ON_FACE: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["type", "name", "of_feature", "face", "diameter"],
    "properties": {
        "type": {"const": "sketch_circle_on_face"},
        "name": {"type": "string", "pattern": "^[A-Za-z_][A-Za-z0-9_]*$"},
        "of_feature": {
            "type": "string",
            "description": "Name of an earlier extrusion feature.",
        },
        "face": {
            "enum": ["+x", "-x", "+y", "-y", "+z", "-z"],
            "description": "Outward normal direction of the face in the feature's local frame.",
        },
        "diameter": LENGTH_SCHEMA,
        "center": {
            "type": "object",
            "additionalProperties": False,
            "properties": {"u": {"type": "number"}, "v": {"type": "number"}},
            "description": (
                "In-face center offset (mm) from the face SKETCH ORIGIN, "
                "which is the projection of the part origin onto the face "
                "(NOT the face's geometric center -- see SKETCH_RECTANGLE_ON_FACE). "
                "Default (0, 0)."
            ),
        },
    },
}


# Multi-circle variant: all circles in one sketch (typical for a hole pattern).
# Each circle gets its own diameter dim numbered in selection order: D1, D2, ...
# v1 limit: circle CENTER positions are literal (mm). Parametric positions are
# deferred to v1.1 (needs sketch relations, not just dims).
SKETCH_CIRCLES_ON_FACE: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["type", "name", "of_feature", "face", "circles"],
    "properties": {
        "type": {"const": "sketch_circles_on_face"},
        "name": {"type": "string", "pattern": "^[A-Za-z_][A-Za-z0-9_]*$"},
        "of_feature": {"type": "string"},
        "face": {"enum": ["+x", "-x", "+y", "-y", "+z", "-z"]},
        "circles": {
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
    },
}


BOSS_EXTRUDE_BLIND: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["type", "name", "sketch", "depth"],
    "properties": {
        "type": {"const": "boss_extrude_blind"},
        "name": {"type": "string", "pattern": "^[A-Za-z_][A-Za-z0-9_]*$"},
        "sketch": {
            "type": "string",
            "description": "Name of an earlier sketch feature to extrude.",
        },
        "depth": LENGTH_SCHEMA,
        "flip": {
            "type": "boolean",
            "default": False,
            "description": "Extrude in -normal instead of +normal direction.",
        },
    },
}


CUT_EXTRUDE_THROUGH_ALL: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["type", "name", "sketch"],
    "properties": {
        "type": {"const": "cut_extrude_through_all"},
        "name": {"type": "string", "pattern": "^[A-Za-z_][A-Za-z0-9_]*$"},
        "sketch": {
            "type": "string",
            "description": "Name of an earlier sketch to cut along.",
        },
        "flip": {
            "type": "boolean",
            "default": False,
            "description": "Cut in -normal instead of +normal direction.",
        },
    },
}


CUT_EXTRUDE_BLIND: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["type", "name", "sketch", "depth"],
    "properties": {
        "type": {"const": "cut_extrude_blind"},
        "name": {"type": "string", "pattern": "^[A-Za-z_][A-Za-z0-9_]*$"},
        "sketch": {"type": "string"},
        "depth": LENGTH_SCHEMA,
        "flip": {"type": "boolean", "default": False},
    },
}


# Edge chamfer. Two modes, selected by `mode`:
#   - "equal_distance": single `distance` applied to both sides of each edge.
#     Schema requires `distance` and forbids `width`/`angle`.
#   - "distance_angle": one `distance` plus an `angle` (degrees). Schema
#     requires both. The angle is measured from one face of the chamfered
#     edge -- which face depends on the edge's local orientation.
#
# Edge selection mirrors fillet's: a point-on-edge list, one entry per edge.
#
# v1 limits:
#   - No distance-distance mode (would need a second `distance2`). The two
#     shipped modes cover the common cases; can be added later without
#     breaking change.
#   - No vertex chamfer. swChamferVertex requires a vertex with exactly 3
#     adjacent edges of matching convexity -- niche, defer.
#   - Edge selection by point only (one point per edge).
CHAMFER_EDGE: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["type", "name", "mode", "edges"],
    "properties": {
        "type": {"const": "chamfer_edge"},
        "name": {"type": "string", "pattern": "^[A-Za-z_][A-Za-z0-9_]*$"},
        "mode": {
            "enum": ["equal_distance", "distance_angle"],
            "description": (
                "Chamfer geometry mode. 'equal_distance' takes a single "
                "distance and applies it to both sides. 'distance_angle' "
                "takes a distance plus an angle in degrees, measured from "
                "one face of the chamfered edge."
            ),
        },
        "distance": {
            **LENGTH_SCHEMA,
            "description": "Chamfer distance from edge (mm). Required for both modes.",
        },
        "angle": {
            **LENGTH_SCHEMA,
            "description": (
                "Chamfer angle in DEGREES. Required for mode "
                "'distance_angle', forbidden for mode 'equal_distance'. "
                "Despite reusing LENGTH_SCHEMA for parametric support, this "
                "is an angle in degrees -- the spec author is responsible "
                "for not passing a length-typed locals var here."
            ),
        },
        "flip": {
            "type": "boolean",
            "default": False,
            "description": (
                "Reverse the chamfer asymmetry direction. Only meaningful "
                "for 'distance_angle' (the equal-distance case is symmetric)."
            ),
        },
        "edges": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["x", "y", "z"],
                "properties": {
                    "x": {"type": "number"},
                    "y": {"type": "number"},
                    "z": {"type": "number"},
                },
                "description": (
                    "A point on the target edge in part coordinates (mm). "
                    "Builder converts to meters and calls SelectByID('EDGE')."
                ),
            },
        },
    },
}


# Linear pattern of an earlier feature. Replicates one or more seed features
# along a direction reference (an edge of the model whose direction defines
# the pattern axis), with a fixed spacing and instance count.
#
# v1 limits:
#   - Direction 1 only. Direction 2 (rectangular pattern) is deferred; would
#     add `direction2`, `count2`, `spacing2` fields.
#   - Seed = a single earlier feature by name. Multi-seed not yet supported.
#   - Direction reference = a point on a model edge in part coords. No
#     reference-axis or sketched-line variants yet.
LINEAR_PATTERN: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["type", "name", "seed", "direction", "count", "spacing"],
    "properties": {
        "type": {"const": "linear_pattern"},
        "name": {"type": "string", "pattern": "^[A-Za-z_][A-Za-z0-9_]*$"},
        "seed": {
            "type": "string",
            "description": (
                "Name of an earlier feature to pattern. The seed itself "
                "counts as instance 1; `count` includes it."
            ),
        },
        "direction": {
            "type": "object",
            "additionalProperties": False,
            "required": ["x", "y", "z"],
            "properties": {
                "x": {"type": "number"},
                "y": {"type": "number"},
                "z": {"type": "number"},
            },
            "description": (
                "A point on a model edge whose direction defines the pattern "
                "axis. The builder selects the edge with SelectByID and uses "
                "its tangent at that point."
            ),
        },
        "count": {
            "type": "integer",
            "minimum": 2,
            "description": (
                "Total number of instances along Direction 1 (includes the "
                "seed). Must be >= 2 -- a count of 1 would be a no-op."
            ),
        },
        "spacing": {
            **LENGTH_SCHEMA,
            "description": "Distance between consecutive instances (mm).",
        },
        "flip": {
            "type": "boolean",
            "default": False,
            "description": "Reverse pattern direction relative to the selected edge's tangent.",
        },
    },
}


# Circular pattern of a seed feature around a rotation axis. Replicates the
# seed N times equally spaced over a total sweep angle (default 360 degrees).
#
# v1 limits:
#   - Direction 1 only. Bidirectional / symmetric variants are deferred (would
#     add `bidirectional`, `count2`, `total_angle2`).
#   - Seed = single feature by name. Multi-seed deferred.
#   - Axis reference = a point on either a circular EDGE or a cylindrical FACE
#     in part coords. Both verified GREEN on SW 2024 SP1 in Spike T (Case A:
#     circular edge of disc top; Case B: cylindrical side face of disc).
#   - Equal spacing always on -- variable angular spacing requires a dim ref.
CIRCULAR_PATTERN: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["type", "name", "seed", "axis", "count"],
    "properties": {
        "type": {"const": "circular_pattern"},
        "name": {"type": "string", "pattern": "^[A-Za-z_][A-Za-z0-9_]*$"},
        "seed": {
            "type": "string",
            "description": (
                "Name of an earlier feature to pattern. The seed itself "
                "counts as instance 1; `count` includes it."
            ),
        },
        "axis": {
            "type": "object",
            "additionalProperties": False,
            "required": ["x", "y", "z"],
            "properties": {
                "x": {"type": "number"},
                "y": {"type": "number"},
                "z": {"type": "number"},
            },
            "description": (
                "A point on the rotation-axis reference -- either a circular "
                "EDGE (e.g. the rim of a cylindrical face) or a cylindrical "
                "FACE. The builder tries EDGE first, then FACE on fallback. "
                "SW infers the axis of revolution from the selected entity."
            ),
        },
        "count": {
            "type": "integer",
            "minimum": 2,
            "description": (
                "Total number of instances around the axis (includes the "
                "seed). Must be >= 2 -- a count of 1 would be a no-op."
            ),
        },
        "total_angle": {
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
        "flip": {
            "type": "boolean",
            "default": False,
            "description": "Reverse the rotation direction.",
        },
    },
}


# Mirror of one or more seed features about a reference plane.
#
# v1 limits:
#   - Mirror plane = one of the three default reference planes ("Front",
#     "Top", "Right"). User-created reference planes / planar faces are
#     deferred; they would need a different selection mechanism.
#   - Seed = single feature by name. Multi-seed deferred.
#   - Feature-mirror only, not body-mirror. The single bool flag would
#     have to flip multiple downstream args; defer until a clear need.
MIRROR_FEATURE: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["type", "name", "seed", "plane"],
    "properties": {
        "type": {"const": "mirror_feature"},
        "name": {"type": "string", "pattern": "^[A-Za-z_][A-Za-z0-9_]*$"},
        "seed": {
            "type": "string",
            "description": "Name of an earlier feature to mirror.",
        },
        "plane": {
            "enum": ["Front", "Top", "Right"],
            "description": (
                "Default reference plane to mirror about. Front = XY (mirrors "
                "Z), Top = XZ (mirrors Y), Right = YZ (mirrors X)."
            ),
        },
    },
}


# Constant-radius edge fillet. Selects N edges by part-coord points and
# applies a single radius. Wired via the SW 2020+ canonical pipeline
# (CreateDefinition + ISimpleFilletFeatureData2.Initialize + CreateFeature)
# rather than the obsolete FeatureFillet3 single-call. Verified end-to-end
# in Spike P (swFmFillet = 1, late binding works).
#
# v1 limits:
#   - Constant radius only (no variable-radius, no asymmetric, no setback).
#   - Edge selection by point only (one point per edge); no "all edges of
#     face" sugar yet.
#   - Single radius dim (D1@FilletName) -- parametric via {rhs} as usual.
FILLET_CONSTANT_RADIUS: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["type", "name", "radius", "edges"],
    "properties": {
        "type": {"const": "fillet_constant_radius"},
        "name": {"type": "string", "pattern": "^[A-Za-z_][A-Za-z0-9_]*$"},
        "radius": LENGTH_SCHEMA,
        "edges": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["x", "y", "z"],
                "properties": {
                    "x": {"type": "number"},
                    "y": {"type": "number"},
                    "z": {"type": "number"},
                },
                "description": (
                    "A point on the target edge in part coordinates (mm). "
                    "The builder converts to meters and calls SelectByID "
                    "with type='EDGE'. Each edge entry adds one to the "
                    "selection set before CreateFeature runs."
                ),
            },
        },
    },
}


# Top-level spec
SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "ai-sw-bridge part spec v1",
    "type": "object",
    "additionalProperties": False,
    "required": ["schema_version", "name", "features"],
    "properties": {
        "schema_version": {"const": SCHEMA_VERSION},
        "name": {
            "type": "string",
            "description": "Part name (will become the SLDPRT filename if saved).",
        },
        "locals": {
            "type": "string",
            "description": (
                "Absolute path to the *_locals.txt file to link before binding "
                "dims. Required if any feature's length uses an {rhs} object."
            ),
        },
        "features": {
            "type": "array",
            "minItems": 1,
            "items": {
                "oneOf": [
                    SKETCH_RECTANGLE_ON_PLANE,
                    SKETCH_RECTANGLE_ON_FACE,
                    SKETCH_CIRCLE_ON_PLANE,
                    SKETCH_CIRCLE_ON_FACE,
                    SKETCH_CIRCLES_ON_FACE,
                    BOSS_EXTRUDE_BLIND,
                    CUT_EXTRUDE_THROUGH_ALL,
                    CUT_EXTRUDE_BLIND,
                    FILLET_CONSTANT_RADIUS,
                    CHAMFER_EDGE,
                    LINEAR_PATTERN,
                    CIRCULAR_PATTERN,
                    MIRROR_FEATURE,
                ]
            },
        },
    },
}


# Feature-type metadata for the validator and builder.
SKETCH_TYPES = frozenset(
    {
        "sketch_rectangle_on_plane",
        "sketch_rectangle_on_face",
        "sketch_circle_on_plane",
        "sketch_circle_on_face",
        "sketch_circles_on_face",
    }
)
EXTRUDE_TYPES = frozenset(
    {
        "boss_extrude_blind",
        "cut_extrude_through_all",
        "cut_extrude_blind",
    }
)
# Modify-existing-geometry features (operate on existing edges/faces, do not
# need a parent sketch). Kept separate from EXTRUDE_TYPES so the validator's
# sketch-reference rule doesn't try to demand a sketch on them.
MODIFY_TYPES = frozenset(
    {
        "fillet_constant_radius",
        "chamfer_edge",
    }
)
# Reference-an-earlier-feature types (linear pattern, mirror). These have
# a `seed` field that names a prior feature; the validator must check
# existence + ordering but doesn't constrain the seed's type (any built
# feature is mirrorable / patternable in v1 -- SW will error at build
# time if the seed is incompatible, e.g. patterning a fillet of an edge
# that itself moves).
PATTERN_TYPES = frozenset(
    {
        "linear_pattern",
        "circular_pattern",
        "mirror_feature",
    }
)
ALL_TYPES = SKETCH_TYPES | EXTRUDE_TYPES | MODIFY_TYPES | PATTERN_TYPES
