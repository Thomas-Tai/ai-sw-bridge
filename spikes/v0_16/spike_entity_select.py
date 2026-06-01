"""Spike v0.16 - Epic B: entity-select wall (ref_point + rib/dome/wrap).

Probes typed body traversal + persist round-trip + IEntity.Select2 to crack
the entity-select wall that blocks F0 ref_point, F3 rib, F4 dome, F5 wrap.

Approach: doc.GetBodies2 -> body.GetFaces/GetVertices -> typed persist
round-trip (GetPersistReference3 + GetObjectByPersistReference3) -> live
entity -> IEntity.Select2(append, mark) -> drive Insert* features.

Usage:
    python spikes/v0_16/spike_entity_select.py --out spikes/v0_16/_results/entity_select.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
_V15 = Path(__file__).resolve().parents[1] / "v0_15"
_V16 = Path(__file__).resolve().parent
sys.path.insert(0, str(_PKG_ROOT))
sys.path.insert(0, str(_V15))
sys.path.insert(0, str(_V16))

import pythoncom
import win32com.client as w32

from ai_sw_bridge.com.earlybind import typed, typed_qi, typed_extension
from ai_sw_bridge.com.sw_type_info import wrapper_module

from spike_earlybind_persist import connect_running_sw, ensure_sw_module


SW_DEFAULT_TEMPLATE_PART = 8


def _title(doc):
    t = doc.GetTitle
    return t() if callable(t) else t


def _try_close(sw, doc):
    try:
        sw.CloseDoc(_title(doc))
    except Exception:
        pass


def _capture(fn):
    try:
        result = fn()
        return {"status": "OK"}, result
    except Exception as exc:
        return {"status": "ERR", "type": type(exc).__name__,
                "message": str(exc)[:200]}, None


def _as_list(obj):
    if obj is None:
        return []
    if isinstance(obj, (list, tuple)):
        return list(obj)
    return [obj]


def _build_box(sw):
    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.1, 0.1)
    if doc is None:
        raise RuntimeError("NewDocument returned None")
    doc.ClearSelection2(True)
    doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
    doc.InsertSketch2(True)
    sk = doc.SketchManager
    sk.CreateCornerRectangle(-0.02, -0.02, 0, 0.02, 0.02, 0)
    doc.InsertSketch2(False)
    doc.ClearSelection2(True)
    doc.SelectByID("Sketch1", "SKETCH", 0, 0, 0)
    fm = doc.FeatureManager
    fm.FeatureExtrusion3(
        True, False, False, 0, 0, 0.02, 0.0,
        False, False, False, False, 0.0, 0.0,
        False, False, False, False, True, True, True, 0, 0, False,
    )
    doc.ClearSelection2(True)
    return doc


def _get_body_entities(doc, mod):
    """Get live face/edge/vertex entities via body traversal + persist round-trip."""
    out = {"faces": [], "edges": [], "vertices": []}
    rec, bodies = _capture(lambda: doc.GetBodies2(0, True))
    if rec["status"] != "OK" or not bodies:
        out["bodies_error"] = rec
        return out
    body_list = _as_list(bodies)
    out["body_count"] = len(body_list)
    if not body_list:
        return out
    body = body_list[0]
    # Get raw entities from body
    rec_f, faces_raw = _capture(lambda: body.GetFaces())
    rec_e, edges_raw = _capture(lambda: body.GetEdges())
    rec_v, verts_raw = _capture(lambda: body.GetVertices())
    out["raw_faces"] = len(_as_list(faces_raw)) if rec_f["status"] == "OK" else rec_f
    out["raw_edges"] = len(_as_list(edges_raw)) if rec_e["status"] == "OK" else rec_e
    out["raw_vertices"] = len(_as_list(verts_raw)) if rec_v["status"] == "OK" else rec_v
    # Persist round-trip to get live entities
    ext = typed_extension(doc, module=mod)
    for label, raw_list in [("faces", faces_raw), ("edges", edges_raw), ("vertices", verts_raw)]:
        entities = _as_list(raw_list)
        live = []
        for ei, e in enumerate(entities):
            try:
                pid = ext.GetPersistReference3(e)
                if pid is None:
                    continue
                obj_result = ext.GetObjectByPersistReference3(pid)
                obj = obj_result[0] if isinstance(obj_result, tuple) else obj_result
                if obj is not None and not isinstance(obj, int):
                    live.append(obj)
            except Exception:
                pass
        out[label] = live
    out["live_faces"] = len(out["faces"])
    out["live_edges"] = len(out["edges"])
    out["live_vertices"] = len(out["vertices"])
    return out


def _probe_select2(entities, label, mod):
    """Try Select2 on each entity. Return per-entity results."""
    results = []
    for i, ent in enumerate(entities[:4]):  # probe first 4
        entry = {"index": i, "type": type(ent).__name__}
        # Try typed wrap as IEntity
        try:
            ient = typed(ent, "IEntity", module=mod)
            entry["typed_iface"] = "IEntity"
        except Exception as e:
            entry["typed_error"] = str(e)[:100]
            results.append(entry)
            continue
        # Try Select2(False, 0)
        try:
            sel = ient.Select2(False, 0)
            entry["select2_0"] = sel
        except Exception as e:
            entry["select2_0_err"] = f"{type(e).__name__}: {str(e)[:100]}"
        # Try Select2(True, 0)
        try:
            sel = ient.Select2(True, 0)
            entry["select2_append"] = sel
        except Exception as e:
            entry["select2_append_err"] = f"{type(e).__name__}: {str(e)[:100]}"
        # Try Select4 variants if available
        for method_name in ("Select4", "Select3"):
            m = getattr(ient, method_name, None)
            if m is not None:
                try:
                    sel = m(False, 0, None)
                    entry[f"{method_name}_0"] = sel
                except Exception as e:
                    entry[f"{method_name}_err"] = str(e)[:100]
        results.append(entry)
    return results


def _probe_latebound_select(entities, label):
    """Try Select2 on late-bound entities (no typed wrap)."""
    results = []
    for i, ent in enumerate(entities[:4]):
        entry = {"index": i}
        try:
            sel = ent.Select2(False, 0)
            entry["select2"] = sel
        except Exception as e:
            entry["select2_err"] = f"{type(e).__name__}: {str(e)[:100]}"
        results.append(entry)
    return results


def _probe_ref_point(doc, fm, vertex_entities, mod):
    """Try InsertReferencePoint with a pre-selected vertex."""
    out = {}
    if not vertex_entities:
        out["error"] = "no live vertices"
        return out
    v = vertex_entities[0]
    try:
        ient = typed(v, "IEntity", module=mod)
        doc.ClearSelection2(True)
        sel = ient.Select2(False, 0)
        out["vertex_select2"] = sel
    except Exception as e:
        out["select_error"] = str(e)[:200]
        return out
    # InsertReferencePoint(5, 0, 0.0, 1)
    try:
        feat = fm.InsertReferencePoint(5, 0, 0.0, 1)
        if isinstance(feat, tuple):
            feat = feat[0] if len(feat) == 1 else None
        out["feature"] = str(feat)[:100] if feat is not None else "None"
        out["materialized"] = feat is not None and not isinstance(feat, (int, bool))
    except Exception as e:
        out["insert_error"] = str(e)[:200]
    return out


def _probe_dome(doc, face_entities, mod):
    """Try InsertDome with a pre-selected face."""
    out = {}
    if not face_entities:
        out["error"] = "no live faces"
        return out
    f = face_entities[0]
    try:
        ient = typed(f, "IEntity", module=mod)
        doc.ClearSelection2(True)
        sel = ient.Select2(False, 0)
        out["face_select2"] = sel
    except Exception as e:
        out["select_error"] = str(e)[:200]
        return out
    # InsertDome(Height, FlipDir, Elliptical)
    try:
        feat = doc.InsertDome(0.005, False, False)
        out["feature"] = str(feat)[:100] if feat is not None else "None"
        out["materialized"] = feat is not None and not isinstance(feat, (int, bool))
    except Exception as e:
        out["insert_error"] = str(e)[:200]
    return out


def _probe_rib(doc, fm, face_entities, mod):
    """Try InsertRib with a pre-selected face."""
    out = {}
    if not face_entities:
        out["error"] = "no live faces"
        return out
    f = face_entities[0]
    try:
        ient = typed(f, "IEntity", module=mod)
        doc.ClearSelection2(True)
        sel = ient.Select2(False, 0)
        out["face_select2"] = sel
    except Exception as e:
        out["select_error"] = str(e)[:200]
        return out
    # InsertRib(Bool, Bool, Double, Long, Bool, Bool, Bool, Double, Bool, Bool)
    try:
        feat = fm.InsertRib(True, False, 0.005, 0, True, False, False, 0.0, True, False)
        out["feature"] = str(feat)[:100] if feat is not None else "None"
        out["materialized"] = feat is not None and not isinstance(feat, (int, bool))
    except Exception as e:
        out["insert_error"] = str(e)[:200]
    return out


def _probe_wrap(doc, fm, face_entities, mod):
    """Try InsertWrapFeature2 with a pre-selected face."""
    out = {}
    if not face_entities:
        out["error"] = "no live faces"
        return out
    f = face_entities[0]
    try:
        ient = typed(f, "IEntity", module=mod)
        doc.ClearSelection2(True)
        sel = ient.Select2(False, 0)
        out["face_select2"] = sel
    except Exception as e:
        out["select_error"] = str(e)[:200]
        return out
    # InsertWrapFeature2(Type, Thickness, FlipDir, DraftAngle, DraftType)
    try:
        feat = fm.InsertWrapFeature2(0, 0.001, False, 0.0, 0)
        out["feature"] = str(feat)[:100] if feat is not None else "None"
        out["materialized"] = feat is not None and not isinstance(feat, (int, bool))
    except Exception as e:
        out["insert_error"] = str(e)[:200]
    return out


def run():
    result = {"spike": "entity_select_epic_B"}
    print("[spike] connecting to running SW...")
    mod = wrapper_module()
    if mod is None:
        mod, info = ensure_sw_module()
        result["module_fallback"] = info
    result["module"] = getattr(mod, "__name__", str(mod))
    sw = connect_running_sw()
    print("[spike] building box...")
    doc = _build_box(sw)
    title = _title(doc)
    print(f"[spike] box built: {title}")
    try:
        fm = doc.FeatureManager
        # Phase 1: body traversal + entity acquisition
        print("[spike] body traversal...")
        entities = _get_body_entities(doc, mod)
        result["body_entities"] = {k: (v if not isinstance(v, list) else f"<{len(v)} entities>") for k, v in entities.items()}
        faces = entities.get("faces", [])
        edges = entities.get("edges", [])
        vertices = entities.get("vertices", [])
        print(f"  live: {len(faces)} faces, {len(edges)} edges, {len(vertices)} vertices")
        # Phase 2: Select2 probes on live entities
        print("[spike] Select2 probes (typed IEntity)...")
        if faces:
            result["face_select2_typed"] = _probe_select2(faces, "faces", mod)
        if edges:
            result["edge_select2_typed"] = _probe_select2(edges, "edges", mod)
        if vertices:
            result["vertex_select2_typed"] = _probe_select2(vertices, "vertices", mod)
        # Phase 2b: late-bound Select2 (no typed wrap)
        print("[spike] Select2 probes (late-bound)...")
        rec_f, faces_raw = _capture(lambda: doc.GetBodies2(0, True))
        if rec_f["status"] == "OK" and faces_raw:
            body = _as_list(faces_raw)[0]
            rec_ff, ff = _capture(lambda: body.GetFaces())
            rec_vv, vv = _capture(lambda: body.GetVertices())
            if rec_ff["status"] == "OK" and ff:
                result["face_select2_late"] = _probe_latebound_select(_as_list(ff), "faces")
            if rec_vv["status"] == "OK" and vv:
                result["vertex_select2_late"] = _probe_latebound_select(_as_list(vv), "vertices")
        # Phase 3: feature creation with pre-selected entities
        print("[spike] feature creation probes...")
        # Check if any Select2 succeeded
        face_sel_ok = False
        for entry in result.get("face_select2_typed", []):
            if entry.get("select2_0") is True:
                face_sel_ok = True
                break
        vert_sel_ok = False
        for entry in result.get("vertex_select2_typed", []):
            if entry.get("select2_0") is True:
                vert_sel_ok = True
                break
        result["face_selection_achievable"] = face_sel_ok
        result["vertex_selection_achievable"] = vert_sel_ok
        # ref_point
        print("  ref_point...")
        result["ref_point"] = _probe_ref_point(doc, fm, vertices, mod)
        # dome
        print("  dome...")
        result["dome"] = _probe_dome(doc, faces, mod)
        # rib
        print("  rib...")
        result["rib"] = _probe_rib(doc, fm, faces, mod)
        # wrap
        print("  wrap...")
        result["wrap"] = _probe_wrap(doc, fm, faces, mod)
        # Verdict
        greens = []
        for kind in ("ref_point", "dome", "rib", "wrap"):
            if result.get(kind, {}).get("materialized"):
                greens.append(kind)
        result["green_kinds"] = greens
        if greens:
            result["overall"] = "GREEN"
            result["interpretation"] = f"{len(greens)} kind(s) materialized: {greens}. W0 wires + advertises."
        elif face_sel_ok or vert_sel_ok:
            result["overall"] = "PARTIAL"
            result["interpretation"] = "Selection achievable but features did not materialize. Tuning needed."
        else:
            result["overall"] = "WALL"
            result["interpretation"] = "Entity selection wall persists even with typed persist round-trip."
    finally:
        _try_close(sw, doc)
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    pythoncom.CoInitialize()
    try:
        result = run()
    finally:
        pythoncom.CoUninitialize()
    def _safe(o):
        if hasattr(o, "_oleobj_"): return f"<COM {type(o).__name__}>"
        return str(o)
    payload = json.dumps(result, indent=2, default=_safe)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload, encoding="utf-8")
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(payload)
    return {"GREEN": 0, "PARTIAL": 2, "WALL": 2, "FAIL": 1}.get(result.get("overall"), 1)


if __name__ == "__main__":
    raise SystemExit(main())
