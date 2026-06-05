"""Drawing spec JSON schema (Wave-16).

Defines the ``kind: "drawing"`` spec structure: a model path and a list
of standard views to generate. This is a standalone spec kind (sibling
to ``kind: "part"`` and ``kind: "assembly"``).

The schema enforces:
  - ``kind`` == "drawing" (required)
  - ``name`` (required, non-empty string)
  - ``model`` (required, path to .sldasm or .sldprt)
  - ``views[]`` — each in the allowed standard view set
  - ``sheet`` — optional template size
"""

from __future__ import annotations

from typing import Any

from .formats import DRAWING_FORMAT_NAMES

DRAWING_SPEC_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "ai-sw-bridge drawing spec v1",
    "type": "object",
    "required": ["kind", "name", "model", "views"],
    "additionalProperties": False,
    "properties": {
        "kind": {"const": "drawing"},
        "name": {"type": "string", "minLength": 1},
        "model": {"type": "string", "minLength": 1},
        "views": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": sorted(DRAWING_FORMAT_NAMES),
            },
            "minItems": 1,
        },
        "sheet": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "template_size": {
                    "type": "string",
                    "enum": [
                        "A4", "A3", "A2", "A1", "A0",
                        "A", "B", "C", "D", "E",
                    ],
                },
            },
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
