"""Tests for the export format registry (SW-free, pure data)."""

from __future__ import annotations

import pytest

from ai_sw_bridge.export.formats import (
    EXPORT_FORMAT_NAMES,
    EXPORT_FORMATS,
    ExportFormat,
    SaveMethod,
    resolve_format,
)


class TestExportFormats:
    """EXPORT_FORMATS table integrity."""

    def test_all_formats_registered(self) -> None:
        expected = {
            "step214",
            "step203",
            "iges",
            "parasolid",
            "stl",
            "3mf",
            "pdf",
            "dxf",
            "dxf_flat",
        }
        assert EXPORT_FORMAT_NAMES == expected

    def test_format_names_frozenset_matches_dict(self) -> None:
        assert EXPORT_FORMAT_NAMES == frozenset(EXPORT_FORMATS)

    def test_every_format_has_extension(self) -> None:
        for name, fmt in EXPORT_FORMATS.items():
            assert fmt.extension.startswith("."), f"{name} extension missing dot"
            assert len(fmt.extension) > 1, f"{name} extension is just a dot"

    def test_every_format_has_description(self) -> None:
        for name, fmt in EXPORT_FORMATS.items():
            assert fmt.description, f"{name} has no description"

    def test_formats_are_frozen(self) -> None:
        fmt = EXPORT_FORMATS["step214"]
        with pytest.raises(AttributeError):
            fmt.name = "hacked"  # type: ignore[misc]

    @pytest.mark.parametrize(
        "name",
        ["step214", "iges", "parasolid", "stl", "3mf", "dxf"],
    )
    def test_saveas3_direct_formats(self, name: str) -> None:
        assert EXPORT_FORMATS[name].save_method == SaveMethod.SAVEAS3_DIRECT

    def test_pdf_is_export_pdf(self) -> None:
        assert EXPORT_FORMATS["pdf"].save_method == SaveMethod.EXPORT_PDF

    def test_dxf_flat_is_flat_pattern(self) -> None:
        assert EXPORT_FORMATS["dxf_flat"].save_method == SaveMethod.FLAT_PATTERN_DXF

    def test_step203_has_nonzero_version(self) -> None:
        assert EXPORT_FORMATS["step203"].save_version != 0

    def test_seat_confirmed_formats(self) -> None:
        """P1.1-seat confirmed 6 SAVEAS3_DIRECT formats + PDF on SW 2024 SP1."""
        expected = {"step214", "step203", "iges", "parasolid", "stl", "3mf", "pdf"}
        confirmed = {n for n, f in EXPORT_FORMATS.items() if f.seat_confirmed}
        assert confirmed == expected


class TestResolveFormat:
    """resolve_format() lookup."""

    def test_known_format(self) -> None:
        fmt = resolve_format("step214")
        assert isinstance(fmt, ExportFormat)
        assert fmt.name == "step214"
        assert fmt.extension == ".step"

    def test_unknown_format_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown export format"):
            resolve_format("nonexistent")

    def test_unknown_format_lists_known(self) -> None:
        with pytest.raises(ValueError, match="step214"):
            resolve_format("nonexistent")
