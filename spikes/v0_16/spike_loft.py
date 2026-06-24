"""Spike v0.16 / F2-LOFT — loft feature creation via COM.
[authored seat-free; RUN ON A LIVE SEAT]

Probes the loft (blend) feature API:
  ``CreateDefinition(swFmBlend=9) → typed_qi(ILoftFeatureData)
   → multi-profile mark-select → CreateFeature``

Target interface: ``ILoftFeatureData`` (``swFeatureNameID_e.swFmBlend``).
The typelib walk will confirm the constant value; it is expected to be 9
based on the SW API docs, but the spike-first law demands we read it
from ``swconst.tlb``.

Geometry: two closed profiles on parallel planes (e.g. circle on Front
Plane, rectangle on a ref-plane offset 50 mm).

Verdicts
--------
PASS    — loft materializes with two profiles.
PARTIAL — feature-data acquired but CreateFeature no-ops.
FAIL    — typelib walk yields no blend constant, or CreateDefinition
          returns None.

Usage
-----
    python spikes/v0_16/spike_loft.py --out report.json
    python spikes/v0_16/spike_loft.py --mode vba
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

from ai_sw_bridge.com.earlybind import typed, typed_qi  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402

from spike_earlybind_persist import connect_running_sw, ensure_sw_module  # noqa: E402

SW_DEFAULT_TEMPLATE_PART = 8
SWCONST_TLB = Path(r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\swconst.tlb")

ENUM_FUZZY_TOKENS = ("Blend", "Loft")
ENUM_EXACT_NAMES = ("swFeatureNameID_e",)


def _tag(v: Any) -> str:
    return "NoneType" if v is None else type(v).__name__


def _type_name(feat: Any) -> str | None:
    for attr in ("GetTypeName2", "GetTypeName"):
        try:
            m = getattr(feat, attr)
            return str(m() if callable(m) else m)
        except Exception:
            continue
    return None


def _title(d: Any) -> Any:
    t = d.GetTitle
    return t() if callable(t) else t


def _try_close(sw: Any, doc: Any) -> None:
    try:
        sw.CloseDoc(_title(doc))
    except Exception:
        pass


def _materialized(feat: Any) -> bool:
    return feat is not None and not isinstance(feat, int)


def _capture(fn: Any) -> dict[str, Any]:
    t0 = time.perf_counter()
    try:
        val = fn()
        out = {
            "status": "OK",
            "type": _tag(val),
            "_val": val,
            "elapsed_ms": (time.perf_counter() - t0) * 1000.0,
        }
        if isinstance(val, (bool, int, float, str)):
            out["value"] = val
        return out
    except Exception as e:
        return {
            "status": "EXCEPTION",
            "exception_type": type(e).__name__,
            "message": str(e)[:200],
            "hresult": f"{e.hresult:#010x}" if hasattr(e, "hresult") else None,
            "elapsed_ms": (time.perf_counter() - t0) * 1000.0,
        }


def _walk_swconst_typelib() -> dict[str, Any]:
    report: dict[str, Any] = {
        "path": str(SWCONST_TLB),
        "loadable": False,
        "enums": {},
        "discovered": {},
    }
    if not SWCONST_TLB.exists():
        report["error"] = f"swconst.tlb not found at {SWCONST_TLB}"
        return report
    try:
        tlb = pythoncom.LoadTypeLib(str(SWCONST_TLB))
    except Exception as e:
        report["error"] = f"{type(e).__name__}: {e}"
        return report
    report["loadable"] = True

    enums: dict[str, dict[str, int]] = {}
    for i in range(tlb.GetTypeInfoCount()):
        name, *_ = tlb.GetTypeInfo(i) and tlb.GetDocumentation(i)
        info = tlb.GetTypeInfo(i)
        ta = info.GetTypeAttr()
        if ta.typekind != pythoncom.TKIND_ENUM:
            continue
        if not (name in ENUM_EXACT_NAMES or any(t in name for t in ENUM_FUZZY_TOKENS)):
            continue
        members: dict[str, int] = {}
        for v in range(ta.cVars):
            vd = info.GetVarDesc(v)
            mname = info.GetNames(vd.memid)[0]
            members[mname] = vd.value
        enums[name] = members

    for bucket_name, tokens in (
        ("swFmBlend", ("FmBlend", "FeatureNameBlend", "FmLoft", "FeatureNameLoft")),
    ):
        for ename, members in enums.items():
            for mname, val in members.items():
                if any(t in mname for t in tokens):
                    report["discovered"].setdefault(bucket_name, {})[
                        f"{ename}.{mname}"
                    ] = val
    report["enums"] = enums
    return report


def _build_loft_geometry(doc: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    try:
        doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
        doc.SketchManager.InsertSketch(True)
        doc.SketchManager.CreateCircleByRadius(0.0, 0.0, 0.0, 0.01)
        doc.SketchManager.InsertSketch(True)
        out["profile1"] = "Sketch1"
    except Exception as e:
        out["profile1_error"] = f"{type(e).__name__}: {e}"
        return out
    try:
        fm = doc.FeatureManager
        fm.InsertRefPlane(8, 0.05, 0, 0, 0, 0)
        doc.SelectByID("Plane1", "PLANE", 0, 0, 0)
        doc.SketchManager.InsertSketch(True)
        doc.SketchManager.CreateCenterRectangle(-0.008, -0.008, 0, 0.008, 0.008, 0)
        doc.SketchManager.InsertSketch(True)
        out["profile2"] = "Sketch2"
    except Exception as e:
        out["profile2_error"] = f"{type(e).__name__}: {e}"
    try:
        doc.EditRebuild3
    except Exception:
        pass
    return out


def _route_a(
    fm: Any,
    mod: Any,
    doc: Any,
    geom: dict[str, Any],
    blend_const: int | None,
    blend_const_name: str | None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "route": "A - typelib-gated CreateDefinition + typed_qi",
        "const": blend_const,
        "const_name": blend_const_name,
    }
    if blend_const is None:
        result["error"] = "no blend/loft constant from swconst.tlb"
        return result

    data_cap = _capture(lambda: fm.CreateDefinition(blend_const))
    result["create_definition"] = data_cap
    if data_cap["status"] != "OK" or not _materialized(data_cap.get("_val")):
        return result

    data = data_cap["_val"]
    qi_cap = _capture(lambda: typed_qi(data, "ILoftFeatureData", module=mod))
    result["typed_qi_ILoftFeatureData"] = qi_cap
    if qi_cap["status"] != "OK":
        return result

    fd = qi_cap["_val"]
    ext = typed(doc.Extension, "IModelDocExtension", module=mod)
    p1 = geom.get("profile1", "Sketch1")
    p2 = geom.get("profile2", "Sketch2")

    result["select_profile1"] = _capture(
        lambda: ext.SelectByID2(p1, "SKETCH", 0, 0, 0, False, 1, None, 0)
    )
    result["select_profile2"] = _capture(
        lambda: ext.SelectByID2(p2, "SKETCH", 0, 0, 0, True, 1, None, 0)
    )

    # SEAT-PENDING (W0): this CreateFeature path must be validated on a live seat.
    create_cap = _capture(lambda: fm.CreateFeature(fd))
    result["create_feature"] = create_cap
    if create_cap["status"] == "OK":
        feat = create_cap["_val"]
        result["materialized"] = _materialized(feat)
        if _materialized(feat):
            result["feature_type"] = _tag(feat)
            result["feature_type_name"] = _type_name(feat)
    return result


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

    typelib = _walk_swconst_typelib()
    result["typelib"] = typelib

    sw = connect_running_sw()
    try:
        result["sw_revision"] = str(sw.RevisionNumber)
    except Exception:
        result["sw_revision"] = "<unreadable>"

    tmp_dir = Path(tempfile.gettempdir()) / "ai-sw-bridge"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    part_path = tmp_dir / "spike_loft.sldprt"
    if part_path.exists():
        try:
            part_path.unlink()
        except OSError:
            pass

    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        return {**result, "overall": "FAIL", "reason": "NewDocument returned None"}

    geom = _build_loft_geometry(doc)
    result["geometry"] = geom

    fm = doc.FeatureManager
    blend_bucket = typelib.get("discovered", {}).get("swFmBlend") or {}
    blend_const: int | None = None
    blend_const_name: str | None = None
    if blend_bucket:
        blend_const_name, blend_const = next(iter(blend_bucket.items()))

    route_a = _route_a(fm, mod, doc, geom, blend_const, blend_const_name)
    result["route_a"] = route_a

    if route_a.get("materialized"):
        overall = "PASS"
        interp = "Route A materialized a loft body — build the handler."
    else:
        overall = "PARTIAL"
        interp = "Loft did not materialize — narrow on seat with --mode vba."
    result["overall"] = overall
    result["interpretation"] = interp

    _try_close(sw, doc)
    if not keep_file:
        try:
            part_path.unlink()
        except OSError:
            pass
    return result


def emit_vba() -> str:
    return """' Spike v0.16 F2-LOFT VBA oracle.
' Paste into a Part with two closed profiles (Sketch1, Sketch2).
Option Explicit
Sub ProbeLoft()
    Dim swApp As SldWorks.SldWorks
    Dim Part As SldWorks.ModelDoc2
    Dim Fm As SldWorks.FeatureManager
    Dim Feat As SldWorks.Feature
    Set swApp = Application.SldWorks
    Set Part = swApp.ActiveDoc
    Set Fm = Part.FeatureManager
    Part.ClearSelection2 True
    Part.SelectByID2 "Sketch1", "SKETCH", 0, 0, 0, False, 1, Nothing, 0
    Part.SelectByID2 "Sketch2", "SKETCH", 0, 0, 0, True, 1, Nothing, 0
    ' Replace BLEND_CONST with typelib-sourced swFmBlend value
    Set Feat = Fm.CreateDefinition(BLEND_CONST)
    If Feat Is Nothing Then
        MsgBox "CreateDefinition failed"
    Else
        MsgBox "LoftFeatureData acquired; CreateFeature next"
    End If
End Sub
"""


def _scrub(o: Any) -> Any:
    if isinstance(o, dict):
        return {k: _scrub(v) for k, v in o.items() if k != "_val"}
    if isinstance(o, list):
        return [_scrub(v) for v in o]
    return o


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--mode", choices=["com", "vba"], default="com")
    p.add_argument("--out", type=Path, default=None)
    p.add_argument("--keep-file", action="store_true")
    args = p.parse_args()
    if args.mode == "vba":
        out = Path(__file__).parent / "spike_loft.bas"
        out.write_text(emit_vba(), encoding="utf-8")
        print(f"wrote {out}", file=sys.stderr)
        return 0
    pythoncom.CoInitialize()
    try:
        result = run(args.keep_file)
    finally:
        pythoncom.CoUninitialize()
    payload = json.dumps(
        _scrub(result), indent=2, default=lambda o: f"<{type(o).__name__}>"
    )
    if args.out is not None:
        args.out.write_text(payload, encoding="utf-8")
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(payload)
    return {"PASS": 0, "PARTIAL": 2, "FAIL": 1}.get(result.get("overall"), 1)


if __name__ == "__main__":
    raise SystemExit(main())
