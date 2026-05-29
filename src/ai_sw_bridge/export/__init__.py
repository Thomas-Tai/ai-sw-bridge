"""Export package (Phase 1, spec.md §6, FR-1-03).

Public API for multi-format part export.

- ``ExportFormat`` / ``EXPORT_FORMATS`` — the format registry.
- ``ExportRequest`` / ``ExportResult`` — dispatch envelopes.
- ``export_all(doc, requests, part_name)`` — the dispatch entry point.
- ``EXPORT_BLOCK_SCHEMA`` — the ``export:`` block JSON-Schema fragment
  for the schema-v2 spec.
"""

from __future__ import annotations

from .dispatch import ExportRequest, ExportResult, export_all, resolve_output_path
from .formats import (
    EXPORT_FORMAT_NAMES,
    EXPORT_FORMATS,
    ExportFormat,
    SaveMethod,
    resolve_format,
)
from .schema import EXPORT_BLOCK_SCHEMA, EXPORT_ENTRY_SCHEMA

__all__ = [
    "EXPORT_BLOCK_SCHEMA",
    "EXPORT_ENTRY_SCHEMA",
    "EXPORT_FORMAT_NAMES",
    "EXPORT_FORMATS",
    "ExportFormat",
    "ExportRequest",
    "ExportResult",
    "SaveMethod",
    "export_all",
    "resolve_format",
    "resolve_output_path",
]
