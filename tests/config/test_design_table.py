"""Tests for ai_sw_bridge.config.design_table (SW-free layer, W53).

Covers the offline scaffold: parse_design_table, format_grid_csv,
format_grid_tab_separated, DesignTableSpec.validate, and the
DESIGN_TABLE_BLOCK_SCHEMA.  The COM-touching insert_design_table
is seat-gated and not tested here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ai_sw_bridge.config import (
    DESIGN_TABLE_BLOCK_SCHEMA,
    DesignTableColumn,
    DesignTableRow,
    DesignTableSpec,
    format_grid_csv,
    format_grid_tab_separated,
    parse_design_table,
)
from ai_sw_bridge.config.dt_dispatch import write_grid_file


# ---------------------------------------------------------------------------
# parse_design_table()
# ---------------------------------------------------------------------------


class TestParseDesignTable:
    def test_basic_dimension_grid(self) -> None:
        block = {
            "columns": [
                {"name": "D1@Sketch1", "kind": "dimension", "unit": "mm"},
            ],
            "rows": [
                {"config_name": "Small", "values": {"D1@Sketch1": "20.0"}},
                {"config_name": "Large", "values": {"D1@Sketch1": "50.0"}},
            ],
        }
        spec = parse_design_table(block)
        assert len(spec.columns) == 1
        assert len(spec.rows) == 2
        assert spec.columns[0].name == "D1@Sketch1"
        assert spec.columns[0].kind == "dimension"
        assert spec.rows[0].config_name == "Small"
        assert spec.rows[0].values["D1@Sketch1"] == "20.0"

    def test_multi_column_grid(self) -> None:
        block = {
            "columns": [
                {"name": "D1@Sketch1", "kind": "dimension"},
                {"name": "D2@Sketch1", "kind": "dimension"},
            ],
            "rows": [
                {
                    "config_name": "V1",
                    "values": {"D1@Sketch1": "10.0", "D2@Sketch1": "20.0"},
                },
                {
                    "config_name": "V2",
                    "values": {"D1@Sketch1": "30.0", "D2@Sketch1": "40.0"},
                },
            ],
        }
        spec = parse_design_table(block)
        assert len(spec.columns) == 2
        assert spec.config_names == ["V1", "V2"]

    def test_suppression_column(self) -> None:
        block = {
            "columns": [
                {"name": "Suppression", "kind": "suppression"},
            ],
            "rows": [
                {"config_name": "A", "values": {"Suppression": "Suppressed"}},
                {"config_name": "B", "values": {"Suppression": "Unsuppressed"}},
            ],
        }
        spec = parse_design_table(block)
        assert spec.columns[0].kind == "suppression"

    def test_equation_column(self) -> None:
        block = {
            "columns": [
                {"name": "WIDTH", "kind": "equation"},
            ],
            "rows": [
                {"config_name": "Narrow", "values": {"WIDTH": "20.0"}},
                {"config_name": "Wide", "values": {"WIDTH": "80.0"}},
            ],
        }
        spec = parse_design_table(block)
        assert spec.columns[0].kind == "equation"
        assert spec.rows[0].values["WIDTH"] == "20.0"

    def test_default_name(self) -> None:
        block = {
            "columns": [{"name": "X", "kind": "dimension"}],
            "rows": [
                {"config_name": "A", "values": {"X": "1"}},
                {"config_name": "B", "values": {"X": "2"}},
            ],
        }
        spec = parse_design_table(block)
        assert spec.name == "Design Table"

    def test_custom_name(self) -> None:
        block = {
            "name": "MyTable",
            "columns": [{"name": "X", "kind": "dimension"}],
            "rows": [
                {"config_name": "A", "values": {"X": "1"}},
                {"config_name": "B", "values": {"X": "2"}},
            ],
        }
        spec = parse_design_table(block)
        assert spec.name == "MyTable"

    def test_default_kind_is_dimension(self) -> None:
        block = {
            "columns": [{"name": "D1@SK1"}],
            "rows": [
                {"config_name": "A", "values": {"D1@SK1": "1"}},
                {"config_name": "B", "values": {"D1@SK1": "2"}},
            ],
        }
        spec = parse_design_table(block)
        assert spec.columns[0].kind == "dimension"

    def test_rejects_non_dict_block(self) -> None:
        with pytest.raises(ValueError, match="must be an object"):
            parse_design_table([])  # type: ignore[arg-type]

    def test_rejects_non_string_name(self) -> None:
        with pytest.raises(ValueError, match="'name' must be a string"):
            parse_design_table({"name": 42, "columns": [], "rows": []})

    def test_rejects_non_list_columns(self) -> None:
        with pytest.raises(ValueError, match="'columns' must be an array"):
            parse_design_table({"columns": "bad", "rows": []})

    def test_rejects_non_list_rows(self) -> None:
        with pytest.raises(ValueError, match="'rows' must be an array"):
            parse_design_table(
                {"columns": [{"name": "X"}], "rows": "bad"},
            )

    def test_rejects_missing_column_name(self) -> None:
        with pytest.raises(ValueError, match="missing or non-string 'name'"):
            parse_design_table(
                {"columns": [{}], "rows": []},
            )

    def test_rejects_missing_config_name(self) -> None:
        with pytest.raises(ValueError, match="missing or non-string"):
            parse_design_table(
                {
                    "columns": [{"name": "X"}],
                    "rows": [{"values": {}}],
                },
            )

    def test_rejects_duplicate_config_names(self) -> None:
        with pytest.raises(ValueError, match="duplicate config name"):
            parse_design_table(
                {
                    "columns": [{"name": "X"}],
                    "rows": [
                        {"config_name": "A", "values": {"X": "1"}},
                        {"config_name": "A", "values": {"X": "2"}},
                    ],
                }
            )

    def test_rejects_duplicate_column_names(self) -> None:
        with pytest.raises(ValueError, match="duplicate column name"):
            parse_design_table(
                {
                    "columns": [
                        {"name": "X", "kind": "dimension"},
                        {"name": "X", "kind": "dimension"},
                    ],
                    "rows": [
                        {"config_name": "A", "values": {"X": "1"}},
                        {"config_name": "B", "values": {"X": "2"}},
                    ],
                }
            )

    def test_rejects_empty_columns(self) -> None:
        with pytest.raises(ValueError, match="no columns"):
            parse_design_table(
                {
                    "columns": [],
                    "rows": [
                        {"config_name": "A", "values": {}},
                        {"config_name": "B", "values": {}},
                    ],
                }
            )

    def test_rejects_empty_rows(self) -> None:
        with pytest.raises(ValueError, match="no rows"):
            parse_design_table(
                {
                    "columns": [{"name": "X"}],
                    "rows": [],
                }
            )

    def test_rejects_unknown_kind(self) -> None:
        with pytest.raises(ValueError, match="unknown kind"):
            parse_design_table(
                {
                    "columns": [{"name": "X", "kind": "invalid"}],
                    "rows": [
                        {"config_name": "A", "values": {"X": "1"}},
                        {"config_name": "B", "values": {"X": "2"}},
                    ],
                }
            )

    def test_rejects_unknown_column_in_values(self) -> None:
        with pytest.raises(ValueError, match="unknown columns"):
            parse_design_table(
                {
                    "columns": [{"name": "X"}],
                    "rows": [
                        {"config_name": "A", "values": {"X": "1", "Y": "2"}},
                        {"config_name": "B", "values": {"X": "3"}},
                    ],
                }
            )

    def test_numeric_values_converted_to_string(self) -> None:
        block = {
            "columns": [{"name": "X"}],
            "rows": [
                {"config_name": "A", "values": {"X": 42}},
                {"config_name": "B", "values": {"X": 99}},
            ],
        }
        spec = parse_design_table(block)
        assert spec.rows[0].values["X"] == "42"
        assert spec.rows[1].values["X"] == "99"


# ---------------------------------------------------------------------------
# DesignTableSpec.validate()
# ---------------------------------------------------------------------------


class TestDesignTableSpecValidate:
    def test_valid_spec(self) -> None:
        spec = DesignTableSpec(
            columns=[DesignTableColumn("D1@SK1", "dimension")],
            rows=[
                DesignTableRow("A", {"D1@SK1": "10"}),
                DesignTableRow("B", {"D1@SK1": "20"}),
            ],
        )
        assert spec.validate() == []

    def test_no_columns(self) -> None:
        spec = DesignTableSpec(
            rows=[DesignTableRow("A"), DesignTableRow("B")],
        )
        errors = spec.validate()
        assert any("no columns" in e for e in errors)

    def test_no_rows(self) -> None:
        spec = DesignTableSpec(
            columns=[DesignTableColumn("X", "dimension")],
        )
        errors = spec.validate()
        assert any("no rows" in e for e in errors)

    def test_duplicate_config(self) -> None:
        spec = DesignTableSpec(
            columns=[DesignTableColumn("X", "dimension")],
            rows=[
                DesignTableRow("A", {"X": "1"}),
                DesignTableRow("A", {"X": "2"}),
            ],
        )
        errors = spec.validate()
        assert any("duplicate config" in e for e in errors)

    def test_empty_config_name(self) -> None:
        spec = DesignTableSpec(
            columns=[DesignTableColumn("X", "dimension")],
            rows=[
                DesignTableRow("", {"X": "1"}),
                DesignTableRow("B", {"X": "2"}),
            ],
        )
        errors = spec.validate()
        assert any("empty config_name" in e for e in errors)


# ---------------------------------------------------------------------------
# format_grid_csv()
# ---------------------------------------------------------------------------


class TestFormatGridCsv:
    def test_basic_format(self) -> None:
        spec = DesignTableSpec(
            columns=[DesignTableColumn("D1@SK1", "dimension")],
            rows=[
                DesignTableRow("Small", {"D1@SK1": "20.0"}),
                DesignTableRow("Large", {"D1@SK1": "50.0"}),
            ],
        )
        csv_text = format_grid_csv(spec)
        lines = csv_text.strip().split("\n")
        assert len(lines) == 3
        assert lines[0] == ",D1@SK1"
        assert lines[1] == "Small,20.0"
        assert lines[2] == "Large,50.0"

    def test_multi_column(self) -> None:
        spec = DesignTableSpec(
            columns=[
                DesignTableColumn("D1@SK1"),
                DesignTableColumn("D2@SK1"),
            ],
            rows=[
                DesignTableRow("V1", {"D1@SK1": "10", "D2@SK1": "20"}),
                DesignTableRow("V2", {"D1@SK1": "30", "D2@SK1": "40"}),
            ],
        )
        csv_text = format_grid_csv(spec)
        lines = csv_text.strip().split("\n")
        assert lines[0] == ",D1@SK1,D2@SK1"
        assert lines[1] == "V1,10,20"
        assert lines[2] == "V2,30,40"

    def test_missing_value_becomes_empty(self) -> None:
        spec = DesignTableSpec(
            columns=[
                DesignTableColumn("X"),
                DesignTableColumn("Y"),
            ],
            rows=[
                DesignTableRow("A", {"X": "1"}),
                DesignTableRow("B", {"X": "2", "Y": "3"}),
            ],
        )
        csv_text = format_grid_csv(spec)
        lines = csv_text.strip().split("\n")
        assert lines[1] == "A,1,"
        assert lines[2] == "B,2,3"


# ---------------------------------------------------------------------------
# format_grid_tab_separated()
# ---------------------------------------------------------------------------


class TestFormatGridTabSeparated:
    def test_basic_format(self) -> None:
        spec = DesignTableSpec(
            columns=[DesignTableColumn("D1@SK1")],
            rows=[
                DesignTableRow("Small", {"D1@SK1": "20.0"}),
                DesignTableRow("Large", {"D1@SK1": "50.0"}),
            ],
        )
        text = format_grid_tab_separated(spec)
        lines = text.rstrip("\n").split("\n")
        # First cell is empty config-name header, then column names
        header_cells = lines[0].split("\t")
        assert header_cells[0] == ""
        assert header_cells[1] == "D1@SK1"
        assert lines[1] == "Small\t20.0"
        assert lines[2] == "Large\t50.0"


# ---------------------------------------------------------------------------
# DesignTableSpec properties
# ---------------------------------------------------------------------------


class TestDesignTableSpecProperties:
    def test_config_names(self) -> None:
        spec = DesignTableSpec(
            columns=[DesignTableColumn("X")],
            rows=[
                DesignTableRow("A", {"X": "1"}),
                DesignTableRow("B", {"X": "2"}),
                DesignTableRow("C", {"X": "3"}),
            ],
        )
        assert spec.config_names == ["A", "B", "C"]

    def test_column_names(self) -> None:
        spec = DesignTableSpec(
            columns=[
                DesignTableColumn("D1@SK1"),
                DesignTableColumn("D2@SK2"),
            ],
            rows=[
                DesignTableRow("A", {"D1@SK1": "1", "D2@SK2": "2"}),
                DesignTableRow("B", {"D1@SK1": "3", "D2@SK2": "4"}),
            ],
        )
        assert spec.column_names == ["D1@SK1", "D2@SK2"]


# ---------------------------------------------------------------------------
# DESIGN_TABLE_BLOCK_SCHEMA
# ---------------------------------------------------------------------------


class TestDesignTableBlockSchema:
    def test_schema_type(self) -> None:
        assert DESIGN_TABLE_BLOCK_SCHEMA["type"] == "object"

    def test_required_fields(self) -> None:
        assert "columns" in DESIGN_TABLE_BLOCK_SCHEMA["required"]
        assert "rows" in DESIGN_TABLE_BLOCK_SCHEMA["required"]

    def test_columns_min_items(self) -> None:
        cols = DESIGN_TABLE_BLOCK_SCHEMA["properties"]["columns"]
        assert cols["minItems"] == 1

    def test_rows_min_items(self) -> None:
        rows = DESIGN_TABLE_BLOCK_SCHEMA["properties"]["rows"]
        assert rows["minItems"] == 2

    def test_column_kind_enum(self) -> None:
        col_items = DESIGN_TABLE_BLOCK_SCHEMA["properties"]["columns"]["items"]
        kind_prop = col_items["properties"]["kind"]
        assert "dimension" in kind_prop["enum"]
        assert "suppression" in kind_prop["enum"]
        assert "equation" in kind_prop["enum"]
        assert "property" in kind_prop["enum"]


# ---------------------------------------------------------------------------
# write_grid_file()
# ---------------------------------------------------------------------------


class TestWriteGridFile:
    def test_writes_csv_file(self, tmp_path: Path) -> None:
        spec = DesignTableSpec(
            columns=[DesignTableColumn("D1@SK1")],
            rows=[
                DesignTableRow("A", {"D1@SK1": "10"}),
                DesignTableRow("B", {"D1@SK1": "20"}),
            ],
        )
        path = write_grid_file(spec, tmp_path)
        assert path.is_file()
        assert path.name == "design_table.csv"
        text = path.read_text(encoding="utf-8")
        assert "A,10" in text
        assert "B,20" in text

    def test_custom_filename(self, tmp_path: Path) -> None:
        spec = DesignTableSpec(
            columns=[DesignTableColumn("X")],
            rows=[
                DesignTableRow("A", {"X": "1"}),
                DesignTableRow("B", {"X": "2"}),
            ],
        )
        path = write_grid_file(spec, tmp_path, filename="my_grid.csv")
        assert path.name == "my_grid.csv"

    def test_creates_output_dir(self, tmp_path: Path) -> None:
        spec = DesignTableSpec(
            columns=[DesignTableColumn("X")],
            rows=[
                DesignTableRow("A", {"X": "1"}),
                DesignTableRow("B", {"X": "2"}),
            ],
        )
        sub = tmp_path / "nested" / "dir"
        path = write_grid_file(spec, sub)
        assert path.is_file()
