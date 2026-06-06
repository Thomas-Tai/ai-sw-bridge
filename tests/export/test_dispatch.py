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

    SUPPORTED_EXTENSIONS = {".step", ".igs", ".x_t", ".stl", ".3mf", ".dxf"}

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
            def SaveAs3(self, path: str, opts: int, ver: int) -> int:
                return 0

        doc = _BadDoc()
        req = ExportRequest(format="step214", output_dir=tmp_path)
        result = _export_one(doc, req, "TestPart")
        assert result.ok is False
        assert "missing or empty" in result.error

    def test_saveas3_direct_exception(self, tmp_path: Path) -> None:
        class _RaisingDoc:
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

    def test_dxf_flat_is_seat_gated(self, tmp_path: Path) -> None:
        doc = _MockDoc()
        req = ExportRequest(format="dxf_flat", output_dir=tmp_path)
        result = _export_one(doc, req, "TestPart")
        assert result.ok is False
        assert "SEAT-gated" in result.error
        assert "S-SHEETMETAL" in result.error

    def test_step203_uses_nonzero_version(self, tmp_path: Path) -> None:
        doc = _MockDoc()
        req = ExportRequest(format="step203", output_dir=tmp_path)
        _export_one(doc, req, "TestPart")
        assert len(doc.save_calls) == 1
        _, _, version = doc.save_calls[0]
        assert version != 0

    @pytest.mark.parametrize(
        "fmt_name",
        ["step214", "iges", "parasolid", "stl", "3mf", "dxf"],
    )
    def test_all_saveas3_formats_succeed(
        self, tmp_path: Path, fmt_name: str
    ) -> None:
        doc = _MockDoc()
        req = ExportRequest(format=fmt_name, output_dir=tmp_path)
        result = _export_one(doc, req, "TestPart")
        assert result.ok is True, f"{fmt_name}: {result.error}"

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
