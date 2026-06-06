"""Wave-33 Slice 1: Drawing -> DXF export de-risk (HARD GO/NO-GO).

Characterises the SOLIDWORKS 2024 SP1 surface needed to export a drawing
to DXF — the 2D format laser/waterjet/plasma/CNC shops consume.

Two candidate routes — confirm sigs from typelib FIRST (T6):
  1. **SaveAs3/IModelDocExtension.SaveAs** with a `.dxf` path (the SAVEAS3_DIRECT
     path the format table claims) — same InvokeTypes discipline as W25v's PDF
     SaveAs if early-bind walls on `[out] VARIANT*`.
  2. **IDrawingDoc.ExportToDWG2(...)** (9-arg, the W4-characterized route) —
     dump the exact arg VTs and call it.

Try route 1 first (matches the format table); fall back to route 2.

LIVENESS GATE — verify the EFFECT, do NOT trust "no error" or file-exists alone:
  A DXF is a TEXT vector file. After export:
  (a) the `.dxf` exists + non-trivial size;
  (b) **parse it** — assert it contains real `ENTITIES` (count `LINE`/`LWPOLYLINE`/
      `CIRCLE`/`ARC` entity records via a simple text scan of the DXF group codes
      `0\nLINE` etc.), NOT an empty/header-only file;
  (c) the entity count is plausible for the view's geometry (a box front view → ≥4 lines).

A clean export call that yields a header-only / zero-entity DXF is the silent-no-op
trap (the W25v PDF lesson) → NO-GO.

>>> HARD CHECKPOINT.
GREEN = DXF exports out-of-process AND parses to real geometry entities matching
the view (not header-only). NO-GO (export walls / yields empty DXF) = characterize
+ DEFERRED.md + STOP. No brute-forcing.

Prereq: SOLIDWORKS 2024 SP1 running.
"""

from __future__ import annotations

import glob
import json
import os
import re
import sys
import tempfile
import time
import traceback
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

WORKTREE = Path(__file__).resolve().parents[2]
RESULTS_PATH = WORKTREE / "spikes" / "v0_2x" / "_results" / "export_dxf.json"

# swDocumentTypes_e
SW_DOC_PART = 1
SW_DOC_ASSEMBLY = 2
SW_DOC_DRAWING = 3

# swSaveAsVersion_e
SW_SAVE_AS_CURRENT_VERSION = 0

# swSaveAsOptions_e
SW_SAVE_AS_OPTIONS_SILENT = 1

# ExportToDWG2 constants (from W4 characterization)
# ExportToDWG2(FileName, Model, Options, UseSheetMetal, UseSelectedObjects, UseModelViews, Selections, Views, Scale)
# Options: swDwgExportAsDXF = ?
# For drawing doc, Model = doc itself

results: dict[str, Any] = {
    "spike": "w33_export_dxf",
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "gates": {},
    "verdict": "UNKNOWN",
    "typelib_dump": {},
    "export_route": None,
    "confirmed_sig": None,
    "dxf_paths": {},
    "entity_counts": {},
    "dxf_size_bytes": {},
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
    """Close all open documents (without corrupting COM mid-session)."""
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
        "name": "W33SpikeBox",
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
    """Dump confirmed typelib entries for ExportToDWG2, SaveAs signatures."""
    dump: dict[str, Any] = {}

    # IDrawingDoc
    iface = getattr(mod, "IDrawingDoc", None)
    if iface:
        dump["IDrawingDoc"] = {
            "CLSID": str(iface.CLSID),
            "methods": [a for a in dir(iface) if not a.startswith("_")],
        }
        # Check for ExportToDWG2
        export_methods = [m for m in dir(iface) if "Export" in m or "DWG" in m]
        dump["IDrawingDoc"]["export_methods"] = export_methods
    else:
        dump["IDrawingDoc"] = "NOT FOUND"

    # IModelDocExtension
    ext_cls = getattr(mod, "IModelDocExtension", None)
    if ext_cls:
        dump["IModelDocExtension"] = {
            "exists": True,
            "methods": [a for a in dir(ext_cls) if not a.startswith("_")],
        }
        # Check for ExportToDWG2 on Extension
        export_methods = [m for m in dir(ext_cls) if "Export" in m or "DWG" in m]
        dump["IModelDocExtension"]["export_methods"] = export_methods
    else:
        dump["IModelDocExtension"] = "NOT FOUND"

    # IModelDoc2.SaveAs3
    m2_cls = getattr(mod, "IModelDoc2", None)
    if m2_cls:
        dump["IModelDoc2"] = {
            "exists": True,
            "save_methods": [m for m in dir(m2_cls) if "Save" in m],
        }
    else:
        dump["IModelDoc2"] = "NOT FOUND"

    # ExportToDWG2 signature characterization
    dump["ExportToDWG2_characterization"] = {
        "source": "W4 spike (spike_sheetmetal_v2.py)",
        "method_location": "IDrawingDoc or IModelDocExtension",
        "arg_count": 9,
        "args": [
            "FileName (BSTR)",
            "Model (IDispatch/VARIANT)",
            "Options (I4)",
            "UseSheetMetal (BOOL)",
            "UseSelectedObjects (BOOL)",
            "UseModelViews (BOOL)",
            "Selections (VARIANT)",
            "Views (VARIANT)",
            "Scale (R8)",
        ],
        "drawing_doc_usage": "For Drawing docs, Model = the drawing doc itself",
        "sheetmetal_usage": "For flat-pattern, UseSheetMetal=True, Options=swDwgExportSheetMetal=4",
    }

    return dump


def _build_drawing(
    sw: Any,
    tsw: Any,
    mod: Any,
    part_path: str,
    template_path: str,
) -> tuple[Any, Any, Any, str] | None:
    """Build a single-sheet drawing with one Front view.

    Returns (drawing_doc, doc_model2, raw_doc, drawing_path) or None on failure.
    """
    from ai_sw_bridge.com.earlybind import typed_qi

    _tmp = Path(tempfile.gettempdir())
    _ts = int(time.time())
    drw_path = str(_tmp / f"w33_spike_drawing_{_ts}.SLDDRW")

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

    # Get default sheet name
    try:
        names = list(drawing_doc.GetSheetNames())
        sheet1_name = names[0] if names else "Sheet1"
    except Exception:
        sheet1_name = "Sheet1"

    # Activate sheet 1
    try:
        drawing_doc.ActivateSheet(sheet1_name)
    except Exception:
        pass

    # Place Front view (4 edges visible: top, bottom, left, right)
    try:
        v1 = drawing_doc.CreateDrawViewFromModelView3(
            part_path, "*Front", 0.10, 0.15, 0.0
        )
        v1_ok = v1 is not None and not isinstance(v1, int)
        gate("place_front_view", v1_ok, f"type={type(v1).__name__}")
        if not v1_ok:
            return None
    except Exception as e:
        gate("place_front_view", False, f"raised: {e}")
        return None

    # Save the drawing
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

    return drawing_doc, doc_m2, doc_raw, drw_path


def _parse_dxf_entities(dxf_path: str) -> dict[str, int]:
    """Parse a DXF file and count entity types.

    DXF is a text file with group codes. Each group code line has leading spaces.
    Entity records look like:
        0
      LINE
        ...
        0
      LWPOLYLINE
        ...

    The "0" group code line has leading spaces (DXF formatting).
    Entity type names are NOT indented (immediately after the "0" line).

    Returns dict of entity_type -> count for common geometry entities.
    """
    entity_types = ["LINE", "LWPOLYLINE", "POLYLINE", "CIRCLE", "ARC", "SPLINE", "ELLIPSE", "POINT", "TEXT", "MTEXT"]
    counts: dict[str, int] = {et: 0 for et in entity_types}
    total_entities = 0

    try:
        with open(dxf_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        # DXF format: "  0\n" (group code line) followed by entity type on next line
        # Pattern: whitespace + "0" + newline + entity type name
        # The entity type line is NOT indented in standard DXF format
        for et in entity_types:
            # Pattern: group code 0 followed by entity type name (may have slight whitespace)
            # DXF format: "  0\nLINE\n" or "0\nLINE\n"
            pattern = rf"^\s*0\s*\n\s*{et}\s*$"
            matches = re.findall(pattern, content, re.MULTILINE | re.IGNORECASE)
            counts[et] = len(matches)

        # Alternative: count all entity type lines that follow a group code 0
        # Find all lines that are entity types after a "0" group code
        lines = content.split("\n")
        prev_line = ""
        for line in lines:
            stripped = line.strip()
            if prev_line == "0" and stripped.upper() in entity_types:
                counts[stripped.upper()] = counts.get(stripped.upper(), 0) + 1
                total_entities += 1
            prev_line = stripped

        # Also count from ENTITIES section explicitly
        entities_section_match = re.search(
            r"SECTION\s*\n\s*2\s*\n\s*ENTITIES\s*\n(.*?)\s*ENDSEC",
            content,
            re.DOTALL | re.IGNORECASE
        )
        if entities_section_match:
            entities_section = entities_section_match.group(1)
            section_lines = entities_section.split("\n")
            prev = ""
            section_count = 0
            for line in section_lines:
                stripped = line.strip()
                if prev == "0" and stripped.upper() in entity_types:
                    section_count += 1
                prev = stripped
            counts["_entities_section_count"] = section_count

        counts["_total_geometry"] = total_entities

    except Exception as e:
        counts["_error"] = str(e)

    return counts


def _export_dxf_route1_saveas3(
    doc_m2: Any,
    mod: Any,
    out_path: str,
) -> tuple[bool, int, str]:
    """Route 1: SaveAs3 with .dxf extension.

    Uses doc.SaveAs3(path, 0, 0) with .dxf extension.
    Returns (success, file_size, detail).
    """
    try:
        err = doc_m2.SaveAs3(out_path, 0, 0)
        err_code = int(err) if err is not None else 0
        if err_code != 0:
            return False, 0, f"SaveAs3 returned swFileSaveError={err_code}"
    except Exception as e:
        return False, 0, f"SaveAs3 raised: {e}"

    # Verify file on disk
    p = Path(out_path)
    if not p.exists():
        return False, 0, "DXF not found on disk after SaveAs3"

    size = p.stat().st_size
    if size < 100:
        return False, size, f"DXF too small ({size} bytes), likely header-only"

    return True, size, f"DXF written via SaveAs3 ({size} bytes)"


def _export_dxf_route1_extension_saveas(
    doc_m2: Any,
    mod: Any,
    out_path: str,
) -> tuple[bool, int, str]:
    """Route 1b: IModelDocExtension.SaveAs with .dxf extension.

    Uses the W25v InvokeTypes recipe for SaveAs.
    Returns (success, file_size, detail).
    """
    from ai_sw_bridge.com.earlybind import typed

    try:
        ext = typed(doc_m2.Extension, "IModelDocExtension", module=mod)
    except Exception as e:
        return False, 0, f"typed(Extension) raised: {e}"

    try:
        # InvokeTypes with 6 args (matching W25v PDF recipe)
        # dispid 93, return BOOL, args: BSTR, I4, I4, IDispatch, [out] VARIANT, [out] VARIANT
        result = ext._oleobj_.InvokeTypes(
            93,  # dispid for SaveAs
            0,   # LCID
            1,   # DISPATCH_METHOD
            (11, 0),  # Return: BOOL
            (
                (8, 1),      # Name: BSTR in
                (3, 1),      # Version: I4 in
                (3, 1),      # Options: I4 in
                (9, 1),      # ExportData: IDispatch in (None for DXF)
                (16387, 3),  # Errors: VARIANT|BYREF, in/out
                (16387, 3),  # Warnings: VARIANT|BYREF, in/out
            ),
            out_path,
            SW_SAVE_AS_CURRENT_VERSION,
            SW_SAVE_AS_OPTIONS_SILENT,
            None,  # No ExportData for DXF
            0,  # placeholder for [out] Errors
            0,  # placeholder for [out] Warnings
        )

        if isinstance(result, tuple):
            retval = result[0]
        else:
            retval = result

        if not retval:
            return False, 0, "IModelDocExtension.SaveAs returned False"
    except Exception as e:
        return False, 0, f"Extension.SaveAs raised: {e}"

    # Verify file on disk
    p = Path(out_path)
    if not p.exists():
        return False, 0, "DXF not found on disk after Extension.SaveAs"

    size = p.stat().st_size
    if size < 100:
        return False, size, f"DXF too small ({size} bytes), likely header-only"

    return True, size, f"DXF written via Extension.SaveAs ({size} bytes)"


def _export_dxf_route2_exporttodwg2(
    drawing_doc: Any,
    doc_m2: Any,
    mod: Any,
    out_path: str,
) -> tuple[bool, int, str]:
    """Route 2: IDrawingDoc.ExportToDWG2.

    ExportToDWG2(FileName, Model, Options, UseSheetMetal, UseSelectedObjects,
                 UseModelViews, Selections, Views, Scale)

    For drawing doc export, Model should be the drawing doc itself.
    Returns (success, file_size, detail).
    """
    # First, try IDrawingDoc.ExportToDWG2
    try:
        # Probe the method signature first
        oleobj = drawing_doc._oleobj_

        # ExportToDWG2 dispid? Check from typelib or try to find
        # W4 notes: ExportToDWG2 is on IDrawingDoc
        # Let's try to find the dispid
        try:
            dispid = oleobj.GetIDsOfNames(0, 1, ("ExportToDWG2",))[0]
            gate("exporttodwg2_dispid", True, f"dispid={dispid}")
        except Exception as e:
            gate("exporttodwg2_dispid", False, f"GetIDsOfNames raised: {e}")
            # Try late-bound call
            try:
                # Late-bound attempt
                result = drawing_doc.ExportToDWG2(
                    out_path,
                    doc_m2,
                    0,  # Options: default DXF export
                    False,  # UseSheetMetal: False for drawing
                    False,  # UseSelectedObjects
                    True,   # UseModelViews
                    None,   # Selections
                    None,   # Views
                    1.0,    # Scale
                )
                if result:
                    p = Path(out_path)
                    if p.exists():
                        size = p.stat().st_size
                        return True, size, f"DXF via late-bound ExportToDWG2 ({size} bytes)"
                return False, 0, f"late-bound ExportToDWG2 returned {result}"
            except Exception as e2:
                return False, 0, f"late-bound ExportToDWG2 raised: {e2}"

        # Try InvokeTypes with the dispid
        # Signature: (FileName: BSTR, Model: IDispatch, Options: I4,
        #             UseSheetMetal: BOOL, UseSelectedObjects: BOOL,
        #             UseModelViews: BOOL, Selections: VARIANT, Views: VARIANT,
        #             Scale: R8) -> BOOL
        VT_BOOL = 11
        VT_BSTR = 8
        VT_I4 = 3
        VT_R8 = 5
        VT_DISPATCH = 9
        VT_VARIANT = 12

        result = oleobj.InvokeTypes(
            dispid,
            0,  # LCID
            1,  # DISPATCH_METHOD
            (VT_BOOL, 0),  # Return: BOOL
            (
                (VT_BSTR, 1),     # FileName
                (VT_DISPATCH, 1), # Model (drawing doc)
                (VT_I4, 1),       # Options
                (VT_BOOL, 1),     # UseSheetMetal
                (VT_BOOL, 1),     # UseSelectedObjects
                (VT_BOOL, 1),     # UseModelViews
                (VT_VARIANT, 1),  # Selections
                (VT_VARIANT, 1),  # Views
                (VT_R8, 1),       # Scale
            ),
            out_path,
            doc_m2._oleobj_,  # Pass the underlying COM object
            0,   # Options: default
            False,  # UseSheetMetal
            False,  # UseSelectedObjects
            True,   # UseModelViews
            None,   # Selections
            None,   # Views
            1.0,    # Scale
        )

        if result:
            p = Path(out_path)
            if p.exists():
                size = p.stat().st_size
                return True, size, f"DXF via ExportToDWG2 InvokeTypes ({size} bytes)"

        return False, 0, f"ExportToDWG2 returned {result}"

    except Exception as e:
        return False, 0, f"ExportToDWG2 raised: {e}"


def run() -> str:
    print("=" * 70)
    print("Wave-33 Slice 1: Drawing -> DXF export de-risk (HARD GO/NO-GO)")
    print("=" * 70)

    import win32com.client as w32

    from ai_sw_bridge.com.earlybind import typed, typed_qi
    from ai_sw_bridge.com.sw_type_info import wrapper_module

    mod = wrapper_module()
    sw = w32.Dispatch("SldWorks.Application")
    _close_all_docs(sw)

    tsw = typed(sw, "ISldWorks", module=mod)

    # --- Typelib dump ---
    print("\n--- Typelib dump ---")
    results["typelib_dump"] = _dump_typelib(mod)
    gate("typelib_dump", True, "recorded")

    # --- Build test part ---
    print("\n--- Build test part ---")
    _tmp = Path(tempfile.gettempdir())
    _ts = int(time.time())
    part_path = str(_tmp / f"w33_spike_box_{_ts}.SLDPRT")
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

    # --- Build drawing ---
    print("\n--- Build test drawing ---")
    _close_all_docs(sw)
    build_result = _build_drawing(sw, tsw, mod, part_path, template_path)
    if build_result is None:
        results["verdict"] = "NO-GO (cannot build drawing)"
        save_results()
        return "NO-GO"

    drawing_doc, doc_m2, raw_doc, drawing_path = build_result
    results["dxf_paths"]["drawing"] = drawing_path

    # ================================================================
    # ROUTE 1a: SaveAs3 with .dxf extension
    # ================================================================
    print("\n=== ROUTE 1a: SaveAs3 with .dxf extension ===")
    dxf_path1 = str(_tmp / f"w33_spike_dxf_route1a_{_ts}.dxf")

    ok1a, size1a, detail1a = _export_dxf_route1_saveas3(doc_m2, mod, dxf_path1)
    gate("route1a_saveas3", ok1a, f"size={size1a}, {detail1a}")
    results["dxf_paths"]["route1a"] = dxf_path1
    results["dxf_size_bytes"]["route1a"] = size1a

    if ok1a:
        # Parse entities
        counts1a = _parse_dxf_entities(dxf_path1)
        results["entity_counts"]["route1a"] = counts1a
        total_geo = counts1a.get("_total_geometry", 0)
        line_count = counts1a.get("LINE", 0) + counts1a.get("LWPOLYLINE", 0)
        gate(
            "route1a_entity_parse",
            total_geo >= 4 or line_count >= 4,
            f"total_geo={total_geo}, lines={line_count}, counts={counts1a}",
        )

        if total_geo >= 4 or line_count >= 4:
            results["export_route"] = "SaveAs3_DIRECT"
            results["confirmed_sig"] = {
                "method": "IModelDoc2.SaveAs3",
                "args": "SaveAs3(path, 0, 0) with .dxf extension",
                "return": "swFileSaveError_e (0 = success)",
            }
            print(">>> ROUTE 1a SUCCESS: SaveAs3 with .dxf extension works")
            _try_close(sw, raw_doc)
            results["verdict"] = "GREEN"
            save_results()
            return "GREEN"

    # ================================================================
    # ROUTE 1b: IModelDocExtension.SaveAs with .dxf
    # ================================================================
    print("\n=== ROUTE 1b: IModelDocExtension.SaveAs ===")
    dxf_path1b = str(_tmp / f"w33_spike_dxf_route1b_{_ts}.dxf")

    ok1b, size1b, detail1b = _export_dxf_route1_extension_saveas(doc_m2, mod, dxf_path1b)
    gate("route1b_ext_saveas", ok1b, f"size={size1b}, {detail1b}")
    results["dxf_paths"]["route1b"] = dxf_path1b
    results["dxf_size_bytes"]["route1b"] = size1b

    if ok1b:
        counts1b = _parse_dxf_entities(dxf_path1b)
        results["entity_counts"]["route1b"] = counts1b
        total_geo = counts1b.get("_total_geometry", 0)
        line_count = counts1b.get("LINE", 0) + counts1b.get("LWPOLYLINE", 0)
        gate(
            "route1b_entity_parse",
            total_geo >= 4 or line_count >= 4,
            f"total_geo={total_geo}, lines={line_count}, counts={counts1b}",
        )

        if total_geo >= 4 or line_count >= 4:
            results["export_route"] = "Extension_SaveAs_InvokeTypes"
            results["confirmed_sig"] = {
                "method": "IModelDocExtension.SaveAs via InvokeTypes",
                "args": "SaveAs(Name: BSTR, Version: I4, Options: I4, ExportData: None, [out] Errors, [out] Warnings)",
                "dispid": 93,
                "return_type": "BOOL",
            }
            print(">>> ROUTE 1b SUCCESS: Extension.SaveAs with .dxf extension works")
            _try_close(sw, raw_doc)
            results["verdict"] = "GREEN"
            save_results()
            return "GREEN"

    # ================================================================
    # ROUTE 2: IDrawingDoc.ExportToDWG2
    # ================================================================
    print("\n=== ROUTE 2: IDrawingDoc.ExportToDWG2 ===")
    dxf_path2 = str(_tmp / f"w33_spike_dxf_route2_{_ts}.dxf")

    ok2, size2, detail2 = _export_dxf_route2_exporttodwg2(
        drawing_doc, doc_m2, mod, dxf_path2
    )
    gate("route2_exporttodwg2", ok2, f"size={size2}, {detail2}")
    results["dxf_paths"]["route2"] = dxf_path2
    results["dxf_size_bytes"]["route2"] = size2

    if ok2:
        counts2 = _parse_dxf_entities(dxf_path2)
        results["entity_counts"]["route2"] = counts2
        total_geo = counts2.get("_total_geometry", 0)
        line_count = counts2.get("LINE", 0) + counts2.get("LWPOLYLINE", 0)
        gate(
            "route2_entity_parse",
            total_geo >= 4 or line_count >= 4,
            f"total_geo={total_geo}, lines={line_count}, counts={counts2}",
        )

        if total_geo >= 4 or line_count >= 4:
            results["export_route"] = "ExportToDWG2"
            results["confirmed_sig"] = {
                "method": "IDrawingDoc.ExportToDWG2",
                "args": "ExportToDWG2(FileName, Model, Options, UseSheetMetal, UseSelectedObjects, UseModelViews, Selections, Views, Scale)",
                "arg_count": 9,
            }
            print(">>> ROUTE 2 SUCCESS: ExportToDWG2 works")
            _try_close(sw, raw_doc)
            results["verdict"] = "GREEN"
            save_results()
            return "GREEN"

    # ================================================================
    # ALL ROUTES FAILED
    # ================================================================
    print("\n--- All routes failed ---")
    _try_close(sw, raw_doc)

    # Characterize the failure
    fail_reasons = []
    if not ok1a:
        fail_reasons.append(f"route1a: {detail1a}")
    if not ok1b:
        fail_reasons.append(f"route1b: {detail1b}")
    if not ok2:
        fail_reasons.append(f"route2: {detail2}")

    # Check if we got files but they were empty/header-only
    empty_files = []
    for route, path in results["dxf_paths"].items():
        if route.startswith("route") and Path(path).exists():
            counts = results["entity_counts"].get(route, {})
            total = counts.get("_total_geometry", 0)
            if total < 4:
                empty_files.append(f"{route}: {path} has {total} geometry entities")

    if empty_files:
        fail_reasons.append(f"Empty/header-only DXF files: {empty_files}")

    results["verdict"] = f"NO-GO ({'; '.join(fail_reasons)})"
    print(f">>> VERDICT: NO-GO ({'; '.join(fail_reasons)})")

    save_results()
    return "NO-GO"


def _try_close(sw: Any, doc: Any) -> None:
    """Close a document without corrupting COM."""
    try:
        t = doc.GetTitle
        t = t() if callable(t) else t
        sw.CloseDoc(t)
    except Exception:
        pass


if __name__ == "__main__":
    try:
        verdict = run()
    except Exception:
        traceback.print_exc()
        results["verdict"] = f"NO-GO (unhandled exception: {traceback.format_exc()[:200]})"
        save_results()
        verdict = "NO-GO"
    sys.exit(0 if verdict == "GREEN" else 1)