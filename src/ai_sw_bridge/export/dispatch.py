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
_SW_DOC_PART = 1
_SW_DOC_ASSEMBLY = 2
_SW_DOC_DRAWING = 3

# 3D formats require Part or Assembly (NOT Drawing) — W34 doc-type guard.
_3D_FORMATS: frozenset[str] = frozenset({
    "step214", "step203", "iges", "parasolid", "stl", "3mf",
})

# swExportDataFileType_e
_SW_EXPORT_PDF_DATA = 1

# swExportDataSheetsToExport_e
_SW_EXPORT_ALL_SHEETS = 1
_SW_EXPORT_SPECIFIED_SHEETS = 3

# swSaveAsVersion_e
_SW_SAVE_AS_CURRENT_VERSION = 0

# swSaveAsOptions_e
_SW_SAVE_AS_OPTIONS_SILENT = 1

# swDWGExportType_e (IPartDoc.ExportToDWG2)
_SW_EXPORT_SHEETMETAL = 2


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


def _get_doc_type(doc: Any) -> int:
    """Return the document type (1=Part, 2=Assembly, 3=Drawing).

    Handles both early-bound typed dispatch (``GetType`` is a method
    requiring ``()``) and late-bound CDispatch (``GetType`` auto-invokes
    on attribute access, returning the int directly).
    """
    raw = doc.GetType
    return raw() if callable(raw) else int(raw)


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
        return _flat_pattern_dxf(doc, fmt, out_path)
    if fmt.save_method == SaveMethod.FLAT_PATTERN_DXF_DRAWING:
        return _flat_pattern_dxf_drawing(doc, fmt, out_path)
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
        doc_type = _get_doc_type(doc)
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

        # Step 3: SetSheets via InvokeTypes with correct arg types
        # (the makepy-generated method uses VT_VARIANT (12) for the Sheets arg,
        #  but the actual API expects VT_ARRAY|VT_BSTR (8200) for SAFEARRAY(BSTR))
        # dispid 3, return BOOL (11), args: I4 (3, 1), SAFEARRAY|BSTR (8200, 1)
        VT_ARRAY = 8192
        VT_BSTR = 8
        VT_ARRAY_BSTR = VT_ARRAY | VT_BSTR  # 8200
        set_sheets_ok = pdf_data._oleobj_.InvokeTypes(
            3,  # dispid for SetSheets
            0,  # LCID
            1,  # DISPATCH_METHOD
            (11, 0),  # Return: BOOL
            ((3, 1), (VT_ARRAY_BSTR, 1)),  # Which: I4, Sheets: SAFEARRAY(BSTR)
            sheets_mode,
            tuple(sheet_names),  # Convert to tuple for SAFEARRAY marshaling
        )
        if not set_sheets_ok:
            logger.warning(
                "SetSheets(mode=%d, names=%s) returned False; export may include "
                "more sheets than requested",
                sheets_mode,
                sheet_names,
            )

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

    Doc-type fail-closed (W33 + W34):
      - DXF requires a Drawing document (.SLDDRW). A part or assembly
        passed to format:'dxf' raises a clear ValueError.
      - STEP/IGES/STL/Parasolid/3MF require a Part or Assembly document.
        A drawing (.SLDDRW) passed to these formats raises ValueError.
    """
    path_str = str(out_path)

    # --- Fail-closed: DXF requires a Drawing doc (W33) ---
    if fmt.name == "dxf":
        try:
            doc_type = _get_doc_type(doc)
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
                    f"format:'{fmt.name}' requires a Drawing (.SLDDRW) document, "
                    f"but doc type is {doc_type} "
                    f"(1=Part, 2=Assembly, 3=Drawing)"
                ),
            )

    # --- Fail-closed: 3D formats require Part or Assembly (W34) ---
    if fmt.name in _3D_FORMATS:
        try:
            doc_type = _get_doc_type(doc)
        except Exception as exc:
            return ExportResult(
                format=fmt.name,
                path=path_str,
                ok=False,
                error=f"Cannot determine document type: {exc}",
            )

        if doc_type not in (_SW_DOC_PART, _SW_DOC_ASSEMBLY):
            return ExportResult(
                format=fmt.name,
                path=path_str,
                ok=False,
                error=(
                    f"format:'{fmt.name}' requires a Part (.SLDPRT) or Assembly "
                    f"(.SLDASM) document, but doc type is {doc_type} "
                    f"(1=Part, 2=Assembly, 3=Drawing)"
                ),
            )

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


def _flat_pattern_dxf(
    doc: Any, fmt: ExportFormat, out_path: Path
) -> ExportResult:
    """Export a sheet-metal part's flat pattern to DXF via ExportToDWG2.

    Requires a Part document (``.SLDPRT``) that contains a Flat-Pattern
    feature (auto-generated when sheet-metal features like Base-Flange are
    added). The Flat-Pattern feature ships suppressed by default — this
    function unsuppresses it before calling ``ExportToDWG2``.

    Fail-closed:
      - Non-Part documents -> typed error, no file written.
      - No Flat-Pattern feature found -> typed error, no file written.

    COM route (W42 S1 characterization):
      ``IPartDoc.ExportToDWG2(path, source, exportType, sheetMetalOpt,
      alignment, bends, exportLayers, geoms, version)``
    with ``exportType=2`` (swExportToDWG_ExportSheetMetal) and
    ``sheetMetalOpt=True``. Falls back to ``InvokeTypes`` if the late-bound
    call raises (ExportToDWG2 is not always makepy-exposed).
    """
    path_str = str(out_path)

    try:
        doc_type = _get_doc_type(doc)
    except Exception as exc:
        return ExportResult(
            format=fmt.name,
            path=path_str,
            ok=False,
            error=f"Cannot determine document type: {exc}",
        )

    if doc_type != _SW_DOC_PART:
        return ExportResult(
            format=fmt.name,
            path=path_str,
            ok=False,
            error=(
                f"format:'dxf_flat' requires a Part (.SLDPRT) document, "
                f"but doc type is {doc_type} "
                f"(1=Part, 2=Assembly, 3=Drawing)"
            ),
        )

    # --- Save the part so ExportToDWG2 has a valid SourceFile ---
    try:
        source_path = doc.GetPathName
        if callable(source_path):
            source_path = source_path()
        source_path = str(source_path) if source_path else ""
    except Exception:
        source_path = ""

    if not source_path:
        tmp_dir = out_path.parent
        tmp_part = tmp_dir / f"_flat_tmp_{out_path.stem}.sldprt"
        try:
            err = doc.SaveAs3(str(tmp_part), 0, 0)
            err_code = int(err) if err is not None else 0
            if err_code != 0:
                return ExportResult(
                    format=fmt.name,
                    path=path_str,
                    ok=False,
                    error=f"Cannot save part for flat-pattern export: SaveAs3 error {err_code}",
                )
            source_path = str(tmp_part)
        except Exception as exc:
            return ExportResult(
                format=fmt.name,
                path=path_str,
                ok=False,
                error=f"Cannot save part for flat-pattern export: {exc}",
            )

    # --- Find and unsuppress the Flat-Pattern feature ---
    flat_found = False
    try:
        raw_count = doc.GetFeatureCount
        count = raw_count(True) if callable(raw_count) else int(raw_count)

        for i in range(count):
            try:
                feat = doc.FeatureByPositionReverse(i)
            except Exception:
                break
            if feat is None:
                break
            try:
                type_name_raw = feat.GetTypeName
                type_name = (
                    type_name_raw() if callable(type_name_raw) else str(type_name_raw)
                )
            except Exception:
                type_name = ""

            if "FlatPattern" in type_name or "Flat-Pattern" in type_name:
                flat_found = True
                try:
                    feat.SetSuppression(1)
                except Exception as exc:
                    logger.warning("Flat-Pattern unsuppress failed: %s", exc)
                break
    except Exception as exc:
        logger.warning("Feature tree walk for Flat-Pattern failed: %s", exc)

    if not flat_found:
        return ExportResult(
            format=fmt.name,
            path=path_str,
            ok=False,
            error=(
                "No Flat-Pattern feature found in this part. "
                "format:'dxf_flat' requires a sheet-metal part with a "
                "Flat-Pattern feature (auto-generated from Base-Flange / "
                "Edge-Flange features)."
            ),
        )

    doc.ForceRebuild3(False)

    # --- Export flat-pattern DXF ---
    # Primary route: ExportFlatPatternView (W42 S1 proven — 2 args, reliable).
    # Fallback: ExportToDWG2 with 9 bool args (COM-accepted but may return
    # False without writing a file on some SW builds).
    try:
        success = doc.ExportFlatPatternView(path_str, 0)
    except Exception as exc:
        logger.info(
            "ExportFlatPatternView failed (%r); trying ExportToDWG2 fallback",
            exc,
        )
        try:
            success = doc.ExportToDWG2(
                path_str, source_path,
                _SW_EXPORT_SHEETMETAL,
                True, False, False, False, False, 0,
            )
        except Exception as exc2:
            return ExportResult(
                format=fmt.name,
                path=path_str,
                ok=False,
                error=(
                    f"Flat-pattern export failed: "
                    f"ExportFlatPatternView={exc!r}, "
                    f"ExportToDWG2={exc2!r}"
                ),
            )

    if success is None or not bool(success):
        return ExportResult(
            format=fmt.name,
            path=path_str,
            ok=False,
            error="Flat-pattern export returned False (DXF not written)",
        )

    if not out_path.exists() or out_path.stat().st_size == 0:
        return ExportResult(
            format=fmt.name,
            path=path_str,
            ok=False,
            error="Flat-pattern export returned True but DXF is missing or empty on disk",
        )

    return ExportResult(format=fmt.name, path=path_str, ok=True)


def _find_flat_pattern_and_config(doc: Any) -> tuple[bool, str]:
    """Find + unsuppress the Flat-Pattern feature and read the active config.

    Returns ``(flat_found, config_name)``. ``config_name`` falls back to
    ``"Default"`` if the active configuration cannot be read.
    """
    flat_found = False
    try:
        raw_count = doc.GetFeatureCount
        count = raw_count(True) if callable(raw_count) else int(raw_count)
        for i in range(count):
            try:
                feat = doc.FeatureByPositionReverse(i)
            except Exception:
                break
            if feat is None:
                break
            try:
                tn_raw = feat.GetTypeName
                tn = tn_raw() if callable(tn_raw) else str(tn_raw)
            except Exception:
                tn = ""
            if "FlatPattern" in tn or "Flat-Pattern" in tn:
                flat_found = True
                try:
                    feat.SetSuppression(1)  # unsuppress
                except Exception as exc:
                    logger.warning("Flat-Pattern unsuppress failed: %s", exc)
                break
    except Exception as exc:
        logger.warning("Feature walk for Flat-Pattern failed: %s", exc)

    config_name = "Default"
    try:
        cfgmgr = doc.ConfigurationManager
        active = cfgmgr.ActiveConfiguration
        if active is not None:
            nm = active.Name
            config_name = nm() if callable(nm) else str(nm)
    except Exception:
        pass
    return flat_found, config_name


def _flat_pattern_dxf_drawing(
    doc: Any, fmt: ExportFormat, out_path: Path
) -> ExportResult:
    """Export a sheet-metal flat pattern to DXF WITH a dedicated BEND layer (W48).

    The part-space ``_flat_pattern_dxf`` route emits the developed OUTLINE only —
    SOLIDWORKS exposes no bend-line switch there. This route instead renders the
    flat pattern as a DRAWING view (``CreateFlatPatternViewFromModelView3`` with
    ``HideBendLines=False``), where SW draws the interior fold lines as real
    entities, exports the drawing to DXF (the W33-proven Drawing-only DXF path),
    then re-assigns those interior bend LINEs to the ``BEND`` layer via the
    geometric classifier (SW collapses everything to layer ``0``, so the split is
    topological, not by layer name).

    Fail-closed: non-Part doc, no Flat-Pattern feature, no drawing template, or a
    null flat-pattern view → typed error, no file written.
    """
    import tempfile

    path_str = str(out_path)

    try:
        doc_type = _get_doc_type(doc)
    except Exception as exc:
        return ExportResult(
            format=fmt.name, path=path_str, ok=False,
            error=f"Cannot determine document type: {exc}",
        )
    if doc_type != _SW_DOC_PART:
        return ExportResult(
            format=fmt.name, path=path_str, ok=False,
            error=(
                f"format:'dxf_flat_bends' requires a Part (.SLDPRT) document, "
                f"but doc type is {doc_type} (1=Part, 2=Assembly, 3=Drawing)"
            ),
        )

    # --- The drawing view needs the part on disk as its source model ---
    try:
        source_path = doc.GetPathName
        source_path = source_path() if callable(source_path) else source_path
        source_path = str(source_path) if source_path else ""
    except Exception:
        source_path = ""
    if not source_path:
        tmp_part = out_path.parent / f"_flatbends_tmp_{out_path.stem}.sldprt"
        try:
            err = doc.SaveAs3(str(tmp_part), 0, 0)
            if (int(err) if err is not None else 0) != 0:
                return ExportResult(
                    format=fmt.name, path=path_str, ok=False,
                    error=f"Cannot save part for flat-pattern export: SaveAs3 error {err}",
                )
            source_path = str(tmp_part)
        except Exception as exc:
            return ExportResult(
                format=fmt.name, path=path_str, ok=False,
                error=f"Cannot save part for flat-pattern export: {exc}",
            )

    # --- GATE: a Flat-Pattern feature must exist (this is a sheet-metal part) ---
    flat_found, config_name = _find_flat_pattern_and_config(doc)
    if not flat_found:
        return ExportResult(
            format=fmt.name, path=path_str, ok=False,
            error=(
                "No Flat-Pattern feature found in this part. "
                "format:'dxf_flat_bends' requires a sheet-metal part with a "
                "Flat-Pattern feature (auto-generated from Base-Flange features)."
            ),
        )
    doc.ForceRebuild3(False)
    try:
        doc.SaveAs3(source_path, 0, 0)  # persist the unsuppressed flat pattern
    except Exception:
        pass

    # --- Seat helpers (lazy: the dispatch module is partly SW-free) ---
    from ..com.earlybind import typed_qi
    from ..com.sw_type_info import wrapper_module
    from ..drawing.lifecycle import _find_drawing_template
    from ..sw_com import get_sw_app
    from .dxf_bend_layers import rewrite_dxf_with_bend_layer

    drw_template = _find_drawing_template()
    if not drw_template:
        return ExportResult(
            format=fmt.name, path=path_str, ok=False,
            error="No .DRWDOT drawing template found for the bend-line route.",
        )

    try:
        sw = get_sw_app()
        mod = wrapper_module()
        drw_raw = sw.NewDocument(drw_template, 0, 0.420, 0.297)
        if drw_raw is None or isinstance(drw_raw, int):
            return ExportResult(
                format=fmt.name, path=path_str, ok=False,
                error="NewDocument(.DRWDOT) returned None for the bend-line route.",
            )
        drawing_doc = typed_qi(drw_raw, "IDrawingDoc", module=mod)
        # CreateFlatPatternViewFromModelView3(ModelName, ConfigName, x, y, z,
        #   HideBendLines, FlipView) -> IView. HideBendLines=False is load-
        # bearing: it renders the fold lines as real entities (W48 seat-proven).
        view = drawing_doc.CreateFlatPatternViewFromModelView3(
            source_path, config_name, 0.15, 0.15, 0.0, False, False
        )
        if view is None or isinstance(view, int):
            return ExportResult(
                format=fmt.name, path=path_str, ok=False,
                error=(
                    "CreateFlatPatternViewFromModelView3 returned no view "
                    f"(config={config_name!r})"
                ),
            )
        typed_qi(drw_raw, "IModelDoc2", module=mod).ForceRebuild3(False)

        # Export the DRAWING to a raw DXF (W33-proven Drawing-only DXF route).
        tmp_dxf = (
            Path(tempfile.mkdtemp(prefix="w48_flatbends_"))
            / f"{out_path.stem}_raw.dxf"
        )
        derr = drw_raw.SaveAs3(str(tmp_dxf), 0, 0)
        if (int(derr) if derr is not None else 0) != 0:
            return ExportResult(
                format=fmt.name, path=path_str, ok=False,
                error=f"Drawing SaveAs3(.dxf) returned {derr}",
            )
        if not tmp_dxf.exists() or tmp_dxf.stat().st_size == 0:
            return ExportResult(
                format=fmt.name, path=path_str, ok=False,
                error="Drawing->DXF produced no file for the bend-line route.",
            )
    except Exception as exc:
        return ExportResult(
            format=fmt.name, path=path_str, ok=False,
            error=f"Bend-line drawing-view route failed: {exc!r}",
        )

    # --- Re-assign interior bend LINEs to the BEND layer, write final DXF ---
    raw_text = tmp_dxf.read_text(encoding="utf-8", errors="replace")
    rewritten, classified = rewrite_dxf_with_bend_layer(raw_text, "BEND")
    out_path.write_text(rewritten, encoding="utf-8")
    if not out_path.exists() or out_path.stat().st_size == 0:
        return ExportResult(
            format=fmt.name, path=path_str, ok=False,
            error="Bend-layer DXF write produced no file.",
        )
    logger.info(
        "dxf_flat_bends: %d bend line(s) re-assigned to BEND layer (%d outline)",
        classified.get("bend_line_count", 0),
        classified.get("outline_line_count", 0),
    )
    return ExportResult(format=fmt.name, path=path_str, ok=True)
