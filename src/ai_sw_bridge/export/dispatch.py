"""Export dispatch (spec.md §6, FR-1-03, todolist P1.1).

Iterates the ``export:`` block from a schema-v2 spec, dispatches each
entry to the correct save path, and collects results.

Two-stream discipline (``UIUX.md`` §8):
  - **Human stream** (stderr): one line per file written, with path.
  - **Machine stream**: ``ExportResult`` list returned to the caller;
    the caller (builder / CLI) folds it into the JSON result.

The SW-free skeleton validates format names, resolves output paths,
and structures the dispatch loop. The actual COM save calls are:

- **SaveAs3-direct** formats (STEP / IGES / Parasolid / STL / 3MF /
  DXF): use the proven ``doc.SaveAs3(path, 0, version)`` call from
  ``builder.py``. The extension in the path selects the exporter.
  SW-free in the sense that the call shape is already proven for
  ``.sldprt``; the per-format extension strings need a seat to confirm.
- **ExportPdfData** (``pdf``): uses ``ISldWorks.GetExportFileData(1)``
  → ``IExportPdfData.SetSheets`` → ``IModelDocExtension.SaveAs``.
  Requires the open document to be a Drawing (.SLDDRW). W25 seat-
  confirmed.
- **Flat-pattern DXF** (``dxf_flat``): needs the flat-pattern config
  activated first — SEAT-gated + gated by S-SHEETMETAL.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .formats import (
    EXPORT_FORMATS,
    ExportFormat,
    SaveMethod,
    resolve_format,
)

logger = logging.getLogger("ai_sw_bridge.export")

# swDocumentTypes_e
_SW_DOC_DRAWING = 3

# swExportDataFileType_e
_SW_EXPORT_PDF_DATA = 1

# swExportDataSheetsToExport_e
_SW_EXPORT_ALL_SHEETS = 1
_SW_EXPORT_SPECIFIED_SHEETS = 3

# swSaveAsVersion_e
_SW_SAVE_AS_CURRENT_VERSION = 0

# swSaveAsOptions_e
_SW_SAVE_AS_OPTIONS_SILENT = 1


@dataclass(frozen=True)
class ExportRequest:
    """One entry from the spec's ``export:`` block.

    Attributes:
        format: Format name from ``EXPORT_FORMATS`` (e.g. ``"step214"``).
        output_dir: Directory to write the exported file into.
        filename: Override filename (without extension). When ``None``,
            the part name is used.
        sheets: PDF-only sheet selection. ``"all"`` (default) exports
            every sheet; a list of sheet name strings exports only
            those. Ignored for non-PDF formats.
    """

    format: str
    output_dir: Path
    filename: str | None = None
    sheets: str | list[str] = "all"


@dataclass
class ExportResult:
    """Outcome of one export attempt.

    Attributes:
        format: The format name that was requested.
        path: Resolved absolute path of the output file (set even on
            failure, so the caller knows where it *would* have landed).
        ok: ``True`` if the file was written and verified.
        error: Human-readable error string on failure; ``None`` on
            success.
    """

    format: str
    path: str
    ok: bool
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "format": self.format,
            "path": self.path,
            "ok": self.ok,
        }
        if self.error is not None:
            out["error"] = self.error
        return out


def resolve_output_path(
    request: ExportRequest,
    part_name: str,
    fmt: ExportFormat,
) -> Path:
    """Compute the absolute output path for an export request.

    Uses ``request.filename`` if set, otherwise ``part_name``. Appends
    the format's extension. Creates the output directory if missing.
    """
    stem = request.filename or part_name
    out_path = (request.output_dir / f"{stem}{fmt.extension}").resolve()
    request.output_dir.mkdir(parents=True, exist_ok=True)
    return out_path


def export_all(
    doc: Any,
    requests: list[ExportRequest],
    part_name: str,
) -> list[ExportResult]:
    """Export the open document in every requested format.

    Args:
        doc: An ``IModelDoc2``-like dispatch object (live or mock).
        requests: Parsed entries from the spec's ``export:`` block.
        part_name: The part name, used as the default filename stem.

    Returns:
        One ``ExportResult`` per request, in the same order. Failures
        are captured per-entry (one bad format doesn't abort the rest).

    Side effects:
        Prints each written path to stderr (human stream).
    """
    results: list[ExportResult] = []
    for req in requests:
        result = _export_one(doc, req, part_name)
        if result.ok:
            print(f"  exported {result.format} → {result.path}", file=sys.stderr)
        else:
            print(
                f"  FAILED {result.format} → {result.path}: {result.error}",
                file=sys.stderr,
            )
        results.append(result)
    return results


def _export_one(doc: Any, req: ExportRequest, part_name: str) -> ExportResult:
    """Dispatch one export request to the correct save path."""
    try:
        fmt = resolve_format(req.format)
    except ValueError as exc:
        return ExportResult(
            format=req.format,
            path="",
            ok=False,
            error=str(exc),
        )

    out_path = resolve_output_path(req, part_name, fmt)
    path_str = str(out_path)

    if fmt.save_method == SaveMethod.SAVEAS3_DIRECT:
        return _saveas3_direct(doc, fmt, out_path)
    if fmt.save_method == SaveMethod.EXPORT_PDF:
        return _export_pdf(doc, fmt, out_path, req.sheets)
    if fmt.save_method == SaveMethod.FLAT_PATTERN_DXF:
        return ExportResult(
            format=fmt.name,
            path=path_str,
            ok=False,
            error=(
                "Flat-pattern DXF export is SEAT-gated (P1.1) and gated "
                "by S-SHEETMETAL. Needs the flat-pattern config activated "
                "before ExportToDWG2."
            ),
        )
    return ExportResult(
        format=fmt.name,
        path=path_str,
        ok=False,
        error=f"Unhandled save method: {fmt.save_method}",
    )


def _export_pdf(
    doc: Any,
    fmt: ExportFormat,
    out_path: Path,
    sheets: str | list[str],
) -> ExportResult:
    """Export a drawing document to PDF via IExportPdfData.

    Requires the open document to be a Drawing (``.SLDDRW``). Uses
    the W25-confirmed recipe::

        sw.GetExportFileData(1)           # swExportPdfData
        typed_qi(raw, "IExportPdfData")
        pdf_data.SetSheets(mode, names)   # mode: 1=all, 3=specified
        ext.SaveAs(path, 0, 1, pdf_data)  # IModelDocExtension.SaveAs

    Fail-closed: ``format:"pdf"`` on a non-drawing document raises
    ``ValueError`` (mirrors W18 ``bom:true``+``.sldprt`` cross-field).
    Unknown sheet names in ``sheets`` list are rejected.
    """
    path_str = str(out_path)

    # --- Fail-closed: PDF requires a Drawing doc ---
    try:
        doc_type = doc.GetType()
    except Exception as exc:
        return ExportResult(
            format=fmt.name,
            path=path_str,
            ok=False,
            error=f"Cannot determine document type: {exc}",
        )

    if doc_type != _SW_DOC_DRAWING:
        return ExportResult(
            format=fmt.name,
            path=path_str,
            ok=False,
            error=(
                f"format:'pdf' requires a Drawing (.SLDDRW) document, "
                f"but doc type is {doc_type} "
                f"(1=Part, 2=Assembly, 3=Drawing)"
            ),
        )

    # --- Resolve sheet selection ---
    if sheets == "all":
        sheets_mode = _SW_EXPORT_ALL_SHEETS
        sheet_names: list[str] = []
    elif isinstance(sheets, list) and len(sheets) > 0:
        sheets_mode = _SW_EXPORT_SPECIFIED_SHEETS
        sheet_names = sheets
        # Validate sheet names against the drawing
        try:
            from ai_sw_bridge.com.earlybind import typed_qi

            drawing_doc = typed_qi(doc, "IDrawingDoc")
            actual_names = set(drawing_doc.GetSheetNames())
            unknown = [n for n in sheet_names if n not in actual_names]
            if unknown:
                return ExportResult(
                    format=fmt.name,
                    path=path_str,
                    ok=False,
                    error=(
                        f"Unknown sheet name(s): {unknown}. "
                        f"Available sheets: {sorted(actual_names)}"
                    ),
                )
        except Exception as exc:
            # If we can't validate sheet names, let the COM call fail
            # naturally — don't block the export attempt
            logger.warning(
                "Could not validate sheet names against drawing: %s", exc
            )
    else:
        return ExportResult(
            format=fmt.name,
            path=path_str,
            ok=False,
            error=f"Invalid 'sheets' value: {sheets!r}. Expected 'all' or a non-empty list of sheet names.",
        )

    # --- COM export path ---
    try:
        from ai_sw_bridge.com.earlybind import typed, typed_qi
        from ai_sw_bridge.com.sw_type_info import wrapper_module
        from ai_sw_bridge.sw_com import get_sw_app

        mod = wrapper_module()
        sw = get_sw_app()
        tsw = typed(sw, "ISldWorks", module=mod)

        # Step 1: GetExportFileData
        pdf_data_raw = tsw.GetExportFileData(_SW_EXPORT_PDF_DATA)
        if pdf_data_raw is None:
            return ExportResult(
                format=fmt.name,
                path=path_str,
                ok=False,
                error="GetExportFileData(swExportPdfData) returned None",
            )

        # Step 2: QI to IExportPdfData
        pdf_data = typed_qi(pdf_data_raw, "IExportPdfData", module=mod)

        # Step 3: SetSheets
        pdf_data.SetSheets(sheets_mode, sheet_names)

        # Step 4: IModelDocExtension.SaveAs via InvokeTypes
        # (early-bind SaveAs has [out] VARIANT handling issues in pywin32)
        ext = typed(doc.Extension, "IModelDocExtension", module=mod)

        # InvokeTypes with 6 args (including placeholders for [out] VARIANT*)
        # dispid 93, return BOOL, arg types: BSTR, I4, I4, IDispatch, [out] VARIANT, [out] VARIANT
        result = ext._oleobj_.InvokeTypes(
            93,  # dispid for SaveAs
            0,   # LCID
            1,   # DISPATCH_METHOD
            (11, 0),  # Return: BOOL
            (
                (8, 1),      # Name: BSTR in
                (3, 1),      # Version: I4 in
                (3, 1),      # Options: I4 in
                (9, 1),      # ExportData: IDispatch in
                (16387, 3),  # Errors: VARIANT|BYREF, in/out
                (16387, 3),  # Warnings: VARIANT|BYREF, in/out
            ),
            path_str,
            _SW_SAVE_AS_CURRENT_VERSION,
            _SW_SAVE_AS_OPTIONS_SILENT,
            pdf_data._oleobj_,  # Underlying COM object
            0,  # placeholder for [out] Errors
            0,  # placeholder for [out] Warnings
        )

        # result is the BOOL return value (InvokeTypes returns just the retval for [out] VARIANT*)
        if isinstance(result, tuple):
            retval = result[0]
        else:
            retval = result

        # Check return value
        if not retval:
            return ExportResult(
                format=fmt.name,
                path=path_str,
                ok=False,
                error="IModelDocExtension.SaveAs returned False",
            )

    except ValueError as exc:
        # Re-raise ValueError (our fail-closed checks)
        return ExportResult(
            format=fmt.name,
            path=path_str,
            ok=False,
            error=str(exc),
        )
    except Exception as exc:
        return ExportResult(
            format=fmt.name,
            path=path_str,
            ok=False,
            error=f"PDF export raised {type(exc).__name__}: {exc}",
        )

    # Step 5: Verify file on disk
    if not out_path.exists() or out_path.stat().st_size == 0:
        return ExportResult(
            format=fmt.name,
            path=path_str,
            ok=False,
            error="SaveAs returned True but PDF is missing or empty on disk",
        )

    return ExportResult(format=fmt.name, path=path_str, ok=True)


def _saveas3_direct(
    doc: Any, fmt: ExportFormat, out_path: Path
) -> ExportResult:
    """SaveAs3-direct export path.

    Uses the same call shape as ``builder._save_as_with_verification``:
    ``doc.SaveAs3(path, 0, version)``. The file extension in the path
    selects the exporter. Post-condition: file exists with non-zero
    size.

    The per-format extension string is 🔴 SEAT — confirmed on a live
    seat per the spike-first law. This skeleton implements the call
    shape; the format strings are not yet confirmed.
    """
    path_str = str(out_path)
    try:
        err = doc.SaveAs3(path_str, 0, fmt.save_version)
    except Exception as exc:
        return ExportResult(
            format=fmt.name,
            path=path_str,
            ok=False,
            error=f"SaveAs3 raised {type(exc).__name__}: {exc}",
        )

    err_code = int(err) if err is not None else 0
    if err_code != 0:
        return ExportResult(
            format=fmt.name,
            path=path_str,
            ok=False,
            error=f"SaveAs3 returned swFileSaveError={err_code}",
        )

    if not out_path.exists() or out_path.stat().st_size == 0:
        return ExportResult(
            format=fmt.name,
            path=path_str,
            ok=False,
            error="SaveAs3 returned NoError but file is missing or empty",
        )

    return ExportResult(format=fmt.name, path=path_str, ok=True)
