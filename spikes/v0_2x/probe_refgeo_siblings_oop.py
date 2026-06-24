"""W64 sibling audit — do the OTHER shipped ref-geo handlers wall OOP?

Companion to ``probe_existing_ref_axis_oop.py``. That probe confirmed
``mutate._create_ref_axis`` walls OOP on a bare-None SelectByID2 callout.
The static audit (mutate.py 677-1100) shows the bare-None callout is
ISOLATED to _create_ref_axis line 998; every sibling selection is either
the 5-arg ``doc.SelectByID`` (no callout arg) or the callout-FREE
``select_entity`` (typed ``IEntity.Select2(append, mark)`` — no callout
parameter exists in that signature). This probe CONFIRMS that empirically
on the live seat, end-to-end:

  C. _create_ref_point (face-centroid, durable face_ref) — select_entity path
  D. _create_ref_plane (normal-to-edge, durable edge_ref) — select_entity path
  E. select_entity() directly on a live face — the shared mechanism, isolated

Verdict per handler:
  CLEAN — materializes a node OOP (the bug does not reach it).
  WALLS — Type-mismatch / no materialization (would need the VARIANT fix too).

Usage:
    C:/Python314/python.exe spikes/v0_2x/probe_refgeo_siblings_oop.py
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # _feature_spike_fixtures

RESULTS_PATH = (
    Path(__file__).resolve().parents[1] / "_results" / "probe_refgeo_siblings_oop.json"
)

import pythoncom  # noqa: E402
from win32com.client import VARIANT  # noqa: E402

from _feature_spike_fixtures import build_block  # noqa: E402
from ai_sw_bridge.sw_com import get_sw_app  # noqa: E402
from ai_sw_bridge import mutate  # noqa: E402
from ai_sw_bridge.selection.live import capture_persist_id, select_entity  # noqa: E402
from ai_sw_bridge.selection._edge_ref import DurableEdgeRef  # noqa: E402

BOX_W_M = 0.040
BOX_H_M = 0.030
BOX_D_M = 0.010


def _null() -> Any:
    return VARIANT(pythoncom.VT_DISPATCH, None)


def _count_nodes(doc: Any) -> int:
    try:
        feats = doc.FeatureManager.GetFeatures(False)
        return len(feats) if feats else 0
    except Exception:
        return 0


def _type_name(node: Any) -> str | None:
    for attr in ("GetTypeName2", "GetTypeName"):
        try:
            m = getattr(node, attr)
            return str(m() if callable(m) else m)
        except Exception:
            continue
    return None


def _find_type(doc: Any, *needles: str) -> str | None:
    try:
        feats = doc.FeatureManager.GetFeatures(False) or []
    except Exception:
        return None
    for node in feats:
        t = _type_name(node)
        if t and any(n in t.lower() for n in needles):
            return t
    return None


def _pick(doc: Any, sel_type: str, x: float, y: float, z: float) -> Any:
    """Coordinate-pick one entity; return the live COM object (or None)."""
    try:
        doc.ClearSelection2(True)
        ok = doc.Extension.SelectByID2("", sel_type, x, y, z, False, 0, _null(), 0)
        if not ok:
            return None
        ent = doc.SelectionManager.GetSelectedObject6(1, -1)
        doc.ClearSelection2(True)
        return ent
    except Exception:
        return None


def _b64(b: bytes | None) -> str | None:
    if b is None:
        return None
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")


def _probe_ref_point(sw: Any) -> dict[str, Any]:
    """C: _create_ref_point via durable face_ref (face-centroid, type 4)."""
    out: dict[str, Any] = {"handler": "_create_ref_point", "path": "face_ref centroid"}
    doc = build_block(sw)
    try:
        before = _count_nodes(doc)
        # +X face of the centered block: x=+W/2, y=0, z=+D/2.
        face = _pick(doc, "FACE", BOX_W_M / 2, 0.0, BOX_D_M / 2)
        if face is None:
            return {**out, "verdict": "ERROR", "reason": "could not pick +X face"}
        pid = capture_persist_id(doc, face)
        out["persist_captured"] = pid is not None
        face_ref = {
            "normal": [1.0, 0.0, 0.0],
            "centroid": [BOX_W_M / 2, 0.0, BOX_D_M / 2],
            "area_mm2": BOX_H_M * BOX_D_M * 1e6,
            "persist_id": _b64(pid),
            "role_hint": "audit_plus_x_face",
        }
        ok, note = mutate._create_ref_point(doc, {}, {"face_ref": face_ref})
        after = _count_nodes(doc)
        out["handler_ok"] = ok
        out["handler_note"] = note
        out["node_delta"] = after - before
        out["node_type"] = _find_type(doc, "refpoint", "referencepoint")
        note_l = (note or "").lower()
        walled = "type mismatch" in note_l or "arg 8" in note_l
        if ok and out["node_type"]:
            out["verdict"] = "CLEAN"
        elif walled:
            out["verdict"] = "WALLS"
        else:
            out["verdict"] = "INCONCLUSIVE"
        return out
    finally:
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass


def _probe_ref_plane_normal_to_edge(sw: Any) -> dict[str, Any]:
    """D: _create_ref_plane normal-to-edge via durable edge_ref."""
    out: dict[str, Any] = {
        "handler": "_create_ref_plane",
        "path": "normal-to-edge edge_ref",
    }
    doc = build_block(sw)
    try:
        before = _count_nodes(doc)
        # A vertical edge at the +X/+Y corner of the centered block, running in Z.
        ex, ey = BOX_W_M / 2, BOX_H_M / 2
        edge = _pick(doc, "EDGE", ex, ey, BOX_D_M / 2)
        if edge is None:
            return {**out, "verdict": "ERROR", "reason": "could not pick corner edge"}
        pid = capture_persist_id(doc, edge)
        out["persist_captured"] = pid is not None
        edge_ref = DurableEdgeRef(
            persist_id=pid,
            start=(ex, ey, 0.0),
            end=(ex, ey, BOX_D_M),
            length=BOX_D_M,
            role_hint="audit_corner_edge",
        ).to_dict()
        ok, note = mutate._create_ref_plane(doc, {}, {"edge_ref": edge_ref})
        after = _count_nodes(doc)
        out["handler_ok"] = ok
        out["handler_note"] = note
        out["node_delta"] = after - before
        out["node_type"] = _find_type(doc, "refplane", "plane")
        note_l = (note or "").lower()
        walled = "type mismatch" in note_l or "arg 8" in note_l
        if ok and out["node_type"]:
            out["verdict"] = "CLEAN"
        elif walled:
            out["verdict"] = "WALLS"
        else:
            out["verdict"] = "INCONCLUSIVE"
        return out
    finally:
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass


def _probe_select_entity(sw: Any) -> dict[str, Any]:
    """E: select_entity() directly on a live face — the shared mechanism."""
    out: dict[str, Any] = {
        "mechanism": "select_entity -> IEntity.Select2 (callout-free)"
    }
    doc = build_block(sw)
    try:
        face = _pick(doc, "FACE", BOX_W_M / 2, 0.0, BOX_D_M / 2)
        if face is None:
            return {**out, "verdict": "ERROR", "reason": "could not pick face"}
        doc.ClearSelection2(True)
        r = select_entity(face)
        out["select_entity_ok"] = bool(r)
        out["verdict"] = "CLEAN" if r else "WALLS"
        return out
    finally:
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass


def run() -> dict[str, Any]:
    result: dict[str, Any] = {"probe_id": "W64_refgeo_siblings_oop_audit"}
    try:
        sw = get_sw_app()
    except Exception as exc:
        return {**result, "overall": "ERROR", "reason": f"cannot connect: {exc!r}"}

    result["ref_point"] = _probe_ref_point(sw)
    result["ref_plane_normal_to_edge"] = _probe_ref_plane_normal_to_edge(sw)
    result["select_entity_direct"] = _probe_select_entity(sw)

    verdicts = {
        "ref_point": result["ref_point"].get("verdict"),
        "ref_plane_normal_to_edge": result["ref_plane_normal_to_edge"].get("verdict"),
        "select_entity_direct": result["select_entity_direct"].get("verdict"),
    }
    result["verdicts"] = verdicts
    if all(v == "CLEAN" for v in verdicts.values()):
        result["overall"] = "ALL_CLEAN"
        result["finding"] = (
            "All siblings materialize OOP; select_entity is callout-safe. "
            "The bare-None callout bug is ISOLATED to _create_ref_axis."
        )
    elif any(v == "WALLS" for v in verdicts.values()):
        result["overall"] = "SOME_WALL"
        result["finding"] = f"A sibling also walls OOP: {verdicts}"
    else:
        result["overall"] = "MIXED"
        result["finding"] = f"Non-clean, non-wall result(s): {verdicts}"
    return result


def main() -> None:
    pythoncom.CoInitialize()
    try:
        result = run()
    finally:
        pythoncom.CoUninitialize()
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(
        json.dumps(result, indent=2, default=lambda o: f"<{type(o).__name__}>"),
        encoding="utf-8",
    )
    print(f"overall: {result.get('overall')}", file=sys.stderr)
    print(f"verdicts: {json.dumps(result.get('verdicts', {}))}", file=sys.stderr)
    print(f"finding: {result.get('finding')}", file=sys.stderr)
    print(f"results written to {RESULTS_PATH}", file=sys.stderr)


if __name__ == "__main__":
    main()
