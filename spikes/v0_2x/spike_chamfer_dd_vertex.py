"""Seat-proof — chamfer ``distance_distance`` + ``vertex`` modes (LIVE seat).

Fires the PRODUCTION handler ``mutate._create_chamfer(doc, feature, target)``
in the two new closed-form modes added this session, each on a FRESH box so the
topology probes are independent:

  * distance_distance — EDGE target (captured durable ref); d1=2mm / d2=3mm.
  * vertex            — VERTEX target {'point':[x,y,z]} mm; d1=d2=d3=2mm at a
                        top corner of the box.

A chamfer REMOVES a corner, so the witness is ΔVol < 0 AND ΔFaces > 0 (a new
bevel face).  GREEN iff BOTH modes materialize and alter geometry.

Usage::

    C:/Python314/python.exe spikes/v0_2x/spike_chamfer_dd_vertex.py
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

from ai_sw_bridge.com.earlybind import typed  # noqa: E402
from ai_sw_bridge.sw_com import get_sw_app  # noqa: E402
from ai_sw_bridge.selection import DurableEdgeRef  # noqa: E402
from ai_sw_bridge.features import verify  # noqa: E402
from ai_sw_bridge import mutate  # noqa: E402

RESULTS_PATH = Path(__file__).resolve().parents[2] / "spikes" / "v0_2x" / "_results" / "chamfer_dd_vertex.json"

SW_DEFAULT_TEMPLATE_PART = 8
BOX_W_M = 0.020  # x: -10..10 mm
BOX_H_M = 0.020  # y: -10..10 mm
BOX_D_M = 0.010  # z:   0..10 mm


def _title(d: Any) -> Any:
    t = d.GetTitle
    return t() if callable(t) else t


def _try_close(sw: Any, doc: Any) -> None:
    try:
        sw.CloseDoc(_title(doc))
    except Exception:
        pass


def _face_count(doc: Any) -> int:
    try:
        bodies = doc.GetBodies2(True, False)
        if not bodies:
            return -1
        faces = bodies[0].GetFaces()
        return len(faces) if faces else 0
    except Exception:
        return -1


def _volume(doc: Any) -> float | None:
    try:
        props = doc.Extension.CreateMassProperty()
        return float(props.Volume) if props is not None else None
    except Exception:
        return None


def _build_box(sw: Any) -> Any:
    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        return None
    doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
    sk = doc.SketchManager
    sk.InsertSketch(True)
    sk.CreateCornerRectangle(-BOX_W_M / 2, -BOX_H_M / 2, 0.0, BOX_W_M / 2, BOX_H_M / 2, 0.0)
    sk.InsertSketch(True)
    doc.FeatureManager.FeatureExtrusion3(
        True, False, False, 0, 0, BOX_D_M, 0.0,
        False, False, False, False, 0.0, 0.0,
        False, False, False, False, True, True, True, 0, 0, False,
    )
    try:
        doc.EditRebuild3()
    except Exception:
        pass
    return doc


def _capture_top_edge_ref(doc: Any) -> dict | None:
    """Capture a durable ref to the top-front edge (y=0 mid, z=top)."""
    try:
        ext = typed(doc.Extension, "IModelDocExtension")
        if not ext.SelectByID2("", "EDGE", BOX_W_M / 2, 0.0, BOX_D_M, False, 0, None, 0):
            return None
        sm = doc.SelectionManager
        if sm.GetSelectedObjectCount2(-1) < 1:
            return None
        edge = sm.GetSelectedObject6(1, -1)
        if edge is None:
            return None
        from ai_sw_bridge.selection.live import capture_persist_id
        persist_id = capture_persist_id(doc, edge)
        try:
            p = edge.GetCurveParams2()
            start = (p[7], p[8], p[9])
            end = (p[10], p[11], p[12])
            length = float(p[1]) - float(p[0])
        except Exception:
            start = (BOX_W_M / 2, BOX_H_M / 2, BOX_D_M)
            end = (BOX_W_M / 2, -BOX_H_M / 2, BOX_D_M)
            length = BOX_H_M
        doc.ClearSelection2(True)
        return DurableEdgeRef(persist_id=persist_id, start=start, end=end, length=length).to_dict()
    except Exception:
        return None


def _probe(sw: Any, label: str, feature: dict, target_fn) -> dict:
    out: dict[str, Any] = {"label": label, "feature": feature}
    doc = _build_box(sw)
    if doc is None:
        out["verdict"] = "ERROR"
        out["reason"] = "box build failed"
        return out
    try:
        target = target_fn(doc)
        if target is None:
            out["verdict"] = "ERROR"
            out["reason"] = "target capture failed"
            return out
        out["target"] = target
        f0, v0 = verify.solid_metrics(doc)
        ok, note = mutate._create_chamfer(doc, feature, target)
        try:
            doc.EditRebuild3()
        except Exception:
            pass
        f1, v1 = verify.solid_metrics(doc)
        out["handler_ok"] = ok
        out["handler_note"] = note
        out["before"] = {"faces": f0, "vol": v0}
        out["after"] = {"faces": f1, "vol": v1}
        d_faces = (f1 - f0) if (f0 >= 0 and f1 >= 0) else None
        d_vol = (v1 - v0) if (v0 is not None and v1 is not None) else None
        out["delta"] = {"faces": d_faces, "vol": d_vol}
        geom_altered = (d_faces is not None and d_faces > 0) and (d_vol is not None and d_vol < -1e-12)
        out["verdict"] = "GO" if (ok and geom_altered) else ("NO_OP" if not ok else "GHOST")
        return out
    finally:
        _try_close(sw, doc)


def run() -> dict[str, Any]:
    result: dict[str, Any] = {"spike": "chamfer_dd_vertex", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")}
    sw = get_sw_app()
    try:
        result["sw_revision"] = str(sw.RevisionNumber)
    except Exception:
        result["sw_revision"] = "<unreadable>"

    dd = _probe(
        sw, "distance_distance",
        {"type": "chamfer", "chamfer_type": "distance_distance", "distance_mm": 2.0, "distance2_mm": 3.0},
        _capture_top_edge_ref,
    )
    vtx = _probe(
        sw, "vertex",
        {"type": "chamfer", "chamfer_type": "vertex", "distance_mm": 2.0, "distance2_mm": 2.0, "distance3_mm": 2.0},
        lambda doc: {"point": [BOX_W_M / 2 * 1000, BOX_H_M / 2 * 1000, BOX_D_M * 1000]},  # top corner (10,10,10) mm
    )
    result["distance_distance"] = dd
    result["vertex"] = vtx
    both_go = dd.get("verdict") == "GO" and vtx.get("verdict") == "GO"
    result["overall"] = "PASS" if both_go else "FAIL"
    result["finding"] = f"dd={dd.get('verdict')} (Δvol={dd.get('delta', {}).get('vol')}, Δfaces={dd.get('delta', {}).get('faces')}); vertex={vtx.get('verdict')} (Δvol={vtx.get('delta', {}).get('vol')}, Δfaces={vtx.get('delta', {}).get('faces')})"
    return result


def main() -> int:
    pythoncom.CoInitialize()
    try:
        result = run()
    finally:
        pythoncom.CoUninitialize()
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(result.get("overall", "ERROR"), file=sys.stderr)
    print(result.get("finding", ""), file=sys.stderr)
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("overall") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
