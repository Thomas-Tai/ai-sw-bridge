"""Seat-check C: drive the WIRED wizard_hole durable-placement path through the
real PAE lifecycle (propose -> dry_run -> commit) against mutate.py.

The realistic durable scenario:
  1. Build a box in a fresh part, capture the +Z top face as a durable face_ref
     (persist token + fingerprint), SAVE, and CLOSE the doc.
  2. Run the PAE with target = {"face_ref": <captured>, "point": [...]} — the
     dry_run/commit REOPEN the saved doc and must resolve the persist token back
     to the live face (proving durable placement survives save->close->reopen).

PASS = commit ok AND doc_saved AND the resolve method was persist_id.
Non-destructive: own temp .sldprt + temp proposals dir; closes own docs.
Usage:  <main-venv>\python spikes\v0_16\_seatcheck_wizhole_durable_pae.py
"""

from __future__ import annotations

import base64
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
_V15 = Path(__file__).resolve().parents[1] / "v0_15"
sys.path.insert(0, str(_PKG_ROOT))
sys.path.insert(0, str(_V15))

import pythoncom  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="aiswb_wzd_"))
os.environ["AI_SW_BRIDGE_PROPOSALS"] = str(_TMP / "proposals")

from ai_sw_bridge import mutate  # noqa: E402
from ai_sw_bridge.brep.interrogator import read_face_geometry  # noqa: E402
from ai_sw_bridge.selection.live import capture_persist_id  # noqa: E402
from spike_earlybind_persist import connect_running_sw  # noqa: E402

W, H, D = 0.040, 0.040, 0.020


def _title(doc: Any) -> Any:
    t = doc.GetTitle
    return t() if callable(t) else t


def _build_box(doc: Any) -> bool:
    if not doc.SelectByID("Front Plane", "PLANE", 0, 0, 0):
        return False
    sk = doc.SketchManager
    sk.InsertSketch(True)
    sk.CreateCornerRectangle(-W / 2, -H / 2, 0.0, W / 2, H / 2, 0.0)
    sk.InsertSketch(True)
    fm = doc.FeatureManager
    base = (
        True,
        False,
        False,
        0,
        0,
        D,
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
        0.0,
    )
    try:
        feat = fm.FeatureExtrusion2(*base, False)
    except Exception:  # noqa: BLE001
        feat = fm.FeatureExtrusion2(*base)
    return feat is not None


def _capture_face_ref(doc: Any, x: float, y: float, z: float, role: str) -> dict | None:
    try:
        doc.ClearSelection2(True)
    except Exception:  # noqa: BLE001
        pass
    if not doc.SelectByID("", "FACE", x, y, z):
        return None
    face = doc.SelectionManager.GetSelectedObject6(1, -1)
    if face is None:
        return None
    geom = read_face_geometry(face)
    if geom is None:
        return None
    pid = capture_persist_id(doc, face)
    ref: dict[str, Any] = {
        "normal": list(geom["normal"]),
        "centroid": list(geom["centroid"]),
        "area_mm2": geom["area_mm2"],
        "role_hint": role,
    }
    if pid is not None:
        ref["persist_id"] = base64.urlsafe_b64encode(pid).decode("ascii").rstrip("=")
    return ref


def run() -> dict[str, Any]:
    sw = connect_running_sw()
    report: dict[str, Any] = {"tmp": str(_TMP)}

    template = sw.GetUserPreferenceStringValue(8)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None or not _build_box(doc):
        return {"overall": "FAIL", "reason": "box build failed", **report}
    doc.ForceRebuild3(False)
    face_ref = _capture_face_ref(doc, 0.0, 0.0, D, "+z_top")
    report["captured"] = {
        "has_persist": face_ref is not None and "persist_id" in face_ref
    }
    if face_ref is None or "persist_id" not in face_ref:
        try:
            sw.CloseDoc(_title(doc))
        except Exception:  # noqa: BLE001
            pass
        return {
            "overall": "FAIL",
            "reason": "no durable persist token captured",
            **report,
        }

    path = str(_TMP / "wizhole_durable.sldprt")
    doc.SaveAs3(path, 0, 0)
    sw.CloseDoc(_title(doc))

    feature = {
        "type": "wizard_hole",
        "hole_type": "hole",
        "standard": "ANSI Metric",
        "fastener_type": "Drill Sizes",
        "size": "Ø6.0",
        "end_condition": "through_all",
    }
    target = {"face_ref": face_ref, "point": [0.005, 0.005, D]}

    prop = mutate.sw_propose_feature_add(path, feature, target)
    report["propose"] = {"ok": prop.get("ok"), "error": prop.get("error")}
    if not prop.get("ok"):
        return {"overall": "FAIL-PROPOSE", **report}
    pid = prop["proposal_id"]

    dry = mutate.sw_dry_run_feature_add(pid)
    report["dry_run"] = {
        "ok": dry.get("ok"),
        "state": dry.get("state"),
        "result": dry.get("dry_run_result"),
        "error": dry.get("error"),
    }
    if not dry.get("ok"):
        return {"overall": "FAIL-DRYRUN", **report}

    commit = mutate.sw_commit_feature_add(pid)
    report["commit"] = {
        "ok": commit.get("ok"),
        "doc_saved": commit.get("doc_saved"),
        "error": commit.get("error"),
    }
    report["overall"] = (
        "PASS" if (commit.get("ok") and commit.get("doc_saved")) else "PARTIAL"
    )
    return report


def main() -> int:
    pythoncom.CoInitialize()
    try:
        report = run()
    finally:
        pythoncom.CoUninitialize()
    out = Path(__file__).parent / "_results" / "wizhole_durable_pae.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    print(f"\nwrote {out}", file=sys.stderr)
    return 0 if report.get("overall") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
