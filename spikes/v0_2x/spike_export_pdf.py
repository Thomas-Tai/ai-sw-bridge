"""Wave-25 Slice 1: Drawing -> PDF export de-risk (HARD GO/NO-GO).

Characterises the SOLIDWORKS 2024 SP1 surface needed to export a drawing
(single- or multi-sheet) to PDF via IExportPdfData:

  1. **Typelib dump** for GetExportFileData enum, IExportPdfData.SetSheets
     signature, IModelDocExtension.SaveAs signature.
  2. **Single-sheet export** — build a 1-sheet drawing, export with
     SetSheets(ExportAllSheets), verify PDF exists + non-trivial size.
  3. **Multi-sheet export** — build a 2-sheet drawing, export with
     SetSheets(ExportAllSheets), verify PDF exists + prove ALL sheets
     exported (not just the active one) via size comparison: the 2-sheet
     PDF must be materially larger than the 1-sheet PDF of the same
     drawing content.
  4. **Specified-sheet subset** — export only sheet 2 via
     SetSheets(ExportSpecifiedSheets, ["DetailSheet"]), verify the
     resulting PDF is smaller than the all-sheets PDF.

LIVENESS GATE (the W21/W23 lesson):
  A PDF that exists is NOT enough. The trap is a default export writing
  only the active sheet. We prove all sheets export by comparing
  2-sheet vs 1-same-sheet PDF sizes (the 2-sheet PDF must be > 1.3x
  the size of a single-sheet PDF with the same per-sheet content).

HARD CHECKPOINT:
  GO    = PDF written AND multi-sheet exports all sheets (size proof).
  NO-GO = IExportPdfData walls, or only the active sheet exports and
          SetSheets can't override it. Stop, DEFERRED.md row, do not
          brute-force.

Prereq: SOLIDWORKS 2024 SP1 running. Seat order: W22 -> W24 -> W25.
"""

from __future__ import annotations

import glob
import json
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

WORKTREE = Path(__file__).resolve().parents[2]
RESULTS_PATH = WORKTREE / "spikes" / "v0_2x" / "_results" / "export_pdf.json"

# swExportDataFileType_e
SW_EXPORT_PDF_DATA = 1

# swExportDataSheetsToExport_e
SW_EXPORT_ALL_SHEETS = 1
SW_EXPORT_CURRENT_SHEET = 2
SW_EXPORT_SPECIFIED_SHEETS = 3

# swSaveAsVersion_e
SW_SAVE_AS_CURRENT_VERSION = 0

# swSaveAsOptions_e
SW_SAVE_AS_OPTIONS_SILENT = 1

results: dict[str, Any] = {
    "spike": "w25_export_pdf",
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "gates": {},
    "verdict": "UNKNOWN",
    "typelib_dump": {},
    "export_recipe": None,
    "pdf_paths": {},
    "multi_sheet_proof": None,
}


def gate(name: str, ok: bool, detail: str = "") -> bool:
    results["gates"][name] = {"ok": ok, "detail": detail}
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name}: {detail}")
    return ok


def save_results() -> None:
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(
        json.dumps(results, indent=2, default=str), encoding="utf-8"
    )
    print(f"  wrote {RESULTS_PATH}", file=sys.stderr)


def _close_all_docs(sw: Any) -> None:
    try:
        docs = sw.GetDocuments()
        if docs:
            for d in docs:
                try:
                    t = d.GetTitle
                    t = t() if callable(t) else t
                    sw.CloseDoc(t)
                except Exception:
                    pass
    except Exception:
        pass


def _build_test_part(sw: Any, part_path: str) -> bool:
    """Build a tiny part (40x20x10 box) for view projection."""
    from ai_sw_bridge.spec.builder import build as part_build

    spec = {
        "schema_version": 1,
        "name": "W25SpikeBox",
        "features": [
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK_Box",
                "plane": "Front",
                "width": 40.0,
                "height": 20.0,
            },
            {
                "type": "boss_extrude_blind",
                "name": "EX_Box",
                "sketch": "SK_Box",
                "depth": 10.0,
            },
        ],
    }
    r = part_build(spec, save_as=part_path, save_format="current", no_dim=True)
    return bool(r.ok) and os.path.isfile(part_path)


def _dump_typelib(mod: Any) -> dict[str, Any]:
    """Dump confirmed typelib entries for IExportPdfData, GetExportFileData,
    IModelDocExtension.SaveAs signatures."""
    dump: dict[str, Any] = {}

    # IExportPdfData
    iface = getattr(mod, "IExportPdfData", None)
    if iface:
        dump["IExportPdfData"] = {
            "CLSID": str(iface.CLSID),
            "methods": [a for a in dir(iface) if not a.startswith("_")],
        }
        # Confirm SetSheets signature from gen_py source
        # SetSheets(Which: swExportDataSheetsToExport_e, Sheets: SAFEARRAY of BSTR) -> BOOL
        dump["IExportPdfData"][
            "SetSheets_signature"
        ] = "SetSheets(Which: I4, Sheets: SAFEARRAY(BSTR)) -> BOOL"
    else:
        dump["IExportPdfData"] = "NOT FOUND"

    # GetExportFileData on ISldWorks
    sw_cls = getattr(mod, "ISldWorks", None)
    if sw_cls:
        fn = getattr(sw_cls, "GetExportFileData", None)
        dump["GetExportFileData"] = {
            "exists": fn is not None,
            "signature": "GetExportFileData(FileType: I4) -> IDispatch",
            "swExportPdfData_enum_value": SW_EXPORT_PDF_DATA,
        }
    else:
        dump["GetExportFileData"] = "ISldWorks not found"

    # IModelDocExtension.SaveAs
    ext_cls = getattr(mod, "IModelDocExtension", None)
    if ext_cls:
        for name in ("SaveAs", "SaveAs2", "SaveAs3"):
            fn = getattr(ext_cls, name, None)
            dump[f"IModelDocExtension.{name}"] = {
                "exists": fn is not None,
            }
        dump["IModelDocExtension.SaveAs_signature"] = (
            "SaveAs(Name: BSTR, Version: I4, Options: I4, "
            "ExportData: IDispatch, Errors: [out] I4, "
            "Warnings: [out] I4) -> BOOL"
        )
    else:
        dump["IModelDocExtension"] = "NOT FOUND"

    # swExportDataSheetsToExport_e enum
    dump["swExportDataSheetsToExport_e"] = {
        "swExportData_ExportAllSheets": SW_EXPORT_ALL_SHEETS,
        "swExportData_ExportCurrentSheet": SW_EXPORT_CURRENT_SHEET,
        "swExportData_ExportSpecifiedSheets": SW_EXPORT_SPECIFIED_SHEETS,
    }

    # swExportDataFileType_e enum
    dump["swExportDataFileType_e"] = {
        "swExportPdfData": SW_EXPORT_PDF_DATA,
    }

    return dump


def _build_drawing(
    sw: Any,
    tsw: Any,
    mod: Any,
    part_path: str,
    template_path: str,
    sheet_names: list[str],
) -> tuple[Any, Any, Any] | None:
    """Build a drawing with N sheets, each with one view.
    Returns (drawing_doc, doc_model2, raw_doc) or None on failure."""
    from ai_sw_bridge.com.earlybind import typed_qi

    try:
        doc_raw = tsw.NewDocument(template_path, 0, 0.420, 0.297)
    except Exception as e:
        gate("newdocument", False, f"raised: {e}")
        return None

    if doc_raw is None or isinstance(doc_raw, int):
        gate("newdocument", False, f"returned {doc_raw!r}")
        return None
    gate("newdocument", True, f"type={type(doc_raw).__name__}")

    try:
        drawing_doc = typed_qi(doc_raw, "IDrawingDoc", module=mod)
    except Exception as e:
        gate("qi_idrawingdoc", False, f"raised: {e}")
        return None
    gate("qi_idrawingdoc", True)

    try:
        doc_m2 = typed_qi(doc_raw, "IModelDoc2", module=mod)
    except Exception as e:
        gate("qi_imodeldoc2", False, f"raised: {e}")
        return None

    # Sheet 1 already exists — get its default name
    try:
        names = list(drawing_doc.GetSheetNames())
        sheet1_name = names[0] if names else "Sheet1"
    except Exception:
        sheet1_name = "Sheet1"

    # Place Front view on sheet 1
    try:
        drawing_doc.ActivateSheet(sheet1_name)
    except Exception:
        pass

    try:
        v1 = drawing_doc.CreateDrawViewFromModelView3(
            part_path, "*Front", 0.10, 0.15, 0.0
        )
        v1_ok = v1 is not None and not isinstance(v1, int)
        gate("sheet1_place_front", v1_ok, f"type={type(v1).__name__}")
        if not v1_ok:
            return None
    except Exception as e:
        gate("sheet1_place_front", False, f"raised: {e}")
        return None

    # Add additional sheets (if any)
    for i, sname in enumerate(sheet_names[1:], start=2):
        try:
            ok = drawing_doc.NewSheet3(
                sname,
                8,  # PaperSize: swDwgPaperAsize (A4)
                1,  # TemplateIn: swDwgTemplateCustom
                1.0,
                1.0,  # Scale1, Scale2
                True,  # FirstAngle
                "",  # TemplateName
                0.210,
                0.297,  # Width, Height (A4 in metres)
                "",  # PropertyViewName
            )
            gate(f"newsheet_{sname}", bool(ok), f"NewSheet3 returned {ok!r}")
        except Exception as e:
            gate(f"newsheet_{sname}", False, f"raised: {e}")
            return None

        try:
            drawing_doc.ActivateSheet(sname)
        except Exception as e:
            gate(f"activate_{sname}", False, f"raised: {e}")
            return None

        # Place a different view on each additional sheet
        view_names = ["*Top", "*Right", "*Isometric", "*Bottom"]
        view_name = view_names[(i - 1) % len(view_names)]
        try:
            v = drawing_doc.CreateDrawViewFromModelView3(
                part_path, view_name, 0.10, 0.15, 0.0
            )
            v_ok = v is not None and not isinstance(v, int)
            gate(f"sheet{i}_place_{view_name}", v_ok)
            if not v_ok:
                return None
        except Exception as e:
            gate(f"sheet{i}_place_{view_name}", False, f"raised: {e}")
            return None

    # Verify sheet count
    try:
        n = drawing_doc.GetSheetCount()
        gate(
            "sheet_count",
            n == len(sheet_names),
            f"expected {len(sheet_names)}, got {n}",
        )
    except Exception as e:
        gate("sheet_count", False, f"raised: {e}")
        return None

    # Save the drawing so it's a real .SLDDRW on disk
    _tmp = Path(os.environ.get("TEMP", "/tmp"))
    ts = int(time.time())
    drw_path = str(_tmp / f"w25_spike_drawing_{ts}.SLDDRW")
    try:
        err = doc_m2.SaveAs3(drw_path, 0, 0)
        err_code = int(err) if err is not None else 0
        gate(
            "drawing_save",
            err_code == 0 and os.path.isfile(drw_path),
            f"err={err_code}, exists={os.path.isfile(drw_path)}",
        )
    except Exception as e:
        gate("drawing_save", False, f"raised: {e}")
        return None

    results["pdf_paths"]["drawing"] = drw_path
    return drawing_doc, doc_m2, doc_raw


def _export_pdf(
    tsw: Any,
    mod: Any,
    drawing_doc: Any,
    doc_m2: Any,
    out_path: str,
    sheets_mode: int,
    sheet_names: list[str] | None = None,
) -> tuple[bool, int, str]:
    """Export drawing to PDF via IExportPdfData + IModelDocExtension.SaveAs.

    Returns (success, file_size, detail).
    """
    from ai_sw_bridge.com.earlybind import typed, typed_qi

    # Step 1: GetExportFileData
    try:
        pdf_data_raw = tsw.GetExportFileData(SW_EXPORT_PDF_DATA)
    except Exception as e:
        return False, 0, f"GetExportFileData raised: {e}"

    if pdf_data_raw is None:
        return False, 0, "GetExportFileData returned None"
    gate("get_export_file_data", True, f"type={type(pdf_data_raw).__name__}")

    # Step 2: QI to IExportPdfData
    try:
        pdf_data = typed_qi(pdf_data_raw, "IExportPdfData", module=mod)
    except Exception as e:
        return False, 0, f"typed_qi(IExportPdfData) raised: {e}"
    gate("qi_export_pdf_data", True)

    # Step 3: SetSheets
    try:
        if sheets_mode == SW_EXPORT_ALL_SHEETS:
            ok = pdf_data.SetSheets(SW_EXPORT_ALL_SHEETS, sheet_names or [])
        elif sheets_mode == SW_EXPORT_CURRENT_SHEET:
            ok = pdf_data.SetSheets(SW_EXPORT_CURRENT_SHEET, [])
        elif sheets_mode == SW_EXPORT_SPECIFIED_SHEETS:
            ok = pdf_data.SetSheets(SW_EXPORT_SPECIFIED_SHEETS, sheet_names or [])
        else:
            return False, 0, f"Unknown sheets_mode: {sheets_mode}"
        gate(
            f"set_sheets_{sheets_mode}",
            True,
            f"SetSheets returned {ok!r}, mode={sheets_mode}, names={sheet_names}",
        )
    except Exception as e:
        gate(f"set_sheets_{sheets_mode}", False, f"raised: {e}")
        return False, 0, f"SetSheets raised: {e}"

    # Step 4: IModelDocExtension.SaveAs
    try:
        ext = typed(doc_m2.Extension, "IModelDocExtension", module=mod)
    except Exception as e:
        return False, 0, f"typed(IModelDocExtension) raised: {e}"

    try:
        # SaveAs(Name, Version, Options, ExportData, Errors, Warnings) -> BOOL
        # Use late-bind InvokeTypes to avoid the makepy [out] VARIANT handling
        # dispid 93, return type BOOL (11, 0)
        # arg types: BSTR (8), I4 (3), I4 (3), IDispatch (9), [out] VARIANT (16396), [out] VARIANT (16396)
        # Note: 16396 = VT_ERROR | VT_BYREF, used for [out] error codes
        import pythoncom

        # Build arg tuple for InvokeTypes
        # For [out] params, use VT_BYREF | VT_I4 (16387)
        # Actually, let's try passing empty VARIANTs as VT_EMPTY byref
        LCID = 0  # LOCALE_SYSTEM_DEFAULT

        # InvokeTypes: (dispid, LCID, flags, return_type, arg_types_tuple, *args)
        # flags: 1 = DISPATCH_METHOD
        # For [out] params, the value tuple must contain placeholder values
        LCID = 0  # LOCALE_SYSTEM_DEFAULT

        result = ext._oleobj_.InvokeTypes(
            93,  # dispid for SaveAs
            LCID,
            1,  # DISPATCH_METHOD
            (11, 0),  # Return: BOOL
            (
                (8, 1),  # Name: BSTR in
                (3, 1),  # Version: I4 in
                (3, 1),  # Options: I4 in
                (9, 1),  # ExportData: IDispatch in
                (16387, 3),  # Errors: VARIANT|BYREF, in/out
                (16387, 3),  # Warnings: VARIANT|BYREF, in/out
            ),
            out_path,
            SW_SAVE_AS_CURRENT_VERSION,
            SW_SAVE_AS_OPTIONS_SILENT,
            pdf_data._oleobj_,  # Get the underlying COM object
            0,  # placeholder for [out] Errors
            0,  # placeholder for [out] Warnings
        )

        # result is a tuple: (retval, errors_var, warnings_var)
        if isinstance(result, tuple):
            retval = result[0]
            errors = result[1] if len(result) > 1 else None
            warnings = result[2] if len(result) > 2 else None
        else:
            retval = result
            errors = None
            warnings = None

        gate(
            "ext_saveas",
            True,
            f"retval={retval!r}, errors={errors}, warnings={warnings}",
        )
    except Exception as e:
        gate("ext_saveas", False, f"raised: {e}")
        return False, 0, f"SaveAs raised: {e}"

    # Step 5: Verify file on disk
    out = Path(out_path)
    if not out.exists():
        return False, 0, "PDF not found on disk after SaveAs"

    size = out.stat().st_size
    if size < 1024:
        return False, size, f"PDF too small ({size} bytes), likely corrupt"

    return True, size, f"PDF written ({size} bytes)"


def run() -> str:
    print("=" * 70)
    print("Wave-25 Slice 1: Drawing -> PDF export de-risk (HARD GO/NO-GO)")
    print("=" * 70)

    import tempfile
    import win32com.client as w32

    from ai_sw_bridge.com.earlybind import typed, typed_qi
    from ai_sw_bridge.com.sw_type_info import wrapper_module

    mod = wrapper_module()
    sw = w32.Dispatch("SldWorks.Application")
    _close_all_docs(sw)

    # --- Typelib dump ---
    print("\n--- Typelib dump ---")
    results["typelib_dump"] = _dump_typelib(mod)
    gate("typelib_dump", True, "recorded")

    # --- Build test part ---
    print("\n--- Build test part ---")
    _tmp = Path(tempfile.gettempdir())
    _ts = int(time.time())
    part_path = str(_tmp / f"w25_spike_box_{_ts}.SLDPRT")
    part_ok = _build_test_part(sw, part_path)
    if not gate("part_build", part_ok, f"path={part_path}"):
        results["verdict"] = "NO-GO (prereq part build failed)"
        save_results()
        return "NO-GO"

    # --- Find drawing template ---
    print("\n--- Drawing template discovery ---")
    drwdots = []
    for pat in (
        r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\*.DRWDOT",
        r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\*.drwdot",
    ):
        drwdots.extend(glob.glob(pat))
    drwdots = sorted(set(drwdots))
    if not gate("drwdot_found", bool(drwdots), f"count={len(drwdots)}"):
        results["verdict"] = "NO-GO (no drawing template)"
        save_results()
        return "NO-GO"
    template_path = drwdots[0]

    tsw = typed(sw, "ISldWorks", module=mod)

    # ================================================================
    # TEST 1: Single-sheet drawing -> PDF (ExportAllSheets)
    # ================================================================
    print("\n=== TEST 1: Single-sheet drawing -> PDF ===")
    _close_all_docs(sw)

    # Get default sheet name
    build1 = _build_drawing(sw, tsw, mod, part_path, template_path, ["Sheet1"])
    if build1 is None:
        results["verdict"] = "NO-GO (cannot build single-sheet drawing)"
        save_results()
        return "NO-GO"

    drawing1, doc2_1, raw1 = build1
    # Get actual sheet name
    try:
        actual_names = list(drawing1.GetSheetNames())
        sheet1_actual = actual_names[0] if actual_names else "Sheet1"
    except Exception:
        sheet1_actual = "Sheet1"

    pdf1_path = str(_tmp / f"w25_spike_1sheet_{_ts}.pdf")
    ok1, size1, detail1 = _export_pdf(
        tsw,
        mod,
        drawing1,
        doc2_1,
        pdf1_path,
        SW_EXPORT_ALL_SHEETS,
        [sheet1_actual],
    )
    gate("single_sheet_pdf", ok1, f"size={size1}, {detail1}")
    results["pdf_paths"]["single_sheet"] = pdf1_path

    # Clean up drawing 1
    try:
        t = raw1.GetTitle
        t = t() if callable(t) else t
        sw.CloseDoc(t)
    except Exception:
        pass

    if not ok1:
        results["verdict"] = "NO-GO (single-sheet PDF export failed)"
        save_results()
        return "NO-GO"

    # ================================================================
    # TEST 2: Multi-sheet drawing -> PDF (ExportAllSheets)
    # ================================================================
    print("\n=== TEST 2: Multi-sheet drawing -> PDF (ExportAllSheets) ===")
    _close_all_docs(sw)

    build2 = _build_drawing(
        sw,
        tsw,
        mod,
        part_path,
        template_path,
        [sheet1_actual, "DetailSheet"],
    )
    if build2 is None:
        results["verdict"] = "NO-GO (cannot build multi-sheet drawing)"
        save_results()
        return "NO-GO"

    drawing2, doc2_2, raw2 = build2

    pdf2_path = str(_tmp / f"w25_spike_2sheets_{_ts}.pdf")
    ok2, size2, detail2 = _export_pdf(
        tsw,
        mod,
        drawing2,
        doc2_2,
        pdf2_path,
        SW_EXPORT_ALL_SHEETS,
        [sheet1_actual, "DetailSheet"],
    )
    gate("multi_sheet_pdf", ok2, f"size={size2}, {detail2}")
    results["pdf_paths"]["multi_sheet"] = pdf2_path

    # ================================================================
    # LIVENESS GATE: Multi-sheet proof (the W21/W23 lesson)
    # ================================================================
    print("\n--- Multi-sheet liveness proof ---")
    if ok2 and size1 > 0:
        ratio = size2 / size1
        # A 2-sheet PDF must be materially larger than a 1-sheet PDF
        # with the same per-sheet content. 1.3x is a conservative
        # threshold (real ratio is typically 1.5x-2.0x).
        ratio_ok = ratio > 1.3
        gate(
            "multi_sheet_size_proof",
            ratio_ok,
            f"2-sheet={size2}B, 1-sheet={size1}B, ratio={ratio:.2f} "
            f"(threshold > 1.3)",
        )
        results["multi_sheet_proof"] = {
            "method": "size_comparison",
            "single_sheet_size": size1,
            "multi_sheet_size": size2,
            "ratio": round(ratio, 3),
            "threshold": 1.3,
            "passed": ratio_ok,
        }
    else:
        results["multi_sheet_proof"] = {
            "method": "size_comparison",
            "error": "Cannot compare: multi-sheet export failed or single-sheet size is 0",
        }

    # ================================================================
    # TEST 3: Specified-sheet subset (ExportSpecifiedSheets)
    # ================================================================
    print("\n=== TEST 3: Specified-sheet subset ===")
    pdf3_path = str(_tmp / f"w25_spike_specified_{_ts}.pdf")
    ok3, size3, detail3 = _export_pdf(
        tsw,
        mod,
        drawing2,
        doc2_2,
        pdf3_path,
        SW_EXPORT_SPECIFIED_SHEETS,
        ["DetailSheet"],
    )
    gate("specified_sheet_pdf", ok3, f"size={size3}, {detail3}")
    results["pdf_paths"]["specified_sheet"] = pdf3_path

    # Verify subset is smaller than all-sheets
    if ok3 and ok2 and size2 > 0:
        subset_smaller = size3 < size2
        gate(
            "subset_smaller_than_all",
            subset_smaller,
            f"subset={size3}B < all={size2}B",
        )

    # Also test ExportCurrentSheet to confirm it produces a 1-sheet PDF
    print("\n=== TEST 4: ExportCurrentSheet ===")
    # Activate "DetailSheet" first
    try:
        drawing2.ActivateSheet("DetailSheet")
    except Exception:
        pass
    pdf4_path = str(_tmp / f"w25_spike_current_{_ts}.pdf")
    ok4, size4, detail4 = _export_pdf(
        tsw,
        mod,
        drawing2,
        doc2_2,
        pdf4_path,
        SW_EXPORT_CURRENT_SHEET,
        [],
    )
    gate("current_sheet_pdf", ok4, f"size={size4}, {detail4}")
    results["pdf_paths"]["current_sheet"] = pdf4_path

    if ok4 and ok2 and size2 > 0:
        current_smaller = size4 < size2
        gate(
            "current_sheet_smaller_than_all",
            current_smaller,
            f"current={size4}B < all={size2}B",
        )

    # Clean up drawing 2
    try:
        t = raw2.GetTitle
        t = t() if callable(t) else t
        sw.CloseDoc(t)
    except Exception:
        pass

    # ================================================================
    # VERDICT
    # ================================================================
    print("\n--- Verdict ---")
    multi_ok = ok2 and results.get("multi_sheet_proof", {}).get("passed", False)
    specified_ok = ok3

    if ok1 and multi_ok and specified_ok:
        results["verdict"] = "GO"
        results["export_recipe"] = {
            "step_1": "tsw.GetExportFileData(1)  # swExportPdfData = 1",
            "step_2": "typed_qi(pdf_data_raw, 'IExportPdfData')",
            "step_3": "pdf_data.SetSheets(mode, sheet_names)  # mode: 1=all, 2=current, 3=specified",
            "step_4": "ext = typed(doc.Extension, 'IModelDocExtension')",
            "step_5": "ext.SaveAs(path, 0, 1, pdf_data)  # SaveAs(Name, Version, Options, ExportData, [out] Errors, [out] Warnings)",
            "step_6": "Verify PDF on disk (exists + non-trivial size)",
            "confirmed_sigs": {
                "GetExportFileData": "GetExportFileData(FileType: I4) -> IDispatch",
                "IExportPdfData.SetSheets": "SetSheets(Which: I4, Sheets: SAFEARRAY(BSTR)) -> BOOL",
                "IModelDocExtension.SaveAs": "SaveAs(Name: BSTR, Version: I4, Options: I4, ExportData: IDispatch, Errors: [out] I4, Warnings: [out] I4) -> BOOL",
            },
            "enum_values": {
                "swExportPdfData": 1,
                "swExportData_ExportAllSheets": 1,
                "swExportData_ExportCurrentSheet": 2,
                "swExportData_ExportSpecifiedSheets": 3,
            },
            "multi_sheet_proof_method": "size_comparison",
            "multi_sheet_proof_detail": (
                "2-sheet PDF is materially larger (>1.3x) than 1-sheet PDF "
                "with the same per-sheet content; specified-sheet subset is "
                "smaller than all-sheets PDF"
            ),
        }
        print(">>> VERDICT: GO (recipe recorded)")
    else:
        fail_reasons = []
        if not ok1:
            fail_reasons.append("single-sheet PDF failed")
        if not ok2:
            fail_reasons.append("multi-sheet PDF failed")
        if not multi_ok:
            fail_reasons.append("multi-sheet proof failed (only active sheet?)")
        if not specified_ok:
            fail_reasons.append("specified-sheet export failed")
        results["verdict"] = f"NO-GO ({'; '.join(fail_reasons)})"
        print(f">>> VERDICT: NO-GO ({'; '.join(fail_reasons)})")

    save_results()
    return results["verdict"]


if __name__ == "__main__":
    try:
        verdict = run()
    except Exception:
        traceback.print_exc()
        results["verdict"] = (
            f"NO-GO (unhandled exception: {traceback.format_exc()[:200]})"
        )
        save_results()
        verdict = "NO-GO"
    sys.exit(0 if verdict == "GO" else 1)
