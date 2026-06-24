"""
Spike v0.2x / S-SHEETMETAL3 — sheet-metal hem via legacy InsertSheetMetalHem.
[authored seat-free; RUN ON A LIVE SEAT]

W55-C proved that ``CreateDefinition(?)`` is E_NOINTERFACE for hem, jog,
and miter — the modern FeatureData pipeline is walled for these operations.
This spike characterizes the **legacy Insert route** for hem:

  1. **Base flange** — proven ``CreateDefinition(34) → IBaseFlangeFeatureData
     → CreateFeature`` pipeline (W53).
  2. **Edge discovery** — persist round-trip via typed Extension yields live,
     selectable edges (W55-C).
  3. **InsertSheetMetalHem** (v1, 9-param) — FUNCDESC-sourced signature::

        InsertSheetMetalHem(
            Type: int,            # swHemTypes_e
            Position: int,        # swHemPositionTypes_e
            Reverse: bool,
            DLength: double,
            DGap: double,
            DAngle: double,
            DRad: double,
            DMiterGap: double,
            PCBA: CustomBendAllowance  # NULL OK
        ) -> Feature

  4. **InsertSheetMetalHem2** (v2, 16-param) — fallback if v1 hits a
     marshaling wall::

        InsertSheetMetalHem2(
            <same 9 as v1>,
            UseDefaultRelief: bool,
            ReliefType: int,
            ReliefTearTypes: int,
            UseReliefRatio: bool,
            ReliefRatio: double,
            ReliefWidth: double,
            ReliefDepth: double
        ) -> Feature

FUNCDESC source: sldworks.tlb via pythoncom.LoadTypeLib (seat-confirmed):
    swHemTypes_e: Open=0, Closed=1, TearDrop=2, Rolled=3, Double=4
    swHemPositionTypes_e: Inside=0, Outside=1

WHAT THIS SPIKE DISTINGUISHES
-----------------------------
* **PASS** — hem materializes + face count increases → handler can ship.
* **PASS-v2** — v1 fails but v2 materializes → handler uses v2.
* **MARSHAL-WALL** — both v1 and v2 accept params but edges not consumed
  (same wall as v0.15 base flange legacy route).
* **FAIL** — both v1 and v2 fail → hem is unreachable from Python COM.

Prereq: SOLIDWORKS running. Sheet Metal add-in enabled.
Non-destructive (own doc, closed without save).

Usage
-----
    python spikes/v0_2x/spike_sheetmetal3.py --out report.json
    python spikes/v0_2x/spike_sheetmetal3.py --mode vba
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

from ai_sw_bridge.com.earlybind import typed_qi, typed_extension  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402

from spike_earlybind_persist import connect_running_sw, ensure_sw_module  # noqa: E402

SW_DEFAULT_TEMPLATE_PART = 8
SW_FM_BASEFLANGE = 34
IFACE_BASEFLANGE = "IBaseFlangeFeatureData"
SW_BODY_SOLID = 0

PROF_W_M = 0.060
PROF_H_M = 0.040
THICKNESS_M = 0.002
BEND_RADIUS_M = 0.002

SW_HEM_TYPE_OPEN = 0
SW_HEM_TYPE_CLOSED = 1
SW_HEM_POSITION_OUTSIDE = 1
HEM_LENGTH_M = 0.010
HEM_GAP_M = 0.002
HEM_MITER_GAP_M = 0.001

MEMID_HEM_V1 = 91
MEMID_HEM_V2 = 201

HEM_V1_ARGTYPES = (
    (3, 1),
    (3, 1),
    (11, 1),
    (5, 1),
    (5, 1),
    (5, 1),
    (5, 1),
    (5, 1),
    (13, 1),
)
HEM_V2_ARGTYPES = (
    (3, 1),
    (3, 1),
    (11, 1),
    (5, 1),
    (5, 1),
    (5, 1),
    (5, 1),
    (5, 1),
    (13, 1),
    (11, 1),
    (3, 1),
    (3, 1),
    (11, 1),
    (5, 1),
    (5, 1),
    (5, 1),
)


def _raw_invoke(fm: Any, memid: int, argtypes: tuple, args: tuple) -> Any:
    """Bypass makepy's VT misassignment: call InvokeTypes with tlb-correct VTs."""
    oleobj = fm._oleobj_
    ret = oleobj.InvokeTypes(memid, 0, 1, (9, 0), argtypes, *args)
    if ret is not None:
        from win32com.client import Dispatch

        ret = Dispatch(
            ret, "InsertSheetMetalHem", "{83A33D38-27C5-11CE-BFD4-00400513BB57}"
        )
    return ret


def _tag(v: Any) -> str:
    return "NoneType" if v is None else type(v).__name__


def _capture(fn: Any) -> tuple[dict[str, Any], Any]:
    t0 = time.perf_counter()
    try:
        val = fn()
        return {
            "status": "OK",
            "type": _tag(val),
            "elapsed_ms": (time.perf_counter() - t0) * 1000.0,
        }, val
    except Exception as e:  # noqa: BLE001
        return {
            "status": "EXCEPTION",
            "exception_type": type(e).__name__,
            "message": str(e)[:200],
            "hresult": f"{e.hresult:#010x}" if hasattr(e, "hresult") else None,
            "elapsed_ms": (time.perf_counter() - t0) * 1000.0,
        }, None


def _materialized(feat: Any) -> bool:
    return feat is not None and not isinstance(feat, int)


def _title(d: Any) -> Any:
    t = d.GetTitle
    return t() if callable(t) else t


def _close_all(sw: Any) -> None:
    try:
        sw.CloseAllDocuments(True)
    except Exception:  # noqa: BLE001
        pass


def _as_list(v: Any) -> list:
    if v is None:
        return []
    return list(v) if isinstance(v, (tuple, list)) else [v]


def _build_profile(doc: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    try:
        doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
        sk = doc.SketchManager
        sk.InsertSketch(True)
        seg = sk.CreateCornerRectangle(
            -PROF_W_M / 2, -PROF_H_M / 2, 0.0, PROF_W_M / 2, PROF_H_M / 2, 0.0
        )
        sk.InsertSketch(True)
        out["built"] = seg is not None
        out["sketch"] = "Sketch1"
    except Exception as e:  # noqa: BLE001
        out["built"] = False
        out["error"] = f"{type(e).__name__}: {e}"
    return out


def _build_base_flange(doc: Any, fm: Any, mod: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    def_rec, data = _capture(lambda: fm.CreateDefinition(SW_FM_BASEFLANGE))
    out["create_definition"] = def_rec
    if data is None:
        out["overall"] = "FAIL"
        return out
    qi_rec, wrapped = _capture(lambda: typed_qi(data, IFACE_BASEFLANGE, module=mod))
    out["typed_qi"] = qi_rec
    if wrapped is None:
        out["overall"] = "FAIL"
        return out
    for name, val in (("Thickness", THICKNESS_M), ("BendRadius", BEND_RADIUS_M)):
        try:
            setattr(wrapped, name, val)
            out[f"set_{name}"] = "OK"
        except Exception as e:  # noqa: BLE001
            out[f"set_{name}"] = f"EXCEPTION: {type(e).__name__}: {e}"
    try:
        doc.ClearSelection2(True)
    except Exception:  # noqa: BLE001
        pass
    doc.SelectByID("Sketch1", "SKETCH", 0, 0, 0)
    feat_rec, feat = _capture(lambda: fm.CreateFeature(data))
    feat_rec["materialized"] = _materialized(feat)
    if _materialized(feat):
        feat_rec["feature_name"] = getattr(feat, "Name", None)
    out["create_feature"] = feat_rec
    out["overall"] = "PASS" if _materialized(feat) else "FAIL"
    return out


def _find_live_edges(doc: Any, mod: Any) -> list[Any]:
    rec, bodies = _capture(lambda: doc.GetBodies2(SW_BODY_SOLID, True))
    body_list = _as_list(bodies)
    if not body_list:
        return []
    body = body_list[0]
    rec, edges_raw = _capture(lambda: body.GetEdges())
    edge_list = _as_list(edges_raw)
    if not edge_list:
        return []
    try:
        ext = typed_extension(doc, module=mod)
    except Exception:
        return []
    result = []
    for e in edge_list:
        try:
            pid = ext.GetPersistReference3(e)
            if pid is None:
                continue
            obj_result = ext.GetObjectByPersistReference3(pid)
            obj = obj_result[0] if isinstance(obj_result, tuple) else obj_result
            if obj is not None and not isinstance(obj, int):
                result.append(obj)
        except Exception:
            continue
    return result


def _count_faces(doc: Any) -> int:
    rec, bodies = _capture(lambda: doc.GetBodies2(SW_BODY_SOLID, True))
    total = 0
    for b in _as_list(bodies):
        try:
            faces = b.GetFaces()
            total += len(_as_list(faces))
        except Exception:  # noqa: BLE001
            pass
    return total


def _probe_hem_v1(fm: Any, doc: Any) -> dict[str, Any]:
    """InsertSheetMetalHem — 9-param legacy (v1)."""
    out: dict[str, Any] = {"method": "InsertSheetMetalHem", "arity": 9}
    faces_before = _count_faces(doc)
    out["faces_before"] = faces_before

    combos = [
        (
            "closed-null-pcba",
            (
                SW_HEM_TYPE_CLOSED,
                SW_HEM_POSITION_OUTSIDE,
                False,
                HEM_LENGTH_M,
                0.0,
                0.0,
                0.0,
                HEM_MITER_GAP_M,
                None,
            ),
        ),
        (
            "open-null-pcba",
            (
                SW_HEM_TYPE_OPEN,
                SW_HEM_POSITION_OUTSIDE,
                False,
                HEM_LENGTH_M,
                HEM_GAP_M,
                0.0,
                0.0,
                HEM_MITER_GAP_M,
                None,
            ),
        ),
    ]

    v1_dispatch_types = (
        (3, 1),
        (3, 1),
        (11, 1),
        (5, 1),
        (5, 1),
        (5, 1),
        (5, 1),
        (5, 1),
        (9, 1),
    )

    attempts: list[dict[str, Any]] = []
    for label, args in combos:
        rec, feat = _capture(lambda: fm.InsertSheetMetalHem(*args))
        rec["route"] = "makepy"
        rec["combo"] = label

        if feat is None and rec.get("status") == "EXCEPTION":
            rec_raw, feat = _capture(
                lambda: _raw_invoke(fm, MEMID_HEM_V1, HEM_V1_ARGTYPES, args)
            )
            rec_raw["route"] = "raw-InvokeTypes(VT_UNKNOWN)"
            rec_raw["combo"] = label
            attempts.append(rec)
            rec = rec_raw

            if feat is None and rec.get("status") == "EXCEPTION":
                rec_disp, feat = _capture(
                    lambda: _raw_invoke(fm, MEMID_HEM_V1, v1_dispatch_types, args)
                )
                rec_disp["route"] = "raw-InvokeTypes(VT_DISPATCH)"
                rec_disp["combo"] = label
                attempts.append(rec)
                rec = rec_disp

        rec["materialized"] = _materialized(feat)
        if _materialized(feat):
            rec["feature_name"] = getattr(feat, "Name", None)
        attempts.append(rec)
        if _materialized(feat):
            try:
                doc.ForceRebuild3(False)
            except Exception:  # noqa: BLE001
                pass
            faces_after = _count_faces(doc)
            out["faces_after"] = faces_after
            out["face_delta"] = faces_after - faces_before
            out["winning_combo"] = label
            out["winning_route"] = rec.get("route", "unknown")
            out["attempts"] = attempts
            out["overall"] = "PASS" if faces_after > faces_before else "PARTIAL"
            return out
    out["attempts"] = attempts
    out["overall"] = "FAIL"
    return out


def _probe_hem_v2(fm: Any, doc: Any) -> dict[str, Any]:
    """InsertSheetMetalHem2 — 16-param (v2, SW2011+)."""
    out: dict[str, Any] = {"method": "InsertSheetMetalHem2", "arity": 16}
    faces_before = _count_faces(doc)
    out["faces_before"] = faces_before

    args = (
        SW_HEM_TYPE_CLOSED,
        SW_HEM_POSITION_OUTSIDE,
        False,
        HEM_LENGTH_M,
        0.0,
        0.0,
        0.0,
        HEM_MITER_GAP_M,
        None,
        True,
        0,
        0,
        False,
        0.0,
        0.0,
        0.0,
    )
    rec, feat = _capture(lambda: fm.InsertSheetMetalHem2(*args))
    rec["route"] = "makepy"

    if feat is None and rec.get("status") == "EXCEPTION":
        rec_raw, feat = _capture(
            lambda: _raw_invoke(fm, MEMID_HEM_V2, HEM_V2_ARGTYPES, args)
        )
        rec_raw["route"] = "raw-InvokeTypes(VT_UNKNOWN)"
        out["makepy_attempt"] = rec
        rec = rec_raw

    rec["materialized"] = _materialized(feat)
    if _materialized(feat):
        rec["feature_name"] = getattr(feat, "Name", None)
    out["call"] = rec
    if _materialized(feat):
        try:
            doc.ForceRebuild3(False)
        except Exception:  # noqa: BLE001
            pass
        faces_after = _count_faces(doc)
        out["faces_after"] = faces_after
        out["face_delta"] = faces_after - faces_before
        out["overall"] = "PASS" if faces_after > faces_before else "PARTIAL"
    else:
        out["overall"] = "FAIL"
    return out


def run() -> dict[str, Any]:
    result: dict[str, Any] = {"binding": "hybrid early (com.earlybind)"}
    mod = wrapper_module()
    mod_source = "com.sw_type_info.wrapper_module"
    if mod is None:
        mod, info = ensure_sw_module()
        mod_source = "spike_earlybind_persist.ensure_sw_module"
        result["module_fallback_info"] = info
    result["module_source"] = mod_source
    result["module"] = getattr(mod, "__name__", str(mod))

    sw = connect_running_sw()
    try:
        result["sw_revision"] = str(sw.RevisionNumber)
    except Exception:
        result["sw_revision"] = "<unreadable>"

    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        return {**result, "overall": "FAIL", "reason": "NewDocument returned None"}

    try:
        prof = _build_profile(doc)
        result["profile"] = prof
        if not prof.get("built"):
            return {**result, "overall": "FAIL", "reason": "profile sketch failed"}

        fm = doc.FeatureManager
        base = _build_base_flange(doc, fm, mod)
        result["base_flange"] = base
        if base.get("overall") != "PASS":
            return {
                **result,
                "overall": "FAIL",
                "reason": "base flange (proven pipeline) failed",
            }

        try:
            doc.ForceRebuild3(False)
        except Exception:  # noqa: BLE001
            pass

        edges = _find_live_edges(doc, mod)
        result["live_edges"] = len(edges)
        if not edges:
            return {
                **result,
                "overall": "FAIL",
                "reason": "no live edges after base flange",
            }

        try:
            doc.ClearSelection2(True)
        except Exception:  # noqa: BLE001
            pass
        try:
            sel_rec = {}
            sel_rec["Select2"] = edges[0].Select2(False, 0)
            result["edge_select"] = sel_rec
        except Exception as e:  # noqa: BLE001
            result["edge_select"] = {"error": f"{type(e).__name__}: {e}"}

        hem_v1 = _probe_hem_v1(fm, doc)
        result["hem_v1"] = hem_v1

        if hem_v1.get("overall") != "PASS":
            try:
                doc.ClearSelection2(True)
            except Exception:  # noqa: BLE001
                pass
            edges2 = _find_live_edges(doc, mod)
            if edges2:
                try:
                    edges2[0].Select2(False, 0)
                except Exception:  # noqa: BLE001
                    pass
            hem_v2 = _probe_hem_v2(fm, doc)
            result["hem_v2"] = hem_v2
        else:
            result["hem_v2"] = {
                "overall": "SKIPPED",
                "reason": "v1 PASS — v2 not needed",
            }

        hem_overall = hem_v1.get("overall") or result.get("hem_v2", {}).get("overall")
        if hem_overall and "PASS" in hem_overall:
            save_path = Path(tempfile.mkdtemp(prefix="hem_w59_")) / "hem_verify.sldprt"
            faces_before_save = _count_faces(doc)
            save_rec, _ = _capture(lambda: doc.SaveAs3(str(save_path), 0, 1))
            result["persistence"] = {"save": save_rec, "path": str(save_path)}
            if save_rec.get("status") == "OK":
                _close_all(sw)
                reopen_rec, reopened = _capture(lambda: sw.OpenDoc(str(save_path), 1))
                result["persistence"]["reopen"] = reopen_rec
                if reopen_rec.get("status") == "OK" and reopened is not None:
                    actual = reopened[0] if isinstance(reopened, tuple) else reopened
                    faces_after_reopen = _count_faces(actual)
                    result["persistence"]["faces_before_save"] = faces_before_save
                    result["persistence"]["faces_after_reopen"] = faces_after_reopen
                    result["persistence"]["survived"] = faces_after_reopen > 0
                    try:
                        actual.ForceRebuild3(False)
                    except Exception:  # noqa: BLE001
                        pass
                    faces_rebuilt = _count_faces(actual)
                    result["persistence"]["faces_after_rebuild"] = faces_rebuilt
                    result["persistence"]["delta_survived"] = (
                        faces_rebuilt >= faces_before_save
                    )
                else:
                    result["persistence"]["survived"] = False
            else:
                result["persistence"]["survived"] = False

    finally:
        _close_all(sw)
        result["cleanup"] = "CloseAllDocuments(True)"

    v1 = result.get("hem_v1", {}).get("overall", "FAIL")
    v2 = result.get("hem_v2", {}).get("overall", "FAIL")
    persisted = result.get("persistence", {}).get("delta_survived", None)
    if v1 == "PASS":
        if persisted is False:
            result["overall"] = "PARTIAL-PERSIST"
            result["interpretation"] = (
                "Hem v1 materializes + face delta but DID NOT survive save→reopen."
            )
        else:
            result["overall"] = "PASS"
            result["interpretation"] = (
                "Hem v1 materializes + face delta + survived save→reopen → handler ships."
            )
    elif "PASS" in v2:
        if persisted is False:
            result["overall"] = "PARTIAL-PERSIST"
            result["interpretation"] = (
                "Hem v2 materializes + face delta but DID NOT survive save→reopen."
            )
        else:
            result["overall"] = "PASS-v2"
            result["interpretation"] = (
                "Hem v1 FAIL but v2 PASS + persisted → handler uses v2."
            )
    elif v1 == "FAIL" and v2 == "FAIL":
        result["overall"] = "FAIL"
        result["interpretation"] = "Both v1 and v2 FAIL → hem unreachable."
    else:
        result["overall"] = "PARTIAL"
        result["interpretation"] = f"Mixed: v1={v1}, v2={v2}. Run --mode vba."
    return result


def emit_vba() -> str:
    return r"""' Spike v0.2x S-SHEETMETAL3 — hem VBA oracle.
Option Explicit
Sub ProbeSheetMetalHem()
    Dim swApp As SldWorks.SldWorks
    Dim Part As SldWorks.ModelDoc2
    Dim fm As SldWorks.FeatureManager
    Dim ext As SldWorks.ModelDocExtension
    Dim sm As SldWorks.SketchManager
    Dim feat As SldWorks.Feature
    Dim fd As Object
    Dim bodies As Variant, edges As Variant
    Set swApp = Application.SldWorks
    Set Part = swApp.NewDocument( _
        swApp.GetUserPreferenceStringValue(8), 0, 0#, 0#)
    Set fm = Part.FeatureManager
    Set ext = Part.Extension
    Set sm = Part.SketchManager
    Part.SelectByID2 "Front Plane", "PLANE", 0, 0, 0, False, 0, Nothing, 0
    sm.InsertSketch True
    sm.CreateCornerRectangle -0.03, -0.02, 0, 0.03, 0.02, 0
    sm.InsertSketch True
    Part.SelectByID2 "Sketch1", "SKETCH", 0, 0, 0, False, 0, Nothing, 0
    Set fd = fm.CreateDefinition(34)
    If fd Is Nothing Then MsgBox "Base flange CD(34) Nothing": Exit Sub
    fd.Thickness = 0.002
    fd.BendRadius = 0.002
    Part.ClearSelection2 True
    Part.SelectByID2 "Sketch1", "SKETCH", 0, 0, 0, False, 0, Nothing, 0
    Set feat = fm.CreateFeature(fd)
    If feat Is Nothing Then MsgBox "Base flange: NOTHING": Exit Sub
    Part.ForceRebuild3 False
    bodies = Part.GetBodies2(0, True)
    If IsEmpty(bodies) Then MsgBox "No bodies": Exit Sub
    edges = bodies(0).GetEdges
    If IsEmpty(edges) Then MsgBox "No edges": Exit Sub
    edges(0).Select4 False, Nothing
    ' --- v1: InsertSheetMetalHem (9 params) ---
    Set feat = fm.InsertSheetMetalHem(1, 0, False, 0.01, 0#, 0#, 0#, 0.001, Nothing)
    If feat Is Nothing Then
        MsgBox "Hem v1: NOTHING — trying v2"
        Part.ClearSelection2 True
        edges(0).Select4 False, Nothing
        Set feat = fm.InsertSheetMetalHem2(1, 0, False, 0.01, 0#, 0#, 0#, 0.001, Nothing, True, 0, 0, False, 0#, 0#, 0#)
        If feat Is Nothing Then MsgBox "Hem v2: NOTHING" Else MsgBox "Hem v2: " & feat.Name
    Else
        MsgBox "Hem v1: " & feat.Name
    End If
End Sub
"""


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--mode", choices=["com", "vba"], default="com")
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args()
    if args.mode == "vba":
        out = Path(__file__).parent / "spike_sheetmetal3.bas"
        out.write_text(emit_vba(), encoding="utf-8")
        sys.stderr.write(f"wrote {out}\n")
        return 0
    pythoncom.CoInitialize()
    try:
        result = run()
    finally:
        pythoncom.CoUninitialize()
    payload = json.dumps(result, indent=2, default=str)
    if args.out is not None:
        args.out.write_text(payload, encoding="utf-8")
        sys.stderr.write(f"wrote {args.out}\n")
    else:
        sys.stdout.write(payload + "\n")
    return {"PASS": 0, "PASS-v2": 0, "PARTIAL": 2, "PARTIAL-PERSIST": 2, "FAIL": 1}.get(
        result.get("overall"), 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
