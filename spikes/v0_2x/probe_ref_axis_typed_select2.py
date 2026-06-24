"""MEASURE-FIRST probe round 2 — ref_axis 2nd-plane append on a TYPED doc.

Round 1 proved: typed Extension + VARIANT(VT_DISPATCH,None) callout RAISES;
5-arg SelectByID does NOT append (sel_count stays 1); typed IModelDoc2 has no
FeatureByName. Round 2 finds a callout-free / binding-robust append that yields
sel_count==2 and materializes a RefAxis:

  C typed_ext_bare_none : typed ext.SelectByID2(p2,...,None,0) — early-bound may
                          marshal a bare-None dispatch where late-bound needs a
                          VARIANT (the inverse of the OOP late-bound case).
  D latebound_ext_variant : re-wrap the Extension late-bound via
                          win32com.client.dynamic.Dispatch and use the PROVEN
                          VARIANT(VT_DISPATCH,None) callout (the direct-call recipe).
  E feature_walk_select2 : walk FirstFeature/GetNextFeature to the plane nodes,
                          typed(IFeature).Select2(append,0) — callout-free.

Each candidate runs on a FRESH typed reopen.
Run: PYTHONPATH=<repo>/src python spikes/v0_2x/probe_ref_axis_typed_select2.py
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
import win32com.client.dynamic as w32dyn  # noqa: E402
from win32com.client import VARIANT  # noqa: E402

from ai_sw_bridge.com.earlybind import typed  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402

_WORK = _HERE.parent / "_results" / "probe_refaxis_work2"
_OUT = _HERE.parent / "_results" / "probe_refaxis_typed_select2.json"
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


def _feature_by_name_walk(doc: Any, name: str, mod: Any) -> Any:
    """typed-doc has no FeatureByName; walk the tree and match GetName."""
    try:
        f = doc.FirstFeature()
    except Exception:
        f = None
    while f is not None:
        try:
            tf = typed(f, "IFeature", module=mod)
            nm = tf.GetName
            nm = nm() if callable(nm) else nm
            if str(nm) == name:
                return tf
            nxt = tf.GetNextFeature
            f = nxt() if callable(nxt) else nxt
        except Exception:
            break
    return None


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

        # ── C: typed ext, bare None callout ──
        doc = _open_typed(sw, seed)
        try:
            doc.ClearSelection2(True)
            doc.SelectByID(p1, "PLANE", 0, 0, 0)
            ext = doc.Extension
            r2 = ext.SelectByID2(p2, "PLANE", 0, 0, 0, True, 0, None, 0)
            cnt = _sel_count(doc)
            ax = doc.InsertAxis2(True)
            doc.ForceRebuild3(False)
            out["C_typed_ext_bare_none"] = {
                "r2": bool(r2),
                "sel_count": cnt,
                "insertaxis_ret": repr(ax),
                "refaxis_node": _has_refaxis(doc),
            }
        except Exception as exc:  # noqa: BLE001
            out["C_typed_ext_bare_none"] = {"exc": repr(exc)}
        finally:
            sw.CloseAllDocuments(True)

        # ── D: late-bound Extension via dynamic.Dispatch + VARIANT callout ──
        doc = _open_typed(sw, seed)
        try:
            doc.ClearSelection2(True)
            doc.SelectByID(p1, "PLANE", 0, 0, 0)
            ext_lb = w32dyn.Dispatch(doc.Extension)
            r2 = ext_lb.SelectByID2(
                p2, "PLANE", 0, 0, 0, True, 0, VARIANT(pythoncom.VT_DISPATCH, None), 0
            )
            cnt = _sel_count(doc)
            ax = doc.InsertAxis2(True)
            doc.ForceRebuild3(False)
            out["D_latebound_ext_variant"] = {
                "r2": bool(r2),
                "sel_count": cnt,
                "insertaxis_ret": repr(ax),
                "refaxis_node": _has_refaxis(doc),
                "ext_lb_type": type(ext_lb).__name__,
            }
        except Exception as exc:  # noqa: BLE001
            out["D_latebound_ext_variant"] = {"exc": repr(exc)}
        finally:
            sw.CloseAllDocuments(True)

        # ── E: feature-walk + typed IFeature.Select2 append ──
        doc = _open_typed(sw, seed)
        try:
            mod = wrapper_module()
            doc.ClearSelection2(True)
            f1 = _feature_by_name_walk(doc, p1, mod)
            f2 = _feature_by_name_walk(doc, p2, mod)
            r1 = bool(f1.Select2(False, 0)) if f1 is not None else False
            r2 = bool(f2.Select2(True, 0)) if f2 is not None else False
            cnt = _sel_count(doc)
            ax = doc.InsertAxis2(True)
            doc.ForceRebuild3(False)
            out["E_feature_walk_select2"] = {
                "f1_found": f1 is not None,
                "f2_found": f2 is not None,
                "r1": r1,
                "r2": r2,
                "sel_count": cnt,
                "insertaxis_ret": repr(ax),
                "refaxis_node": _has_refaxis(doc),
            }
        except Exception as exc:  # noqa: BLE001
            out["E_feature_walk_select2"] = {"exc": repr(exc)}
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
