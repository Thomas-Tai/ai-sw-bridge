"""Seat-check: drive the wizard_hole feature_add through the real PAE lifecycle
against mutate.py, with dynamically-resolved DB args.

Non-destructive: own box in a temp .sldprt; proposals to a temp dir. If the
requested size is invalid, the dry-run error reports the valid sizes and this
script retries once with the first valid size.

Usage:  .venv-py310\Scripts\python spikes\v0_16\_seatcheck_wizhole_pae.py
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
_V15 = Path(__file__).resolve().parents[1] / "v0_15"
sys.path.insert(0, str(_PKG_ROOT))
sys.path.insert(0, str(_V15))

import pythoncom  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="aiswb_wiz_"))
os.environ["AI_SW_BRIDGE_PROPOSALS"] = str(_TMP / "proposals")

from ai_sw_bridge import mutate  # noqa: E402
from spike_earlybind_persist import connect_running_sw  # noqa: E402

BOX_W_M = 0.020
BOX_H_M = 0.020
BOX_D_M = 0.010

FACE = [0.0, 0.0, BOX_D_M]       # world coord to pick the top face
POINT = [0.003, 0.002, 0.0]      # sketch-local point on that face

FEATURE = {
    "type": "wizard_hole",
    "hole_type": "hole",
    "standard": "ANSI Metric",
    "fastener_type": "Drill sizes",
    "size": "Ø6.0",              # may be corrected from the dry-run error
    "end_condition": "blind",
    "depth_mm": 6.0,
}


def _title(doc: Any) -> Any:
    t = doc.GetTitle
    return t() if callable(t) else t


def _build_box(doc: Any) -> bool:
    if not doc.SelectByID("Front Plane", "PLANE", 0, 0, 0):
        return False
    sk = doc.SketchManager
    sk.InsertSketch(True)
    sk.CreateCornerRectangle(-BOX_W_M / 2, -BOX_H_M / 2, 0.0,
                             BOX_W_M / 2, BOX_H_M / 2, 0.0)
    sk.InsertSketch(True)
    fm = doc.FeatureManager
    base = (True, False, False, 0, 0, BOX_D_M, 0.0, False, False, False, False,
            0.0, 0.0, False, False, False, False, True, True, True, 0, 0.0)
    try:
        feat = fm.FeatureExtrusion2(*base, False)
    except Exception:  # noqa: BLE001
        feat = fm.FeatureExtrusion2(*base)
    return feat is not None


def _valid_sizes_from_error(err: str) -> list[str]:
    m = re.search(r"valid sizes:\s*\[(.*)\]", err or "")
    if not m:
        return []
    return [s.strip().strip("'\"") for s in m.group(1).split(",") if s.strip()]


def main() -> int:
    pythoncom.CoInitialize()
    report: dict[str, Any] = {"tmp": str(_TMP)}
    try:
        sw = connect_running_sw()
        template = sw.GetUserPreferenceStringValue(8)
        doc = sw.NewDocument(template, 0, 0.0, 0.0)
        if doc is None or not _build_box(doc):
            report["overall"] = "FAIL-BUILD"
            return _emit(report, 1)
        path = str(_TMP / "wiz_test.sldprt")
        doc.SaveAs3(path, 0, 0)
        sw.CloseDoc(_title(doc))
        report["profile_part"] = path

        target = {"face": FACE, "point": POINT}
        feature = dict(FEATURE)

        for attempt in range(2):
            prop = mutate.sw_propose_feature_add(path, feature, target)
            if not prop.get("ok"):
                report["overall"] = "FAIL-PROPOSE"
                report["propose"] = prop
                return _emit(report, 1)
            pid = prop["proposal_id"]
            dry = mutate.sw_dry_run_feature_add(pid)
            report[f"dry_run_{attempt}"] = {
                "ok": dry.get("ok"), "state": dry.get("state"),
                "result": dry.get("dry_run_result"), "error": dry.get("error"),
                "size_tried": feature["size"],
            }
            if dry.get("ok"):
                commit = mutate.sw_commit_feature_add(pid)
                report["commit"] = {"ok": commit.get("ok"),
                                    "doc_saved": commit.get("doc_saved"),
                                    "error": commit.get("error")}
                ok = bool(commit.get("ok") and commit.get("doc_saved"))
                report["overall"] = "PASS" if ok else "PARTIAL"
                report["final_size"] = feature["size"]
                return _emit(report, 0 if ok else 2)
            # invalid size? retry with a valid one from the error.
            err = (dry.get("dry_run_result") or {}).get("error") or dry.get("error") or ""
            valid = _valid_sizes_from_error(err)
            report[f"valid_sizes_{attempt}"] = valid
            if valid:
                feature["size"] = valid[len(valid) // 2]
                continue
            report["overall"] = "FAIL-DRYRUN"
            return _emit(report, 1)

        report["overall"] = "FAIL-DRYRUN-RETRY"
        return _emit(report, 1)
    finally:
        pythoncom.CoUninitialize()


def _emit(report: dict[str, Any], code: int) -> int:
    out = _TMP / "wizhole_pae.json"
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    print(f"\nwrote {out}", file=sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
