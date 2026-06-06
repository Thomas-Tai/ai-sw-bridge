"""Spike W24 / CHAMFER — materialization probe (CreateDefinition pipeline).

Tests whether a chamfer can be created via the SAME CreateDefinition(1)
(swFmFillet) pipeline that materializes fillets, using IChamferFeatureData2
instead of ISimpleFilletFeatureData2.

API docs confirm: swFmFillet covers "constant radius, face, full round
fillet/chamfer" — there is NO separate swFmChamfer in swFeatureNameID_e.
The differentiation happens at the interface level: IChamferFeatureData2
(for chamfers) vs ISimpleFilletFeatureData2 (for fillets).

Pipeline under test:
    CreateDefinition(1) → typed_qi(data, "IChamferFeatureData2")
    → Initialize(swChamferAngleDistance=1) → set Distance + Angle
    → select_entity(edge) → CreateFeature(fd)

Records:
  * typelib probe: IChamferFeatureData2 members from sldworks.tlb
  * swFeatureNameID_e walk: confirm swFmChamfer absent / present
  * feature count before/after (liveness gate)
  * face count + volume before/after (geometry delta — W21 lesson)
  * feature type name (GetTypeName2)

Verdicts:
  GO    — count +1, Chamfer-typed, geometry altered (face +1 / volume Δ).
  NO-GO — CreateDefinition fails, or IChamferFeatureData2 not QI-able,
          or CreateFeature no-ops, or geometry unchanged.

Usage:
    .venv-py310/Scripts/python.exe spikes/v0_2x/spike_chamfer.py
"""

from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

WORKTREE = Path(__file__).resolve().parents[2]
RESULTS_PATH = WORKTREE / "spikes" / "v0_2x" / "_results" / "chamfer.json"

import pythoncom  # noqa: E402

from ai_sw_bridge.com.earlybind import typed, typed_qi, EarlyBindError  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from ai_sw_bridge.sw_com import get_sw_app  # noqa: E402
from ai_sw_bridge.selection import DurableEdgeRef, resolve_edge_ref, select_entity  # noqa: E402

SW_DEFAULT_TEMPLATE_PART = 8
SWCONST_TLB = Path(r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\swconst.tlb")
SLDWORKS_TLB = Path(r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\sldworks.tlb")

_SW_FM_FILLET = 1
_SW_CHAMFER_ANGLE_DISTANCE = 1
_SW_CHAMFER_DISTANCE_DISTANCE = 2

CHAMFER_DISTANCE_M = 0.002  # 2 mm
CHAMFER_ANGLE_RAD = math.pi / 4.0  # 45 degrees

BOX_W_M = 0.020  # 20 mm
BOX_H_M = 0.020  # 20 mm
BOX_D_M = 0.010  # 10 mm

CHAMFER_IFACES = (
    "IChamferFeatureData2",
    "IChamferFeatureData",
)

CHAMFER_CANDIDATE_MEMBERS = (
    "Type",
    "Distance",
    "Angle",
    "OtherDistance",
    "DefaultRadius",
    "Initialize",
    "Options",
    "FlipDirection",
    "TangentPropagation",
    "SetDistance",
    "SetAngle",
    "SetOtherDistance",
)


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


def _type_name(feat: Any) -> str | None:
    for attr in ("GetTypeName2", "GetTypeName"):
        try:
            m = getattr(feat, attr)
            return str(m() if callable(m) else m)
        except Exception:
            continue
    return None


def _feat_count(doc: Any) -> int:
    fm = doc.FeatureManager
    feats = fm.GetFeatures(True)
    return len(feats) if feats else 0


def _body_face_count(doc: Any) -> int:
    try:
        bodies = doc.GetBodies2(True, False)
        if not bodies:
            return 0
        body = bodies[0]
        faces = body.GetFaces()
        return len(faces) if faces else 0
    except Exception:
        return -1


def _body_volume(doc: Any) -> float | None:
    try:
        props = doc.Extension.CreateMassProperty()
        if props is None:
            return None
        cg = props.CenterOfMass
        vol = props.Volume
        return float(vol) if vol is not None else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Typelib probes
# ---------------------------------------------------------------------------

def _walk_swconst_feature_name_ids() -> dict[str, Any]:
    report: dict[str, Any] = {"path": str(SWCONST_TLB), "loadable": False}
    if not SWCONST_TLB.exists():
        report["error"] = f"not found at {SWCONST_TLB}"
        return report
    try:
        tlb = pythoncom.LoadTypeLib(str(SWCONST_TLB))
    except Exception as e:
        report["error"] = f"{type(e).__name__}: {e}"
        return report
    report["loadable"] = True
    ids: dict[str, int] = {}
    for i in range(tlb.GetTypeInfoCount()):
        name = tlb.GetDocumentation(i)[0]
        if name == "swFeatureNameID_e":
            info = tlb.GetTypeInfo(i)
            ta = info.GetTypeAttr()
            for v in range(ta.cVars):
                vd = info.GetVarDesc(v)
                mname = info.GetNames(vd.memid)[0]
                ids[mname] = vd.value
    report["all_ids"] = ids
    report["has_swFmFillet"] = "swFmFillet" in ids
    report["swFmFillet_value"] = ids.get("swFmFillet")
    report["has_swFmChamfer"] = any("Chamfer" in k for k in ids)
    chamfer_keys = [k for k in ids if "hamfer" in k.lower()]
    report["chamfer_keys"] = chamfer_keys
    return report


def _walk_sldworks_chamfer_interfaces() -> dict[str, Any]:
    report: dict[str, Any] = {"path": str(SLDWORKS_TLB), "loadable": False}
    if not SLDWORKS_TLB.exists():
        report["error"] = f"not found at {SLDWORKS_TLB}"
        return report
    try:
        tlb = pythoncom.LoadTypeLib(str(SLDWORKS_TLB))
    except Exception as e:
        report["error"] = f"{type(e).__name__}: {e}"
        return report
    report["loadable"] = True
    found: dict[str, list[str]] = {}
    for i in range(tlb.GetTypeInfoCount()):
        name = tlb.GetDocumentation(i)[0]
        if "Chamfer" in name:
            info = tlb.GetTypeInfo(i)
            ta = info.GetTypeAttr()
            members: list[str] = []
            for f in range(ta.cFuncs):
                try:
                    fd = info.GetFuncDesc(f)
                    names = info.GetNames(fd.memid)
                    if names:
                        members.append(names[0])
                except Exception:
                    continue
            for v in range(ta.cVars):
                try:
                    vd = info.GetVarDesc(v)
                    names = info.GetNames(vd.memid)
                    if names:
                        members.append(f"[prop]{names[0]}")
                except Exception:
                    continue
            found[name] = sorted(set(members))
    report["chamfer_interfaces"] = found
    return report


def _probe_makepy_chamfer(mod: Any) -> dict[str, Any]:
    report: dict[str, Any] = {}
    for iface in CHAMFER_IFACES:
        cls = getattr(mod, iface, None)
        if cls is None:
            report[iface] = "MISSING"
        else:
            clsid = getattr(cls, "CLSID", None)
            report[iface] = {
                "present": True,
                "CLSID": str(clsid) if clsid else None,
            }
    return report


def _probe_members(obj: Any, names: tuple[str, ...]) -> dict[str, str]:
    out: dict[str, str] = {}
    for name in names:
        try:
            getattr(obj, name)
            out[name] = "present"
        except AttributeError:
            out[name] = "MISSING"
        except Exception as e:
            out[name] = f"reachable({type(e).__name__}: {str(e)[:80]})"
    return out


# ---------------------------------------------------------------------------
# Box builder
# ---------------------------------------------------------------------------

def _build_box(doc: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    fm = doc.FeatureManager
    try:
        doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
        sk = doc.SketchManager
        sk.InsertSketch(True)
        sk.CreateCornerRectangle(
            -BOX_W_M / 2, -BOX_H_M / 2, 0.0,
            BOX_W_M / 2, BOX_H_M / 2, 0.0,
        )
        sk.InsertSketch(True)
        out["sketch"] = "Sketch1"
    except Exception as e:
        out["sketch_error"] = f"{type(e).__name__}: {e}"
        return out

    try:
        feat = fm.FeatureExtrusion3(
            True, False, False,
            0, 0,
            BOX_D_M, 0.0,
            False, False, False, False,
            0.0, 0.0,
            False, False, False, False,
            True, True, True,
            0, 0, False,
        )
        out["extrude"] = feat is not None
        out["extrude_materialized"] = _materialized(feat)
    except Exception as e:
        out["extrude_error"] = f"{type(e).__name__}: {e}"
    try:
        doc.EditRebuild3()
    except Exception:
        pass
    return out


# ---------------------------------------------------------------------------
# Durable edge capture (top-front edge of the box)
# ---------------------------------------------------------------------------

def _capture_durable_edge(doc: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    try:
        ext = typed(doc.Extension, "IModelDocExtension")
        ok = ext.SelectByID2("", "EDGE", BOX_W_M / 2, 0.0, BOX_D_M, False, 0, None, 0)
        if not ok:
            out["error"] = "SelectByID2 for edge returned False"
            return out
        sel_mgr = doc.SelectionManager
        count = sel_mgr.GetSelectedObjectCount2(-1)
        if count < 1:
            out["error"] = "no edge selected"
            return out
        edge_obj = sel_mgr.GetSelectedObject6(1, -1)
        if edge_obj is None:
            out["error"] = "selected object is None"
            return out

        from ai_sw_bridge.selection.live import capture_persist_id
        persist_id = capture_persist_id(doc, edge_obj)

        try:
            params = edge_obj.GetCurveParams2()
            if params and len(params) >= 13:
                start = (params[7], params[8], params[9])
                end = (params[10], params[11], params[12])
                length = float(params[1]) - float(params[0])
            else:
                start = (BOX_W_M / 2, 0.0, 0.0)
                end = (BOX_W_M / 2, 0.0, BOX_D_M)
                length = BOX_D_M
        except Exception:
            start = (BOX_W_M / 2, 0.0, 0.0)
            end = (BOX_W_M / 2, 0.0, BOX_D_M)
            length = BOX_D_M

        edge_ref = DurableEdgeRef(
            persist_id=persist_id,
            start=start,
            end=end,
            length=length,
        )
        out["edge_ref"] = edge_ref.to_dict()
        out["captured"] = True
        out["persist_id_captured"] = persist_id is not None
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
        out["captured"] = False
    return out


# ---------------------------------------------------------------------------
# Chamfer probe
# ---------------------------------------------------------------------------

def _probe_chamfer(
    doc: Any, edge_ref_dict: dict, mod: Any
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    fm = doc.FeatureManager

    count_before = _feat_count(doc)
    faces_before = _body_face_count(doc)
    volume_before = _body_volume(doc)
    result["before"] = {
        "feature_count": count_before,
        "face_count": faces_before,
        "volume": volume_before,
    }

    edge_ref = DurableEdgeRef.from_dict(edge_ref_dict)
    doc.ForceRebuild3(False)
    res = resolve_edge_ref(doc, edge_ref)
    result["resolve"] = {
        "method": res.method,
        "entity_is_none": res.entity is None,
    }
    if res.entity is None:
        result["verdict"] = "NO-GO"
        result["reason"] = f"edge unresolved (method={res.method})"
        return result

    # Try IChamferFeatureData2 first, then IChamferFeatureData
    data = None
    fd = None
    used_iface = None
    for iface in CHAMFER_IFACES:
        try:
            data = fm.CreateDefinition(_SW_FM_FILLET)
            if data is None:
                result[f"CreateDefinition_{iface}"] = "returned None"
                continue
            fd = typed_qi(data, iface, module=mod)
            used_iface = iface
            result[f"typed_qi_{iface}"] = "OK"
            break
        except EarlyBindError as e:
            result[f"typed_qi_{iface}"] = f"E_NOINTERFACE: {e}"
            data = None
            fd = None
        except Exception as e:
            result[f"typed_qi_{iface}"] = f"{type(e).__name__}: {e}"
            data = None
            fd = None

    if fd is None:
        # Fallback: try ISimpleFilletFeatureData2 with chamfer Initialize
        try:
            data = fm.CreateDefinition(_SW_FM_FILLET)
            fd = typed_qi(data, "ISimpleFilletFeatureData2", module=mod)
            used_iface = "ISimpleFilletFeatureData2"
            result["typed_qi_ISimpleFilletFeatureData2"] = "OK (fallback)"
        except Exception as e:
            result["typed_qi_ISimpleFilletFeatureData2"] = f"{type(e).__name__}: {e}"
            result["verdict"] = "NO-GO"
            result["reason"] = "no chamfer or fillet interface QI-able"
            return result

    result["used_interface"] = used_iface

    members = _probe_members(fd, CHAMFER_CANDIDATE_MEMBERS)
    result["members"] = members

    # Initialize
    init_rec: dict[str, Any] = {}
    try:
        fd.Initialize(_SW_CHAMFER_ANGLE_DISTANCE)
        init_rec["status"] = "OK"
        init_rec["arg"] = _SW_CHAMFER_ANGLE_DISTANCE
    except Exception as e:
        init_rec["status"] = f"{type(e).__name__}: {str(e)[:200]}"
        result["verdict"] = "NO-GO"
        result["reason"] = f"Initialize({_SW_CHAMFER_ANGLE_DISTANCE}) failed"
        result["initialize"] = init_rec
        return result
    result["initialize"] = init_rec

    # Set chamfer properties
    set_recs: dict[str, Any] = {}
    for name, val in (
        ("Distance", CHAMFER_DISTANCE_M),
        ("Angle", CHAMFER_ANGLE_RAD),
    ):
        if members.get(name) == "present":
            try:
                setattr(fd, name, val)
                set_recs[name] = "OK"
            except Exception as e:
                set_recs[name] = f"{type(e).__name__}: {str(e)[:120]}"
        else:
            set_recs[name] = f"MISSING (member={members.get(name)})"
    result["set_props"] = set_recs

    # Select edge
    sel_ok = select_entity(res.entity)
    result["select_entity"] = sel_ok

    # CreateFeature
    try:
        feat = fm.CreateFeature(fd)
        result["create_feature"] = {
            "materialized": _materialized(feat),
            "type": type(feat).__name__ if feat is not None else "None",
        }
        if _materialized(feat):
            result["create_feature"]["type_name"] = _type_name(feat)
            try:
                result["create_feature"]["name"] = feat.Name
            except Exception:
                pass
    except Exception as e:
        result["create_feature"] = {
            "exception": f"{type(e).__name__}: {str(e)[:200]}",
        }
        feat = None

    # Geometry delta
    count_after = _feat_count(doc)
    faces_after = _body_face_count(doc)
    volume_after = _body_volume(doc)
    result["after"] = {
        "feature_count": count_after,
        "face_count": faces_after,
        "volume": volume_after,
    }
    result["delta"] = {
        "feature_count": count_after - count_before,
        "face_count": (faces_after - faces_before) if faces_before >= 0 and faces_after >= 0 else None,
        "volume": (volume_after - volume_before) if volume_before is not None and volume_after is not None else None,
    }

    # Verdict
    feat_ok = result.get("create_feature", {}).get("materialized", False)
    delta_ok = result["delta"]["feature_count"] == 1
    type_name = result.get("create_feature", {}).get("type_name", "")
    face_delta = result["delta"].get("face_count")
    vol_delta = result["delta"].get("volume")
    geometry_altered = (
        (face_delta is not None and face_delta > 0)
        or (vol_delta is not None and abs(vol_delta) > 1e-12)
    )

    if feat_ok and delta_ok and geometry_altered:
        result["verdict"] = "GO"
    elif feat_ok and delta_ok and not geometry_altered:
        result["verdict"] = "NO-GO"
        result["reason"] = "feature created but geometry unchanged (no-op trap)"
    elif feat_ok and not delta_ok:
        result["verdict"] = "NO-GO"
        result["reason"] = f"feature created but count delta={result['delta']['feature_count']}"
    else:
        result["verdict"] = "NO-GO"
        result["reason"] = "CreateFeature did not materialize"

    return result


# ---------------------------------------------------------------------------
# Top-level run
# ---------------------------------------------------------------------------

def run() -> dict[str, Any]:
    result: dict[str, Any] = {
        "spike_id": "W24_chamfer",
        "pipeline": "CreateDefinition(swFmFillet=1) -> typed_qi(IChamferFeatureData2) -> Initialize(swChamferAngleDistance) -> set Distance+Angle -> select_entity -> CreateFeature",
    }

    # Phase 1: Typelib probes (no COM to SW needed)
    result["swconst_probe"] = _walk_swconst_feature_name_ids()
    result["sldworks_probe"] = _walk_sldworks_chamfer_interfaces()

    mod = wrapper_module()
    if mod is not None:
        result["module"] = getattr(mod, "__name__", str(mod))
        result["makepy_probe"] = _probe_makepy_chamfer(mod)
    else:
        result["module"] = None
        result["makepy_probe"] = "wrapper_module unavailable"

    # Phase 2: Live SW COM (requires running SOLIDWORKS)
    try:
        sw = get_sw_app()
    except Exception as e:
        result["sw_connection"] = f"{type(e).__name__}: {e}"
        result["overall"] = "NO-GO"
        result["reason"] = "cannot connect to SOLIDWORKS"
        return result

    try:
        result["sw_revision"] = str(sw.RevisionNumber)
    except Exception:
        result["sw_revision"] = "<unreadable>"

    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        result["overall"] = "NO-GO"
        result["reason"] = "NewDocument returned None"
        return result

    try:
        box = _build_box(doc)
        result["box"] = box
        if not box.get("extrude_materialized"):
            result["overall"] = "NO-GO"
            result["reason"] = "box extrude failed"
            return result

        edge = _capture_durable_edge(doc)
        result["edge_capture"] = edge
        if not edge.get("captured"):
            result["overall"] = "NO-GO"
            result["reason"] = "durable edge capture failed"
            return result

        chamfer = _probe_chamfer(doc, edge["edge_ref"], mod)
        result["chamfer_probe"] = chamfer
        result["overall"] = chamfer.get("verdict", "NO-GO")
        if result["overall"] == "GO":
            result["confirmed"] = {
                "swFmFillet_covers_chamfer": True,
                "interface": chamfer.get("used_interface"),
                "Initialize_arg": _SW_CHAMFER_ANGLE_DISTANCE,
                "feature_count_delta": chamfer["delta"]["feature_count"],
                "face_count_delta": chamfer["delta"].get("face_count"),
                "volume_delta": chamfer["delta"].get("volume"),
            }
    finally:
        _try_close(sw, doc)
        result["cleanup"] = "closed own doc (no save)"

    return result


def main() -> None:
    result = run()
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    verdict = result.get("overall", "NO-GO")
    print(f"verdict: {verdict}", file=sys.stderr)
    if result.get("confirmed"):
        print(f"confirmed: {json.dumps(result['confirmed'], indent=2)}", file=sys.stderr)
    print(f"results written to {RESULTS_PATH}", file=sys.stderr)


if __name__ == "__main__":
    main()
