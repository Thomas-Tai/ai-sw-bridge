"""MEASURE-FIRST probe — multibody-PART interference (the genuine E4 gap).

Reflect-first finding: ASSEMBLY interference (component-component) already SHIPPED
W27 (`observe_interference.py`, `client.observe.interference()`, seat-proven, PAE
5/5) — DEFERRED.md line 68. That lane REJECTS non-assembly docs, so interference
between solid BODIES WITHIN ONE PART (multibody) is the uncovered path —
DEFERRED.md line 68 explicitly defers "body-level detail".

DLL recon (docs/sw_api_full.md, IBody2 @ build 32.1.0.123):
  * IModelDocExtension.GetInterferenceEdges — PHANTOM (the directive's guess; does
    not exist, like CheckModel).
  * IBody2.GetIntersectionEdges(ToolBodyIn) -> Object  — body-body intersection
    edges. The read-only interference signal: count > 0 ⇒ the two bodies clash.
  * IBody2.Copy() -> temp body; IBody2.Operations2(SWBODYINTERSECT=15901, ToolBody,
    out err) -> result bodies; IBody2.GetMassProperties(density) -> array incl
    volume. On TEMP COPIES this yields the interference VOLUME without mutating
    the document (read-only).
  * IBody2.Name (property) — body name for the payload.

Probe matrix:
  overlapping     — 2 solid bodies sharing space (merge=False) → expect
                    GetIntersectionEdges count > 0, intersect volume > 0.
  non_overlapping — 2 disjoint bodies → expect count 0 / None (negative control).

Witness: does GetIntersectionEdges discriminate clash vs clear? Can Copy+
Operations2(INTERSECT)+GetMassProperties yield a JSON-serializable volume (mm³)
read-only? What is the body-name source?

Run: PYTHONPATH=<repo>/src python spikes/v0_2x/probe_body_interference.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
_SRC = _HERE.parents[2] / "src"
for _p in (str(_SRC), str(_HERE.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import pythoncom  # noqa: E402
import win32com.client as w32  # noqa: E402

from ai_sw_bridge.com.earlybind import typed  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
import _feature_spike_fixtures as fx  # noqa: E402

_OUT = _HERE.parent / "_results" / "probe_body_interference.json"
out: dict[str, Any] = {"probe": "body_interference"}

_SWBODYINTERSECT = 15901
_SW_SOLID = 0


# FeatureExtrusion2 arg-18 (0-indexed 17) = Merge. False => separate body.
def _extrude(doc: Any, sketch_name: str, depth_m: float, *, merge: bool) -> None:
    fx._select_feature(doc, sketch_name)
    doc.FeatureManager.FeatureExtrusion2(
        True,
        False,
        False,
        0,
        0,
        depth_m,
        0.0,
        False,
        False,
        False,
        False,
        0,
        0,
        False,
        False,
        False,
        False,
        merge,
        True,
        True,
        0,
        0,
        False,
    )
    doc.ClearSelection2(True)


def _build_multibody(sw: Any, *, overlap: bool) -> Any:
    """Two solid bodies in one part. overlap=True => they share space."""
    doc = sw.NewDocument(fx.PART_TEMPLATE, 0, 0, 0)
    # Body 1
    fx._select_feature(doc, "Front Plane")
    doc.SketchManager.InsertSketch(True)
    doc.SketchManager.CreateCornerRectangle(-0.020, -0.015, 0.0, 0.020, 0.015, 0.0)
    doc.SketchManager.InsertSketch(True)
    doc.ClearSelection2(True)
    _extrude(doc, "Sketch1", 0.020, merge=True)
    # Body 2 (merge=False -> separate body)
    fx._select_feature(doc, "Front Plane")
    doc.SketchManager.InsertSketch(True)
    if overlap:
        doc.SketchManager.CreateCornerRectangle(0.000, -0.005, 0.0, 0.040, 0.025, 0.0)
    else:
        doc.SketchManager.CreateCornerRectangle(0.100, -0.015, 0.0, 0.140, 0.015, 0.0)
    doc.SketchManager.InsertSketch(True)
    doc.ClearSelection2(True)
    _extrude(doc, "Sketch2", 0.020, merge=False)
    doc.ForceRebuild3(False)
    return doc


def _name(body: Any) -> str | None:
    for attr in ("Name", "Name2"):
        try:
            v = getattr(body, attr)
            return str(v() if callable(v) else v)
        except Exception:
            continue
    return None


def _intersection_edge_count(a: Any, b: Any) -> dict[str, Any]:
    r: dict[str, Any] = {}
    try:
        edges = a.GetIntersectionEdges(b)
        if edges is None:
            r["edge_count"] = 0
        elif isinstance(edges, (list, tuple)):
            r["edge_count"] = len(edges)
        else:
            r["edge_count"] = 1
    except Exception as e:  # noqa: BLE001
        r["edges_exc"] = repr(e)
    return r


def _intersect_volume_mm3(a: Any, b: Any) -> dict[str, Any]:
    """Read-only interference volume via temp-body boolean COMMON."""
    r: dict[str, Any] = {}
    try:
        ta = a.Copy()
        tb = b.Copy()
    except Exception as e:  # noqa: BLE001
        r["copy_exc"] = repr(e)
        return r
    try:
        res = ta.Operations2(_SWBODYINTERSECT, tb, 0)
    except Exception as e:  # noqa: BLE001
        r["operations2_exc"] = repr(e)
        return r
    # res may be (bodies, errcode) tuple or bodies array.
    bodies = res
    if isinstance(res, tuple):
        r["op_errcode"] = res[-1] if len(res) > 1 else None
        bodies = res[0]
    if bodies is None:
        r["result_bodies"] = 0
        return r
    if not isinstance(bodies, (list, tuple)):
        bodies = (bodies,)
    r["result_bodies"] = len(bodies)
    total_m3 = 0.0
    for rb in bodies:
        try:
            mp = rb.GetMassProperties(0.0)
            # IBody2.GetMassProperties: [cx,cy,cz, vol, area, mass, ...]
            if mp is not None and len(mp) > 3:
                total_m3 += float(mp[3])
                r["mass_props_len"] = len(mp)
        except Exception as e:  # noqa: BLE001
            r["massprops_exc"] = repr(e)
    r["intersect_volume_mm3"] = total_m3 * 1e9
    return r


def _probe_case(sw: Any, *, overlap: bool) -> dict[str, Any]:
    case: dict[str, Any] = {"overlap": overlap}
    fx._close_all(sw) if hasattr(fx, "_close_all") else None
    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass
    doc = _build_multibody(sw, overlap=overlap)
    mod = wrapper_module()
    try:
        bodies = doc.GetBodies2(_SW_SOLID, False) or ()
    except Exception as e:  # noqa: BLE001
        case["getbodies_exc"] = repr(e)
        return case
    bodies = list(bodies)
    case["solid_body_count"] = len(bodies)
    case["body_names"] = [_name(b) for b in bodies]
    if len(bodies) < 2:
        case["error"] = "fewer than 2 solid bodies — fixture did not split"
        return case
    a, b = bodies[0], bodies[1]
    # late-bound first
    case["edges_latebound"] = _intersection_edge_count(a, b)
    # typed IBody2 fallback/confirm
    try:
        ta = typed(a, "IBody2", module=mod)
        tb = typed(b, "IBody2", module=mod)
        case["edges_typed"] = _intersection_edge_count(ta, tb)
        case["volume"] = _intersect_volume_mm3(ta, tb)
    except Exception as e:  # noqa: BLE001
        case["typed_exc"] = repr(e)
    return case


def main() -> int:
    pythoncom.CoInitialize()
    _ = wrapper_module()
    sw = w32.Dispatch("SldWorks.Application")
    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass
    try:
        out["overlapping"] = _probe_case(sw, overlap=True)
        out["non_overlapping"] = _probe_case(sw, overlap=False)
    finally:
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass
        pythoncom.CoUninitialize()
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(json.dumps(out, indent=2, default=str))
    print(f"\n(wrote {_OUT})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
