"""Seat-proof / geometry probe — full-round fillet (LIVE seat).

The W68 ``fillet_full_round`` path binds all three face-sets (GetFaceCount
1/1/1 via the VARIANT-array SetFaces) but ``CreateFeature`` ghosted on the
prior square-SLAB fixture.  This probe gives it one CLEAN shot on a canonical
full-round candidate, selecting the three faces LIVE-BY-COORDINATE (no manifest
round-trip) to isolate kernel behaviour from ref resolution:

  Box 40x20x10 mm (x:-20..20, y:-10..10, z:0..10).  Full-round the TOP:
    side1  = +y face (y=+10)      WhichFaceList 3
    center = top face (z=+10)     WhichFaceList 4
    side2  = -y face (y=-10)      WhichFaceList 5
  -> the 20mm-wide top rounds into a half-cylinder tangent to both sides.

Pipeline: CreateDefinition(swFmFillet=1) -> typed_qi ISimpleFilletFeatureData2
-> Initialize(swFullRoundFillet=3) -> SetFaces(which, VARIANT[face]) x3 with a
GetFaceCount==1 readback guard -> CreateFeature.

Witness: feature materialized AND |ΔVol| > eps (full-round removes material).
  GO     -> full-round materializes OOP; un-defer the handler.
  GHOST  -> binds (1/1/1) but CreateFeature no-ops -> WALL-class confirmed
            (kernel tangent-solve refused OOP, corroborating the boundary law).

Usage::
    C:/Python314/python.exe spikes/v0_2x/spike_fillet_fullround_probe.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

_SRC = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_SRC))

import pythoncom  # noqa: E402
from win32com.client import VARIANT  # noqa: E402

from ai_sw_bridge.com.earlybind import typed_qi  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from ai_sw_bridge.sw_com import get_sw_app  # noqa: E402
from ai_sw_bridge.features import verify  # noqa: E402

RESULTS_PATH = Path(__file__).resolve().parents[2] / "spikes" / "v0_2x" / "_results" / "fillet_fullround_probe.json"

SW_DEFAULT_TEMPLATE_PART = 8
_SW_FM_FILLET = 1
_SW_FULL_ROUND_FILLET = 3
_FULL_ROUND_WHICH = (3, 4, 5)  # side1 / center / side2
_MEMBER_NOT_FOUND = -2147352573

# Box 40x20x10 mm
_HW_X = 0.020  # x half-width -> x in [-0.020, 0.020]
_HW_Y = 0.010  # y half-width -> y in [-0.010, 0.010]
_H_Z = 0.010   # z height


def _null():
    return VARIANT(pythoncom.VT_DISPATCH, None)


def _face_safearray(face: Any) -> Any:
    return VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, [face])


def _title(d: Any) -> Any:
    t = d.GetTitle
    return t() if callable(t) else t


def _build_box(sw: Any) -> Any:
    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        return None
    doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
    sk = doc.SketchManager
    sk.InsertSketch(True)
    sk.CreateCornerRectangle(-_HW_X, -_HW_Y, 0.0, _HW_X, _HW_Y, 0.0)
    sk.InsertSketch(True)
    doc.FeatureManager.FeatureExtrusion3(
        True, False, False, 0, 0, _H_Z, 0.0,
        False, False, False, False, 0.0, 0.0,
        False, False, False, False, True, True, True, 0, 0, False,
    )
    try:
        doc.EditRebuild3()
    except Exception:
        pass
    return doc


def _face_at(doc: Any, x: float, y: float, z: float) -> Any:
    doc.ClearSelection2(True)
    if not doc.Extension.SelectByID2("", "FACE", x, y, z, False, 0, _null(), 0):
        return None
    face = doc.SelectionManager.GetSelectedObject6(1, -1)
    doc.ClearSelection2(True)
    return face


def run() -> dict[str, Any]:
    result: dict[str, Any] = {"spike": "fillet_fullround_probe", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")}
    sw = get_sw_app()
    try:
        result["sw_revision"] = str(sw.RevisionNumber)
    except Exception:
        result["sw_revision"] = "<unreadable>"

    doc = _build_box(sw)
    if doc is None:
        result["overall"] = "ERROR"
        result["reason"] = "box build failed"
        return result
    try:
        side1 = _face_at(doc, 0.0, _HW_Y, _H_Z / 2)   # +y face
        center = _face_at(doc, 0.0, 0.0, _H_Z)         # top face
        side2 = _face_at(doc, 0.0, -_HW_Y, _H_Z / 2)   # -y face
        result["faces_selected"] = {
            "side1": side1 is not None, "center": center is not None, "side2": side2 is not None,
        }
        if None in (side1, center, side2):
            result["overall"] = "ERROR"
            result["reason"] = "could not select all three faces"
            return result

        f0, v0 = verify.solid_metrics(doc)
        result["before"] = {"faces": f0, "vol": v0}

        fm = doc.FeatureManager
        data = fm.CreateDefinition(_SW_FM_FILLET)
        if data is None:
            result["overall"] = "ERROR"
            result["reason"] = "CreateDefinition(swFmFillet) returned None"
            return result
        fd = typed_qi(data, "ISimpleFilletFeatureData2", module=wrapper_module())
        fd.Initialize(_SW_FULL_ROUND_FILLET)

        binds = {}
        for face, which in zip((side1, center, side2), _FULL_ROUND_WHICH):
            fd.SetFaces(which, _face_safearray(face))
            binds[which] = fd.GetFaceCount(which)
        result["face_counts"] = binds  # expect {3:1, 4:1, 5:1}
        if any(c != 1 for c in binds.values()):
            result["overall"] = "FAIL"
            result["reason"] = f"face-set binding failed: {binds}"
            return result

        try:
            feat = fm.CreateFeature(fd)
            result["create_feature_return"] = repr(feat)[:80]
        except Exception as exc:
            hr = getattr(exc, "args", [None])[0] if hasattr(exc, "args") else None
            result["create_feature_exc"] = f"{type(exc).__name__}: {str(exc)[:120]}"
            if hr != _MEMBER_NOT_FOUND:
                feat = None
            else:
                feat = "membernotfound_but_built"

        try:
            doc.EditRebuild3()
        except Exception:
            pass
        f1, v1 = verify.solid_metrics(doc)
        result["after"] = {"faces": f1, "vol": v1}
        d_vol = v1 - v0
        d_faces = f1 - f0
        result["delta"] = {"faces": d_faces, "vol": d_vol}
        materialized = abs(d_vol) > verify.VOL_EPS_MM3
        result["overall"] = "PASS" if materialized else "GHOST"
        result["finding"] = (
            f"full_round: bind={binds}, Δvol={d_vol:.4f}, Δfaces={d_faces}, "
            f"{'MATERIALIZED' if materialized else 'GHOST (binds 1/1/1 but CreateFeature no-op -> WALL-class)'}"
        )
        return result
    finally:
        try:
            sw.CloseDoc(_title(doc))
        except Exception:
            pass


def main() -> int:
    pythoncom.CoInitialize()
    try:
        result = run()
    finally:
        pythoncom.CoUninitialize()
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(result.get("overall", "ERROR"), file=sys.stderr)
    print(result.get("finding", result.get("reason", "")), file=sys.stderr)
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("overall") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
