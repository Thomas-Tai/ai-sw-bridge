"""Foreign geometry import (STEP / IGES → B-rep body in a .SLDPRT).

Wave 40 (FR-1-07 audit gap). v1 is import → body + verify ONLY — no feature-
tree reconstruction, no healing, no re-parameterization. The imported part is
a dumb-solid.

Public API:

- ``ImportSpec``  — the parsed, validated request envelope.
- ``ImportResult`` — the outcome of one import attempt.
- ``ImportValidationError`` — fail-closed validation error (typed, with path).
- ``import_part(spec)`` — the dispatch entry point.
- ``IMPORT_SPEC_SCHEMA`` — JSON Schema fragment for the ``kind:"import"`` spec.

CLI: ``ai-sw-import --source <path> --output <part.sldprt>``.
"""

from __future__ import annotations

from .dispatch import ImportResult, ImportSpec, import_part
from .schema import IMPORT_SPEC_SCHEMA, SUPPORTED_EXTENSIONS
from .validator import ImportValidationError, parse_import_spec, validate_import_spec

__all__ = [
    "IMPORT_SPEC_SCHEMA",
    "ImportResult",
    "ImportSpec",
    "ImportValidationError",
    "SUPPORTED_EXTENSIONS",
    "import_part",
    "parse_import_spec",
    "validate_import_spec",
]
