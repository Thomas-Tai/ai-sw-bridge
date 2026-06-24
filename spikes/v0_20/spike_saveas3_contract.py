"""Spike v0.20 / SaveAs3 return-contract probe.  [W11 Slice 1A]

Settles the question: does ``IModelDoc2.SaveAs3(path, version, options)``
return a **bool** (TRUE = success) or a ``swFileSaveError_e`` int code
(0 = NoError)?

Two production sites (``builder._save_as_with_verification`` and
``export.dispatch._saveas3_direct``) treat the return as an error code and
raise on nonzero.  If the return is actually bool-TRUE (int 1), that raise
fires on every successful save — which is exactly the W10 Phase-2 PAE
symptom ("returned swFileSaveError=1 … file not written" with the file on
disk).

Bind path mirrors production EXACTLY:
  pythoncom.CoInitialize()
  sw  = connect_running_sw()          # dynamic dispatch (late-bound)
  mod = wrapper_module()              # ai_sw_bridge.com.sw_type_info
  tsw = typed(sw, "ISldWorks", module=mod)
  doc = tsw.NewDocument(template, 0, 0.0, 0.0)
  tdoc = typed(doc, "IModelDoc2", module=mod)

Box recipe: proven InsertSketch + CreateCornerRectangle + FeatureExtrusion2
(same as spike_persist_reference / production builder).

Probe 1 (good): save to %TEMP% (non-synced) path.
Probe 2 (forced fail): dirty the doc, save to Q:\\invalid\\...

Writes ``spikes/v0_20/_results/saveas3_contract.json``.

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

# -- proven box constants (mirror spike_persist_reference) -----------------
BOX_W_M = 0.020
BOX_H_M = 0.020
BOX_D_M = 0.010
SW_DEFAULT_TEMPLATE_PART = 8
SW_START_SKETCH_PLANE = 0


def connect_running_sw() -> Any:
    """Late-bound dynamic dispatch to a running SW instance."""
    from win32com.client import dynamic  # noqa: WPS433

    try:
        return dynamic.Dispatch(pythoncom.GetActiveObject("SldWorks.Application"))
    except Exception:
        return dynamic.Dispatch("SldWorks.Application")


def build_box(doc: Any) -> dict[str, Any]:
    """Insert one Boss-Extrude box on the Front Plane (proven recipe)."""
    if not doc.SelectByID("Front Plane", "PLANE", 0.0, 0.0, 0.0):
        return {"built": False, "error": "could not select Front Plane"}

    sk = doc.SketchManager
    sk.InsertSketch(True)
    seg = sk.CreateCornerRectangle(
        -BOX_W_M / 2, -BOX_H_M / 2, 0.0, BOX_W_M / 2, BOX_H_M / 2, 0.0
    )
    if seg is None:
        sk.InsertSketch(True)
        return {"built": False, "error": "CreateCornerRectangle returned None"}
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
    if feat is None:
        return {"built": False, "error": "FeatureExtrusion2 returned None"}
    return {"built": True, "feature_name": getattr(feat, "Name", None)}


def dirty_doc(doc: Any) -> dict[str, Any]:
    """Add a second sketch+circle so the doc is dirty for probe 2."""
    if not doc.SelectByID("Front Plane", "PLANE", 0.0, 0.0, 0.0):
        return {"dirtied": False, "error": "re-select Front Plane failed"}
    sk = doc.SketchManager
    sk.InsertSketch(True)
    sk.CreateCircle(0.0, 0.0, 0.0, 0.005, 0.0, 0.0)
    sk.InsertSketch(True)
    return {"dirtied": True}


def capture_saveas3(tdoc: Any, path: str, label: str) -> dict[str, Any]:
    """Call SaveAs3 and capture every observable."""
    info: dict[str, Any] = {"label": label, "path": path}

    t0 = time.perf_counter()
    raised = False
    ret = None
    exc_info = None
    try:
        ret = tdoc.SaveAs3(path, 0, 0)
    except Exception as exc:
        raised = True
        exc_info = {
            "type": type(exc).__name__,
            "message": str(exc)[:500],
        }
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    info["raised"] = raised
    info["exception"] = exc_info
    info["return_value"] = repr(ret)
    info["return_type"] = type(ret).__name__
    info["return_int"] = int(ret) if ret is not None and not raised else None
    info["return_bool"] = bool(ret) if ret is not None and not raised else None
    info["elapsed_ms"] = round(elapsed_ms, 2)

    try:
        info["get_save_flag"] = bool(tdoc.GetSaveFlag)
    except Exception as exc:
        info["get_save_flag"] = f"<error: {type(exc).__name__}: {exc}>"

    info["file_exists"] = os.path.isfile(path)
    if info["file_exists"]:
        try:
            info["file_size_bytes"] = os.path.getsize(path)
        except OSError:
            info["file_size_bytes"] = -1
    else:
        info["file_size_bytes"] = 0

    return info


def run() -> dict[str, Any]:
    result: dict[str, Any] = {
        "spike": "saveas3_contract",
        "wave": 11,
        "slice": "1A",
    }

    mod = wrapper_module()
    if mod is None:
        return {**result, "overall": "FAIL", "reason": "wrapper_module() returned None"}
    result["module"] = getattr(mod, "__name__", str(mod))

    sw = connect_running_sw()
    tsw = typed(sw, "ISldWorks", module=mod)

    try:
        result["sw_revision"] = str(sw.RevisionNumber)
    except Exception:
        result["sw_revision"] = "<unreadable>"

    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = tsw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        return {**result, "overall": "FAIL", "reason": "NewDocument returned None"}

    tdoc = typed(doc, "IModelDoc2", module=mod)

    build = build_box(doc)
    result["build"] = build
    if not build.get("built"):
        return {**result, "overall": "FAIL", "reason": "box build failed"}

    try:
        doc.EditRebuild3
    except Exception:
        pass

    # -- Probe 1: good path (save to %TEMP%, non-synced) --------------------
    ts = int(time.time())
    good_path = os.path.join(tempfile.gettempdir(), f"saveas3_probe_{ts}.SLDPRT")
    if os.path.exists(good_path):
        os.unlink(good_path)
    result["probe_good"] = capture_saveas3(tdoc, good_path, "good_path")

    # -- Dirty the doc so probe 2's GetSaveFlag read is meaningful ----------
    dirty_result = dirty_doc(doc)
    result["dirty"] = dirty_result

    # -- Probe 2: forced failure (invalid drive) ----------------------------
    bad_path = r"Q:\invalid_drive\saveas3_fail.SLDPRT"
    result["probe_bad"] = capture_saveas3(tdoc, bad_path, "forced_fail")

    # -- Verdict ------------------------------------------------------------
    pg = result["probe_good"]
    pb = result["probe_bad"]

    good_ret_truthy = (
        not pg["raised"] and pg["return_int"] is not None and pg["return_int"] != 0
    )
    good_file_ok = pg["file_exists"] and pg.get("file_size_bytes", 0) > 0
    good_flag_clean = pg["get_save_flag"] is False

    bad_no_file = not pb["file_exists"]
    bad_fail_signal = (
        pb["raised"]
        or (pb["return_int"] is not None and pb["return_int"] == 0)
        or (pb["return_value"] in ("False", "None", "0"))
    )

    if (
        good_ret_truthy
        and good_file_ok
        and good_flag_clean
        and bad_no_file
        and bad_fail_signal
    ):
        result["overall"] = "CONFIRMED"
        result["verdict"] = (
            "SaveAs3 returns bool-TRUE (int 1) on success, bool-FALSE (int 0) or "
            "raises on failure. The swFileSaveError interpretation is WRONG. "
            "Fix premise CONFIRMED: scalar return is NOT a reliable error code."
        )
    elif good_file_ok and good_flag_clean:
        result["overall"] = "PARTIAL"
        result["verdict"] = (
            f"File saved OK but return shape unexpected: "
            f"ret={pg['return_value']} (type={pg['return_type']}, "
            f"int={pg['return_int']}). Manual review needed."
        )
    else:
        result["overall"] = "WALL"
        result["verdict"] = (
            f"Good probe failed: raised={pg['raised']}, ret={pg['return_value']}, "
            f"file_exists={pg['file_exists']}, get_save_flag={pg['get_save_flag']}. "
            f"Fix premise may be wrong — STOP and review."
        )

    # -- Cleanup: close the doc without saving again ------------------------
    try:
        doc.CloseDoc
    except Exception:
        pass

    return result


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Write JSON report to this path (default: _results/saveas3_contract.json).",
    )
    args = p.parse_args()

    pythoncom.CoInitialize()
    try:
        result = run()
    finally:
        pythoncom.CoUninitialize()

    out_path = args.out or Path(__file__).parent / "_results" / "saveas3_contract.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"wrote {out_path}", file=sys.stderr)

    rc = {"CONFIRMED": 0, "PARTIAL": 2, "WALL": 1, "FAIL": 1}
    return rc.get(result.get("overall"), 1)


if __name__ == "__main__":
    raise SystemExit(main())
