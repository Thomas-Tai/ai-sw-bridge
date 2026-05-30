"""Drawing block JSON-Schema fragment (P2.x).

Defines the ``drawing:`` object schema for the schema-v2 spec. This
fragment is consumed by the v2 validator when assembling the top-level
schema.

The ``drawing:`` block configures drawing generation: which views to
include, sheet size, and output path.

Example in a v2 spec::

    "drawing": {
        "enabled": true,
        "sheet_size": "A3",
        "views": ["front", "top", "right", "isometric"],
        "output_dir": "./drawings"
    }
"""

from __future__ import annotations

from typing import Any

from .formats import DRAWING_FORMAT_NAMES

DRAWING_ENTRY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "view": {
            "type": "string",
            "enum": sorted(DRAWING_FORMAT_NAMES),
            "description": (
                "View identifier. Must match a registered view in the "
                "drawing format table."
            ),
        },
        "x": {
            "type": "number",
            "description": "X position on the sheet (metres, drawing frame).",
        },
        "y": {
            "type": "number",
            "description": "Y position on the sheet (metres, drawing frame).",
        },
    },
    "required": ["view"],
}

DRAWING_BLOCK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "enabled": {
            "type": "boolean",
            "default": True,
            "description": "Enable or disable drawing generation.",
        },
        "sheet_size": {
            "type": "string",
            "enum": ["A4", "A3", "A2", "A1", "A0", "A", "B", "C", "D", "E"],
            "default": "A3",
            "description": "Drawing sheet size.",
        },
        "views": {
            "type": "array",
            "items": DRAWING_ENTRY_SCHEMA,
            "minItems": 1,
            "description": "List of views to place on the drawing sheet.",
        },
        "output_dir": {
            "type": "string",
            "description": (
                "Output directory for the .slddrw file. "
                "Defaults to the spec directory or CWD."
            ),
        },
    },
    "description": (
        "Optional drawing-generation block. Creates a .slddrw with "
        "standard views of the built part."
    ),
}
