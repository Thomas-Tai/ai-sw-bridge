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
    RELATIONS_SCHEMA,
    assemble_all,
)

SCHEMA_VERSION = 1

# X5 (FR-1/FR-2): the spec format is now version-routed. v1 is the stable,
# shipping surface; v2 is a strict SUPERSET that additionally accepts a
# top-level `material`/`units` plus optional `drawing:`/`export:` blocks and a
# per-feature `tolerance`. The v2 surface is gated behind the `schema_v2`
# feature flag (default OFF) and is currently VALIDATED-BUT-INERT: the schema
# grammar-checks the new blocks, but no builder behaviour keys off them (the
# builder is owned by a different lane). `SCHEMA_VERSION` stays at 1 so existing
# importers/tests see the unchanged default; the routing key is the per-spec
# `schema_version` value, accepted as an enum below.
SCHEMA_VERSION_V2 = 2
SUPPORTED_SCHEMA_VERSIONS = (SCHEMA_VERSION, SCHEMA_VERSION_V2)


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


# ---------------------------------------------------------------------------
# Schema v2 (FR-1/FR-2) -- validated-but-inert superset of v1.
# ---------------------------------------------------------------------------

# A `units` value: the closed set of unit systems the spec layer understands.
# Sourced from `ai_sw_bridge.units.SpecUnit` so the enum can't drift from the
# conversion code. Imported lazily inside the builder to avoid widening this
# module's import surface; here we inline the closed set to keep schema.py a
# leaf module (it must not import builder/units chains).
UNITS_SCHEMA: dict[str, Any] = {
    "enum": ["mm", "inch"],
    "description": (
        "Authoring unit system for all length values in the spec. Defaults to "
        "'mm'. The builder converts to SW's internal SI before each COM call."
    ),
}

# A `material` value: a SOLIDWORKS material library name (free-form string).
MATERIAL_SCHEMA: dict[str, Any] = {
    "type": "string",
    "minLength": 1,
    "description": (
        "SOLIDWORKS material to apply to the part (library name, e.g. "
        "'AISI 1020' or '6061 Alloy'). Validated-but-inert in this release."
    ),
}

# A per-feature `tolerance`: either a single symmetric value (mm) or an
# explicit {plus, minus} pair. Minimal grammar -- enough to grammar-check,
# not a full GD&T model.
TOLERANCE_SCHEMA: dict[str, Any] = {
    "oneOf": [
        {
            "type": "number",
            "minimum": 0,
            "description": "Symmetric +/- tolerance in millimetres.",
        },
        {
            "type": "object",
            "additionalProperties": False,
            "required": ["plus", "minus"],
            "properties": {
                "plus": {"type": "number", "minimum": 0},
                "minus": {"type": "number", "minimum": 0},
            },
            "description": "Asymmetric tolerance band in millimetres.",
        },
    ],
    "description": (
        "Dimensional tolerance carried on the feature. Validated-but-inert in "
        "this release (no builder behaviour keys off it yet)."
    ),
}

# The optional `drawing:` block. Minimal real grammar: an enabled flag plus a
# closed set of standard sheet sizes.
DRAWING_BLOCK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "enabled": {
            "type": "boolean",
            "default": True,
            "description": "Whether to generate a drawing after the build.",
        },
        "sheet_size": {
            "enum": ["A4", "A3", "A2", "A1", "A0", "A", "B", "C", "D", "E"],
            "description": "Standard drawing sheet size.",
        },
    },
    "description": (
        "Optional drawing-generation block. Validated-but-inert in this "
        "release."
    ),
}


def _export_block_schema() -> dict[str, Any]:
    """The `export:` block schema, reused from the export lane's fragment.

    Imported lazily so schema.py stays importable even if the export package
    is mid-refactor; falls back to a permissive-but-real array grammar if the
    export fragment can't be imported.
    """
    try:
        from ..export.schema import EXPORT_BLOCK_SCHEMA

        return EXPORT_BLOCK_SCHEMA
    except Exception:  # pragma: no cover - defensive; export pkg is in-tree
        return {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["format"],
                "properties": {"format": {"type": "string"}},
            },
        }


def _v2_feature_oneof() -> list[dict[str, Any]]:
    """v1 feature fragments augmented with an optional per-feature `tolerance`.

    Each fragment keeps `additionalProperties: False`, so the only way to let a
    new optional key through is to add it to that fragment's `properties`. We
    copy each v1 fragment (shallow on the fragment, fresh `properties` dict) and
    splice in `tolerance`; `required` is untouched (tolerance is optional).
    """
    frags: list[dict[str, Any]] = []
    for frag in assemble_all():
        new_frag = dict(frag)
        new_props = dict(frag["properties"])
        new_props["tolerance"] = TOLERANCE_SCHEMA
        new_frag["properties"] = new_props
        frags.append(new_frag)
    return frags


def build_schema_v2() -> dict[str, Any]:
    """Assemble the v2 top-level schema: a strict superset of `SCHEMA`.

    Adds `schema_version: 2`, the optional top-level `material`/`units` and
    `drawing:`/`export:` blocks, and a per-feature `tolerance`. Keeps
    `additionalProperties: False` so genuinely unknown keys are still rejected.
    """
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "ai-sw-bridge part spec v2",
        "type": "object",
        "additionalProperties": False,
        "required": ["schema_version", "name", "features"],
        "properties": {
            "schema_version": {"const": SCHEMA_VERSION_V2},
            "name": SCHEMA["properties"]["name"],
            "locals": SCHEMA["properties"]["locals"],
            "material": MATERIAL_SCHEMA,
            "units": UNITS_SCHEMA,
            "drawing": DRAWING_BLOCK_SCHEMA,
            "export": _export_block_schema(),
            "features": {
                "type": "array",
                "minItems": 1,
                "items": {"oneOf": _v2_feature_oneof()},
            },
        },
    }


# Assembled once at import; the v2 surface is gated at the validator (it is
# only selected when the `schema_v2` flag is ON and the spec declares v2).
SCHEMA_V2: dict[str, Any] = build_schema_v2()


def schema_for_version(version: int, *, v2_enabled: bool) -> dict[str, Any]:
    """Return the top-level schema to validate a spec of *version* against.

    Routing (FR-1/FR-2):
      - version 1            -> v1 ``SCHEMA`` (always; behaviour unchanged).
      - version 2 + flag ON  -> v2 ``SCHEMA_V2`` (validated-but-inert superset).
      - version 2 + flag OFF -> v1 ``SCHEMA`` (rejects, since its `const: 1`
        fails the version check -- v2 stays sealed behind the flag).
      - any other version    -> v1 ``SCHEMA`` (rejects with a `const` error).
    """
    if version == SCHEMA_VERSION_V2 and v2_enabled:
        return SCHEMA_V2
    return SCHEMA


# Feature-type metadata for the validator and builder.
SKETCH_TYPES = frozenset(
    {
        "sketch_rectangle_on_plane",
        "sketch_rectangle_on_face",
        "sketch_circle_on_plane",
        "sketch_circle_on_face",
        "sketch_circles_on_face",
        # P1.7s — sketch primitives (stub handlers; live COM flagged 🔴 SEAT).
        "sketch_line",
        "sketch_arc",
        "sketch_spline",
        "sketch_slot",
        "sketch_polygon",
        "sketch_ellipse",
        "sketch_text",
        # W53 — 3D-sketch primitive (Phase-5 prerequisite).
        "sketch_3d_sketch",
    }
)
EXTRUDE_TYPES = frozenset(
    {
        "boss_extrude_blind",
        "boss_extrude_midplane",
        "boss_extrude_through_all",
        "boss_extrude_two_direction",
        "boss_extrude_up_to_surface",
        "cut_extrude_through_all",
        "cut_extrude_blind",
        "cut_extrude_midplane",
        "cut_extrude_two_direction",
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
