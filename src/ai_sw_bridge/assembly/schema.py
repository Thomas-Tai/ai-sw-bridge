"""Assembly spec JSON schema (Wave-9 Phase 1).

Defines the ``kind: "assembly"`` spec structure: components with transforms
and mates with face references. This is a sibling spec kind to the part spec,
validated independently.

The schema enforces:
  - ``kind`` == "assembly" (required)
  - ``name`` (required, non-empty string)
  - ``components[]`` — each with ``id``, ``part`` XOR ``part_spec``, ``transform``
  - ``mates[]`` — each with ``type``, ``alignment``, ``a``, ``b`` references
"""

from __future__ import annotations

MATE_TYPES = frozenset(
    {
        "coincident",
        "distance",
        "concentric",
        "parallel",
        "perpendicular",
        "tangent",
        "angle",
        "width",
    }
)

MATE_ALIGNMENTS = frozenset({"aligned", "anti_aligned", "closest"})

XYZ_MM_SCHEMA = {
    "type": "array",
    "items": {"type": "number"},
    "minItems": 3,
    "maxItems": 3,
}

TRANSFORM_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "xyz_mm": XYZ_MM_SCHEMA,
        "rpy_deg": XYZ_MM_SCHEMA,
    },
}

FACE_REF_SCHEMA = {
    "type": "object",
    "minProperties": 1,
}

MATE_REF_SCHEMA = {
    "type": "object",
    "required": ["component", "face_ref"],
    "additionalProperties": False,
    "properties": {
        "component": {"type": "string", "minLength": 1},
        "face_ref": FACE_REF_SCHEMA,
    },
}

COMPONENT_SCHEMA = {
    "type": "object",
    "required": ["id"],
    "additionalProperties": False,
    "properties": {
        "id": {"type": "string", "minLength": 1},
        "part": {"type": "string", "minLength": 1},
        "part_spec": {"type": "string", "minLength": 1},
        "transform": TRANSFORM_SCHEMA,
    },
}

MATE_SCHEMA = {
    "type": "object",
    "required": ["type", "a", "b"],
    "additionalProperties": False,
    "properties": {
        "type": {"type": "string", "enum": sorted(MATE_TYPES)},
        "alignment": {"type": "string", "enum": sorted(MATE_ALIGNMENTS)},
        "value_mm": {"type": "number"},
        "value_deg": {"type": "number"},
        "limit": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "min_mm": {"type": "number"},
                "max_mm": {"type": "number"},
                "min_deg": {"type": "number"},
                "max_deg": {"type": "number"},
            },
        },
        "a": MATE_REF_SCHEMA,
        "b": MATE_REF_SCHEMA,
    },
}

WIDTH_MATE_SCHEMA = {
    "type": "object",
    "required": ["type", "width_faces", "tab_faces"],
    "additionalProperties": False,
    "properties": {
        "type": {"const": "width"},
        "width_faces": {
            "type": "array",
            "items": MATE_REF_SCHEMA,
            "minItems": 2,
            "maxItems": 2,
        },
        "tab_faces": {
            "type": "array",
            "items": MATE_REF_SCHEMA,
            "minItems": 2,
            "maxItems": 2,
        },
    },
}

MIRROR_PATTERN_SCHEMA = {
    "type": "object",
    "required": ["type", "seed", "plane"],
    "additionalProperties": False,
    "properties": {
        "type": {"const": "mirror"},
        "seed": {"type": "string", "minLength": 1},
        "plane": {"type": "string", "enum": ["front", "top", "right"]},
        "name_modifier": {"type": "integer", "minimum": 0},
    },
}

COMPONENT_PATTERNS_SCHEMA = {
    "type": "array",
    "items": MIRROR_PATTERN_SCHEMA,
}

_DIRECTION_SCHEMA = {
    "type": "array",
    "items": {"type": "number"},
    "minItems": 3,
    "maxItems": 3,
}

LINEAR_ARRAY_SCHEMA = {
    "type": "object",
    "required": ["id", "type", "count", "spacing_mm", "direction"],
    "additionalProperties": False,
    "properties": {
        "id": {"type": "string", "minLength": 1},
        "type": {"const": "linear"},
        "count": {"type": "integer", "minimum": 2},
        "spacing_mm": {"type": "number", "exclusiveMinimum": 0},
        "direction": _DIRECTION_SCHEMA,
        "base_xyz_mm": XYZ_MM_SCHEMA,
        "base_rpy_deg": XYZ_MM_SCHEMA,
        "part": {"type": "string", "minLength": 1},
        "part_spec": {"type": "string", "minLength": 1},
    },
}

CIRCULAR_ARRAY_SCHEMA = {
    "type": "object",
    "required": ["id", "type", "count", "radius_mm", "axis"],
    "additionalProperties": False,
    "properties": {
        "id": {"type": "string", "minLength": 1},
        "type": {"const": "circular"},
        "count": {"type": "integer", "minimum": 2},
        "radius_mm": {"type": "number", "exclusiveMinimum": 0},
        "axis": _DIRECTION_SCHEMA,
        "center_xyz_mm": XYZ_MM_SCHEMA,
        "angle_deg": {"type": "number", "exclusiveMinimum": 0, "maximum": 360},
        "base_rpy_deg": XYZ_MM_SCHEMA,
        "part": {"type": "string", "minLength": 1},
        "part_spec": {"type": "string", "minLength": 1},
    },
}

COMPONENT_ARRAYS_SCHEMA = {
    "type": "array",
    "items": {"oneOf": [LINEAR_ARRAY_SCHEMA, CIRCULAR_ARRAY_SCHEMA]},
}

EXPLODE_STEP_SCHEMA = {
    "type": "object",
    "required": ["components", "distance_mm", "direction"],
    "additionalProperties": False,
    "properties": {
        "components": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
            "minItems": 1,
        },
        "distance_mm": {"type": "number", "exclusiveMinimum": 0},
        "direction": {"type": "string", "enum": ["front", "top", "right"]},
        "reverse": {"type": "boolean"},
    },
}

EXPLODED_VIEW_SCHEMA = {
    "type": "object",
    "required": ["name", "steps"],
    "additionalProperties": False,
    "properties": {
        "name": {"type": "string", "minLength": 1},
        "steps": {
            "type": "array",
            "items": EXPLODE_STEP_SCHEMA,
            "minItems": 1,
        },
    },
}

EXPLODED_VIEWS_SCHEMA = {
    "type": "array",
    "items": EXPLODED_VIEW_SCHEMA,
}

ASSEMBLY_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "ai-sw-bridge assembly spec v1",
    "type": "object",
    "required": ["kind", "name", "components"],
    "additionalProperties": False,
    "properties": {
        "kind": {"const": "assembly"},
        "name": {"type": "string", "minLength": 1},
        "components": {
            "type": "array",
            "minItems": 1,
            "items": COMPONENT_SCHEMA,
        },
        "mates": {
            "type": "array",
            "items": {
                "oneOf": [MATE_SCHEMA, WIDTH_MATE_SCHEMA],
            },
        },
        "component_patterns": COMPONENT_PATTERNS_SCHEMA,
        "component_arrays": COMPONENT_ARRAYS_SCHEMA,
        "exploded_views": EXPLODED_VIEWS_SCHEMA,
    },
}
