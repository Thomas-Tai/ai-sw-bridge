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
                        'Pasted verbatim into EquationMgr.Add2. Quote variable '
                        'references yourself, e.g. \'"S1B_W"\' for a bare var.'
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
        "width":  LENGTH_SCHEMA,
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
        "width":  LENGTH_SCHEMA,
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
                ]
            },
        },
    },
}


# Feature-type metadata for the validator and builder.
SKETCH_TYPES = frozenset({
    "sketch_rectangle_on_plane",
    "sketch_rectangle_on_face",
    "sketch_circle_on_plane",
    "sketch_circle_on_face",
    "sketch_circles_on_face",
})
EXTRUDE_TYPES = frozenset({
    "boss_extrude_blind",
    "cut_extrude_through_all",
    "cut_extrude_blind",
})
ALL_TYPES = SKETCH_TYPES | EXTRUDE_TYPES
