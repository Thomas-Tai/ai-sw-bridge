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

X3 (FR-X-03): the per-feature fragments are no longer hand-written here -- they
are *assembled* from the declarative descriptors in `descriptors.py` (the
single source of truth per primitive). The shared sub-schemas live there too
and are re-exported below so existing importers keep working.
"""

from __future__ import annotations

from typing import Any

# Re-exported for back-compat: the validator and tests import EXPECT_SCHEMA
# from here, and the sub-schemas historically lived in this module.
from .descriptors import (  # noqa: F401
    CENTERLINE_SCHEMA,
    EXPECT_SCHEMA,
    LENGTH_SCHEMA,
    NAME_PATTERN,
    assemble_all,
)

SCHEMA_VERSION = 1


# Top-level spec. The per-feature `oneOf` is assembled from the descriptors
# (one fragment per primitive, in descriptors.FEATURE_ORDER).
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
            "items": {"oneOf": assemble_all()},
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
        "revolve_boss",
        "revolve_cut",
    }
)
# Modify-existing-geometry features (operate on existing edges/faces, do not
# need a parent sketch). Kept separate from EXTRUDE_TYPES so the validator's
# sketch-reference rule doesn't try to demand a sketch on them.
MODIFY_TYPES = frozenset(
    {
        "fillet_constant_radius",
        "chamfer_edge",
        "simple_hole",
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
