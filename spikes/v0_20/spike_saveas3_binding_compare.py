"""Spike v0.20 / SaveAs3 binding-comparison probe.

Follow-up to spike_saveas3_contract.py. The first spike found that under
the TYPED IModelDoc2 wrapper, SaveAs3 returns 0 on success and 1 on failure
— the opposite of the bool-TRUE hypothesis. But production calls SaveAs3
on the LATE-BOUND doc object. This spike probes both paths side-by-side
to determine whether the binding is the variable.

Also probes whether GetSaveFlag is a method (must be called) vs a property
under the typed wrapper, since the first spike saw it stuck at True.

Prereq: SOLIDWORKS 2024 SP1 running.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

import pythoncom  # noqa: E402

from ai_sw_bridge.com.earlybind import typed  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402

BOX_W_M = 0.020
BOX_H_M = 0.020
BOX_D_M = 0.010
SW_DEFAULT_TEMPLATE_PART = 8
SW_START_SKETCH_PLANE = 0


def connect_running_sw() -> Any:
    from win32com.client import dynamic

    try:
        return dynamic.Dispatch(pythoncom.GetActiveObject("SldWorks.Application"))
    except Exception:
        return dynamic.Dispatch("SldWorks.Application")


def build_box(doc: Any) -> bool:
    if not doc.SelectByID("Front Plane", "PLANE", 0.0, 0.0, 0.0):
        return False
    sk = doc.SketchManager
    sk.InsertSketch(True)
    seg = sk.CreateCornerRectangle(
        -BOX_W_M / 2, -BOX_H_M / 2, 0.0, BOX_W_M / 2, BOX_H_M / 2, 0.0
    )
    if seg is None:
        sk.InsertSketch(True)
        return False
    sk.InsertSketch(True)
    fm = doc.FeatureManager
    base_args = (
        True,
        False,
        False,
        0,
        0,
        BOX_D_M,
        0.0,
        False,
        False,
        False,
        False,
        0.0,
        0.0,
        False,
        False,
        False,
        False,
        True,
        True,
        True,
        SW_START_SKETCH_PLANE,
        0.0,
        False,
    )
    try:
        feat = fm.FeatureExtrusion2(*base_args, False)
    except Exception:
        feat = fm.FeatureExtrusion2(*base_args)
    return feat is not None


def probe_save(doc_any: Any, path: str, label: str) -> dict[str, Any]:
    """Call SaveAs3 on any doc-like object, capture everything."""
    info: dict[str, Any] = {"label": label, "path": path}
    raised = False
    ret = None
    exc_info = None
    t0 = time.perf_counter()
    try:
        ret = doc_any.SaveAs3(path, 0, 0)
    except Exception as exc:
        raised = True
        exc_info = {"type": type(exc).__name__, "message": str(exc)[:300]}
    info["raised"] = raised
    info["exception"] = exc_info
    info["return_value"] = repr(ret)
    info["return_type"] = type(ret).__name__
    info["return_int"] = int(ret) if ret is not None and not raised else None
    info["elapsed_ms"] = round((time.perf_counter() - t0) * 1000, 2)
    info["file_exists"] = os.path.isfile(path)
    info["file_size"] = os.path.getsize(path) if info["file_exists"] else 0
    return info


def probe_getsaveflag(doc_any: Any, label: str) -> dict[str, Any]:
    """Probe GetSaveFlag as both property (getattr) and method (call)."""
    info: dict[str, Any] = {"label": label}
    # As property / auto-invoke
    try:
        val = doc_any.GetSaveFlag
        info["as_property"] = repr(val)
        info["as_property_type"] = type(val).__name__
        info["as_property_bool"] = bool(val)
    except Exception as e:
        info["as_property"] = f"<error: {type(e).__name__}: {e}>"

    # As explicit method call (some typed interfaces need this)
    try:
        val = doc_any.GetSaveFlag()
        info["as_method"] = repr(val)
        info["as_method_type"] = type(val).__name__
        info["as_method_bool"] = bool(val)
    except Exception as e:
        info["as_method"] = f"<error: {type(e).__name__}: {e}>"

    return info


def run() -> dict[str, Any]:
    result: dict[str, Any] = {"spike": "saveas3_binding_compare", "wave": 11}

    mod = wrapper_module()
    if mod is None:
        return {**result, "overall": "FAIL", "reason": "wrapper_module() None"}

    sw = connect_running_sw()

    # Build TWO boxes in separate docs — one for each binding path
    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)

    # -- Doc A: late-bound SaveAs3 ------------------------------------------
    docA = sw.NewDocument(template, 0, 0.0, 0.0)
    if docA is None:
        return {**result, "overall": "FAIL", "reason": "NewDocument A None"}
    if not build_box(docA):
        return {**result, "overall": "FAIL", "reason": "box A build failed"}
    try:
        docA.EditRebuild3
    except Exception:
        pass

    ts = int(time.time())
    path_a = os.path.join(tempfile.gettempdir(), f"saveas3_LATE_{ts}.SLDPRT")
    if os.path.exists(path_a):
        os.unlink(path_a)

    result["late_bound"] = probe_save(docA, path_a, "late_bound_doc")
    result["late_bound_getsaveflag"] = probe_getsaveflag(docA, "late_bound_after_save")

    # -- Doc B: typed IModelDoc2 SaveAs3 ------------------------------------
    docB = sw.NewDocument(template, 0, 0.0, 0.0)
    if docB is None:
        return {**result, "overall": "FAIL", "reason": "NewDocument B None"}
    if not build_box(docB):
        return {**result, "overall": "FAIL", "reason": "box B build failed"}
    try:
        docB.EditRebuild3
    except Exception:
        pass

    tdocB = typed(docB, "IModelDoc2", module=mod)
    path_b = os.path.join(tempfile.gettempdir(), f"saveas3_TYPED_{ts}.SLDPRT")
    if os.path.exists(path_b):
        os.unlink(path_b)

    result["typed_bound"] = probe_save(tdocB, path_b, "typed_IModelDoc2")
    result["typed_bound_getsaveflag"] = probe_getsaveflag(tdocB, "typed_after_save")

    # -- Also probe GetSaveFlag on the raw late-bound docB (before close) ---
    result["raw_docB_getsaveflag"] = probe_getsaveflag(
        docB, "raw_docB_after_typed_save"
    )

    # -- Negative probe on late-bound doc -----------------------------------
    bad_path = r"Q:\invalid\fail.SLDPRT"
    result["late_bound_fail"] = probe_save(docA, bad_path, "late_bound_invalid_path")

    # -- Cleanup ------------------------------------------------------------
    for d in (docA, docB):
        try:
            d.CloseDoc
        except Exception:
            pass

    # -- Verdict ------------------------------------------------------------
    late_ret = result["late_bound"].get("return_int")
    typed_ret = result["typed_bound"].get("return_int")
    late_file = result["late_bound"].get("file_exists")
    typed_file = result["typed_bound"].get("file_exists")

    if late_ret is not None and typed_ret is not None:
        if late_ret == typed_ret:
            result["binding_effect"] = "NONE — both return same value"
        else:
            result["binding_effect"] = (
                f"SIGNIFICANT — late={late_ret}, typed={typed_ret}. "
                "Binding path changes the return semantics."
            )

    if late_file and typed_file:
        result["overall"] = "DATA_COLLECTED"
    else:
        result["overall"] = "PARTIAL"

    return result


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args()

    pythoncom.CoInitialize()
    try:
        result = run()
    finally:
        pythoncom.CoUninitialize()

    out_path = (
        args.out or Path(__file__).parent / "_results" / "saveas3_binding_compare.json"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"wrote {out_path}", file=sys.stderr)
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
