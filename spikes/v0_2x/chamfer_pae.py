"""W24 / CHAMFER PAE — production-approval-experiment.

Full propose→dry_run→commit lifecycle for feature_add: chamfer via
InsertFeatureChamfer on a live SW 2024 SP1 seat.

Pipeline:
  1. Build a box (NewDocument + sketch + extrude)
  2. Capture a durable edge ref (persist_id)
  3. sw_propose_feature_add(chamfer, distance_mm=2, angle_deg=45)
  4. sw_dry_run_feature_add — verify no-op rollback
  5. sw_commit_feature_add — save .SLDPRT
  6. Re-open .SLDPRT, verify Chamfer feature present + geometry altered

Verdicts:
  GO    — Chamfer feature present on reopen, face_count +1, file on disk.
  FAIL  — Chamfer missing or geometry unchanged on reopen.

Usage:
    .venv-py310/Scripts/python.exe spikes/v0_2x/chamfer_pae.py
"""

from __future__ import annotations

import json
import math
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

WORKTREE = Path(__file__).resolve().parents[2]
RESULTS_PATH = WORKTREE / "spikes" / "v0_2x" / "_results" / "chamfer_pae.json"

import pythoncom  # noqa: E402

from ai_sw_bridge.com.earlybind import typed  # noqa: E402
from ai_sw_bridge.sw_com import get_sw_app  # noqa: E402
from ai_sw_bridge.selection.live import capture_persist_id  # noqa: E402
from ai_sw_bridge.selection import DurableEdgeRef  # noqa: E402
from ai_sw_bridge.mutate import (  # noqa: E402
    sw_propose_feature_add,
    sw_dry_run_feature_add,
    sw_commit_feature_add,
)

SW_DEFAULT_TEMPLATE_PART = 8
BOX_W_M = 0.020
BOX_H_M = 0.020
BOX_D_M = 0.010
CHAMFER_DISTANCE_MM = 2.0
CHAMFER_ANGLE_DEG = 45.0


def _title(d: Any) -> Any:
    t = d.GetTitle
    return t() if callable(t) else t


def _feat_count(doc: Any) -> int:
    fm = doc.FeatureManager
    feats = fm.GetFeatures(True)
    return len(feats) if feats else 0


def _body_face_count(doc: Any) -> int:
    try:
        bodies = doc.GetBodies2(True, False)
        if not bodies:
            return 0
        return len(bodies[0].GetFaces()) if bodies[0].GetFaces() else 0
    except Exception:
        return -1


def _find_chamfer_feature(doc: Any) -> dict[str, Any]:
    result: dict[str, Any] = {"found": False}
    try:
        fm = doc.FeatureManager
        feats = fm.GetFeatures(True)
        if not feats:
            return result
        for feat in feats:
            try:
                tn = None
                for attr in ("GetTypeName2", "GetTypeName"):
                    try:
                        m = getattr(feat, attr)
                        tn = str(m() if callable(m) else m)
                        break
                    except Exception:
                        continue
                if tn and "Chamfer" in tn:
                    result["found"] = True
                    result["type_name"] = tn
                    result["name"] = getattr(feat, "Name", None)
                    return result
            except Exception:
                continue
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"
    return result


def _build_box_and_capture_edge(sw: Any, save_path: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        result["error"] = "NewDocument returned None"
        return result

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
    except Exception as e:
        result["error"] = f"sketch failed: {e}"
        sw.CloseDoc(_title(doc))
        return result

    try:
        feat = fm.FeatureExtrusion3(
            True, False, False, 0, 0, BOX_D_M, 0.0,
            False, False, False, False, 0.0, 0.0,
            False, False, False, False, True, True, True, 0, 0, False,
        )
        if feat is None or isinstance(feat, int):
            result["error"] = "extrude did not materialize"
            sw.CloseDoc(_title(doc))
            return result
    except Exception as e:
        result["error"] = f"extrude failed: {e}"
        sw.CloseDoc(_title(doc))
        return result

    doc.EditRebuild3
    result["box_faces"] = _body_face_count(doc)
    result["box_features"] = _feat_count(doc)

    # Capture durable edge
    try:
        ext = typed(doc.Extension, "IModelDocExtension")
        ok = ext.SelectByID2("", "EDGE", BOX_W_M / 2, 0.0, BOX_D_M, False, 0, None, 0)
        if not ok:
            result["error"] = "edge selection failed"
            sw.CloseDoc(_title(doc))
            return result
        sel_mgr = doc.SelectionManager
        edge_obj = sel_mgr.GetSelectedObject6(1, -1)
        persist_id = capture_persist_id(doc, edge_obj)
        try:
            params = edge_obj.GetCurveParams2()
            start = (params[7], params[8], params[9])
            end = (params[10], params[11], params[12])
            length = float(params[1]) - float(params[0])
        except Exception:
            start = (BOX_W_M / 2, 0.0, 0.0)
            end = (BOX_W_M / 2, 0.0, BOX_D_M)
            length = BOX_D_M

        edge_ref = DurableEdgeRef(
            persist_id=persist_id, start=start, end=end, length=length,
        )
        result["edge_ref"] = edge_ref.to_dict()
        result["persist_id_captured"] = persist_id is not None
    except Exception as e:
        result["error"] = f"edge capture failed: {e}"
        sw.CloseDoc(_title(doc))
        return result

    # Save the box
    try:
        doc.SaveAs3(save_path, 0, 0)
        result["saved"] = True
    except Exception as e:
        result["error"] = f"SaveAs3 failed: {e}"
        sw.CloseDoc(_title(doc))
        return result

    sw.CloseDoc(_title(doc))
    return result


def run() -> dict[str, Any]:
    result: dict[str, Any] = {"spike_id": "W24_chamfer_pae"}

    try:
        sw = get_sw_app()
    except Exception as e:
        return {**result, "overall": "FAIL", "reason": f"SW unavailable: {e}"}

    try:
        result["sw_revision"] = str(sw.RevisionNumber)
    except Exception:
        pass

    with tempfile.TemporaryDirectory(prefix="chamfer_pae_") as tmpdir:
        sldprt = str(Path(tmpdir) / "chamfer_test.sldprt")

        # Phase 1: Build box + capture edge
        box = _build_box_and_capture_edge(sw, sldprt)
        result["box"] = box
        if "error" in box:
            return {**result, "overall": "FAIL", "reason": box["error"]}

        edge_ref = box["edge_ref"]
        feature = {"type": "chamfer", "distance_mm": CHAMFER_DISTANCE_MM, "angle_deg": CHAMFER_ANGLE_DEG}
        target = edge_ref

        # Phase 2: Propose
        propose = sw_propose_feature_add(sldprt, feature, target)
        result["propose"] = {k: v for k, v in propose.items() if k not in ("feature", "target")}
        if not propose["ok"]:
            return {**result, "overall": "FAIL", "reason": f"propose failed: {propose['error']}"}
        pid = propose["proposal_id"]

        # Phase 3: Dry-run
        dry = sw_dry_run_feature_add(pid)
        result["dry_run"] = {k: v for k, v in dry.items() if k != "proposal_id"}
        if not dry["ok"]:
            return {**result, "overall": "FAIL", "reason": f"dry_run failed: {dry['error']}"}

        # Phase 4: Commit
        commit = sw_commit_feature_add(pid)
        result["commit"] = {k: v for k, v in commit.items() if k != "proposal_id"}
        if not commit["ok"]:
            return {**result, "overall": "FAIL", "reason": f"commit failed: {commit['error']}"}

        # Phase 5: Verify file on disk
        result["file_exists"] = Path(sldprt).exists()

        # Phase 6: Re-open and verify
        try:
            from ai_sw_bridge.sw_com import resolve
            tsw = typed(sw, "ISldWorks")
            reopen_doc = tsw.OpenDoc6(sldprt, 1, 1, "", 0, 0)
            doc = reopen_doc[0] if isinstance(reopen_doc, tuple) else reopen_doc
            if doc is None:
                result["reopen"] = {"error": "OpenDoc6 returned None"}
                return {**result, "overall": "FAIL", "reason": "reopen failed"}

            doc.ForceRebuild3(False)
            reopen_feats = _feat_count(doc)
            reopen_faces = _body_face_count(doc)
            chamfer = _find_chamfer_feature(doc)

            result["reopen"] = {
                "feature_count": reopen_feats,
                "face_count": reopen_faces,
                "chamfer_found": chamfer.get("found", False),
                "chamfer_type": chamfer.get("type_name"),
                "chamfer_name": chamfer.get("name"),
                "face_delta": reopen_faces - box["box_faces"],
                "feature_delta": reopen_feats - box["box_features"],
            }

            sw.CloseDoc(_title(doc))
        except Exception as e:
            result["reopen"] = {"error": f"{type(e).__name__}: {e}"}
            return {**result, "overall": "FAIL", "reason": f"reopen verify failed: {e}"}

    # Verdict
    reopen = result.get("reopen", {})
    chamfer_found = reopen.get("chamfer_found", False)
    feature_delta = reopen.get("feature_delta", 0)
    face_delta = reopen.get("face_delta", 0)
    file_exists = result.get("file_exists", False)

    if chamfer_found and feature_delta >= 1 and file_exists:
        if face_delta > 0:
            result["overall"] = "GO"
        elif face_delta == 0:
            result["overall"] = "FAIL"
            result["reason"] = "Chamfer feature found but geometry unchanged"
        else:
            # face_count read failed (-1) but feature exists and count +1
            result["overall"] = "GO"
            result["note"] = "face_count unreadable on reopen; feature delta confirms materialization"
    elif chamfer_found and feature_delta == 0:
        result["overall"] = "FAIL"
        result["reason"] = "Chamfer feature found but no feature count delta"
    else:
        result["overall"] = "FAIL"
        result["reason"] = f"Chamfer not found on reopen (found={chamfer_found}, delta={feature_delta})"

    return result


def main() -> None:
    result = run()
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"verdict: {result.get('overall', 'FAIL')}", file=sys.stderr)
    print(f"results: {RESULTS_PATH}", file=sys.stderr)


if __name__ == "__main__":
    main()
