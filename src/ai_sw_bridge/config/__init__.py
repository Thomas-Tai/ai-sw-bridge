"""Config package (Phase 4, FR-4-01, todolist P4.1 + W53 design tables).

Public API for configuration variant management.

- ConfigVariant / VariantOverride — the variant data model.
- ConfigResult — dispatch outcome envelope (path + volume_mm3).
- parse_variants — parse the variants: block from a spec.
- apply_overrides — pure locals-override computation.
- validate_overrides — check variable existence before dispatch.
- create_all — the in-file dispatch entry point (SEAT-gated COM call).
- materialize_all — the multifile dispatch entry point (build per variant).
- deep_merge — recursive dict merge for spec overrides.
- DesignTableSpec / DesignTableColumn / DesignTableRow — design table model.
- parse_design_table — parse the design_table: block from a spec.
- format_grid_csv / format_grid_tab_separated — grid text formatters.
- write_grid_file — write grid CSV to disk (SW-free).
- insert_design_table — SEAT-gated design table insertion.
"""

from __future__ import annotations

from .deep_merge import deep_merge
from .design_table import (
    DESIGN_TABLE_BLOCK_SCHEMA,
    DesignTableColumn,
    DesignTableRow,
    DesignTableSpec,
    format_grid_csv,
    format_grid_tab_separated,
    parse_design_table,
)
from .dispatch import apply_overrides, create_all, materialize_all, validate_overrides
from .dt_dispatch import insert_design_table, write_grid_file
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
    "DESIGN_TABLE_BLOCK_SCHEMA",
    "DesignTableColumn",
    "DesignTableRow",
    "DesignTableSpec",
    "VARIANTS_BLOCK_SCHEMA",
    "VARIANT_ENTRY_SCHEMA",
    "VARIANT_OVERRIDE_SCHEMA",
    "ConfigResult",
    "ConfigVariant",
    "VariantOverride",
    "apply_overrides",
    "create_all",
    "deep_merge",
    "format_grid_csv",
    "format_grid_tab_separated",
    "insert_design_table",
    "materialize_all",
    "parse_design_table",
    "parse_variants",
    "validate_overrides",
    "write_grid_file",
]
