"""Export block JSON-Schema fragment (spec.md §2, FR-1-03).

Defines the ``export:`` array schema for the schema-v2 spec. This
fragment is consumed by X5's v2 validator when assembling the
top-level schema — it is not wired into the v1 ``SCHEMA`` constant
in ``spec/schema.py`` until the v2 routing lands.

The ``export:`` block is an array of objects, each with a ``format``
field naming one of the registered export formats.

Example in a v2 spec::

    "export": [
        {"format": "step214"},
        {"format": "pdf"},
        {"format": "pdf", "sheets": ["Overview", "Detail"]},
        {"format": "dxf_flat"}
    ]
"""

from __future__ import annotations

from typing import Any

from .formats import EXPORT_FORMAT_NAMES

EXPORT_ENTRY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["format"],
    "properties": {
        "format": {
            "type": "string",
            "enum": sorted(EXPORT_FORMAT_NAMES),
            "description": (
                "Export format identifier. Must match a registered "
                "format in the export format table."
            ),
        },
        "filename": {
            "type": "string",
            "description": (
                "Override the output filename (without extension). "
                "Defaults to the part name."
            ),
        },
        "output_dir": {
            "type": "string",
            "description": (
                "Override the output directory for this entry. "
                "Defaults to the spec-level output directory or CWD."
            ),
        },
        "sheets": {
            "oneOf": [
                {"type": "string", "const": "all"},
                {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                },
            ],
            "description": (
                "Which drawing sheets to export (PDF only). "
                '"all" (default) exports every sheet; a list of sheet '
                "names exports only those sheets. Ignored for non-PDF "
                "formats. Unknown sheet names are rejected at dispatch."
            ),
        },
        "binary": {
            "type": "boolean",
            "description": (
                "STL binary/ASCII toggle (STL only). "
                "true (default) produces binary STL; false produces "
                "ASCII STL. Ignored for non-STL formats."
            ),
        },
    },
}

EXPORT_BLOCK_SCHEMA: dict[str, Any] = {
    "type": "array",
    "minItems": 1,
    "items": EXPORT_ENTRY_SCHEMA,
    "description": (
        "List of export formats to produce after the build completes. "
        "Each entry names a format from the export format table."
    ),
}
