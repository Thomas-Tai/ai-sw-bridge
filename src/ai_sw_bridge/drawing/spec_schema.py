"""Drawing spec JSON schema (Wave-16/W18/W19/W23/W28).

Defines the ``kind: "drawing"`` spec structure: a model path and a list
of standard views to generate. This is a standalone spec kind (sibling
to ``kind: "part"`` and ``kind: "assembly"``).

Two authoring modes (W23):
  - **Legacy single-sheet** (unchanged): top-level ``views[]`` with optional
    ``sheet``/``dimensions``/``bom``. Behaviour identical to pre-W23.
  - **Multi-sheet**: optional ``sheets[]`` array; each entry carries its
    own ``views[]`` plus optional ``name``/``template_size``/``dimensions``/
    ``bom``. Top-level ``views`` MUST be absent.

W28 adds dimension tolerances:
  - ``dimensions`` extended from ``boolean`` to ``boolean | object``
  - ``dimensions: true`` unchanged (dims with NO tolerance)
  - ``dimensions: {tolerance: {...}}`` applies general tolerance to all dims
  - Supported tolerance types: symmetric, bilateral, limit
  - GD&T (feature-control-frames) explicitly deferred

The schema enforces:
  - ``kind`` == "drawing" (required)
  - ``name`` (required, non-empty string)
  - ``model`` (required, path to .sldasm or .sldprt)
  - ``views[]`` OR ``sheets[]`` (one authoring mode; mutual-exclusion is
    enforced in ``validate_drawing_spec`` for precise error messages)
  - Each view entry is a string (ortho/iso name) or an object with
    ``type`` in {section, detail}; cross-field validation (parent exists,
    cut present for section) is done in ``validate_drawing_spec``
  - ``sheet`` — optional template size (legacy mode only)
  - ``bom`` — optional bool (legacy mode); per-sheet ``bom`` in sheets mode
"""

from __future__ import annotations

from typing import Any

from .formats import DRAWING_FORMAT_NAMES

# W28: Tolerance schema fragment
# swTolType_e values: symmetric=4, bilateral=2, limit=3
# Units: metres (SW system units)
_TOLERANCE_SYMMETRIC_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["type", "value"],
    "additionalProperties": False,
    "properties": {
        "type": {"const": "symmetric"},
        "value": {
            "type": "number",
            "minimum": 0,
            "description": "Tolerance value in metres (±value)",
        },
    },
}

_TOLERANCE_BILATERAL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["type", "max", "min"],
    "additionalProperties": False,
    "properties": {
        "type": {"const": "bilateral"},
        "max": {
            "type": "number",
            "description": "Upper tolerance in metres (+max)",
        },
        "min": {
            "type": "number",
            "description": "Lower tolerance in metres (-min, typically negative)",
        },
    },
}

_TOLERANCE_LIMIT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["type", "max", "min"],
    "additionalProperties": False,
    "properties": {
        "type": {"const": "limit"},
        "max": {
            "type": "number",
            "description": "Upper limit delta in metres",
        },
        "min": {
            "type": "number",
            "description": "Lower limit delta in metres",
        },
    },
}

_TOLERANCE_SCHEMA: dict[str, Any] = {
    "oneOf": [
        _TOLERANCE_SYMMETRIC_SCHEMA,
        _TOLERANCE_BILATERAL_SCHEMA,
        _TOLERANCE_LIMIT_SCHEMA,
    ],
    "description": (
        "Dimension tolerance specification. v1 supports only symmetric, "
        "bilateral, and limit types. GD&T (feature-control-frames) is deferred."
    ),
}

# dimensions: true (bool) OR {tolerance: {...}}
_DIMENSIONS_SCHEMA: dict[str, Any] = {
    "oneOf": [
        {
            "type": "boolean",
            "description": (
                "true = insert model dimensions with no tolerance; "
                "false = skip dimension insertion"
            ),
        },
        {
            "type": "object",
            "required": ["tolerance"],
            "additionalProperties": False,
            "properties": {
                "tolerance": _TOLERANCE_SCHEMA,
            },
            "description": (
                "Insert model dimensions and apply a general tolerance "
                "to all dimensions on this sheet."
            ),
        },
    ],
    "default": False,
}

_VIEW_ITEM_SCHEMA: dict[str, Any] = {
    "oneOf": [
        {
            "type": "string",
            "enum": sorted(DRAWING_FORMAT_NAMES),
        },
        {
            "type": "object",
            "required": ["type", "name", "parent"],
            "additionalProperties": False,
            "properties": {
                "type": {"type": "string", "enum": ["section", "detail"]},
                "name": {"type": "string", "minLength": 1},
                "parent": {"type": "string", "minLength": 1},
                "cut": {"type": "string", "enum": ["horizontal", "vertical"]},
                "center": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 2,
                    "maxItems": 2,
                },
                "radius": {"type": "number", "exclusiveMinimum": 0},
            },
        },
    ]
}

_VIEWS_ARRAY_SCHEMA: dict[str, Any] = {
    "type": "array",
    "items": _VIEW_ITEM_SCHEMA,
    "minItems": 1,
}

_SHEET_SIZE_ENUM: dict[str, Any] = {
    "type": "string",
    "enum": ["A4", "A3", "A2", "A1", "A0", "A", "B", "C", "D", "E"],
}

# W38: Canonical title-block field names.
#
# These are the well-known field codes that SOLIDWORKS title-block templates
# surface via ``$PRP:"Name"`` / ``$PRPSHEET:"Name"``. Authoring a field is
# really authoring a drawing-file custom property — the title-block note
# resolves at display time. Unknown names are rejected fail-closed (S2 DoD)
# so a typo doesn't silently become a no-op.
TITLE_BLOCK_KNOWN_FIELDS: tuple[str, ...] = (
    "DrawingNo",
    "Title",
    "Revision",
    "DrawnBy",
    "CheckedBy",
    "ApprovedBy",
    "Date",
    "Scale",
    "Material",
    "SheetOf",
    "Company",
    "Project",
)

# W38: title_block JSON-schema fragment (flat string->string map, closed to
# the known vocabulary). additionalProperties:false means an unknown field
# name is a schema error — fail-closed per spec.
_TITLE_BLOCK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "minProperties": 1,
    "properties": {
        name: {"type": "string", "minLength": 1}
        for name in TITLE_BLOCK_KNOWN_FIELDS
    },
    "description": (
        "Title-block field map. Keys must be from the canonical vocabulary "
        "(DrawingNo, Title, Revision, DrawnBy, CheckedBy, ApprovedBy, Date, "
        "Scale, Material, SheetOf, Company, Project). Values are persisted "
        "as drawing-level custom file properties; title-block notes with "
        "matching $PRP: / $PRPSHEET: field codes resolve to these values "
        "at display time."
    ),
}


def validate_title_block(spec: dict[str, Any], *, path: str) -> None:
    """Semantic validation of a title_block block (W38).

    Raises ``ValueError`` on the first semantic error. Schema-level checks
    (unknown field, non-string value) already ran via jsonschema — this
    function handles the dict-shape invariants jsonschema can't easily
    express (e.g. the whole block being a non-dict).
    """
    tb = spec.get("title_block")
    if tb is None:
        return
    if not isinstance(tb, dict):
        raise ValueError(f"{path}.title_block must be a dict")
    if not tb:
        raise ValueError(f"{path}.title_block must be non-empty")
    for name, value in tb.items():
        if name not in TITLE_BLOCK_KNOWN_FIELDS:
            raise ValueError(
                f"{path}.title_block.{name}: unknown field; "
                f"allowed: {sorted(TITLE_BLOCK_KNOWN_FIELDS)}"
            )
        if not isinstance(value, str) or not value:
            raise ValueError(
                f"{path}.title_block.{name}: value must be a non-empty "
                f"string; got {type(value).__name__}"
            )

_SHEET_ENTRY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["views"],
    "additionalProperties": False,
    "properties": {
        "name": {"type": "string", "minLength": 1},
        "template_size": _SHEET_SIZE_ENUM,
        "views": _VIEWS_ARRAY_SCHEMA,
        "dimensions": _DIMENSIONS_SCHEMA,
        "bom": {"type": "boolean", "default": False},
    },
}

DRAWING_SPEC_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "ai-sw-bridge drawing spec v1",
    "type": "object",
    "required": ["kind", "name", "model"],
    "additionalProperties": False,
    "properties": {
        "kind": {"const": "drawing"},
        "name": {"type": "string", "minLength": 1},
        "model": {"type": "string", "minLength": 1},
        "views": _VIEWS_ARRAY_SCHEMA,
        "sheets": {
            "type": "array",
            "items": _SHEET_ENTRY_SCHEMA,
            "minItems": 1,
        },
        "sheet": {
            "type": "object",
            "additionalProperties": False,
            "properties": {"template_size": _SHEET_SIZE_ENUM},
        },
        "dimensions": _DIMENSIONS_SCHEMA,
        "bom": {
            "type": "boolean",
            "default": False,
            "description": (
                "If true, insert a top-level Bill-of-Materials table "
                "anchored to the first view. Requires model to be a "
                ".sldasm — a .sldprt rejects with a clear error message."
            ),
        },
        "title_block": _TITLE_BLOCK_SCHEMA,
    },
}

# Sheet dimensions in metres (width, height) for NewDocument
SHEET_SIZES: dict[str, tuple[float, float]] = {
    "A4": (0.210, 0.297),
    "A3": (0.420, 0.297),
    "A2": (0.594, 0.420),
    "A1": (0.841, 0.594),
    "A0": (1.189, 0.841),
    "A": (0.279, 0.216),
    "B": (0.432, 0.279),
    "C": (0.559, 0.432),
    "D": (0.864, 0.559),
    "E": (1.118, 0.864),
}

DEFAULT_SHEET_SIZE = "A3"
