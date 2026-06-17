"""Spike v0.2x / W63-lane1 — mate_reference creation via COM.

[authored seat-free; RUN ON A LIVE SEAT — W0 fires]

Probes the mate-reference API:
  Mode-A (quarantined): no swFmMateReference in swconst.tlb — skipped.
  Mode-B (primary path): select 1--3 entities with role-specific marks,
  then ``IModelDoc2.InsertMateReference()`` (callable-or-property guarded).

Geometry: a 40x30x10 mm block on the Front Plane (same archetype as
``_feature_spike_fixtures.build_block``). Entities:
  - primary:   +X face (normal=[1,0,0])  mark=1
  - secondary: a top edge                mark=2

Verdicts
--------
PASS    — MateReference node materializes, survives save->reopen.
PARTIAL — InsertMateReference returns ok but no node found.
FAIL    — all modes fail.

Usage
-----
    C:/Python314/python.exe spikes/v0_2x/spike_mate_reference.py --out report.json
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
from win32com.client import dynamic  # noqa: E402

from ai_sw_bridge.features.mate_reference import create_mate_reference  # noqa: E402
from spike_earlybind_persist import connect_running_sw, ensure_sw_module  # noqa: E402

BOX_W_M = 0.040
BOX_H_M = 0.030
BOX_D_M = 0.010

SW_DEFAULT_TEMPLATE_PART = 8


def _title(d: Any) -> Any:
    t = d.GetTitle
    return t() if callable(t) else t


def _build_block(doc: Any) -> dict[str, Any]:
    """Build a 40x30x10 mm box on the Front Plane (W62 archetype)."""
    if not doc.SelectByID("Front Plane", "PLANE", 0.0, 0.0, 0.0):
        return {"built": False, "error": "could not select Front Plane"}

    sk = doc.SketchManager
    sk.InsertSketch(True)
    seg = sk.CreateCornerRectangle(
        -BOX_W_M / 2, -BOX_H_M / 2, 0.0,
        BOX_W_M / 2, BOX_H_M / 2, 0.0,
    )
    if seg is None:
        sk.InsertSketch(True)
        return {"built": False, "error": "CreateCornerRectangle returned None"}
    sk.InsertSketch(True)

    fm = doc.FeatureManager
    base_args = (
        True, False, False, 0, 0, BOX_D_M, 0.0,
        False, False, False, False,
        0.0, 0.0, False, False, False, False,
        True, True, True, 0, 0.0,
    )
    try:
        feat = fm.FeatureExtrusion2(*base_args, False)
    except Exception:
        feat = fm.FeatureExtrusion2(*base_args)
    if feat is None:
        return {"built": False, "error": "FeatureExtrusion2 returned None"}
    return {"built": True, "feature_name": getattr(feat, "Name", None)}


def _count_feature_nodes(doc: Any) -> int:
    feats = doc.FeatureManager.GetFeatures(False)
    return len(feats) if feats else 0


def _type_name_of(node: Any) -> str:
    for attr in ("GetTypeName2", "GetTypeName"):
        try:
            _v = getattr(node, attr)
            return str(_v() if callable(_v) else _v)
        except Exception:
            continue
    return ""


def _find_plus_x_face(doc: Any) -> Any:
    """Find the face with normal closest to +X on the block."""
    try:
        bodies = doc.GetBodies2(0, True)
        if not bodies:
            return None
        body = bodies[0]
        faces = body.GetFaces()
        if not faces:
            return None
        for face in faces:
            try:
                surf = face.GetSurface()
                if surf is None:
                    continue
                is_plane_val = getattr(surf, "IsPlane", None)
                is_plane = is_plane_val() if callable(is_plane_val) else is_plane_val
                if not is_plane:
                    continue
                origin, normal = surf.PlaneParams
                nx, ny, nz = normal[0], normal[1], normal[2]
                if abs(nx - 1.0) < 0.01 and abs(ny) < 0.01 and abs(nz) < 0.01:
                    return face
            except Exception:
                continue
    except Exception:
        pass
    return None


def _find_top_edge(doc: Any) -> Any:
    """Find any edge on the top face (z-max) of the block."""
    try:
        bodies = doc.GetBodies2(0, True)
        if not bodies:
            return None
        body = bodies[0]
        edges = body.GetEdges()
        if not edges:
            return None
        return edges[0]
    except Exception:
        return None


def _make_face_ref_dict(face: Any, doc: Any) -> dict | None:
    """Build a minimal manifest-face dict from a live face entity."""
    try:
        surf = face.GetSurface()
        origin, normal = surf.PlaneParams
        return {
            "feature": "Boss-Extrude1",
            "role": "top",
            "normal": [normal[0], normal[1], normal[2]],
            "center": [origin[0], origin[1], origin[2]],
        }
    except Exception:
        return None


def _save_reopen(sw: Any, doc: Any) -> dict[str, Any]:
    """Save to a temp file, close, reopen, and check the feature tree."""
    tmp = Path(tempfile.gettempdir()) / "w63_materef_spike.sldprt"
    try:
        save_ok = doc.SaveAs3(str(tmp), 0, 2)
        if save_ok not in (0, True):
            return {"saved": False, "error": f"SaveAs3 returned {save_ok}"}
    except Exception as exc:
        return {"saved": False, "error": f"SaveAs3 raised {exc!r}"}

    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass

    try:
        doc2 = sw.OpenDoc(str(tmp), 1)
        if doc2 is None:
            return {"saved": True, "reopened": False, "error": "OpenDoc returned None"}
    except Exception as exc:
        return {"saved": True, "reopened": False, "error": f"OpenDoc raised {exc!r}"}

    feats = doc2.FeatureManager.GetFeatures(False)
    nodes_after = len(feats) if feats else 0
    mate_ref_found = False
    if feats:
        for node in feats:
            if _type_name_of(node) == "MateReference":
                mate_ref_found = True
                break
    return {
        "saved": True,
        "reopened": True,
        "node_count_after": nodes_after,
        "mate_reference_survived": mate_ref_found,
        "file": str(tmp),
    }


def run() -> dict[str, Any]:
    result: dict[str, Any] = {"binding": "late (dynamic dispatch)"}
    mod, info = ensure_sw_module()
    result["module_info"] = info

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
        build = _build_block(doc)
        result["block"] = build
        if not build.get("built"):
            return {**result, "overall": "FAIL", "reason": "block build failed"}

        before = _count_feature_nodes(doc)
        result["nodes_before"] = before

        plus_x_face = _find_plus_x_face(doc)
        top_edge = _find_top_edge(doc)
        result["plus_x_face_found"] = plus_x_face is not None
        result["top_edge_found"] = top_edge is not None

        entities = []
        if plus_x_face is not None:
            face_dict = _make_face_ref_dict(plus_x_face, doc)
            if face_dict is not None:
                entities.append({"ref": face_dict, "role": "primary"})

        feature = {
            "type": "mate_reference",
            "name": "MateRef-1",
            "entities": entities,
        }
        result["feature_spec"] = {
            "type": feature["type"],
            "entity_count": len(entities),
        }

        if not entities:
            return {**result, "overall": "FAIL", "reason": "no entities resolved for spike"}

        t0 = time.perf_counter()
        ok, note = create_mate_reference(doc, feature, {})
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        result["handler_ok"] = ok
        result["handler_note"] = note
        result["elapsed_ms"] = round(elapsed_ms, 2)

        after = _count_feature_nodes(doc)
        result["nodes_after"] = after
        result["node_delta"] = after - before

        mate_ref_found = False
        feats = doc.FeatureManager.GetFeatures(False)
        if feats:
            for node in feats:
                tn = _type_name_of(node)
                if tn == "MateReference":
                    mate_ref_found = True
                    break
        result["mate_reference_in_tree"] = mate_ref_found

        save_reopen = _save_reopen(sw, doc)
        result["save_reopen"] = save_reopen

        if ok and mate_ref_found and save_reopen.get("mate_reference_survived"):
            result["overall"] = "PASS"
        elif ok and mate_ref_found:
            result["overall"] = "PARTIAL"
            result["partial_reason"] = "node found but save/reopen failed"
        else:
            result["overall"] = "FAIL"
            result["fail_reason"] = note or "handler returned False"
    finally:
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass

    return result


def _scrub(o: Any) -> Any:
    if isinstance(o, dict):
        return {k: _scrub(v) for k, v in o.items() if k != "_val"}
    if isinstance(o, list):
        return [_scrub(v) for v in o]
    return o


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args()

    pythoncom.CoInitialize()
    try:
        result = run()
    finally:
        pythoncom.CoUninitialize()

    payload = json.dumps(
        _scrub(result), indent=2, default=lambda o: f"<{type(o).__name__}>"
    )
    if args.out is not None:
        args.out.write_text(payload, encoding="utf-8")
    else:
        print(payload)
    return {"PASS": 0, "PARTIAL": 2, "FAIL": 1}.get(result.get("overall"), 1)


if __name__ == "__main__":
    raise SystemExit(main())
