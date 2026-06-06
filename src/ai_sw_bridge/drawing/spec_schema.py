"""Drawing spec JSON schema (Wave-16/W18/W19/W23).

Defines the ``kind: "drawing"`` spec structure: a model path and a list
of standard views to generate. This is a standalone spec kind (sibling
to ``kind: "part"`` and ``kind: "assembly"``).

Two authoring modes (W23):
  - **Legacy single-sheet** (unchanged): top-level ``views[]`` with optional
    ``sheet``/``dimensions``/``bom``. Behaviour identical to pre-W23.
  - **Multi-sheet**: optional ``sheets[]`` array; each entry carries its
    own ``views[]`` plus optional ``name``/``template_size``/``dimensions``/
    ``bom``. Top-level ``views`` MUST be absent.

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

_SHEET_ENTRY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["views"],
    "additionalProperties": False,
    "properties": {
        "name": {"type": "string", "minLength": 1},
        "template_size": _SHEET_SIZE_ENUM,
        "views": _VIEWS_ARRAY_SCHEMA,
        "dimensions": {"type": "boolean", "default": False},
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
        "dimensions": {
            "type": "boolean",
            "default": False,
            "description": (
                "If true, insert model dimensions onto each view via "
                "InsertModelAnnotations3. Requires the model to have "
                "display dimensions (built with no_dim=False)."
            ),
        },
        "bom": {
            "type": "boolean",
            "default": False,
            "description": (
                "If true, insert a top-level Bill-of-Materials table "
                "anchored to the first view. Requires model to be a "
                ".sldasm — a .sldprt rejects with a clear error message."
            ),
        },
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
