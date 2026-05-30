"""Drawing package (P2.x, spec.md §6).

Public API for drawing generation from part documents.

- ``DrawingFormat`` / ``DRAWING_FORMATS`` — the view-type registry.
- ``DrawingRequest`` / ``DrawingResult`` — dispatch envelopes.
- ``generate_all(doc, requests, part_name)`` — the dispatch entry point.
- ``DRAWING_BLOCK_SCHEMA`` — the ``drawing:`` block JSON-Schema fragment.
"""

from __future__ import annotations

from .dispatch import DrawingRequest, DrawingResult, generate_all, resolve_output_path
from .formats import (
    DRAWING_FORMAT_NAMES,
    DRAWING_FORMATS,
    DrawingFormat,
    DrawingMethod,
    resolve_format,
)
from .schema import DRAWING_BLOCK_SCHEMA, DRAWING_ENTRY_SCHEMA

__all__ = [
    "DRAWING_BLOCK_SCHEMA",
    "DRAWING_ENTRY_SCHEMA",
    "DRAWING_FORMAT_NAMES",
    "DRAWING_FORMATS",
    "DrawingFormat",
    "DrawingMethod",
    "DrawingRequest",
    "DrawingResult",
    "generate_all",
    "resolve_format",
    "resolve_output_path",
]
