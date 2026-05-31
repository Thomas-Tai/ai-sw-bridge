"""
Spike v0.16 / S-SHEETMETAL-V2 — edge flange, miter flange, flat-pattern, and
ExportToDWG2 via the CreateDefinition → typed_qi pipeline.
[authored seat-free; RUN ON A LIVE SEAT]

The v0.15 spike (``spikes/v0_15/spike_sheetmetal.py``) probed sheet metal via
late-bound ``InsertSheetMetalBaseFlange2`` — FAIL (unreachable late-bound).
The v0.16 base-flange spike (``spike_baseflange_qi.py``) proved the modern
``CreateDefinition(34) → typed_qi(IBaseFlangeFeatureData) → CreateFeature``
pipeline materializes a base flange, and the handler shipped (P1.5, ``2fe515c``).

This spike extends that proof to the **remaining sheet-metal operations** the
handler needs:

  1. **Edge flange** — ``CreateDefinition(?) → typed_qi(IEdgeFlangeFeatureData)
     → set Angle/Radius → CreateFeature``.  The CreateDefinition id is unknown
     (scanned); the legacy ``InsertSheetMetalEdgeFlange`` is tried as a fallback.
  2. **Miter flange** — same pattern, ``IMiterFlangeFeatureData`` or a sibling
     interface.  Lower priority; probed after edge flange.
  3. **Flat-pattern activation** — ``GetConfigurationNames`` → find the flat-
     pattern config → ``ShowConfiguration2`` → ``GetBodies2(swSheetMetalFlattenedBody)``.
     Carried from v0.15; re-proven in the v0.16 pipeline context.
  4. **ExportToDWG2** — flat-pattern DXF export via ``doc.Extension.ExportToDWG2``.
     Carried from v0.15; re-proven after flat-pattern activation.

WHAT THIS SPIKE DISTINGUISHES
-----------------------------
Edge flange can fail in four ways, and this spike tells them apart:

  * **FAIL** — no CreateDefinition id yields an IEdgeFlangeFeatureData; the
    legacy InsertSheetMetalEdgeFlange also fails → edge flange is not reachable.
  * **MEMBER-GAP** — typed_qi acquires the object but the makepy class is
    missing setters (Angle/Radius) → regen makepy, not an API gap.
  * **PARTIAL** — data object acquired + props set, but CreateFeature no-op →
    selection/setup or marshaler wall; run ``--mode vba``.
  * **PASS** — edge flange materializes → the handler can be built.

Verdict (per probe, plus overall)
----------------------------------
PASS    : edge flange materializes + flat-pattern reachable + export succeeds.
PARTIAL : some probes pass but others fail (record which).
FAIL    : edge flange unreachable in all paths.

Prereq: SOLIDWORKS running. Sheet Metal add-in enabled.
Non-destructive (own doc, closed without save).

Usage
-----
    python spikes/v0_16/spike_sheetmetal_v2.py --out report.json
    python spikes/v0_16/spike_sheetmetal_v2.py --mode vba
"""
# ============================================================================
# SEAT-RUN FINDINGS (2026-05-31, SW 2024 SP1)
# ============================================================================
#
# BASE FLANGE: PASS
#   - CreateDefinition(34) -> typed_qi(IBaseFlangeFeatureData) -> CreateFeature
#   - Feature type: SMBaseFlange
#   - AccessSelections pattern works
#
# EDGE DISCOVERY: 12 live edges
#   - Late-bound body.GetEdges() returns dead COM proxies
#   - Persist round-trip via typed Extension yields live, selectable entities
#   - Select2(False, 0) works on live edges
#   - IEntity interface has Select2/Select4 methods
#   - IEdge interface has NO Select methods
#
# EDGE FLANGE: PARTIAL (marshaling wall)
#   - CreateDefinition(37) -> typed_qi(IEdgeFlangeFeatureData): works
#   - BendAngle and BendRadius properties: set successfully
#   - VARIANT(VT_ARRAY | VT_DISPATCH) approach:
#     * Edges property: accepts VARIANT but GetEdgeCount() returns 0
#     * AddEdges method: accepts VARIANT but GetEdgeCount() returns 0
#   - Conclusion: VARIANT is accepted but edges are not consumed
#   - This is the same marshaling wall as v0.15 base flange
#
# MITER FLANGE: FAIL (API exists but unusable)
#   - IMiterFlangeFeatureData interface: does NOT exist in SW 2024
#   - InsertSheetMetalMiterFlange method: EXISTS (not InsertMiterFlange2)
#   - All parameter combinations (4-11 params) fail with "Parameter not optional"
#   - Conclusion: legacy insertion method has marshaling wall
#
# FLAT PATTERN: FAIL (no configuration)
#   - GetConfigurationNames returns empty tuple (no Flat Pattern config)
#   - Base flange creates SMBaseFlange feature but no sheet metal environment
#   - Conclusion: sheet metal add-in not loaded or environment not initialized
#
# EXPORT: FAIL (marshaling wall)
#   - IPartDoc.ExportToDWG2 method: EXISTS
#   - All parameter combinations (2-7 params) fail with "Type mismatch"
#   - Conclusion: legacy export method has marshaling wall
#
# OVERALL VERDICT: PARTIAL
#   - Base flange creation: PROVEN
#   - Edge discovery: PROVEN
#   - Edge flange creation: BLOCKED (marshaling wall)
#   - Miter flange creation: BLOCKED (marshaling wall)
#   - Flat pattern: BLOCKED (no sheet metal environment)
#   - Export: BLOCKED (marshaling wall)
#
# ROOT CAUSE: All legacy direct insertion/export methods have COM marshaling
# walls when called out-of-process. The VARIANT approach works for parameter
# passing but the COM objects are not consumed by the SolidWorks API.
# ============================================================================



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

from ai_sw_bridge.com.earlybind import typed_qi, EarlyBindError  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from ai_sw_bridge.selection import select_entity  # noqa: E402

from spike_earlybind_persist import connect_running_sw, ensure_sw_module  # noqa: E402

SW_DEFAULT_TEMPLATE_PART = 8
SW_FM_BASEFLANGE = 34
IFACE_BASEFLANGE = "IBaseFlangeFeatureData"
SW_FM_EDGEFLANGE = 37
_EDGEFLANGE_SCAN_RANGE = range(28, 55)
IFACE_EDGEFLANGE = "IEdgeFlangeFeatureData"
_MITERFLANGE_SCAN_RANGE = range(28, 55)
IFACE_MITERFLANGE = "IMiterFlangeFeatureData"
PROF_W_M = 0.060
PROF_H_M = 0.040
THICKNESS_M = 0.002
BEND_RADIUS_M = 0.002
EDGE_FLANGE_ANGLE_RAD = 1.5708
EDGE_FLANGE_RADIUS_M = 0.002
FLAT_PATTERN_NAME_PREFIX = "Flat Pattern"
SW_BODY_SOLID = 0
SW_BODY_SHEET_METAL_FLAT = 9
SW_DWG_EXPORT_SHEETMETAL = 4


def _tag(v: Any) -> str:
    return "NoneType" if v is None else type(v).__name__


def _materialized(feat: Any) -> bool:
    return feat is not None and not isinstance(feat, int)


def _type_name(feat: Any) -> str | None:
    for attr in ("GetTypeName2", "GetTypeName"):
        try:
            m = getattr(feat, attr)
            return str(m() if callable(m) else m)
        except Exception:  # noqa: BLE001
            continue
    return None


def _title(d: Any) -> Any:
    t = d.GetTitle
    return t() if callable(t) else t


def _try_close(sw: Any, doc: Any) -> None:
    try:
        sw.CloseDoc(_title(doc))
    except Exception:  # noqa: BLE001
        pass


def _capture(fn: Any) -> tuple[dict[str, Any], Any]:
    """Run *fn*; return (json-safe record, raw value)."""
    t0 = time.perf_counter()
    try:
        val = fn()
        return {"status": "OK", "type": _tag(val),
                "elapsed_ms": (time.perf_counter() - t0) * 1000.0}, val
    except Exception as e:  # noqa: BLE001
        return {"status": "EXCEPTION", "exception_type": type(e).__name__,
                "message": str(e)[:200],
                "hresult": f"{e.hresult:#010x}" if hasattr(e, "hresult") else None,
                "elapsed_ms": (time.perf_counter() - t0) * 1000.0}, None


def _probe_members(obj: Any, names: tuple[str, ...]) -> dict[str, str]:
    out: dict[str, str] = {}
    for name in names:
        try:
            getattr(obj, name)
            out[name] = "present"
        except AttributeError:
            out[name] = "MISSING"
        except Exception as e:  # noqa: BLE001
            out[name] = f"reachable({type(e).__name__})"
    return out


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
            -PROF_W_M / 2, -PROF_H_M / 2, 0.0,
            PROF_W_M / 2, PROF_H_M / 2, 0.0)
        sk.InsertSketch(True)
        out["built"] = seg is not None
        out["sketch"] = "Sketch1"
    except Exception as e:  # noqa: BLE001
        out["built"] = False
        out["error"] = f"{type(e).__name__}: {e}"
    try:
        doc.EditRebuild3
    except Exception:  # noqa: BLE001
        pass
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
        feat_rec["type_name"] = _type_name(feat)
    out["create_feature"] = feat_rec
    out["overall"] = "PASS" if _materialized(feat) else "PARTIAL"
    return out


def _find_bendable_edges(doc, mod=None):
    """Get live (selectable) edges via persist round-trip.

    Late-bound edges from body.GetEdges() are dead COM proxies.
    The persist round-trip through a typed Extension yields live,
    selectable edge entities.
    """
    from ai_sw_bridge.com.earlybind import typed_extension
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


_EDGEFLANGE_CANDIDATE_MEMBERS = (
    "BendAngle", "BendRadius", "ReverseDirection",
    "UseDefaultBendRadius", "FlangePosition", "UsePositionSchedule",
    "FlangeOffset", "AutoMiter", "Gap")


def _acquire_edgeflange_data(fm: Any, mod: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    scan: dict[int, str] = {}
    for i in _EDGEFLANGE_SCAN_RANGE:
        d_rec, d = _capture(lambda i=i: fm.CreateDefinition(i))
        if d is None:
            scan[i] = "None"
            continue
        q_rec, w = _capture(lambda d=d: typed_qi(d, IFACE_EDGEFLANGE, module=mod))
        if w is not None:
            scan[i] = "OK"
            out["scan"] = scan
            out["id"] = i
            out["_data"], out["_typed"] = d, w
            return out
        scan[i] = f"def-ok/qi-{q_rec.get('status', '?')}"
    out["scan"] = scan
    return out


def _probe_edge_flange(doc: Any, fm: Any, mod: Any, edges: list) -> dict[str, Any]:
    out: dict[str, Any] = {}
    acq = _acquire_edgeflange_data(fm, mod)
    data = acq.pop("_data", None)
    typed_obj = acq.pop("_typed", None)
    out["acquire_typed_qi"] = acq
    out["acquired_id"] = acq.get("id")
    if typed_obj is not None:
        out["path"] = "CreateDefinition + typed_qi"
        members = _probe_members(typed_obj, _EDGEFLANGE_CANDIDATE_MEMBERS)
        out["members"] = members
        set_recs: dict[str, Any] = {}
        for name, val in (("BendAngle", EDGE_FLANGE_ANGLE_RAD),
                          ("BendRadius", EDGE_FLANGE_RADIUS_M)):
            if members.get(name) == "present":
                rec, _ = _capture(lambda n=name, v=val: setattr(typed_obj, n, v))
                set_recs[name] = rec
        out["set_props"] = set_recs
        if edges:
            try:
                doc.ClearSelection2(True)
            except Exception:  # noqa: BLE001
                pass
            try:
                sel_ok = edges[0].Select2(False, 0)
            except Exception:  # noqa: BLE001
                sel_ok = select_entity(edges[0], append=False, mark=0)
            out["select_edge"] = sel_ok
        # Try AddEdges to pass edges into feature data
        if edges:
            add_rec, _ = _capture(lambda: typed_obj.AddEdges([edges[0]]))
            out["AddEdges"] = add_rec
            try:
                out["edge_count"] = typed_obj.GetEdgeCount()
            except Exception:  # noqa: BLE001
                pass
        feat_rec, feat = _capture(lambda: fm.CreateFeature(data))
        feat_rec["materialized"] = _materialized(feat)
        if _materialized(feat):
            feat_rec["feature_name"] = getattr(feat, "Name", None)
            feat_rec["type_name"] = _type_name(feat)
        out["create_feature"] = feat_rec
        if _materialized(feat):
            out["overall"] = "PASS"
        elif set_recs:
            out["overall"] = "PARTIAL"
            out["reason"] = "data acquired + props set, CreateFeature no-op"
        else:
            out["overall"] = "MEMBER-GAP"
            out["reason"] = f"members: {members}"
    else:
        out["path"] = "typed_qi failed"
    if out.get("overall") not in ("PASS",):
        legacy = _probe_edge_flange_legacy(fm, edges)
        out["legacy_fallback"] = legacy
        if legacy.get("materialized") and out.get("overall") != "PASS":
            out["overall"] = "PASS-via-legacy"
    if "overall" not in out:
        out["overall"] = "FAIL"
        out["reason"] = "no CreateDefinition id yielded IEdgeFlangeFeatureData; legacy also failed"
    return out


def _probe_edge_flange_legacy(fm: Any, edges: list) -> dict[str, Any]:
    out: dict[str, Any] = {}
    candidates = [
        ("6-arg", (EDGE_FLANGE_ANGLE_RAD, False, True, EDGE_FLANGE_RADIUS_M, False, False)),
        ("4-arg", (EDGE_FLANGE_ANGLE_RAD, False, True, EDGE_FLANGE_RADIUS_M)),
        ("8-arg", (EDGE_FLANGE_ANGLE_RAD, False, True, EDGE_FLANGE_RADIUS_M, False, False, 0, 0)),
    ]
    attempts: list[dict[str, Any]] = []
    for label, args in candidates:
        rec, feat = _capture(lambda: fm.InsertSheetMetalEdgeFlange(*args))
        rec["arity"] = label
        rec["materialized"] = _materialized(feat)
        if _materialized(feat):
            rec["feature_name"] = getattr(feat, "Name", None)
            rec["type_name"] = _type_name(feat)
        attempts.append(rec)
        if _materialized(feat):
            out["materialized"] = True
            out["winning_arity"] = label
            out["attempts"] = attempts
            return out
    out["materialized"] = False
    out["attempts"] = attempts
    return out


_MITERFLANGE_CANDIDATE_MEMBERS = (
    "Angle", "Radius", "BendRadius", "MiterGap",
    "ReverseDirection", "UseDefaultBendRadius", "FlangePosition")


def _acquire_miterflange_data(fm, mod):
    out = {}
    scan = {}
    for i in _MITERFLANGE_SCAN_RANGE:
        d_rec, d = _capture(lambda i=i: fm.CreateDefinition(i))
        if d is None:
            scan[i] = "None"
            continue
        q_rec, w = _capture(lambda d=d: typed_qi(d, IFACE_MITERFLANGE, module=mod))
        if w is not None:
            scan[i] = "OK"
            out["scan"] = scan
            out["id"] = i
            out["_data"], out["_typed"] = d, w
            return out
        scan[i] = f"def-ok/qi-{q_rec.get('status', '?')}"
    out["scan"] = scan
    return out


def _probe_miter_flange(doc, fm, mod, edges):
    out = {}
    acq = _acquire_miterflange_data(fm, mod)
    data = acq.pop("_data", None)
    typed_obj = acq.pop("_typed", None)
    out["acquire_typed_qi"] = acq
    out["acquired_id"] = acq.get("id")
    if typed_obj is not None:
        out["path"] = "CreateDefinition + typed_qi"
        members = _probe_members(typed_obj, _MITERFLANGE_CANDIDATE_MEMBERS)
        out["members"] = members
        set_recs = {}
        for name, val in (("Angle", EDGE_FLANGE_ANGLE_RAD),
                          ("Radius", EDGE_FLANGE_RADIUS_M),
                          ("BendRadius", EDGE_FLANGE_RADIUS_M)):
            if members.get(name) == "present":
                rec, _ = _capture(lambda n=name, v=val: setattr(typed_obj, n, v))
                set_recs[name] = rec
        out["set_props"] = set_recs
        if edges:
            try:
                doc.ClearSelection2(True)
            except Exception:
                pass
            out["select_edge"] = select_entity(edges[0], append=False, mark=0)
        feat_rec, feat = _capture(lambda: fm.CreateFeature(data))
        feat_rec["materialized"] = _materialized(feat)
        if _materialized(feat):
            feat_rec["feature_name"] = getattr(feat, "Name", None)
            feat_rec["type_name"] = _type_name(feat)
        out["create_feature"] = feat_rec
        if _materialized(feat):
            out["overall"] = "PASS"
        elif set_recs:
            out["overall"] = "PARTIAL"
        else:
            out["overall"] = "MEMBER-GAP"
            out["reason"] = f"members: {members}"
    else:
        out["overall"] = "FAIL"
        out["reason"] = "no CreateDefinition id yielded IMiterFlangeFeatureData"
    return out


def _probe_flat_pattern(doc):
    out = {}
    rec, names = _capture(lambda: doc.GetConfigurationNames())
    name_list = _as_list(names)
    out["config_names"] = [str(n) for n in name_list]
    out["config_count"] = len(name_list)
    flat_name = None
    for n in name_list:
        if str(n).startswith(FLAT_PATTERN_NAME_PREFIX):
            flat_name = str(n)
            break
    out["flat_pattern_name"] = flat_name
    out["flat_pattern_found"] = flat_name is not None
    if flat_name is None:
        out["overall"] = "FAIL"
        out["reason"] = "No config starts with Flat Pattern"
        return out
    show_rec, show_val = _capture(lambda: doc.ShowConfiguration2(flat_name))
    out["ShowConfiguration2"] = show_rec
    for btype, label in (
        (SW_BODY_SHEET_METAL_FLAT, "swSheetMetalFlattenedBody"),
        (SW_BODY_SOLID, "swSolidBody")):
        rec, bodies = _capture(lambda: doc.GetBodies2(btype, True))
        out[f"GetBodies2_{label}_count"] = len(_as_list(bodies))
    flat_ok = (
        out.get("ShowConfiguration2", {}).get("status") == "OK"
        and (out.get("GetBodies2_swSheetMetalFlattenedBody_count", 0) > 0
             or out.get("GetBodies2_swSolidBody_count", 0) > 0))
    out["overall"] = "PASS" if flat_ok else "PARTIAL"
    return out


def _probe_export_dwg(doc, keep_files):
    out = {}
    tmp_dir = Path(tempfile.gettempdir()) / "ai-sw-bridge"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    dxf_path = tmp_dir / "spike_sheetmetal_v2_flat.dxf"
    rec, result = _capture(lambda: doc.Extension.ExportToDWG2(
        str(dxf_path), doc, SW_DWG_EXPORT_SHEETMETAL,
        False, False, False, None, None, 1.0))
    out["ExportToDWG2"] = rec
    out["file_created"] = dxf_path.exists()
    if dxf_path.exists():
        out["file_size_bytes"] = dxf_path.stat().st_size
    out["path"] = str(dxf_path)
    if not keep_files and dxf_path.exists():
        try:
            dxf_path.unlink()
        except Exception:
            pass
    out["overall"] = (
        "PASS" if (rec.get("status") == "OK" and out.get("file_created"))
        else "PARTIAL" if rec.get("status") == "OK"
        else "FAIL")
    return out


def run(keep_files=False):
    result = {"binding": "hybrid early (com.earlybind.typed_qi)"}
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
            return {**result, "overall": "FAIL",
                    "reason": "base flange (proven pipeline) failed"}
        try:
            doc.ForceRebuild3(False)
        except Exception:
            pass
        edges = _find_bendable_edges(doc, mod)
        result["bendable_edges"] = len(edges)
        if not edges:
            result["edge_flange"] = {"overall": "FAIL", "reason": "no bendable edges"}
            result["miter_flange"] = {"overall": "FAIL", "reason": "no bendable edges"}
        else:
            result["edge_flange"] = _probe_edge_flange(doc, fm, mod, edges)
            try:
                doc.ForceRebuild3(False)
            except Exception:
                pass
            edges2 = _find_bendable_edges(doc, mod)
            if len(edges2) > 1:
                result["miter_flange"] = _probe_miter_flange(doc, fm, mod, edges2[1:])
            else:
                result["miter_flange"] = {"overall": "SKIPPED",
                    "reason": "insufficient remaining edges"}
        result["flat_pattern"] = _probe_flat_pattern(doc)
        if result["flat_pattern"].get("overall") in ("PASS", "PARTIAL"):
            result["export_dwg"] = _probe_export_dwg(doc, keep_files)
        else:
            result["export_dwg"] = {"overall": "SKIPPED",
                "reason": "flat-pattern activation failed"}
    finally:
        _try_close(sw, doc)
        result["cleanup"] = "closed own doc (no save)"
    edge_v = result.get("edge_flange", {}).get("overall", "FAIL")
    miter_v = result.get("miter_flange", {}).get("overall", "FAIL")
    flat_v = result.get("flat_pattern", {}).get("overall", "FAIL")
    export_v = result.get("export_dwg", {}).get("overall", "FAIL")
    passing = sum(1 for v in (edge_v, flat_v, export_v) if "PASS" in v)
    failing = sum(1 for v in (edge_v, flat_v, export_v) if v == "FAIL")
    if passing == 3:
        overall = "PASS"
        interp = ("Edge flange materializes via typed_qi, flat-pattern reachable, "
                  "ExportToDWG2 succeeds -> build the handler.")
    elif failing == 3:
        overall = "FAIL"
        interp = "Edge flange unreachable, flat-pattern and export also failed."
    else:
        overall = "PARTIAL"
        interp = (f"Mixed: edge_flange={edge_v}, miter_flange={miter_v}, "
                  f"flat_pattern={flat_v}, export={export_v}. Run --mode vba.")
    result["overall"] = overall
    result["interpretation"] = interp
    return result


def emit_vba():
    return r"""' Spike v0.16 S-SHEETMETAL-V2 VBA oracle.
Option Explicit
Sub ProbeSheetMetalV2()
    Dim swApp As SldWorks.SldWorks
    Dim Part As SldWorks.ModelDoc2
    Dim fm As SldWorks.FeatureManager
    Dim ext As SldWorks.ModelDocExtension
    Dim sm As SldWorks.SketchManager
    Dim feat As SldWorks.Feature
    Dim fd As Object
    Dim bodies As Variant, edges As Variant
    Dim dxfPath As String, ok As Boolean
    Dim cfgNames As Variant, flatName As String
    Dim i As Integer
    Set swApp = Application.SldWorks
    Set Part = swApp.ActiveDoc
    Set fm = Part.FeatureManager
    Set ext = Part.Extension
    Set sm = Part.SketchManager
    Part.SelectByID2 "Front Plane", "PLANE", 0, 0, 0, False, 0, Nothing, 0
    sm.InsertSketch True
    sm.CreateCornerRectangle -0.03, -0.02, 0, 0.03, 0.02, 0
    sm.InsertSketch True
    Part.SelectByID2 "Sketch1", "SKETCH", 0, 0, 0, False, 0, Nothing, 0
    Part.EditSketch
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
    If Not IsEmpty(bodies) Then
        edges = bodies(0).GetEdges
        If Not IsEmpty(edges) Then
            edges(0).Select4 False, Nothing
            Set feat = fm.InsertSheetMetalEdgeFlange(1.5708, False, True, 0.002, False, False, 0, 0)
            If feat Is Nothing Then MsgBox "Edge flange: NOTHING" Else MsgBox "Edge flange: " & feat.Name
        End If
    End If
    cfgNames = Part.GetConfigurationNames
    flatName = ""
    For i = 0 To UBound(cfgNames)
        If Left(cfgNames(i), 12) = "Flat Pattern" Then flatName = cfgNames(i): Exit For
    Next i
    If flatName = "" Then MsgBox "No Flat Pattern config" Else _
        ok = Part.ShowConfiguration2(flatName): _
        dxfPath = Environ("TEMP") & "\spike_sm_v2.dxf": _
        ok = ext.ExportToDWG2(dxfPath, Part, 4, False, False, False, Nothing, Nothing, 1#): _
        MsgBox "ExportToDWG2 = " & ok
End Sub
"""


def main():
    p = argparse.ArgumentParser(description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--mode", choices=["com", "vba"], default="com")
    p.add_argument("--out", type=Path, default=None)
    p.add_argument("--keep-files", action="store_true")
    args = p.parse_args()
    if args.mode == "vba":
        out = Path(__file__).parent / "spike_sheetmetal_v2.bas"
        out.write_text(emit_vba(), encoding="utf-8")
        print(f"wrote {out}", file=sys.stderr)
        return 0
    pythoncom.CoInitialize()
    try:
        result = run(keep_files=args.keep_files)
    finally:
        pythoncom.CoUninitialize()
    payload = json.dumps(result, indent=2, default=str)
    if args.out is not None:
        args.out.write_text(payload, encoding="utf-8")
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(payload)
    return {"PASS": 0, "PARTIAL": 2, "FAIL": 1}.get(result.get("overall"), 1)


if __name__ == "__main__":
    raise SystemExit(main())
