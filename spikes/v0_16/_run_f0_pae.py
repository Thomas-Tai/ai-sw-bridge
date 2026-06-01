"""Gold-standard PAE driver for Wave-5 F0 ref-geom (4 kinds).

Runs propose -> dry_run -> commit on a live SW seat for each of:
  ref_plane, ref_axis, coordinate_system, ref_point.

Both sw_dry_run_feature_add and sw_commit_feature_add refuse to run when the
target doc is currently active in the SW UI, so we close the part between
stages. Each stage re-opens the doc on disk by path.
"""
import os, sys, json, time, tempfile, traceback
from typing import Any

import pythoncom
import win32com.client

sys.path.insert(0, r"C:\D\WorkSpace\[Local]_Station\01_Heavy_Assets\ai-sw-bridge\src")

from ai_sw_bridge.mutate import (
    sw_propose_feature_add,
    sw_dry_run_feature_add,
    sw_commit_feature_add,
)

PART_TEMPLATE = r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\Part.prtdot"
RESULTS_DIR = r"C:\D\WorkSpace\[Local]_Station\01_Heavy_Assets\ai-sw-bridge\spikes\v0_16\_results"


def _get_sw():
    pythoncom.CoInitialize()
    return win32com.client.GetActiveObject("SldWorks.Application")


def _title(doc):
    t = doc.GetTitle
    return t() if callable(t) else t


def _new_closed_part(path: str) -> str:
    """Create a fresh part from template, save to *path*, close. Returns path."""
    sw = _get_sw()
    doc = sw.NewDocument(PART_TEMPLATE, 0, 0.1, 0.1)
    if doc is None:
        raise RuntimeError("NewDocument returned None")
    ok = doc.SaveAs3(path, 0, 2)
    if ok is False:
        raise RuntimeError(f"SaveAs3 failed for {path}")
    sw.CloseDoc(_title(doc))
    return path


def _build_box_and_close(path: str) -> None:
    """Re-open the part at *path*, extrude a 40x40x20 mm box, save, close."""
    sw = _get_sw()
    ret = sw.OpenDoc6(path, 1, 1, "", 0, 0)  # swDocPART=1, swOpenDocOptions_Silent=1
    # OpenDoc6 returns (doc, errors, warnings) tuple in late-bound COM.
    doc = ret[0] if isinstance(ret, tuple) else ret
    if doc is None:
        raise RuntimeError(f"OpenDoc6 failed for {path}: ret={ret!r}")
    try:
        doc.ClearSelection2(True)
        doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
        doc.InsertSketch2(True)
        sk = doc.SketchManager
        sk.CreateLine(-0.02, -0.02, 0,  0.02, -0.02, 0)
        sk.CreateLine( 0.02, -0.02, 0,  0.02,  0.02, 0)
        sk.CreateLine( 0.02,  0.02, 0, -0.02,  0.02, 0)
        sk.CreateLine(-0.02,  0.02, 0, -0.02, -0.02, 0)
        doc.InsertSketch2(False)
        fm = doc.FeatureManager
        fm.FeatureExtrusion2(
            True, False, False,
            0, 0,
            0.02, 0.0,
            False, False, False, False,
            0.0, 0.0, False, False, False, False,
            True, True, True,
            0, 0, False,
        )
        doc.ClearSelection2(True)
        doc.Save()
    finally:
        sw.CloseDoc(_title(doc))


def _run_one(kind, feature, target, part_path):
    out = {"kind": kind, "feature": feature, "target": target, "steps": {}}
    try:
        p = sw_propose_feature_add(part_path, feature, target)
        out["steps"]["propose"] = p
    except Exception:
        out["steps"]["propose"] = {"ok": False, "error": traceback.format_exc()}
        return out
    if not p.get("ok"):
        return out
    try:
        d = sw_dry_run_feature_add(p["proposal_id"])
        out["steps"]["dry_run"] = d
    except Exception:
        out["steps"]["dry_run"] = {"ok": False, "error": traceback.format_exc()}
        return out
    if not d.get("ok"):
        return out
    try:
        c = sw_commit_feature_add(p["proposal_id"])
        out["steps"]["commit"] = c
    except Exception:
        out["steps"]["commit"] = {"ok": False, "error": traceback.format_exc()}
    return out


def main():
    os.makedirs(RESULTS_DIR, exist_ok=True)
    part_path = os.path.join(tempfile.gettempdir(), f"f0_pae_{int(time.time())}.SLDPRT")

    print(f"[seat] creating fresh part -> {part_path}")
    _new_closed_part(part_path)
    print("[seat] part created and closed")

    results = []

    results.append(_run_one(
        "ref_plane",
        {"type": "ref_plane", "distance_mm": 10.0},
        {"plane": "Front Plane"},
        part_path,
    ))
    print("[seat] ref_plane ->", results[-1]["steps"].get("commit", {}).get("ok", "FAIL"))

    results.append(_run_one(
        "ref_axis",
        {"type": "ref_axis"},
        {"planes": ["Front Plane", "Top Plane"]},
        part_path,
    ))
    print("[seat] ref_axis ->", results[-1]["steps"].get("commit", {}).get("ok", "FAIL"))

    results.append(_run_one(
        "coordinate_system",
        {"type": "coordinate_system", "flip_x": False, "flip_y": False, "flip_z": False},
        {"origin": "Origin"},
        part_path,
    ))
    print("[seat] coordinate_system ->", results[-1]["steps"].get("commit", {}).get("ok", "FAIL"))

    # Build a box so a vertex exists for ref_point.
    print("[seat] building box for ref_point")
    _build_box_and_close(part_path)

    results.append(_run_one(
        "ref_point",
        {"type": "ref_point"},
        {"point": [0.02, 0.02, 0.02]},
        part_path,
    ))
    print("[seat] ref_point ->", results[-1]["steps"].get("commit", {}).get("ok", "FAIL"))

    out_path = os.path.join(RESULTS_DIR, "f0_pae_run.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"[seat] results -> {out_path}")

    summary = []
    for r in results:
        ok = (
            r["steps"].get("propose", {}).get("ok")
            and r["steps"].get("dry_run", {}).get("ok")
            and r["steps"].get("commit", {}).get("ok")
        )
        summary.append(f"  {r['kind']:<20} {'GREEN' if ok else 'RED'}")
    print("[seat] summary:\n" + "\n".join(summary))


if __name__ == "__main__":
    main()
