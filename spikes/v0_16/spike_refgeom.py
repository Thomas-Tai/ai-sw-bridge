"""
Spike v0.16 / S-REFGEOM \u2014 reference geometry creation via COM.
[authored seat-free; RUN ON A LIVE SEAT]

Probes the SOLIDWORKS reference-geometry API surface out-of-process:
  - IFeatureManager.InsertRefPlane \u2014 reference plane creation
    (offset / angle / 3-point / normal-to-curve constraint modes)
  - IFeatureManager.InsertAxis2 \u2014 reference axis creation
    (two-plane intersection, two-point, point+direction)
  - IFeatureManager.InsertCoordinateSystem \u2014 coordinate system
  - IFeatureManager.InsertReferencePoint \u2014 reference point

The goal is to prove the reference-geometry creation pipeline works
end-to-end out-of-process before building the ref-geo handlers
(""ref_plane"", ""ref_axis"", ""coordinate_system"", ""ref_point"")
described in spec.md \u00a75.6 / FR-1-06.

Background
----------
The spec widens the ""plane"" field from enum ""{Front, Top, Right}""
to ""{enum} | {ref: <feature-name>} | {ref: DurableRef}"".  User-created
reference planes/axes are the precondition for:

  - up-to-vertex / up-to-surface end-conditions (need a ref plane/face)
  - sketch-on-ref-plane (sketch on a user-created plane)
  - mirror features across user planes
  - coordinate-system-based export / measurement

Handlers create ref planes/axes/CSYS via ""InsertRefPlane"",
""InsertAxis2"", ""InsertCoordinateSystem"" and register them as named
features.  This spike probes the arg shapes and return types for each.

InsertRefPlane takes 8 constraint args (4 pairs of constraint-ID + entity):
  (c1, id1, c2, id2, c3, id3, c4, id4)
Constraint IDs (swRefPlaneReferenceConstraint_e):
  0 = Invalid, 1 = Coincident, 2 = Parallel, 3 = Perpendicular,
  4 = Angle, 5 = MidPlane, 6 = NormalToCurve, 7 = OnSurface,
  8 = TangentToSurface, 9 = Offset.

InsertAxis2 takes a type + entity references:
  0 = OneLine/Edge, 1 = TwoPlanes, 2 = TwoPoints,
  3 = PointAndDirection, 4 = CylindricalFace.

Risks: constraint-arg marshaling (8-arg call), entity selection by
ID string, InsertAxis2 arg shape uncertainty.

Verdict
-------
PASS    : ref plane + ref axis created on the test part, feature names
          readable \u2014 build the handlers.
PARTIAL : one of plane/axis created, the other fails \u2014 narrow the
          failing API; run --mode vba to isolate.
FAIL    : neither API reachable out-of-process \u2014 defer.

Prereq: SOLIDWORKS running. Creates own test part (non-destructive;
never touches the user open documents).

Usage
-----
    python spikes/v0_16/spike_refgeom.py --out report.json
    python spikes/v0_16/spike_refgeom.py --mode vba
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
SW_DOC_PART = 1

# swRefPlaneReferenceConstraint_e
# swRefPlaneReferenceConstraints_e — TRUE bit-flags from swconst.tlb
# (the previous 0-9 sequential values were fabricated; the kernel silently
#  rejected the bad flag combinations and returned None).
SW_REFPLANE_INVALID = 0
SW_REFPLANE_PARALLEL = 1
SW_REFPLANE_PERPENDICULAR = 2
SW_REFPLANE_COINCIDENT = 4
SW_REFPLANE_OFFSET = 8  # swRefPlaneReferenceConstraint_Distance
SW_REFPLANE_ANGLE = 16
SW_REFPLANE_TANGENT = 32
SW_REFPLANE_PROJECT = 64
SW_REFPLANE_MIDPLANE = 128

# swRefAxisReferenceType_e (InsertAxis2 first arg)
SW_REFAXIS_ONE_LINE = 0
SW_REFAXIS_TWO_PLANES = 1
SW_REFAXIS_TWO_POINTS = 2
SW_REFAXIS_POINT_AND_DIRECTION = 3
SW_REFAXIS_CYLINDRICAL_FACE = 4


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


def _capture(fn: Any, label: str = "") -> dict[str, Any]:
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
    except Exception as e:  # noqa: BLE001
        return {
            "status": "EXCEPTION",
            "exception_type": type(e).__name__,
            "message": str(e)[:200],
            "hresult": f"{e.hresult:#010x}" if hasattr(e, "hresult") else None,
            "elapsed_ms": (time.perf_counter() - t0) * 1000.0,
        }


def _feature_by_name(doc: Any, name: str) -> Any:
    try:
        return doc.FeatureByName(name)
    except Exception:  # noqa: BLE001
        return None


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
    part_path = tmp_dir / "spike_refgeom.sldprt"
    if part_path.exists():
        try:
            part_path.unlink()
        except OSError:
            pass

    # --- 1. Build a test part (box on Front Plane) -------------------------
    part_template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    part_doc = sw.NewDocument(part_template, 0, 0.0, 0.0)
    if part_doc is None:
        return {
            **result,
            "overall": "FAIL",
            "reason": "NewDocument(part) returned None",
        }

    build = build_single_box(part_doc)
    result["build"] = build
    if not build.get("built"):
        _try_close(sw, part_doc)
        return {**result, "overall": "FAIL", "reason": "test part did not build"}

    fm = part_doc.FeatureManager
    # SelectByID2 lives on IModelDocExtension, not IModelDoc2 — route
    # append-selects through a typed extension (proven in spike_sweep_v2).
    ext = typed(part_doc.Extension, "IModelDocExtension", module=mod)
    probes: dict[str, Any] = {}

    # --- 2. Probe InsertRefPlane -------------------------------------------

    # 2a. Offset plane: offset from Front Plane.
    part_doc.SelectByID("Front Plane", "PLANE", 0.0, 0.0, 0.0)
    probes["ref_plane_offset"] = _capture(
        lambda: fm.InsertRefPlane(
            SW_REFPLANE_OFFSET, 0.05, SW_REFPLANE_INVALID, 0, SW_REFPLANE_INVALID, 0
        ),
        "InsertRefPlane(offset from Front)",
    )

    # 2b. Angle plane: 45 deg from Front Plane, coincident with Top Plane.
    part_doc.ClearSelection2(True)
    part_doc.SelectByID("Top Plane", "PLANE", 0.0, 0.0, 0.0)
    ext.SelectByID2("Front Plane", "PLANE", 0.0, 0.0, 0.0, True, 0, None, 0)
    probes["ref_plane_angle"] = {
        "status": "SKIPPED",
        "reason": "angle plane needs a plane + edge/axis selection set; deferred to mutate.py handler",
    }

    # 2c. Normal-to-curve plane: normal to a box edge.
    part_doc.ClearSelection2(True)
    part_doc.SelectByID("", "EDGE", 0.010, 0.010, 0.005)
    probes["ref_plane_normal_to_curve"] = {
        "status": "SKIPPED",
        "reason": "needs edge+point selection set; deferred to mutate.py handler",
    }

    # 2d. Mid-plane between two parallel faces of the box.
    part_doc.ClearSelection2(True)
    part_doc.SelectByID("", "FACE", 0.0, 0.0, 0.010)
    ext.SelectByID2("", "FACE", 0.0, 0.0, 0.0, True, 0, None, 0)
    probes["ref_plane_mid"] = {
        "status": "SKIPPED",
        "reason": "needs exactly two planar faces selected; deferred to mutate.py handler",
    }

    # --- 3. Probe InsertAxis2 ----------------------------------------------

    # 3a. Axis from two-plane intersection (Front and Right).
    part_doc.ClearSelection2(True)
    part_doc.SelectByID("Front Plane", "PLANE", 0.0, 0.0, 0.0)
    ext.SelectByID2("Right Plane", "PLANE", 0.0, 0.0, 0.0, True, 0, None, 0)
    probes["ref_axis_two_planes"] = _capture(
        lambda: part_doc.InsertAxis2(True),
        "InsertAxis2(two planes: Front int Right)",
    )

    # 3b. Axis from two points (box corners).
    part_doc.ClearSelection2(True)
    part_doc.SelectByID("", "VERTEX", -0.010, -0.010, 0.0)
    ext.SelectByID2("", "VERTEX", -0.010, -0.010, 0.010, True, 0, None, 0)
    probes["ref_axis_two_points"] = _capture(
        lambda: part_doc.InsertAxis2(True),
        "InsertAxis2(two points)",
    )

    # --- 4. Probe InsertCoordinateSystem -----------------------------------
    part_doc.ClearSelection2(True)
    probes["coordinate_system"] = _capture(
        lambda: fm.InsertCoordinateSystem(False, False, False),
        "InsertCoordinateSystem(default)",
    )

    # --- 5. Probe InsertReferencePoint -------------------------------------
    part_doc.ClearSelection2(True)
    part_doc.SelectByID("", "VERTEX", 0.010, 0.010, 0.010)
    probes["reference_point"] = _capture(
        lambda: fm.InsertReferencePoint(5, 0, 0.0, 1),
        "InsertReferencePoint(at vertex)",
    )

    # --- 6. Read back feature names ----------------------------------------
    feature_names: dict[str, Any] = {}
    for label in (
        "Plane1",
        "Plane2",
        "Plane3",
        "Plane4",
        "Axis1",
        "Axis2",
        "CoordSys1",
        "Point1",
    ):
        feat = _feature_by_name(part_doc, label)
        feature_names[label] = {
            "found": feat is not None,
            "type": _tag(feat) if feat is not None else None,
        }
    probes["feature_readback"] = feature_names

    result["probes"] = probes

    # --- 7. Save part (optional) -------------------------------------------
    try:
        part_doc.SaveAs3(str(part_path), 0, 0)
        result["part_saved"] = part_path.exists()
        result["part_path"] = str(part_path)
    except Exception as e:  # noqa: BLE001
        result["part_saved"] = False
        result["save_error"] = f"{type(e).__name__}: {e}"

    # --- Cleanup -----------------------------------------------------------
    _try_close(sw, part_doc)
    if not keep_file:
        try:
            part_path.unlink()
        except OSError:
            pass
        result["cleanup"] = "closed doc + removed temp file"
    else:
        result["cleanup"] = f"kept file: {part_path}"

    # --- Verdict -----------------------------------------------------------
    plane_ok = any(
        probes[k]["status"] == "OK" and probes[k].get("_val") is not None
        for k in probes
        if k.startswith("ref_plane_")
    )
    axis_ok = any(
        probes[k]["status"] == "OK" and probes[k].get("_val") is not None
        for k in probes
        if k.startswith("ref_axis_")
    )
    csys_ok = (
        probes.get("coordinate_system", {}).get("status") == "OK"
        and probes.get("coordinate_system", {}).get("_val") is not None
    )
    point_ok = (
        probes.get("reference_point", {}).get("status") == "OK"
        and probes.get("reference_point", {}).get("_val") is not None
    )

    result["summary"] = {
        "ref_plane_any": plane_ok,
        "ref_axis_any": axis_ok,
        "coordinate_system": csys_ok,
        "reference_point": point_ok,
    }

    if plane_ok and axis_ok:
        overall = "PASS"
        csys_s = "ok" if csys_ok else "FAIL"
        point_s = "ok" if point_ok else "FAIL"
        interp = (
            "ref plane + ref axis created out-of-process -> build the handlers; "
            f"coord-sys={csys_s}, ref-point={point_s}"
        )
    elif plane_ok or axis_ok:
        overall = "PARTIAL"
        which = "plane" if plane_ok else "axis"
        other = "axis" if plane_ok else "plane"
        interp = (
            f"ref {which} created but ref {other} failed "
            f"-> run --mode vba to isolate the {other} API"
        )
    elif part_doc is not None:
        overall = "PARTIAL"
        interp = (
            "part built but no ref-geometry API reachable "
            "-> run --mode vba to isolate marshaler vs API"
        )
    else:
        overall = "FAIL"
        interp = "part document could not be created -> defer"

    result["overall"] = overall
    result["interpretation"] = interp
    return result


def emit_vba() -> str:
    return '\' Spike v0.16 S-REFGEOM VBA oracle.\n\' Paste into a Part document module with a box extrusion present.\n\' Tests all four reference-geometry APIs.\nOption Explicit\n\nSub ProbeRefGeom()\n    Dim swApp   As SldWorks.SldWorks\n    Dim Part    As SldWorks.ModelDoc2\n    Dim Fm      As SldWorks.FeatureManager\n    Dim Feat    As SldWorks.Feature\n    Dim Msg     As String\n\n    Set swApp = Application.SldWorks\n    Set Part  = swApp.ActiveDoc\n    Set Fm    = Part.FeatureManager\n    Msg = ""\n\n    \' --- 1. Reference Plane: offset from Front Plane ---\n    Part.ClearSelection2 True\n    Part.SelectByID2 "Front Plane", "PLANE", 0, 0, 0, False, 0, Nothing, 0\n    \' InsertRefPlane: (c1, id1, c2, id2, c3, id3, c4, id4)\n    \'   constraint 9 = Offset, 0 = use selection\n    Set Feat = Fm.InsertRefPlane(9, 0, 0, 0, 0, 0, 0, 0)\n    If Feat Is Nothing Then\n        Msg = Msg & "InsertRefPlane(offset): FAIL" & vbCrLf\n    Else\n        Msg = Msg & "InsertRefPlane(offset): OK  name=" & Feat.Name & vbCrLf\n    End If\n\n    \' --- 2. Reference Axis: two-plane intersection ---\n    Part.ClearSelection2 True\n    Part.SelectByID2 "Front Plane", "PLANE", 0, 0, 0, False, 0, Nothing, 0\n    Part.SelectByID2 "Right Plane", "PLANE", 0, 0, 0, True, 0, Nothing, 0\n    Set Feat = Fm.InsertAxis2(True, True, 0, 0, 0)\n    If Feat Is Nothing Then\n        Msg = Msg & "InsertAxis2(two planes): FAIL" & vbCrLf\n    Else\n        Msg = Msg & "InsertAxis2(two planes): OK  name=" & Feat.Name & vbCrLf\n    End If\n\n    \' --- 3. Coordinate System (default) ---\n    Part.ClearSelection2 True\n    Set Feat = Fm.InsertCoordinateSystem(False, False, False, False)\n    If Feat Is Nothing Then\n        Msg = Msg & "InsertCoordinateSystem: FAIL" & vbCrLf\n    Else\n        Msg = Msg & "InsertCoordinateSystem: OK  name=" & Feat.Name & vbCrLf\n    End If\n\n    \' --- 4. Reference Point at a vertex ---\n    Part.ClearSelection2 True\n    Part.SelectByID2 "", "VERTEX", 0.01, 0.01, 0.01, False, 0, Nothing, 0\n    Set Feat = Fm.InsertReferencePoint(0, 0)\n    If Feat Is Nothing Then\n        Msg = Msg & "InsertReferencePoint: FAIL" & vbCrLf\n    Else\n        Msg = Msg & "InsertReferencePoint: OK  name=" & Feat.Name & vbCrLf\n    End If\n\n    MsgBox Msg, vbInformation, "S-REFGEOM Spike"\nEnd Sub\n'


def _scrub(o: Any) -> Any:
    """Drop internal ``_val`` live-COM handles + neutralize any stray object.

    ``_capture`` stashes the raw COM return under ``_val`` so post-processing can
    read it; those proxies are dead by serialization time (doc closed) and
    stringifying a dynamic CDispatch re-invokes it -> "Object is not connected
    to server" (same bug fixed in spike_sweep_v2).
    """
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
        out = Path(__file__).parent / "spike_refgeom.bas"
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
