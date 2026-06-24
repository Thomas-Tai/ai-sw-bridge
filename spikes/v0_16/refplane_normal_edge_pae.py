"""PAE: ref_plane normal-to-edge via the PRODUCTION propose→dry_run→commit path.

Proves the SHIPPING handler — not a spike — materializes a normal-to-edge plane
end-to-end through sw_propose_feature_add → sw_dry_run_feature_add →
sw_commit_feature_add, using a real DurableEdgeRef captured from a live model.

The handler under test (mutate._create_ref_plane_normal_to_edge, wired by W0 at
1704ee9, merged 44a02fc):
  1. DurableEdgeRef.from_dict(edge_ref) → resolve_edge_ref → live edge
  2. typed(IEdge).GetStartVertex() → vertex (Coincident anchor)
  3. select_entity(vertex, mark=0) + select_entity(edge, append=True, mark=1)
  4. fm.InsertRefPlane(Coincident=4, 0, Perpendicular=2, 0, 0, 0)
  5. delta-verify via len(GetFeatures(True))

Flow:
  1. Build a 50mm box (doc open).
  2. Capture a durable edge_ref for a linear edge (persist_id + geometry).
  3. Save doc to file, close doc (production dry_run/commit require closed doc).
  4. sw_propose_feature_add → sw_dry_run_feature_add → sw_commit_feature_add.
  5. Re-open doc, verify: delta==1 + GetTypeName2()=="RefPlane" + perpendicular.
  6. Write _results/refplane_normal_edge_pae.json.

Usage:
    python spikes/v0_16/refplane_normal_edge_pae.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
_V15 = Path(__file__).resolve().parents[1] / "v0_15"
sys.path.insert(0, str(_PKG_ROOT))
sys.path.insert(0, str(_V15))

import pythoncom
import win32com.client as w32

from ai_sw_bridge.com.earlybind import (
    read_persist_reference,
    typed,
    typed_extension,
)
from ai_sw_bridge.com.sw_type_info import wrapper_module
from ai_sw_bridge.mutate import (
    sw_commit_feature_add,
    sw_dry_run_feature_add,
    sw_propose_feature_add,
)
from ai_sw_bridge.selection._edge_ref import DurableEdgeRef

from spike_earlybind_persist import connect_running_sw

SW_DEFAULT_TEMPLATE_PART = 8
RESULTS_DIR = Path(__file__).resolve().parent / "_results"


def _title(doc: Any) -> Any:
    t = doc.GetTitle
    return t() if callable(t) else t


def _build_box(sw: Any, path: str) -> Any:
    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.1, 0.1)
    if doc is None:
        raise RuntimeError("NewDocument None")
    doc.ClearSelection2(True)
    doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
    doc.InsertSketch2(True)
    sk = doc.SketchManager
    sk.CreateCornerRectangle(-0.025, -0.025, 0, 0.025, 0.025, 0)
    doc.InsertSketch2(False)
    doc.ClearSelection2(True)
    doc.SelectByID("Sketch1", "SKETCH", 0, 0, 0)
    fm = doc.FeatureManager
    fm.FeatureExtrusion3(
        True,
        False,
        False,
        0,
        0,
        0.05,
        0.0,
        False,
        False,
        False,
        False,
        0.0,
        0.0,
        False,
        False,
        False,
        False,
        True,
        True,
        True,
        0,
        0,
        False,
    )
    doc.ClearSelection2(True)
    doc.SaveAs3(path, 0, 2)
    return doc


def _feature_count(doc: Any) -> int:
    feats = doc.FeatureManager.GetFeatures(True)
    return len(feats) if feats else 0


def _capture_linear_edge_ref(doc: Any, mod: Any) -> tuple[dict, dict]:
    """Capture a DurableEdgeRef dict for the longest linear edge.

    Returns (edge_ref_dict, diagnostics).
    """
    diag: dict[str, Any] = {}
    bodies = doc.GetBodies2(0, True)
    if not bodies:
        raise RuntimeError("no bodies")
    body = bodies[0] if isinstance(bodies, (list, tuple)) else bodies
    edges_raw = body.GetEdges()
    if not edges_raw:
        raise RuntimeError("no edges")

    best_dict = None
    best_len = -1.0
    linear_count = 0

    for e in edges_raw:
        pid = read_persist_reference(doc, e)
        if pid is None:
            continue
        try:
            ie = typed(e, "IEdge", module=mod)
            icurve_raw = ie.GetCurve()
            if icurve_raw is None:
                continue
            icurve = typed(icurve_raw, "ICurve", module=mod)
            try:
                is_line = bool(icurve.IsLine())
            except Exception:
                is_line = False
            if not is_line:
                continue
            linear_count += 1

            params = icurve.GetEndParams()
            tmin, tmax = params[1], params[2]
            length = float(icurve.GetLength(tmin, tmax))
            if length <= best_len:
                continue

            best_len = length
            t_mid = (tmin + tmax) / 2.0
            eval_out = icurve.Evaluate(t_mid)
            start_pt = icurve.Evaluate(tmin)
            end_pt = icurve.Evaluate(tmax)

            ref = DurableEdgeRef(
                persist_id=pid,
                start=(float(start_pt[0]), float(start_pt[1]), float(start_pt[2])),
                end=(float(end_pt[0]), float(end_pt[1]), float(end_pt[2])),
                length=length,
                midpoint=(float(eval_out[0]), float(eval_out[1]), float(eval_out[2])),
            )
            best_dict = ref.to_dict()
            diag["tangent"] = (
                [eval_out[3], eval_out[4], eval_out[5]] if len(eval_out) >= 6 else None
            )
        except Exception as exc:
            diag["last_error"] = f"{type(exc).__name__}: {exc}"[:200]
            continue

    diag["linear_edges"] = linear_count
    if best_dict is None:
        raise RuntimeError("no linear edge with persist_id")
    return best_dict, diag


def _verify_perpendicularity(doc: Any, mod: Any, tangent: list) -> dict:
    """Verify the new RefPlane is perpendicular to the edge tangent.

    Uses IRefPlaneFeatureData.NormalVector if available; otherwise returns
    a best-effort result.
    """
    out: dict[str, Any] = {"checked": False}
    try:
        raw_feat = doc.FirstFeature()
        while raw_feat is not None:
            ifeat = None
            try:
                ifeat = typed(raw_feat, "IFeature", module=mod)
                tn = ifeat.GetTypeName2()
            except Exception:
                tn = None
            if tn == "RefPlane":
                name = getattr(ifeat, "Name", None) if ifeat else None
                if name and str(name).startswith("Plane"):
                    out["plane_name"] = str(name)
                    try:
                        defn = ifeat.GetDefinition()
                        if defn is not None:
                            typed_def = typed(defn, "IRefPlaneFeatureData", module=mod)
                            normal = typed_def.NormalVector
                            if normal is not None:
                                n = list(normal)
                                t = tangent
                                dot = abs(n[0] * t[0] + n[1] * t[1] + n[2] * t[2])
                                out["normal"] = n
                                out["dot_with_tangent"] = round(dot, 8)
                                out["perpendicular"] = dot < 0.01
                                out["checked"] = True
                    except Exception as exc:
                        out["normal_error"] = f"{type(exc).__name__}: {exc}"[:200]
                    break
            try:
                raw_feat = ifeat.GetNextFeature() if ifeat is not None else None
            except Exception:
                raw_feat = None
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"[:200]
    return out


def main() -> int:
    pythoncom.CoInitialize()
    out: dict[str, Any] = {"ok": False}
    doc = None

    try:
        mod = wrapper_module()
        sw = connect_running_sw()

        part_path = os.path.join(
            tempfile.gettempdir(),
            "refplane_normal_edge_pae_%d.SLDPRT" % int(time.time()),
        )
        print("[pae] building box -> %s" % part_path)
        doc = _build_box(sw, part_path)

        out["feature_count_before"] = _feature_count(doc)
        print("[pae] features before: %d" % out["feature_count_before"])

        print("[pae] capturing durable edge_ref...")
        edge_ref_dict, edge_diag = _capture_linear_edge_ref(doc, mod)
        out["edge_ref"] = edge_ref_dict
        out["edge_diag"] = edge_diag
        out["edge_ref_method"] = "persist_id"
        print(
            "[pae] edge_ref captured: length=%.1fmm, persist_id=%d bytes"
            % (
                edge_ref_dict["length"] * 1000,
                len(edge_diag.get("tangent") or []),
            )
        )

        print("[pae] saving + closing doc for production pipeline...")
        sw.CloseDoc(_title(doc))
        doc = None

        print("[pae] proposing ref_plane {edge_ref}...")
        propose = sw_propose_feature_add(
            part_path,
            {"type": "ref_plane"},
            {"edge_ref": edge_ref_dict},
        )
        out["propose"] = {
            "ok": propose.get("ok"),
            "proposal_id": propose.get("proposal_id"),
            "error": propose.get("error"),
        }
        if not propose.get("ok"):
            out["error"] = "propose failed: %s" % propose.get("error")
            print("[pae] FAIL: %s" % out["error"])
            return 1

        pid = propose["proposal_id"]

        print("[pae] dry_run %s..." % pid)
        dry = sw_dry_run_feature_add(pid)
        out["dry_run"] = {
            "ok": dry.get("ok"),
            "error": dry.get("error"),
            "state": dry.get("state"),
        }
        if not dry.get("ok"):
            out["error"] = "dry_run failed: %s" % dry.get("error")
            print("[pae] FAIL: %s" % out["error"])
            return 1

        print("[pae] commit %s..." % pid)
        commit = sw_commit_feature_add(pid)
        out["commit"] = {
            "ok": commit.get("ok"),
            "error": commit.get("error"),
            "state": commit.get("state"),
            "doc_saved": commit.get("doc_saved"),
        }
        if not commit.get("ok"):
            out["error"] = "commit failed: %s" % commit.get("error")
            print("[pae] FAIL: %s" % out["error"])
            return 1

        print("[pae] re-opening for readback verification...")
        typed_sw = typed(sw, "ISldWorks", module=mod)
        ret = typed_sw.OpenDoc6(part_path, 1, 1, "", 0, 0)
        doc = ret[0] if isinstance(ret, tuple) else ret
        if doc is None:
            out["error"] = "re-open failed"
            print("[pae] FAIL: re-open returned None")
            return 1

        out["feature_count_after"] = _feature_count(doc)
        out["delta"] = out["feature_count_after"] - out["feature_count_before"]

        raw_feat = doc.FirstFeature()
        while raw_feat is not None:
            ifeat = None
            try:
                ifeat = typed(raw_feat, "IFeature", module=mod)
                tn = ifeat.GetTypeName2()
                name = ifeat.Name
            except Exception:
                tn, name = None, None
            if tn == "RefPlane" and name and str(name).startswith("Plane"):
                out["feature_name"] = str(name)
                out["feature_type"] = "RefPlane"
                break
            try:
                raw_feat = ifeat.GetNextFeature() if ifeat is not None else None
            except Exception:
                raw_feat = None

        tangent = edge_diag.get("tangent")
        if tangent and out.get("feature_name"):
            perp = _verify_perpendicularity(doc, mod, tangent)
            out["perpendicularity"] = perp

        out["ok"] = out.get("delta") == 1 and out.get("feature_type") == "RefPlane"

        status = "GREEN" if out["ok"] else "FAIL"
        print(
            "[pae] %s: delta=%s type=%s name=%s"
            % (
                status,
                out.get("delta"),
                out.get("feature_type"),
                out.get("feature_name"),
            )
        )

    except Exception as exc:
        import traceback

        out["error"] = traceback.format_exc()
        out["ok"] = False
        print("[pae] EXCEPTION: %s" % exc)

    finally:
        if doc is not None:
            try:
                sw.CloseDoc(_title(doc))
            except Exception:
                pass
        pythoncom.CoUninitialize()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / "refplane_normal_edge_pae.json"
    out_path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print("[pae] wrote %s" % out_path)
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
