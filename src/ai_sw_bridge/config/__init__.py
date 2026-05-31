"""Config package (Phase 4, FR-4-01, todolist P4.1).

Public API for configuration variant management.

- ConfigVariant / VariantOverride — the variant data model.
- ConfigResult — dispatch outcome envelope.
- parse_variants — parse the variants: block from a spec.
- apply_overrides — pure locals-override computation.
- validate_overrides — check variable existence before dispatch.
- create_all — the dispatch entry point (SEAT-gated COM call).
- VARIANTS_BLOCK_SCHEMA — the variants: block JSON-Schema fragment.
"""

from __future__ import annotations

from .dispatch import apply_overrides, create_all, validate_overrides
from .schema import (
    VARIANTS_BLOCK_SCHEMA,
    VARIANT_ENTRY_SCHEMA,
    VARIANT_OVERRIDE_SCHEMA,
)
from .variants import (
    ConfigResult,
    ConfigVariant,
    VariantOverride,
    parse_variants,
)

__all__ = [
    "VARIANTS_BLOCK_SCHEMA",
    "VARIANT_ENTRY_SCHEMA",
    "VARIANT_OVERRIDE_SCHEMA",
    "ConfigResult",
    "ConfigVariant",
    "VariantOverride",
    "apply_overrides",
    "create_all",
    "parse_variants",
    "validate_overrides",
]
