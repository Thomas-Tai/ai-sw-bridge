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
    },
}
