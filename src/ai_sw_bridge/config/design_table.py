"""Design table specification model (W53, Phase-4 remaining item).

A design table is SOLIDWORKS' native in-file mechanism for driving N
configurations from a parameter grid.  Unlike the W36 native-config
approach (which created configs and tried to suppress/dimension them
individually — all walled at SetSuppression2 / per-config scope),
design tables are the *separate, viable path* because the table
itself is the authoritative config source — SW generates the configs
from the table, not the other way around.

This module defines the SW-free data model:

- ``DesignTableColumn`` — one parameter column (name, type, unit).
- ``DesignTableRow`` — one configuration row (name + values per column).
- ``DesignTableSpec`` — the complete grid (columns + rows).
- ``parse_design_table`` — parse a ``design_table:`` block from a spec.
- ``format_grid_csv`` — format the grid into the CSV text that
  ``IModelDoc2.InsertFamilyTableNew`` / ``IDesignTable`` expects.

The actual COM insertion (``InsertFamilyTableNew`` or
``IDesignTable`` edit operations) is SEAT-gated in ``dt_dispatch.py``.

Column naming convention (SW design table syntax):
  - Dimension: ``"D1@Sketch1"`` or ``"D2@Boss-Extrude1"``
  - Feature suppression: ``"Suppression"`` (values: Suppressed/Unsuppressed)
  - Equation variable: ``"WIDTH"`` (the quoted locals variable name)
  - Configuration property: ``"$PRP:description"`` etc.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class DesignTableColumn:
    """One column in a design table parameter grid.

    Attributes:
        name: The SW design-table column header.  Must use the exact
            SW naming convention so the design table engine binds it
            to the correct parameter.  Examples:
            ``"D1@Sketch1"`` (sketch dimension),
            ``"Suppression"`` (feature suppression),
            ``"WIDTH"`` (equation variable).
        kind: Column kind — ``"dimension"``, ``"suppression"``,
            ``"equation"``, or ``"property"``.  Informational for
            the offline layer; SW determines binding from the
            ``name`` column.
        unit: Optional unit hint (``"mm"``, ``"deg"``).  SW design
            tables use document units by default; this is a
            documentation aid.
    """

    name: str
    kind: str = "dimension"
    unit: str = ""


@dataclass(frozen=True)
class DesignTableRow:
    """One configuration row in the design table.

    Attributes:
        config_name: The configuration name SW will create for this
            row.  Must be unique within the table.
        values: Column-value pairs, keyed by column ``name``.  Values
            are strings matching the SW design table cell format:
            - Dimensions: ``"25.0"`` (numeric string)
            - Suppression: ``"Suppressed"`` or ``"Unsuppressed"``
            - Equations: ``"50.0"`` or ``"\"X\" + 3"``
    """

    config_name: str
    values: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class DesignTableSpec:
    """Complete design table specification.

    Attributes:
        name: The design table feature name in SW (default
            ``"Design Table"``).
        columns: Ordered list of parameter columns.
        rows: Ordered list of configuration rows.
    """

    name: str = "Design Table"
    columns: list[DesignTableColumn] = field(default_factory=list)
    rows: list[DesignTableRow] = field(default_factory=list)

    @property
    def config_names(self) -> list[str]:
        return [r.config_name for r in self.rows]

    @property
    def column_names(self) -> list[str]:
        return [c.name for c in self.columns]

    def validate(self) -> list[str]:
        """Return a list of structural errors (empty = clean)."""
        errors: list[str] = []
        col_names = self.column_names

        if not col_names:
            errors.append("design table has no columns")
        if not self.rows:
            errors.append("design table has no rows")

        seen_configs: set[str] = set()
        for i, row in enumerate(self.rows):
            if not row.config_name:
                errors.append(f"row[{i}] has empty config_name")
            if row.config_name in seen_configs:
                errors.append(
                    f"duplicate config name: {row.config_name!r}"
                )
            seen_configs.add(row.config_name)

            unknown_cols = set(row.values.keys()) - set(col_names)
            if unknown_cols:
                errors.append(
                    f"row {row.config_name!r}: unknown columns "
                    f"{sorted(unknown_cols)}"
                )

        seen_cols: set[str] = set()
        for c in self.columns:
            if not c.name:
                errors.append("column has empty name")
            if c.name in seen_cols:
                errors.append(f"duplicate column name: {c.name!r}")
            seen_cols.add(c.name)
            if c.kind not in (
                "dimension", "suppression", "equation", "property",
            ):
                errors.append(
                    f"column {c.name!r}: unknown kind {c.kind!r}"
                )

        return errors


def parse_design_table(block: dict[str, Any]) -> DesignTableSpec:
    """Parse a ``design_table:`` block from a JSON spec.

    Expected structure::

        {
            "name": "Design Table",
            "columns": [
                {"name": "D1@Sketch1", "kind": "dimension", "unit": "mm"}
            ],
            "rows": [
                {"config_name": "Small", "values": {"D1@Sketch1": "20.0"}},
                {"config_name": "Large", "values": {"D1@Sketch1": "50.0"}}
            ]
        }

    Raises:
        ValueError: on structural problems.
    """
    if not isinstance(block, dict):
        raise ValueError("design_table block must be an object")

    name = block.get("name", "Design Table")
    if not isinstance(name, str):
        raise ValueError("'name' must be a string")

    raw_columns = block.get("columns", [])
    if not isinstance(raw_columns, list):
        raise ValueError("'columns' must be an array")

    columns: list[DesignTableColumn] = []
    for i, col in enumerate(raw_columns):
        if not isinstance(col, dict):
            raise ValueError(f"columns[{i}] must be an object")
        col_name = col.get("name")
        if not col_name or not isinstance(col_name, str):
            raise ValueError(
                f"columns[{i}] missing or non-string 'name'"
            )
        kind = col.get("kind", "dimension")
        if not isinstance(kind, str):
            raise ValueError(
                f"column {col_name!r}: 'kind' must be a string"
            )
        unit = col.get("unit", "")
        if not isinstance(unit, str):
            raise ValueError(
                f"column {col_name!r}: 'unit' must be a string"
            )
        columns.append(DesignTableColumn(
            name=col_name, kind=kind, unit=unit,
        ))

    raw_rows = block.get("rows", [])
    if not isinstance(raw_rows, list):
        raise ValueError("'rows' must be an array")

    rows: list[DesignTableRow] = []
    for i, row in enumerate(raw_rows):
        if not isinstance(row, dict):
            raise ValueError(f"rows[{i}] must be an object")
        config_name = row.get("config_name")
        if not config_name or not isinstance(config_name, str):
            raise ValueError(
                f"rows[{i}] missing or non-string 'config_name'"
            )
        raw_values = row.get("values", {})
        if not isinstance(raw_values, dict):
            raise ValueError(
                f"row {config_name!r}: 'values' must be an object"
            )
        values: dict[str, str] = {}
        for col_name, val in raw_values.items():
            values[col_name] = str(val)
        rows.append(DesignTableRow(
            config_name=config_name, values=values,
        ))

    spec = DesignTableSpec(name=name, columns=columns, rows=rows)
    errors = spec.validate()
    if errors:
        raise ValueError(
            f"design table validation failed: {'; '.join(errors)}"
        )

    return spec


def format_grid_csv(dt_spec: DesignTableSpec) -> str:
    """Format a design table spec as CSV text.

    The first row is the header: ``""`` (blank, for the config-name
    column) followed by each column name.  Subsequent rows have the
    config name in the first column, then values in the same order as
    the columns.

    This matches the format SW expects for design-table insertion
    via ``InsertFamilyTableNew`` or clipboard-paste into
    ``IDesignTable.EditTable2``.
    """
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")

    header = [""] + dt_spec.column_names
    writer.writerow(header)

    for row in dt_spec.rows:
        cells = [row.config_name]
        for col in dt_spec.columns:
            cells.append(row.values.get(col.name, ""))
        writer.writerow(cells)

    return buf.getvalue()


def format_grid_tab_separated(dt_spec: DesignTableSpec) -> str:
    """Format as tab-separated text (SW design table clipboard format).

    SW design tables are Excel-backed OLE objects; the clipboard
    paste path uses tab-separated values.  This format is the
    canonical one for programmatic insertion.
    """
    lines: list[str] = []

    header = "\t".join([""] + dt_spec.column_names)
    lines.append(header)

    for row in dt_spec.rows:
        cells = [row.config_name]
        for col in dt_spec.columns:
            cells.append(row.values.get(col.name, ""))
        lines.append("\t".join(cells))

    return "\n".join(lines) + "\n"


DESIGN_TABLE_BLOCK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["columns", "rows"],
    "properties": {
        "name": {"type": "string"},
        "columns": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["name"],
                "properties": {
                    "name": {"type": "string"},
                    "kind": {
                        "type": "string",
                        "enum": [
                            "dimension", "suppression",
                            "equation", "property",
                        ],
                    },
                    "unit": {"type": "string"},
                },
            },
        },
        "rows": {
            "type": "array",
            "minItems": 2,
            "items": {
                "type": "object",
                "required": ["config_name", "values"],
                "properties": {
                    "config_name": {"type": "string"},
                    "values": {
                        "type": "object",
                        "additionalProperties": True,
                    },
                },
            },
        },
    },
}


__all__ = [
    "DESIGN_TABLE_BLOCK_SCHEMA",
    "DesignTableColumn",
    "DesignTableRow",
    "DesignTableSpec",
    "format_grid_csv",
    "format_grid_tab_separated",
    "parse_design_table",
]
