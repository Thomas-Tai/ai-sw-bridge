"""W71 classification sweep — Scale / FillPattern / AdvancedHole (THROWAWAY).

Not a handler/schema/test author. Fires each unknown API against a fresh
fixture and classifies by the boundary law:

  return == Feature pointer AND |dVol| > 0  -> MATERIALIZE-CLASS (author a lane)
  return == None / error                    -> KERNEL/UI WALL (-> DEFERRED.md)

Fixture: 40x40x10 block + one Ø6 through-hole (the pattern seed + a planar top
face). Rebuilt fresh per probe so dVol is isolated.

Hypotheses:
  Scale        -> MATERIALIZE (closed-form matrix transform; InsertScale->Feature)
  FillPattern  -> WALL (kernel must solve boundary intersection + grid spacing)
  AdvancedHole -> WALL/complex (no InsertAdvancedHole; needs element-data arrays)

Writes spikes/v0_2x/_results/unknowns_probe.json.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

_PKG = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG))

RESULTS = Path(__file__).resolve().parents[2] / "spikes" / "v0_2x" / "_results" / "unknowns_probe.json"


def _build_fixture(path: str) -> bool:
    from ai_sw_bridge.spec.builder import build as part_build
    spec = {
        "schema_version": 1, "name": "W71_Unk",
        "features": [
            {"type": "sketch_rectangle_on_plane", "name": "SK_Base", "plane": "Front", "width": 40.0, "height": 40.0},
            {"type": "boss_extrude_blind", "name": "EX_Base", "sketch": "SK_Base", "depth": 10.0},
            {"type": "sketch_circle_on_face", "name": "SK_Seed", "of_feature": "EX_Base", "face": "+z", "diameter": 6.0, "center": {"u": 0.0, "v": 0.0}},
            {"type": "cut_extrude_through_all", "name": "CUT_Seed", "sketch": "SK_Seed"},
        ],
    }
    r = part_build(spec, no_dim=True, save_as=path)
    ok = getattr(r, "ok", None)
    if ok is None and isinstance(r, dict):
        ok = r.get("ok")
    return bool(ok) and os.path.isfile(path)


def _vol() -> float | None:
    from ai_sw_bridge.observe import sw_get_volume
    return sw_get_volume().get("volume_mm3")


def _ctx():
    from ai_sw_bridge.com.earlybind import typed, typed_qi
    from ai_sw_bridge.com.sw_type_info import wrapper_module
    from ai_sw_bridge.sw_com import get_active_doc, get_sw_app, resolve
    mod = wrapper_module()
    sw = get_sw_app()
    doc = get_active_doc(sw)
    fm = typed_qi(resolve(doc, "FeatureManager"), "IFeatureManager", module=mod)
    ext = resolve(doc, "Extension")
    return sw, doc, fm, ext, mod, typed, typed_qi, resolve


def _close(sw) -> None:
    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass


def _verdict(ret: Any, dvol: float | None, sel: int | None) -> str:
    is_none = ret is None
    has_dvol = dvol is not None and abs(dvol) > 1e-6
    if not is_none and has_dvol:
        return "MATERIALIZE"
    if is_none:
        return "WALL (ret=None)"
    return "INCONCLUSIVE"


def probe_scale() -> dict:
    p: dict[str, Any] = {"name": "scale", "api": "IFeatureManager.InsertScale(Type,Uniform,X,Y,Z)->Feature"}
    try:
        sw, doc, fm, ext, mod, typed, typed_qi, resolve = _ctx()
        v0 = _vol()
        # swScaleAbout_e: 0 = centroid. Uniform 1.5x.
        ret = fm.InsertScale(0, True, 1.5, 1.5, 1.5)
        v1 = _vol()
        dvol = (v1 - v0) if (v0 is not None and v1 is not None) else None
        p.update(ret_repr=repr(ret)[:60], ret_is_none=ret is None, vol_before=v0, vol_after=v1,
                 dvol=dvol, expected_ratio=3.375, verdict=_verdict(ret, dvol, None))
    except Exception as exc:
        p.update(error=f"{type(exc).__name__}: {str(exc)[:120]}", verdict="WALL (error)")
    finally:
        try:
            _close(_ctx()[0])
        except Exception:
            pass
    return p


def probe_fill() -> dict:
    p: dict[str, Any] = {"name": "fill_pattern", "api": "IFeatureManager.FeatureFillPattern(19 args)->Feature"}
    try:
        from pythoncom import VT_DISPATCH
        from win32com.client import VARIANT
        sw, doc, fm, ext, mod, typed, typed_qi, resolve = _ctx()
        null_callout = VARIANT(VT_DISPATCH, None)
        # boundary = top +z face (block z=0..10, center face at (0,0,0.010)); seed = CUT_Seed
        try:
            doc.ClearSelection2(True)
        except Exception:
            pass
        # face point MUST be off the centre Ø6 seed hole -> (15,15,10) mm
        ok_face = ext.SelectByID2("", "FACE", 0.015, 0.015, 0.010, False, 0, null_callout, 0)
        ok_seed = ext.SelectByID2("CUT_Seed", "BODYFEATURE", 0.0, 0.0, 0.0, True, 4, null_callout, 0)
        try:
            sel = doc.SelectionManager.GetSelectedObjectCount2(-1)
        except Exception:
            sel = None
        v0 = _vol()
        # PatternLayoutType=0, LayoutSpacingType=0, InstanceSpacing=8mm, Stagger=0,
        # Margins=0, LoopSpacing=0, NoOfInstances=4, PolygonSides=4, FeaturesToPattern=0,
        # CreateSeedCut=0, Diameter/Dim/Rot/Diag=0, SeedCutPolySides=4, Outer/Inner=0,
        # FlipShape=False, GeometryPattern=True
        ret = fm.FeatureFillPattern(0, 0, 0.008, 0.0, 0.0, 0.0, 4, 4, 0, 0,
                                    0.0, 0.0, 0.0, 0.0, 4, 0.0, 0.0, False, True)
        v1 = _vol()
        dvol = (v1 - v0) if (v0 is not None and v1 is not None) else None
        p.update(sel_face=bool(ok_face), sel_seed=bool(ok_seed), sel_count=sel,
                 ret_repr=repr(ret)[:60], ret_is_none=ret is None, vol_before=v0, vol_after=v1,
                 dvol=dvol, verdict=_verdict(ret, dvol, sel))
        if p.get("verdict", "").startswith("WALL") and (sel or 0) < 2:
            p["verdict"] = "INCONCLUSIVE (selection<2)"
    except Exception as exc:
        p.update(error=f"{type(exc).__name__}: {str(exc)[:120]}", verdict="WALL (error)")
    finally:
        try:
            _close(_ctx()[0])
        except Exception:
            pass
    return p


def probe_advanced_hole() -> dict:
    p: dict[str, Any] = {"name": "advanced_hole", "api": "IFeatureManager.AdvancedHole(near[],far[],...)->Feature"}
    try:
        from pythoncom import VT_DISPATCH
        from win32com.client import VARIANT
        sw, doc, fm, ext, mod, typed, typed_qi, resolve = _ctx()
        null_callout = VARIANT(VT_DISPATCH, None)
        # select a point on the top face for the hole location
        try:
            doc.ClearSelection2(True)
        except Exception:
            pass
        ok_face = ext.SelectByID2("", "FACE", 0.015, 0.015, 0.010, False, 0, null_callout, 0)
        # CreateAdvancedHoleElementData is on IModelDocExtension, NOT IFeatureManager.
        text = typed(ext, "IModelDocExtension", module=mod)
        elem = None
        elem_err = None
        try:
            elem = text.CreateAdvancedHoleElementData(0)  # ElmType 0
        except Exception as exc:
            elem_err = f"{type(exc).__name__}: {str(exc)[:90]}"
        v0 = _vol()
        ret = None
        call_err = None
        try:
            # bare list -> DISP_E_ARRAYISLOCKED ('Memory is locked'); the makepy
            # SAFEARRAY doctrine: wrap as VARIANT(VT_ARRAY|VT_DISPATCH, [...]).
            from pythoncom import VT_ARRAY
            near = VARIANT(VT_ARRAY | VT_DISPATCH, [elem]) if elem is not None else None
            # AdvancedHole(near, far, UseBaseline, IsCustomCallout, out Result)
            ret = fm.AdvancedHole(near, None, False, False)
        except Exception as exc:
            call_err = f"{type(exc).__name__}: {str(exc)[:120]}"
        # out-param: pywin32 returns (Feature, ResultArray); Feature = ret[0]
        feat = ret[0] if isinstance(ret, tuple) else ret
        v1 = _vol()
        dvol = (v1 - v0) if (v0 is not None and v1 is not None) else None
        if call_err is not None:
            verdict = "WALL (error)"
        elif feat is None:
            verdict = "WALL (ret=None)"
        else:
            verdict = _verdict(feat, dvol, None)
        p.update(sel_face=bool(ok_face), elem_created=elem is not None, elem_err=elem_err,
                 ret_repr=repr(ret)[:80], feat_is_none=feat is None, call_err=call_err,
                 vol_before=v0, vol_after=v1, dvol=dvol, verdict=verdict)
    except Exception as exc:
        p.update(error=f"{type(exc).__name__}: {str(exc)[:120]}", verdict="WALL (error)")
    finally:
        try:
            _close(_ctx()[0])
        except Exception:
            pass
    return p


def main() -> int:
    res: dict[str, Any] = {"spike": "unknowns_probe", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"), "probes": []}
    for builder, fn in (("scale", probe_scale), ("fill_pattern", probe_fill), ("advanced_hole", probe_advanced_hole)):
        with tempfile.TemporaryDirectory(prefix=f"w71_unk_{builder}_", ignore_cleanup_errors=True) as tmp:
            path = os.path.join(tmp, "W71_Unk.sldprt")
            if not _build_fixture(path):
                res["probes"].append({"name": builder, "verdict": "ERROR (fixture build failed)"})
                continue
            res["probes"].append(fn())
    res["summary"] = {p["name"]: p.get("verdict") for p in res["probes"]}
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    print("SUMMARY:", res["summary"], file=sys.stderr)
    print(json.dumps(res, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
