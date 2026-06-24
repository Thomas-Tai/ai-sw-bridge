"""Spike v0.20 / SaveAs3 production-path probe.

Tests whether the production ``_save_as_with_verification`` function
succeeds or fails on a live SW doc. This directly tests whether the W10
PAE symptom (raise "swFileSaveError=1") is reproducible through the
actual production code path.

If it succeeds → the W10 symptom was a one-off or environment issue.
If it fails → the exact error message tells us the failure mode.

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


def run() -> dict[str, Any]:
    result: dict[str, Any] = {"spike": "saveas3_prodpath", "wave": 11}

    from ai_sw_bridge.spec.builder import _save_as_with_verification

    sw = connect_running_sw()

    try:
        result["sw_revision"] = str(sw.RevisionNumber)
    except Exception:
        result["sw_revision"] = "<unreadable>"

    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        return {**result, "overall": "FAIL", "reason": "NewDocument returned None"}

    if not build_box(doc):
        return {**result, "overall": "FAIL", "reason": "box build failed"}

    try:
        doc.EditRebuild3
    except Exception:
        pass

    ts = int(time.time())
    out_path = Path(tempfile.gettempdir()) / f"saveas3_prodpath_{ts}.sldprt"
    if out_path.exists():
        out_path.unlink()

    t0 = time.perf_counter()
    raised = False
    exc_info = None
    saved_path = None
    verified = None
    try:
        saved_path, verified = _save_as_with_verification(doc, out_path)
    except Exception as exc:
        raised = True
        exc_info = {
            "type": type(exc).__name__,
            "message": str(exc)[:500],
        }
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    result["production_save"] = {
        "raised": raised,
        "exception": exc_info,
        "saved_path": saved_path,
        "verified": verified,
        "elapsed_ms": round(elapsed_ms, 2),
        "file_exists": out_path.exists(),
        "file_size": out_path.stat().st_size if out_path.exists() else 0,
    }

    # Also probe GetSaveFlag on the late-bound doc after production save
    try:
        result["get_save_flag_after"] = bool(doc.GetSaveFlag)
    except Exception as e:
        result["get_save_flag_after"] = f"<error: {e}>"

    if not raised and verified is True:
        result["overall"] = "GREEN"
        result["verdict"] = (
            "_save_as_with_verification SUCCEEDS through the production code "
            "path on a live SW 2024 SP1 seat. The W10 PAE symptom does NOT "
            "reproduce. The existing err_code check and retry loop are "
            "functioning correctly for the normal case."
        )
    elif raised:
        result["overall"] = "FAIL"
        result["verdict"] = (
            f"_save_as_with_verification RAISED: {exc_info}. "
            "This reproduces (or characterizes) the W10 PAE symptom."
        )
    else:
        result["overall"] = "PARTIAL"
        result["verdict"] = f"Unexpected: raised={raised}, verified={verified}"

    # Also test the export dispatch path
    try:
        from ai_sw_bridge.export.dispatch import _saveas3_direct, ExportRequest
        from ai_sw_bridge.export.formats import resolve_format

        step_path = Path(tempfile.gettempdir()) / f"saveas3_prodpath_{ts}.step"
        if step_path.exists():
            step_path.unlink()
        fmt = resolve_format("step214")
        export_result = _saveas3_direct(doc, fmt, step_path)
        result["export_save"] = {
            "ok": export_result.ok,
            "error": export_result.error,
            "path": export_result.path,
            "file_exists": step_path.exists(),
            "file_size": step_path.stat().st_size if step_path.exists() else 0,
        }
    except Exception as e:
        result["export_save"] = {"error": f"{type(e).__name__}: {e}"}

    # Cleanup
    try:
        doc.CloseDoc
    except Exception:
        pass

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

    out_path = args.out or Path(__file__).parent / "_results" / "saveas3_prodpath.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"wrote {out_path}", file=sys.stderr)
    print(json.dumps(result, indent=2, default=str))

    rc = {"GREEN": 0, "PARTIAL": 2, "FAIL": 1}
    return rc.get(result.get("overall"), 1)


if __name__ == "__main__":
    raise SystemExit(main())
