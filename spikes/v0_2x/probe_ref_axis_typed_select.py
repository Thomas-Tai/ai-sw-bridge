"""MEASURE-FIRST probe — ref_axis typed-doc SelectByID2 callout defect.

Reproduces the EXACT defect context (a TYPED IModelDoc2 from _open_doc_typed,
the disk-transaction path) and determines which CALLOUT-FREE append-select of
the 2nd plane materializes a RefAxis, so the production fix is evidence-led,
not guessed.

  R0 repro            : on the TYPED Extension, the legacy
                        ext.SelectByID2(plane2,"PLANE",...,VARIANT(VT_DISPATCH,
                        None),...) callout RAISES (the transaction-path defect).
  A two_selectbyid    : ClearSelection2; SelectByID(p1,"PLANE"); SelectByID(
                        p2,"PLANE"); count==2 ? InsertAxis2(True) -> RefAxis ?
  B selectbyid_plus_feature_select2 : SelectByID(p1,"PLANE"); typed(FeatureByName
                        (p2),"IFeature").Select2(True,0); count==2 ? InsertAxis2 ?

Each candidate runs on a FRESH typed reopen (no cross-contamination).
Run: PYTHONPATH=<repo>/src python spikes/v0_2x/probe_ref_axis_typed_select.py
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
_SRC = _HERE.parents[2] / "src"
for _p in (str(_SRC), str(_HERE.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import pythoncom  # noqa: E402
import win32com.client as w32  # noqa: E402
from win32com.client import VARIANT  # noqa: E402

from ai_sw_bridge.com.earlybind import typed  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402

_WORK = _HERE.parent / "_results" / "probe_refaxis_work"
_OUT = _HERE.parent / "_results" / "probe_refaxis_typed_select.json"
out: dict[str, Any] = {}


def _build_box(sw: Any, path: str) -> bool:
    template = sw.GetUserPreferenceStringValue(8)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        return False
    fm, sm = doc.FeatureManager, doc.SketchManager
    doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
    sm.InsertSketch(True)
    sm.CreateCornerRectangle(-0.01, -0.01, 0, 0.01, 0.01, 0)
    sm.InsertSketch(True)
    fm.FeatureExtrusion3(
        True,
        False,
        False,
        0,
        0,
        0.01,
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
        0.0,
        0.0,
        False,
    )
    doc.ForceRebuild3(False)
    doc.SaveAs3(path, 0, 0)
    sw.CloseAllDocuments(True)
    return os.path.isfile(path)


def _open_typed(sw: Any, path: str) -> Any:
    """Mirror mutate._open_doc_typed — a TYPED IModelDoc2 (the defect context)."""
    mod = wrapper_module()
    tsw = typed(sw, "ISldWorks", module=mod)
    ret = tsw.OpenDoc6(path, 1, 1, "", 0, 0)
    doc = ret[0] if isinstance(ret, tuple) else ret
    if doc is not None:
        doc.ForceRebuild3(False)
    return doc


def _has_refaxis(doc: Any) -> bool:
    for f in doc.FeatureManager.GetFeatures(False) or []:
        for attr in ("GetTypeName2", "GetTypeName"):
            try:
                v = getattr(f, attr)
                if "refaxis" in str(v() if callable(v) else v).lower():
                    return True
                break
            except Exception:
                continue
    return False


def _sel_count(doc: Any) -> int:
    try:
        sm = doc.SelectionManager
        v = sm.GetSelectedObjectCount2
        return int(v(-1) if callable(v) else v)
    except Exception:
        return -1


def main() -> int:
    pythoncom.CoInitialize()
    _ = wrapper_module()
    sw = w32.Dispatch("SldWorks.Application")
    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass
    if _WORK.exists():
        shutil.rmtree(_WORK, ignore_errors=True)
    _WORK.mkdir(parents=True, exist_ok=True)
    seed = str(_WORK / "probe_seed.SLDPRT")
    p1, p2 = "Front Plane", "Right Plane"
    try:
        if not _build_box(sw, seed):
            out["error"] = "seed build failed"
            return 1

        # ── R0: reproduce the callout TypeError on the TYPED Extension ──
        doc = _open_typed(sw, seed)
        try:
            doc.ClearSelection2(True)
            doc.SelectByID(p1, "PLANE", 0, 0, 0)
            ext = doc.Extension
            ext.SelectByID2(
                p2, "PLANE", 0, 0, 0, True, 0, VARIANT(pythoncom.VT_DISPATCH, None), 0
            )
            out["R0_repro"] = {
                "raised": False,
                "note": "callout did NOT raise (unexpected)",
            }
        except Exception as exc:  # noqa: BLE001
            out["R0_repro"] = {
                "raised": True,
                "exc": repr(exc),
                "ext_type": type(doc.Extension).__name__,
            }
        finally:
            sw.CloseAllDocuments(True)

        # ── A: two 5-arg SelectByID (append-by-default hypothesis) ──
        doc = _open_typed(sw, seed)
        try:
            doc.ClearSelection2(True)
            r1 = doc.SelectByID(p1, "PLANE", 0, 0, 0)
            r2 = doc.SelectByID(p2, "PLANE", 0, 0, 0)
            cnt = _sel_count(doc)
            ax = doc.InsertAxis2(True)
            doc.ForceRebuild3(False)
            out["A_two_selectbyid"] = {
                "r1": bool(r1),
                "r2": bool(r2),
                "sel_count": cnt,
                "insertaxis_ret": repr(ax),
                "refaxis_node": _has_refaxis(doc),
            }
        except Exception as exc:  # noqa: BLE001
            out["A_two_selectbyid"] = {"exc": repr(exc)}
        finally:
            sw.CloseAllDocuments(True)

        # ── B: SelectByID(p1) + typed IFeature.Select2(append) for p2 ──
        doc = _open_typed(sw, seed)
        try:
            mod = wrapper_module()
            doc.ClearSelection2(True)
            r1 = doc.SelectByID(p1, "PLANE", 0, 0, 0)
            feat2 = doc.FeatureByName(p2)
            tfeat2 = typed(feat2, "IFeature", module=mod) if feat2 is not None else None
            r2 = bool(tfeat2.Select2(True, 0)) if tfeat2 is not None else False
            cnt = _sel_count(doc)
            ax = doc.InsertAxis2(True)
            doc.ForceRebuild3(False)
            out["B_selectbyid_plus_feature_select2"] = {
                "r1": bool(r1),
                "feat2_found": feat2 is not None,
                "r2": r2,
                "sel_count": cnt,
                "insertaxis_ret": repr(ax),
                "refaxis_node": _has_refaxis(doc),
            }
        except Exception as exc:  # noqa: BLE001
            out["B_selectbyid_plus_feature_select2"] = {"exc": repr(exc)}
        finally:
            sw.CloseAllDocuments(True)
    finally:
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass
        pythoncom.CoUninitialize()
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(json.dumps(out, indent=2, default=str))
    print(f"\n(wrote {_OUT})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
