"""Tests for the export dispatch (SW-free, mock doc)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from ai_sw_bridge.export.dispatch import (
    ExportRequest,
    ExportResult,
    _export_one,
    export_all,
    resolve_output_path,
)
from ai_sw_bridge.export.formats import EXPORT_FORMATS, resolve_format


class _MockDoc:
    """Minimal IModelDoc2 mock for export dispatch tests.

    Simulates ``SaveAs3`` by creating the file on disk when the
    extension is one the mock knows about. Does NOT simulate
    IExportPdfData (the PDF path is tested with _MockDrawingDoc).
    """

    SUPPORTED_EXTENSIONS = {".step", ".igs", ".x_t", ".stl", ".3mf", ".dxf", ".dwg"}

    def __init__(self, fail_on: str | None = None, return_error: int = 0) -> None:
        self._fail_on = fail_on
        self._return_error = return_error
        self.save_calls: list[tuple[str, int, int]] = []

    def SaveAs3(self, path: str, options: int, version: int) -> int:
        self.save_calls.append((path, options, version))
        if self._return_error != 0:
            return self._return_error
        p = Path(path)
        if self._fail_on and p.suffix == self._fail_on:
            return 1
        if p.suffix in self.SUPPORTED_EXTENSIONS:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"\x00" * 64)
        return 0

    def GetType(self) -> int:
        """Mock: return Part doc type (1)."""
        return 1


class _MockDrawingDoc(_MockDoc):
    """A mock doc that identifies as a Drawing (GetType=3)."""

    def GetType(self) -> int:
        return 3


class TestExportRequest:
    def test_frozen(self) -> None:
        req = ExportRequest(format="step214", output_dir=Path("/tmp"))
        with pytest.raises(AttributeError):
            req.format = "hacked"  # type: ignore[misc]

    def test_filename_default_none(self) -> None:
        req = ExportRequest(format="step214", output_dir=Path("/tmp"))
        assert req.filename is None

    def test_sheets_default_all(self) -> None:
        req = ExportRequest(format="pdf", output_dir=Path("/tmp"))
        assert req.sheets == "all"

    def test_sheets_list(self) -> None:
        req = ExportRequest(
            format="pdf", output_dir=Path("/tmp"), sheets=["Overview", "Detail"]
        )
        assert req.sheets == ["Overview", "Detail"]


class TestExportResult:
    def test_to_dict_success(self) -> None:
        r = ExportResult(format="step214", path="/out/part.step", ok=True)
        d = r.to_dict()
        assert d == {"format": "step214", "path": "/out/part.step", "ok": True}
        assert "error" not in d

    def test_to_dict_failure(self) -> None:
        r = ExportResult(
            format="pdf", path="/out/part.pdf", ok=False, error="not a drawing"
        )
        d = r.to_dict()
        assert d["error"] == "not a drawing"
        assert d["ok"] is False


class TestResolveOutputPath:
    def test_uses_part_name(self, tmp_path: Path) -> None:
        req = ExportRequest(format="step214", output_dir=tmp_path)
        fmt = resolve_format("step214")
        p = resolve_output_path(req, "MotorPlate", fmt)
        assert p.name == "MotorPlate.step"
        assert p.parent == tmp_path.resolve()

    def test_uses_filename_override(self, tmp_path: Path) -> None:
        req = ExportRequest(
            format="step214", output_dir=tmp_path, filename="rev_A"
        )
        fmt = resolve_format("step214")
        p = resolve_output_path(req, "MotorPlate", fmt)
        assert p.name == "rev_A.step"

    def test_creates_missing_dir(self, tmp_path: Path) -> None:
        sub = tmp_path / "nested" / "output"
        req = ExportRequest(format="iges", output_dir=sub)
        fmt = resolve_format("iges")
        p = resolve_output_path(req, "Part", fmt)
        assert sub.exists()
        assert p.name == "Part.igs"


class TestExportOne:
    def test_saveas3_direct_success(self, tmp_path: Path) -> None:
        doc = _MockDoc()
        req = ExportRequest(format="step214", output_dir=tmp_path)
        result = _export_one(doc, req, "TestPart")
        assert result.ok is True
        assert result.format == "step214"
        assert result.path.endswith("TestPart.step")
        assert len(doc.save_calls) == 1

    def test_saveas3_direct_error_code(self, tmp_path: Path) -> None:
        doc = _MockDoc(return_error=2)
        req = ExportRequest(format="stl", output_dir=tmp_path)
        result = _export_one(doc, req, "TestPart")
        assert result.ok is False
        assert "swFileSaveError=2" in result.error

    def test_saveas3_direct_missing_file(self, tmp_path: Path) -> None:
        """Mock returns NoError but doesn't create the file."""

        class _BadDoc:
            def GetType(self) -> int:
                return 1  # Part doc (needed for W34 3D format guard)

            def SaveAs3(self, path: str, opts: int, ver: int) -> int:
                return 0

        doc = _BadDoc()
        req = ExportRequest(format="step214", output_dir=tmp_path)
        result = _export_one(doc, req, "TestPart")
        assert result.ok is False
        assert "missing or empty" in result.error

    def test_saveas3_direct_exception(self, tmp_path: Path) -> None:
        class _RaisingDoc:
            def GetType(self) -> int:
                return 1  # Part doc (needed for W34 3D format guard)

            def SaveAs3(self, path: str, opts: int, ver: int) -> int:
                raise RuntimeError("COM timeout")

        doc = _RaisingDoc()
        req = ExportRequest(format="step214", output_dir=tmp_path)
        result = _export_one(doc, req, "TestPart")
        assert result.ok is False
        assert "COM timeout" in result.error

    def test_unknown_format(self, tmp_path: Path) -> None:
        doc = _MockDoc()
        req = ExportRequest(format="nonexistent", output_dir=tmp_path)
        result = _export_one(doc, req, "TestPart")
        assert result.ok is False
        assert "Unknown export format" in result.error

    def test_pdf_on_part_rejected(self, tmp_path: Path) -> None:
        """format:'pdf' on a Part doc (GetType=1) is rejected."""
        doc = _MockDoc()  # GetType returns 1 (Part)
        req = ExportRequest(format="pdf", output_dir=tmp_path)
        result = _export_one(doc, req, "TestPart")
        assert result.ok is False
        assert "Drawing" in result.error

    def test_pdf_on_drawing_doc_type_check(self, tmp_path: Path) -> None:
        """format:'pdf' passes the doc-type check on a Drawing mock
        but still fails because the mock doesn't implement COM."""
        doc = _MockDrawingDoc()
        req = ExportRequest(format="pdf", output_dir=tmp_path)
        result = _export_one(doc, req, "TestPart")
        # The doc-type check passes (GetType=3), but the COM path
        # will fail because mock doesn't have Extension/GetExportFileData
        assert result.ok is False
        # Should NOT contain "Drawing" doc-type error
        assert "Drawing (.SLDDRW)" not in result.error

    def test_dxf_flat_requires_flat_pattern_feature(self, tmp_path: Path) -> None:
        """W42 SHIPPED: dxf_flat is seat-confirmed, so it no longer fails-closed
        at a seat gate. On a plain (non-sheet-metal) mock it now reaches the
        real export path and fails because there is no Flat-Pattern feature."""
        doc = _MockDoc()
        req = ExportRequest(format="dxf_flat", output_dir=tmp_path)
        result = _export_one(doc, req, "TestPart")
        assert result.ok is False
        assert "Flat-Pattern" in result.error

    def test_step203_uses_nonzero_version(self, tmp_path: Path) -> None:
        doc = _MockDoc()
        req = ExportRequest(format="step203", output_dir=tmp_path)
        _export_one(doc, req, "TestPart")
        assert len(doc.save_calls) == 1
        _, _, version = doc.save_calls[0]
        assert version != 0

    @pytest.mark.parametrize(
        "fmt_name",
        ["step214", "iges", "parasolid", "stl", "3mf"],  # DXF excluded: requires Drawing doc
    )
    def test_all_saveas3_formats_succeed(
        self, tmp_path: Path, fmt_name: str
    ) -> None:
        doc = _MockDoc()
        req = ExportRequest(format=fmt_name, output_dir=tmp_path)
        result = _export_one(doc, req, "TestPart")
        assert result.ok is True, f"{fmt_name}: {result.error}"

    def test_dxf_succeeds_on_drawing_doc(self, tmp_path: Path) -> None:
        """DXF export requires a Drawing doc (W33 doc-type fail-closed)."""
        doc = _MockDrawingDoc()
        req = ExportRequest(format="dxf", output_dir=tmp_path)
        result = _export_one(doc, req, "TestDrawing")
        assert result.ok is True, f"dxf on drawing: {result.error}"

    def test_dxf_fails_on_part_doc(self, tmp_path: Path) -> None:
        """DXF export rejects Part docs with clear error (W33)."""
        doc = _MockDoc()  # GetType() = 1 (Part)
        req = ExportRequest(format="dxf", output_dir=tmp_path)
        result = _export_one(doc, req, "TestPart")
        assert result.ok is False
        assert "Drawing (.SLDDRW)" in result.error
        assert "doc type is 1" in result.error

    # --- W34: 3D formats reject Drawing docs ---

    @pytest.mark.parametrize(
        "fmt_name", ["step214", "step203", "iges", "stl", "parasolid", "3mf"]
    )
    def test_3d_format_rejects_drawing_doc(
        self, tmp_path: Path, fmt_name: str
    ) -> None:
        """3D formats (STEP/IGES/STL/Parasolid/3MF) require Part or Assembly (W34)."""
        doc = _MockDrawingDoc()  # GetType() = 3 (Drawing)
        req = ExportRequest(format=fmt_name, output_dir=tmp_path)
        result = _export_one(doc, req, "TestDrawing")
        assert result.ok is False, f"{fmt_name}: should reject Drawing doc"
        assert "Part (.SLDPRT) or Assembly" in result.error
        assert "doc type is 3" in result.error

    def test_pdf_invalid_sheets_value(self, tmp_path: Path) -> None:
        """sheets with empty list is rejected."""
        doc = _MockDrawingDoc()
        req = ExportRequest(
            format="pdf", output_dir=tmp_path, sheets=[]
        )
        result = _export_one(doc, req, "TestPart")
        assert result.ok is False
        assert "Invalid" in result.error


class TestExportAll:
    def test_multiple_formats(self, tmp_path: Path) -> None:
        doc = _MockDoc()
        requests = [
            ExportRequest(format="step214", output_dir=tmp_path),
            ExportRequest(format="stl", output_dir=tmp_path),
        ]
        results = export_all(doc, requests, "TestPart")
        assert len(results) == 2
        assert all(r.ok for r in results)

    def test_partial_failure(self, tmp_path: Path) -> None:
        doc = _MockDoc()
        requests = [
            ExportRequest(format="step214", output_dir=tmp_path),
            ExportRequest(format="pdf", output_dir=tmp_path),
            ExportRequest(format="stl", output_dir=tmp_path),
        ]
        results = export_all(doc, requests, "TestPart")
        assert len(results) == 3
        assert results[0].ok is True
        assert results[1].ok is False
        assert results[2].ok is True

    def test_empty_requests(self, tmp_path: Path) -> None:
        doc = _MockDoc()
        results = export_all(doc, [], "TestPart")
        assert results == []

    def test_human_stream_output(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        doc = _MockDoc()
        requests = [
            ExportRequest(format="step214", output_dir=tmp_path),
            ExportRequest(format="pdf", output_dir=tmp_path),
        ]
        export_all(doc, requests, "TestPart")
        captured = capsys.readouterr()
        assert "exported step214" in captured.err
        assert "FAILED pdf" in captured.err

    def test_order_preserved(self, tmp_path: Path) -> None:
        doc = _MockDoc()
        formats = ["iges", "stl", "step214", "parasolid"]
        requests = [
            ExportRequest(format=f, output_dir=tmp_path) for f in formats
        ]
        results = export_all(doc, requests, "TestPart")
        assert [r.format for r in results] == formats


class TestDWGDocTypeGuard:
    """W52: DWG requires Drawing doc (mirror DXF fail-closed)."""

    def test_dwg_succeeds_on_drawing_doc(self, tmp_path: Path) -> None:
        doc = _MockDrawingDoc()
        req = ExportRequest(format="dwg", output_dir=tmp_path)
        result = _export_one(doc, req, "TestDrawing")
        assert result.ok is True, f"dwg on drawing: {result.error}"

    def test_dwg_fails_on_part_doc(self, tmp_path: Path) -> None:
        doc = _MockDoc()  # GetType() = 1 (Part)
        req = ExportRequest(format="dwg", output_dir=tmp_path)
        result = _export_one(doc, req, "TestPart")
        assert result.ok is False
        assert "Drawing (.SLDDRW)" in result.error
        assert "doc type is 1" in result.error

    def test_dwg_fails_on_assembly_doc(self, tmp_path: Path) -> None:
        class _MockAssemblyDoc(_MockDoc):
            def GetType(self) -> int:
                return 2

        doc = _MockAssemblyDoc()
        req = ExportRequest(format="dwg", output_dir=tmp_path)
        result = _export_one(doc, req, "TestAssembly")
        assert result.ok is False
        assert "Drawing (.SLDDRW)" in result.error


class TestExportRequestBinary:
    """W52: ExportRequest.binary field."""

    def test_binary_default_none(self) -> None:
        req = ExportRequest(format="stl", output_dir=Path("/tmp"))
        assert req.binary is None

    def test_binary_true(self) -> None:
        req = ExportRequest(format="stl", output_dir=Path("/tmp"), binary=True)
        assert req.binary is True

    def test_binary_false(self) -> None:
        req = ExportRequest(format="stl", output_dir=Path("/tmp"), binary=False)
        assert req.binary is False


class TestSTLBinaryOption:
    """W52: STL binary/ASCII toggle dispatch."""

    def test_stl_default_no_preference_set(self, tmp_path: Path) -> None:
        """binary=None → no preference set, SaveAs3 proceeds normally."""
        doc = _MockDoc()
        req = ExportRequest(format="stl", output_dir=tmp_path)
        result = _export_one(doc, req, "TestPart")
        assert result.ok is True

    def test_stl_binary_true(self, tmp_path: Path) -> None:
        """binary=True → preference set before SaveAs3 (if enum ID known)."""
        doc = _MockDoc()
        req = ExportRequest(format="stl", output_dir=tmp_path, binary=True)
        result = _export_one(doc, req, "TestPart")
        assert result.ok is True

    def test_stl_binary_false(self, tmp_path: Path) -> None:
        """binary=False → preference set before SaveAs3 (if enum ID known)."""
        doc = _MockDoc()
        req = ExportRequest(format="stl", output_dir=tmp_path, binary=False)
        result = _export_one(doc, req, "TestPart")
        assert result.ok is True


class TestApplyExportPreferences:
    """W52: _apply_export_preferences helper."""

    def test_skips_when_no_extension(self) -> None:
        """Doc without Extension attr → silently skips."""
        from ai_sw_bridge.export.dispatch import (
            _apply_export_preferences,
        )
        from ai_sw_bridge.export.formats import resolve_format

        class _NoExtDoc:
            pass

        fmt = resolve_format("stl")
        _apply_export_preferences(_NoExtDoc(), fmt, binary=True)

    def test_stl_toggle_calls_extension(self) -> None:
        """STL with binary=True calls SetUserPreferenceToggle when ID known."""
        from ai_sw_bridge.export import dispatch as disp
        from ai_sw_bridge.export.dispatch import (
            _apply_export_preferences,
        )
        from ai_sw_bridge.export.formats import resolve_format

        class _MockExt:
            calls: list[tuple[int, bool]] = []

            def SetUserPreferenceToggle(self, toggle_id: int, value: bool) -> None:
                self.calls.append((toggle_id, value))

        class _MockDocWithExt:
            Extension = _MockExt()

        fmt = resolve_format("stl")
        old_val = disp._SW_STL_BINARY_TOGGLE
        try:
            disp._SW_STL_BINARY_TOGGLE = 999
            _apply_export_preferences(_MockDocWithExt(), fmt, binary=True)
            assert len(_MockExt.calls) == 1
            assert _MockExt.calls[0] == (999, True)
        finally:
            disp._SW_STL_BINARY_TOGGLE = old_val

    def test_stl_toggle_skipped_when_id_none(self) -> None:
        """STL toggle skipped when enum ID is None (seat-pending)."""
        from ai_sw_bridge.export import dispatch as disp
        from ai_sw_bridge.export.dispatch import (
            _apply_export_preferences,
        )
        from ai_sw_bridge.export.formats import resolve_format

        class _MockExt:
            calls: list = []

            def SetUserPreferenceToggle(self, toggle_id: int, value: bool) -> None:
                self.calls.append((toggle_id, value))

        class _MockDocWithExt:
            Extension = _MockExt()

        fmt = resolve_format("stl")
        old_val = disp._SW_STL_BINARY_TOGGLE
        try:
            disp._SW_STL_BINARY_TOGGLE = None
            _apply_export_preferences(_MockDocWithExt(), fmt, binary=True)
            assert len(_MockExt.calls) == 0
        finally:
            disp._SW_STL_BINARY_TOGGLE = old_val

    def test_step_ap_calls_extension(self) -> None:
        """STEP format calls SetUserPreferenceIntegerValue for AP selection."""
        from ai_sw_bridge.export import dispatch as disp
        from ai_sw_bridge.export.dispatch import (
            _apply_export_preferences,
        )
        from ai_sw_bridge.export.formats import resolve_format

        class _MockExt:
            calls: list[tuple[int, int]] = []

            def SetUserPreferenceIntegerValue(self, pref_id: int, value: int) -> None:
                self.calls.append((pref_id, value))

        class _MockDocWithExt:
            Extension = _MockExt()

        fmt = resolve_format("step203")
        old_int = disp._SW_STEP_AP_INTEGER
        old_203 = disp._SW_STEP_AP203
        old_214 = disp._SW_STEP_AP214
        try:
            disp._SW_STEP_AP_INTEGER = 888
            disp._SW_STEP_AP203 = 1
            disp._SW_STEP_AP214 = 2
            _apply_export_preferences(_MockDocWithExt(), fmt)
            assert len(_MockExt.calls) == 1
            assert _MockExt.calls[0] == (888, 1)
        finally:
            disp._SW_STEP_AP_INTEGER = old_int
            disp._SW_STEP_AP203 = old_203
            disp._SW_STEP_AP214 = old_214

    def test_step214_ap_value(self) -> None:
        """STEP214 format sets AP214 value."""
        from ai_sw_bridge.export import dispatch as disp
        from ai_sw_bridge.export.dispatch import (
            _apply_export_preferences,
        )
        from ai_sw_bridge.export.formats import resolve_format

        class _MockExt:
            calls: list[tuple[int, int]] = []

            def SetUserPreferenceIntegerValue(self, pref_id: int, value: int) -> None:
                self.calls.append((pref_id, value))

        class _MockDocWithExt:
            Extension = _MockExt()

        fmt = resolve_format("step214")
        old_int = disp._SW_STEP_AP_INTEGER
        old_203 = disp._SW_STEP_AP203
        old_214 = disp._SW_STEP_AP214
        try:
            disp._SW_STEP_AP_INTEGER = 888
            disp._SW_STEP_AP203 = 1
            disp._SW_STEP_AP214 = 2
            _apply_export_preferences(_MockDocWithExt(), fmt)
            assert len(_MockExt.calls) == 1
            assert _MockExt.calls[0] == (888, 2)
        finally:
            disp._SW_STEP_AP_INTEGER = old_int
            disp._SW_STEP_AP203 = old_203
            disp._SW_STEP_AP214 = old_214

    def test_non_stl_step_ignored(self) -> None:
        """Non-STL/STEP formats don't trigger any preference calls."""
        from ai_sw_bridge.export import dispatch as disp
        from ai_sw_bridge.export.dispatch import (
            _apply_export_preferences,
        )
        from ai_sw_bridge.export.formats import resolve_format

        class _MockExt:
            toggle_calls: list = []
            int_calls: list = []

            def SetUserPreferenceToggle(self, *args: Any) -> None:
                self.toggle_calls.append(args)

            def SetUserPreferenceIntegerValue(self, *args: Any) -> None:
                self.int_calls.append(args)

        class _MockDocWithExt:
            Extension = _MockExt()

        fmt = resolve_format("iges")
        old_val = disp._SW_STL_BINARY_TOGGLE
        old_int = disp._SW_STEP_AP_INTEGER
        try:
            disp._SW_STL_BINARY_TOGGLE = 999
            disp._SW_STEP_AP_INTEGER = 888
            _apply_export_preferences(_MockDocWithExt(), fmt, binary=True)
            assert len(_MockExt.toggle_calls) == 0
            assert len(_MockExt.int_calls) == 0
        finally:
            disp._SW_STL_BINARY_TOGGLE = old_val
            disp._SW_STEP_AP_INTEGER = old_int
