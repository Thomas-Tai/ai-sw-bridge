"""Spike v0.21 / W53 — 3D-sketch seat de-risk (Phase-5 prerequisite).

Probes the live SOLIDWORKS COM path for 3D sketches:

  S1  ISketchManager.Insert3DSketch — FUNCDESC arity + late-bound call shape
  S2  3D-sketch polyline materialization (non-planar: Z extent > 0)
  S3  Save → close → reopen round-trip (3D sketch survives persistence)
  S4  (Stretch) Swept boss referencing the 3D path as a sweep path

The GREEN gate is the EFFECT, not "no error": a 3D sketch with a non-planar
polyline must materialize (its points span all three axes — assert a non-zero
Z extent), and it must survive save→reopen.

If 3D-sketch mode hits a COM wall, characterize it precisely (FUNCDESC +
the exact failure) and fail-closed — do not fake a pass.

Prereq: SOLIDWORKS 2024 SP1 running with an open session.
Usage:  <main-venv>\\python spikes\\v0_21\\spike_sketch_3d.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import traceback
import winreg
from pathlib import Path
from typing import Any, Callable

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
_V15 = Path(__file__).resolve().parents[1] / "v0_15"
sys.path.insert(0, str(_PKG_ROOT))
sys.path.insert(0, str(_V15))

import pythoncom  # noqa: E402
import win32com.client  # noqa: E402
from win32com.client import dynamic, gencache  # noqa: E402

from spike_earlybind_persist import (  # noqa: E402
    SW_LIBID,
    connect_running_sw,
    ensure_sw_module,
    typed,
)

SW_DEFAULT_TEMPLATE_PART = 8

# Non-planar polyline: 4 points spanning all 3 axes (metres for COM).
# (0,0,0) → (0.1,0,0) → (0.1,0.05,0.03) → (0,0.05,0.06)
_3D_POINTS_M: list[tuple[float, float, float]] = [
    (0.0, 0.0, 0.0),
    (0.1, 0.0, 0.0),
    (0.1, 0.05, 0.03),
    (0.0, 0.05, 0.06),
]


def _title(doc: Any) -> Any:
    t = doc.GetTitle
    return t() if callable(t) else t


def _seg_count(doc: Any) -> int:
    """Count segments in the active sketch (0 if none)."""
    sk = doc.GetActiveSketch2
    if sk is None:
        return 0
    try:
        segs = sk.GetSketchSegments
        segs = segs() if callable(segs) else segs
    except Exception:  # noqa: BLE001
        return 0
    if segs is None:
        return 0
    try:
        return len(segs)
    except TypeError:
        return 1


def _seg_z_extent(doc: Any) -> float:
    """Max |Z| across all segment start/end points in the active sketch."""
    sk = doc.GetActiveSketch2
    if sk is None:
        return 0.0
    try:
        segs = sk.GetSketchSegments
        segs = segs() if callable(segs) else segs
    except Exception:  # noqa: BLE001
        return 0.0
    if segs is None:
        return 0.0
    if not hasattr(segs, "__iter__"):
        segs = [segs]
    z_vals: list[float] = []
    for seg in segs:
        try:
            sp = seg.GetStartPoint
            sp = sp() if callable(sp) else sp
            ep = seg.GetEndPoint
            ep = ep() if callable(ep) else ep
            if sp is not None and len(sp) >= 3:
                z_vals.append(abs(float(sp[2])))
            if ep is not None and len(ep) >= 3:
                z_vals.append(abs(float(ep[2])))
        except Exception:  # noqa: BLE001
            continue
    return max(z_vals) if z_vals else 0.0


# ---------------------------------------------------------------------------
# S1: Typelib FUNCDESC introspection for Insert3DSketch
# ---------------------------------------------------------------------------


def _probe_insert3d_sketch_funcdesc() -> dict[str, Any]:
    """Walk the SW typelib for ISketchManager and dump the FUNCDESC for
    Insert3DSketch.  Characterizes the arity and calling convention without
    guessing."""
    rec: dict[str, Any] = {"step": "S1_funcdesc"}
    try:
        mod, info = ensure_sw_module()
        rec["module_info"] = info
        iface_cls = getattr(mod, "ISketchManager", None)
        if iface_cls is None:
            rec["status"] = "FAIL"
            rec["reason"] = "ISketchManager not found in typelib module"
            return rec
        # Walk the typeinfo for ISketchManager
        ti = iface_cls._typelib_.GetTypeInfo(
            iface_cls._typelib_.FindName("ISketchManager")[0]
        )
        ta = ti.GetTypeAttr()
        found: list[dict[str, Any]] = []
        for i in range(ta[6]):  # cFuncs
            fd = ti.GetFuncDesc(i)
            names = ti.GetNames(fd[0], fd[6] + 1)  # memid, cParams+1
            if names and "Insert3DSketch" in names:
                found.append({
                    "name": names[0],
                    "dispid": fd[0],
                    "invoke_kind": fd[3],  # INVOKE_FUNC / INVOKE_PROPERTYGET / etc
                    "cParams": fd[6],
                    "paramTypes": [str(p) for p in (fd[7] if fd[7] else [])],
                })
        if found:
            rec["status"] = "FOUND"
            rec["funcdescs"] = found
        else:
            rec["status"] = "NOT_FOUND"
            rec["reason"] = (
                "Insert3DSketch not in ISketchManager FUNCDESC map. "
                "Possible rename or absence in this SW version."
            )
    except Exception as e:  # noqa: BLE001
        rec["status"] = "ERROR"
        rec["error"] = repr(e)
    return rec


# ---------------------------------------------------------------------------
# S2: 3D-sketch polyline materialization
# ---------------------------------------------------------------------------


def _probe_3d_sketch_materialize(sw: Any) -> dict[str, Any]:
    """Open a fresh Part, enter 3D-sketch mode, draw a non-planar polyline,
    verify segments materialize with non-zero Z extent."""
    rec: dict[str, Any] = {"step": "S2_materialize"}
    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        rec["status"] = "FAIL"
        rec["reason"] = "NewDocument returned None"
        return rec
    title = _title(doc)
    try:
        sm = doc.SketchManager

        # --- Insert3DSketch(True) — BOOL UpdateEditRebuild (seat-confirmed
        #     arity; the parameterless form raises 'Parameter not optional') ---
        rec["call"] = "Insert3DSketch(True)"
        try:
            sm.Insert3DSketch(True)
        except Exception as e_call:  # noqa: BLE001
            rec["status"] = "WALL"
            rec["error"] = repr(e_call)
            rec["fail_closed"] = True
            return rec

        # Verify we are in 3D-sketch mode
        sk = doc.GetActiveSketch2
        if sk is None:
            rec["status"] = "FAIL"
            rec["reason"] = "no active sketch after Insert3DSketch()"
            return rec
        rec["sketch_type"] = type(sk).__name__
        try:
            is_3d = sk.Is3DSketch
            is_3d = is_3d() if callable(is_3d) else is_3d
            rec["is_3d_sketch"] = bool(is_3d)
        except Exception:  # noqa: BLE001
            rec["is_3d_sketch"] = "<unreadable>"

        before = _seg_count(doc)
        rec["seg_before"] = before

        # Draw the non-planar polyline
        segments_created: list[dict[str, Any]] = []
        for i in range(len(_3D_POINTS_M) - 1):
            a, b = _3D_POINTS_M[i], _3D_POINTS_M[i + 1]
            try:
                seg = sm.CreateLine(a[0], a[1], a[2], b[0], b[1], b[2])
                segments_created.append({
                    "idx": i, "result_type": type(seg).__name__,
                    "is_none": seg is None,
                })
            except Exception as e_seg:  # noqa: BLE001
                segments_created.append({
                    "idx": i, "error": repr(e_seg),
                })
        rec["segments_created"] = segments_created

        after = _seg_count(doc)
        rec["seg_after"] = after
        rec["seg_delta"] = after - before
        rec["materialized"] = (after - before) > 0

        z_extent = _seg_z_extent(doc)
        rec["z_extent_m"] = z_extent
        rec["z_extent_nonzero"] = z_extent > 1e-9

        # Close the 3D sketch
        try:
            sm.Insert3DSketch(True)
        except Exception as e_close:  # noqa: BLE001
            rec["close_error"] = repr(e_close)

        # Verify the sketch feature exists
        sketch_feat = doc.FeatureByPositionReverse(0)
        if sketch_feat is not None:
            feat_name = sketch_feat.Name
            feat_name = feat_name() if callable(feat_name) else feat_name
            rec["sketch_feature_name"] = str(feat_name)
            sketch_feat.Name = "Sketch3D_Spike"
            rec["renamed_to"] = "Sketch3D_Spike"
        else:
            rec["sketch_feature_name"] = None

        # Determine overall status
        if rec["materialized"] and rec.get("z_extent_nonzero"):
            rec["status"] = "GREEN"
        elif rec["materialized"]:
            rec["status"] = "PARTIAL"
            rec["reason"] = "segments materialized but Z extent is zero (planar)"
        else:
            rec["status"] = "FAIL"
            rec["reason"] = "no segments materialized"
    finally:
        try:
            sw.CloseDoc(title)
        except Exception:  # noqa: BLE001
            pass
    return rec


# ---------------------------------------------------------------------------
# S3: Save → close → reopen round-trip
# ---------------------------------------------------------------------------


def _probe_save_reopen(sw: Any) -> dict[str, Any]:
    """Build a 3D sketch, save, close, reopen — verify the 3D sketch survives."""
    rec: dict[str, Any] = {"step": "S3_save_reopen"}
    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        rec["status"] = "FAIL"
        rec["reason"] = "NewDocument returned None"
        return rec
    title = _title(doc)
    save_path = os.path.join(
        tempfile.gettempdir(), f"spike_sketch3d_{int(time.time())}.SLDPRT"
    )
    try:
        sm = doc.SketchManager
        try:
            sm.Insert3DSketch(True)
        except Exception as e_open:  # noqa: BLE001
            rec["status"] = "WALL"
            rec["error"] = repr(e_open)
            rec["fail_closed"] = True
            return rec

        for i in range(len(_3D_POINTS_M) - 1):
            a, b = _3D_POINTS_M[i], _3D_POINTS_M[i + 1]
            sm.CreateLine(a[0], a[1], a[2], b[0], b[1], b[2])

        sm.Insert3DSketch(True)  # close

        sketch_feat = doc.FeatureByPositionReverse(0)
        if sketch_feat is not None:
            sketch_feat.Name = "Sketch3D_Persist"

        # Save
        try:
            saved = doc.SaveAs3(save_path, 0, 0)
            rec["save_result"] = str(saved) if saved is not None else "None"
        except Exception as e_save:  # noqa: BLE001
            rec["save_error"] = repr(e_save)
            rec["status"] = "FAIL"
            rec["reason"] = "save failed"
            return rec

        rec["save_path"] = save_path
        rec["file_exists"] = os.path.isfile(save_path)
        if not rec["file_exists"]:
            rec["status"] = "FAIL"
            rec["reason"] = "save appeared to succeed but file not on disk"
            return rec

        # Close
        sw.CloseDoc(title)

        # Reopen — use typed ISldWorks (proven pattern; late-bound OpenDoc6
        # with VARIANT byref raises 'Parameter not optional' on this seat).
        mod, _mod_info = ensure_sw_module()
        tsw = typed(mod, "ISldWorks", sw)
        try:
            _ret = tsw.OpenDoc6(save_path, 1, 1, "", 0, 0)
            # typed OpenDoc6 marshals the doc plus [out] params as a tuple;
            # the IModelDoc2 handle is the first element.
            reopen_doc = _ret[0] if isinstance(_ret, tuple) else _ret
        except Exception as e_reopen:  # noqa: BLE001
            rec["status"] = "FAIL"
            rec["reopen_error"] = repr(e_reopen)
            rec["reopen_traceback"] = traceback.format_exc()
            return rec

        if reopen_doc is None:
            rec["status"] = "FAIL"
            rec["reason"] = "OpenDoc6 returned None"
            return rec

        # Verify the 3D sketch survived — use FeatureByPositionReverse
        # (proven; GetFeatureByPosition iteration was part of the failing path).
        found_3d = False
        idx = 0
        while True:
            f = reopen_doc.FeatureByPositionReverse(idx)
            if f is None:
                break
            try:
                fn = f.Name
                fn = fn() if callable(fn) else fn
                if str(fn) == "Sketch3D_Persist":
                    found_3d = True
                    rec["found_sketch_name"] = str(fn)
                    ft = f.GetTypeName2
                    ft = ft() if callable(ft) else ft
                    rec["found_sketch_type"] = str(ft)
                    break
            except Exception:  # noqa: BLE001
                pass
            idx += 1

        rec["sketch_survived"] = found_3d
        if found_3d:
            rec["status"] = "GREEN"
        else:
            rec["status"] = "FAIL"
            rec["reason"] = "3D sketch 'Sketch3D_Persist' not found after reopen"

        # Clean up reopened doc
        reopen_title = _title(reopen_doc)
        try:
            sw.CloseDoc(reopen_title)
        except Exception:  # noqa: BLE001
            pass
    except Exception as e:  # noqa: BLE001
        rec["status"] = "ERROR"
        rec["error"] = repr(e)
        rec["traceback"] = traceback.format_exc()
    finally:
        # Clean up the temp file
        try:
            if os.path.isfile(save_path):
                os.unlink(save_path)
        except Exception:  # noqa: BLE001
            pass
    return rec


# ---------------------------------------------------------------------------
# S4 (Stretch): Swept boss referencing the 3D path
# ---------------------------------------------------------------------------


def _probe_sweep_on_3d_path(sw: Any) -> dict[str, Any]:
    """Attempt to create a swept boss using the 3D sketch as the sweep path.
    This is the Phase-5 prerequisite proof (FR-5-02, FR-5-06)."""
    rec: dict[str, Any] = {"step": "S4_sweep_stretch"}
    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        rec["status"] = "FAIL"
        rec["reason"] = "NewDocument returned None"
        return rec
    title = _title(doc)
    try:
        sm = doc.SketchManager

        # Step 1: Create a 3D-sketch path
        try:
            sm.Insert3DSketch(True)
        except Exception as e_open:  # noqa: BLE001
            rec["status"] = "WALL"
            rec["error"] = repr(e_open)
            rec["fail_closed"] = True
            return rec

        for i in range(len(_3D_POINTS_M) - 1):
            a, b = _3D_POINTS_M[i], _3D_POINTS_M[i + 1]
            sm.CreateLine(a[0], a[1], a[2], b[0], b[1], b[2])
        sm.Insert3DSketch(True)  # close path sketch

        path_feat = doc.FeatureByPositionReverse(0)
        if path_feat is not None:
            path_feat.Name = "Path3D"
        rec["path_sketch"] = "Path3D"

        # Step 2: Create a profile circle on the Front Plane at the path start
        if not doc.SelectByID("Front Plane", "PLANE", 0.0, 0.0, 0.0):
            rec["status"] = "FAIL"
            rec["reason"] = "could not select Front Plane for profile"
            return rec
        sm.InsertSketch(True)
        sm.CreateCircle(0.0, 0.0, 0.0, 0.005, 0.0, 0.0)  # 5mm radius
        sm.InsertSketch(True)  # close profile

        profile_feat = doc.FeatureByPositionReverse(0)
        if profile_feat is not None:
            profile_feat.Name = "Profile"
        rec["profile_sketch"] = "Profile"

        # Step 3: Try to create a sweep using the 3D path
        fm = doc.FeatureManager
        sweep_result = None
        sweep_error = None

        # Attempt modern FeatureExtrusion-based sweep: InsertFeatureSweep
        try:
            # Select profile then path, then call InsertProtrusionSwept3
            doc.ClearSelection2(True)
            profile_feat.Select4(
                False,
                win32com.client.VARIANT(pythoncom.VT_DISPATCH, None),
            )
            path_feat.Select4(
                True,
                win32com.client.VARIANT(pythoncom.VT_DISPATCH, None),
            )
            sweep_result = fm.InsertProtrusionSwept3(
                True,   # bPropagateFeature
                False,  # bForceStartToMatchProfileTangent
                0,      # nStartConditionType
                0.0,    # dStartValue
                0,      # nEndConditionType
                0.0,    # dEndValue
                False,  # bTwist
                0.0,    # dTwistAngle
                False,  # bReverseTwist
                False,  # bMergeResult
                False,  # bUseFeatureScope
                False,  # bUseAutoSelect
                0,      # nPathAlignmentType
            )
        except Exception as e_sweep:  # noqa: BLE001
            sweep_error = repr(e_sweep)

        if sweep_result is not None:
            rec["sweep_result_type"] = type(sweep_result).__name__
            rec["sweep_is_none"] = sweep_result is None
            rec["status"] = "GREEN"
        elif sweep_error:
            rec["sweep_error"] = sweep_error
            rec["status"] = "WALL"
            rec["fail_closed"] = True
            rec["note"] = (
                "InsertProtrusionSwept3 raised.  Sweep-on-3D-path may need a "
                "different API (InsertProtrusionSwept4, FeatureExtrusion2 with "
                "sweep flag, or the modern CreateDefinition path).  Characterize "
                "in a dedicated sweep spike."
            )
        else:
            rec["status"] = "FAIL"
            rec["reason"] = "InsertProtrusionSwept3 returned None"
            rec["note"] = (
                "Sweep returned None — likely the profile does not intersect "
                "the 3D path start, or the solver rejected the geometry. "
                "Needs dedicated sweep-on-3D-path investigation."
            )
    finally:
        try:
            sw.CloseDoc(title)
        except Exception:  # noqa: BLE001
            pass
    return rec


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run() -> dict[str, Any]:
    sw = connect_running_sw()
    report: dict[str, Any] = {}
    try:
        report["sw_revision"] = str(sw.RevisionNumber)
    except Exception:  # noqa: BLE001
        report["sw_revision"] = "<unreadable>"

    report["S1_funcdesc"] = _probe_insert3d_sketch_funcdesc()
    report["S2_materialize"] = _probe_3d_sketch_materialize(sw)
    report["S3_save_reopen"] = _probe_save_reopen(sw)
    report["S4_sweep_stretch"] = _probe_sweep_on_3d_path(sw)

    # Overall gate
    s2 = report["S2_materialize"].get("status")
    s3 = report["S3_save_reopen"].get("status")
    if s2 == "GREEN" and s3 == "GREEN":
        report["overall"] = "PASS"
    elif s2 == "GREEN":
        report["overall"] = "PARTIAL"
        report["gate_note"] = "S2 GREEN but S3 not GREEN (save/reopen issue)"
    else:
        report["overall"] = "FAIL"
        report["gate_note"] = f"S2={s2} (need GREEN for de-risk gate)"

    return report


def main() -> int:
    pythoncom.CoInitialize()
    try:
        report = run()
    finally:
        pythoncom.CoUninitialize()
    out = Path(__file__).parent / "_results" / "sketch_3d_derisk.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    print(f"\nwrote {out}", file=sys.stderr)
    return 0 if report.get("overall") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
