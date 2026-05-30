"""
Spike v0.16 / S-DRAWVIEW — drawing generation from a part document.
[authored seat-free; RUN ON A LIVE SEAT]

Probes the SOLIDWORKS drawing-creation API surface out-of-process:
  - Open a blank Drawing (SW_DOC_DRAWING via typed OpenDoc6)
  - IDrawingDoc.CreateDrawViewFromModelView3(part_path, view_name, x, y, z)
  - Standard view types: *Front, *Top, *Right, *Isometric, *Dimetric, *Trimetric
  - IModelDoc2::SaveAs3 to .SLDDRW

The goal is to prove the drawing-generation pipeline works end-to-end
out-of-process before building the ``drawing/`` package handlers.

Background
----------
The spec schema already declares a ``drawing:`` block (validated-but-inert).
This spike proves the COM surface needed to activate it:

  1. Open/create a .slddrw from the default drawing template
  2. Insert model views by name (front/top/right/iso)
  3. Optionally auto-dimension (IDrawingDoc.CreateLinearDim / AutoDimension)
  4. Save the drawing

Risks: template path resolution, view orientation constants, auto-dimension
marshaling (known SEH-prone on SW 2024 SP1).

Verdict
-------
PASS    : drawing created with ≥1 view, saved to .slddrw — build the handler.
PARTIAL : drawing opens but CreateDrawViewFromModelView3 fails — narrow view
          name or template path; run --mode vba to isolate.
FAIL    : drawing doc cannot be opened out-of-process — defer.

Prereq: SOLIDWORKS running. Creates own blank Part + Drawing (non-destructive;
never touches the user's open documents).

Usage
-----
    python spikes/v0_16/spike_drawview.py --out report.json
    python spikes/v0_16/spike_drawview.py --mode vba
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
_V15 = Path(__file__).resolve().parents[1] / "v0_15"
sys.path.insert(0, str(_PKG_ROOT))
sys.path.insert(0, str(_V15))

import pythoncom  # noqa: E402

from ai_sw_bridge.com.earlybind import typed  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402

from spike_persist_reference import build_single_box  # noqa: E402
from spike_earlybind_persist import connect_running_sw, ensure_sw_module  # noqa: E402

SW_DEFAULT_TEMPLATE_PART = 8
SW_DEFAULT_TEMPLATE_DRAWING = 9
SW_DOC_PART = 1
SW_DOC_DRAWING = 3
SW_OPEN_SILENT = 1
SW_SAVEAS3_OPTIONS = 0
SW_SAVEAS3_SILENT = 0


def _tag(v: Any) -> str:
    return "NoneType" if v is None else type(v).__name__


def _title(d: Any) -> Any:
    t = d.GetTitle
    return t() if callable(t) else t


def _try_close(sw: Any, doc: Any) -> None:
    try:
        sw.CloseDoc(_title(doc))
    except Exception:  # noqa: BLE001
        pass


def _new_blank_drawing(sw: Any) -> Any:
    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_DRAWING)
    return sw.NewDocument(template, 0, 0.210, 0.297)


def _capture(fn: Any, label: str = "") -> dict[str, Any]:
    t0 = time.perf_counter()
    try:
        val = fn()
        return {
            "status": "OK",
            "type": _tag(val),
            "_val": val,
            "elapsed_ms": (time.perf_counter() - t0) * 1000.0,
        }
    except Exception as e:  # noqa: BLE001
        return {
            "status": "EXCEPTION",
            "exception_type": type(e).__name__,
            "message": str(e)[:200],
            "hresult": f"{e.hresult:#010x}" if hasattr(e, "hresult") else None,
            "elapsed_ms": (time.perf_counter() - t0) * 1000.0,
        }


def run(keep_file: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {"binding": "hybrid early (com.earlybind pattern)"}

    mod = wrapper_module()
    mod_source = "com.sw_type_info.wrapper_module"
    if mod is None:
        mod, info = ensure_sw_module()
        mod_source = "spike_earlybind_persist.ensure_sw_module (LoadTypeLib fallback)"
        result["module_fallback_info"] = info
    result["module_source"] = mod_source
    result["module"] = getattr(mod, "__name__", str(mod))

    sw = connect_running_sw()
    try:
        result["sw_revision"] = str(sw.RevisionNumber)
    except Exception:  # noqa: BLE001
        result["sw_revision"] = "<unreadable>"

    tmp_dir = Path(tempfile.gettempdir()) / "ai-sw-bridge"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    part_path = tmp_dir / "spike_drawview_part.sldprt"
    drawing_path = tmp_dir / "spike_drawview.slddrw"
    for p in (part_path, drawing_path):
        if p.exists():
            try:
                p.unlink()
            except OSError:
                pass

    # --- 1. Build a part to draw views of -----------------------------------
    part_template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    part_doc = sw.NewDocument(part_template, 0, 0.0, 0.0)
    if part_doc is None:
        return {**result, "overall": "FAIL", "reason": "NewDocument(part) returned None"}

    build = build_single_box(part_doc)
    result["build"] = build
    if not build.get("built"):
        _try_close(sw, part_doc)
        return {**result, "overall": "FAIL", "reason": "test part did not build"}

    try:
        part_doc.SaveAs3(str(part_path), 0, 0)
    except Exception as e:  # noqa: BLE001
        _try_close(sw, part_doc)
        return {**result, "overall": "FAIL", "reason": f"SaveAs3(part) raised: {e}"}
    _try_close(sw, part_doc)
    result["part_saved"] = str(part_path)

    # --- 2. Open a blank drawing --------------------------------------------
    drawing_doc = _new_blank_drawing(sw)
    if drawing_doc is None:
        return {**result, "overall": "FAIL", "reason": "NewDocument(drawing) returned None"}

    result["drawing_opened"] = True
    result["drawing_type"] = _tag(drawing_doc)

    # --- 3. Probe drawing API surface ---------------------------------------
    probes: dict[str, Any] = {}

    # 3a. Get IDrawingDoc interface
    probes["GetIDrawingDoc"] = _capture(
        lambda: drawing_doc if hasattr(drawing_doc, "CreateDrawViewFromModelView3") else None,
        "IDrawingDoc",
    )

    # 3b. Create standard views
    view_names = ["*Front", "*Top", "*Right", "*Isometric"]
    views_created: list[dict[str, Any]] = []
    for i, vn in enumerate(view_names):
        x = 0.1 + i * 0.1
        y = 0.15
        probe = _capture(
            lambda vn=vn, x=x, y=y: drawing_doc.CreateDrawViewFromModelView3(
                str(part_path), vn, x, y, 0.0
            ),
            vn,
        )
        views_created.append({"view": vn, **probe})
    probes["views"] = views_created

    n_ok = sum(1 for v in views_created if v["status"] == "OK" and v.get("_val") is not None)
    result["views_attempted"] = len(view_names)
    result["views_created"] = n_ok

    # 3c. Save the drawing
    try:
        drawing_doc.SaveAs3(str(drawing_path), 0, 0)
        saved = drawing_path.exists()
        result["drawing_saved"] = saved
        result["drawing_path"] = str(drawing_path)
    except Exception as e:  # noqa: BLE001
        result["drawing_saved"] = False
        result["save_error"] = f"{type(e).__name__}: {e}"

    result["probes"] = probes

    # --- Cleanup ------------------------------------------------------------
    _try_close(sw, drawing_doc)
    if not keep_file:
        for p in (part_path, drawing_path):
            try:
                p.unlink()
            except OSError:
                pass
        result["cleanup"] = "closed doc + removed temp files"
    else:
        result["cleanup"] = f"kept files: {part_path}, {drawing_path}"

    # --- Verdict ------------------------------------------------------------
    if n_ok > 0 and result.get("drawing_saved"):
        overall = "PASS"
        interp = "drawing with views created + saved out-of-process -> build the handler"
    elif n_ok > 0:
        overall = "PARTIAL"
        interp = "views created but save failed -> narrow save path or template"
    elif drawing_doc is not None:
        overall = "PARTIAL"
        interp = (
            "drawing opened but CreateDrawViewFromModelView3 failed "
            "-> run --mode vba to isolate the marshaler"
        )
    else:
        overall = "FAIL"
        interp = "drawing doc cannot be opened out-of-process -> defer"

    result["overall"] = overall
    result["interpretation"] = interp
    return result


def emit_vba() -> str:
    return r"""' Spike v0.16 S-DRAWVIEW VBA oracle.
' Paste into a Drawing document module, press F5.
Option Explicit
Sub ProbeDrawView()
    Dim swApp     As SldWorks.SldWorks
    Dim Draw      As SldWorks.DrawingDoc
    Dim PartPath  As String
    Dim View      As SldWorks.View
    Set swApp = Application.SldWorks
    Set Draw  = swApp.ActiveDoc
    PartPath = "C:\Temp\spike_drawview_part.sldprt"
    Set View = Draw.CreateDrawViewFromModelView3(PartPath, "*Front", 0.1, 0.15, 0)
    If View Is Nothing Then
        MsgBox "CreateDrawViewFromModelView3 returned Nothing"
    Else
        MsgBox "View created: " & View.GetName2
    End If
End Sub
"""


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--mode", choices=["com", "vba"], default="com")
    p.add_argument("--out", type=Path, default=None)
    p.add_argument("--keep-file", action="store_true")
    args = p.parse_args()

    if args.mode == "vba":
        out = Path(__file__).parent / "spike_drawview.bas"
        out.write_text(emit_vba(), encoding="utf-8")
        print(f"wrote {out}", file=sys.stderr)
        return 0

    pythoncom.CoInitialize()
    try:
        result = run(args.keep_file)
    finally:
        pythoncom.CoUninitialize()

    payload = json.dumps(result, indent=2, default=str)
    if args.out is not None:
        args.out.write_text(payload, encoding="utf-8")
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(payload)
    return {"PASS": 0, "PARTIAL": 2, "FAIL": 1}.get(result.get("overall"), 1)


if __name__ == "__main__":
    raise SystemExit(main())
