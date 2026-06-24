"""Seat-check: drive the F2 base_flange feature_add through the real PAE
lifecycle (propose -> dry_run -> commit) against mutate.py.

Non-destructive: builds its own part with a closed rectangle profile sketch in
the OS temp dir, never touches the user's files. Proposals go to a temp dir via
AI_SW_BRIDGE_PROPOSALS so the repo's ./proposals is untouched.

Usage:  .venv-py310\Scripts\python spikes\v0_16\_seatcheck_baseflange_pae.py
"""

from __future__ import annotations

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

_TMP = Path(tempfile.mkdtemp(prefix="aiswb_f2_"))
os.environ["AI_SW_BRIDGE_PROPOSALS"] = str(_TMP / "proposals")

from spike_earlybind_persist import connect_running_sw  # noqa: E402
from ai_sw_bridge import mutate  # noqa: E402

SW_TEMPLATE_PART = 8
PROF_W_M = 0.040
PROF_H_M = 0.030


def _title(doc: Any) -> Any:
    t = doc.GetTitle
    return t() if callable(t) else t


def _build_and_save(sw: Any) -> str:
    template = sw.GetUserPreferenceStringValue(SW_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
    sk = doc.SketchManager
    sk.InsertSketch(True)
    sk.CreateCornerRectangle(
        -PROF_W_M / 2, -PROF_H_M / 2, 0.0, PROF_W_M / 2, PROF_H_M / 2, 0.0
    )
    sk.InsertSketch(True)
    path = str(_TMP / "f2_baseflange_test.sldprt")
    saved = False
    for attempt in ("SaveAs3", "SaveAs"):
        try:
            m = getattr(doc, attempt)
            if attempt == "SaveAs3":
                m(path, 0, 0)
            else:
                m(path)
            saved = True
            break
        except Exception as e:  # noqa: BLE001
            print(f"  {attempt} failed: {type(e).__name__}: {str(e)[:120]}")
    if not saved:
        raise RuntimeError("could not save the profile part")
    sw.CloseDoc(_title(doc))
    return path


def _reopen_and_inspect(sw: Any, path: str) -> dict[str, Any]:
    """Reopen the committed part and list its features to confirm the flange."""
    doc = mutate._open_doc_typed(path)
    if doc is None:
        return {"reopened": False}
    out: dict[str, Any] = {"reopened": True, "features": []}
    try:
        fm = doc.FeatureManager
        try:
            count = int(fm.GetFeatureCount())
            out["feature_count"] = count
        except Exception:  # noqa: BLE001
            pass
        feat = doc.FirstFeature() if callable(doc.FirstFeature) else doc.FirstFeature
        names: list[str] = []
        guard = 0
        while feat is not None and guard < 100:
            guard += 1
            try:
                nm = feat.Name() if callable(feat.Name) else feat.Name
                tn = (
                    feat.GetTypeName2()
                    if callable(feat.GetTypeName2)
                    else feat.GetTypeName2
                )
                names.append(f"{nm} [{tn}]")
            except Exception:  # noqa: BLE001
                pass
            try:
                feat = (
                    feat.GetNextFeature()
                    if callable(feat.GetNextFeature)
                    else feat.GetNextFeature
                )
            except Exception:  # noqa: BLE001
                break
        out["features"] = names
        out["has_base_flange"] = any(
            "Base-Flange" in n or "SMBaseFlange" in n for n in names
        )
    finally:
        try:
            sw.CloseDoc(_title(doc))
        except Exception:  # noqa: BLE001
            pass
    return out


def main() -> int:
    pythoncom.CoInitialize()
    report: dict[str, Any] = {"tmp": str(_TMP)}
    try:
        sw = connect_running_sw()
        try:
            report["sw_revision"] = str(sw.RevisionNumber)
        except Exception:  # noqa: BLE001
            report["sw_revision"] = "<unreadable>"

        path = _build_and_save(sw)
        report["profile_part"] = path

        feature = {"type": "base_flange", "thickness_mm": 2.0, "bend_radius_mm": 1.0}
        target = {"sketch": "Sketch1"}

        prop = mutate.sw_propose_feature_add(path, feature, target)
        report["propose"] = prop
        pid = prop.get("proposal_id")
        if not prop.get("ok") or pid is None:
            report["overall"] = "FAIL-PROPOSE"
            return _emit(report, 1)

        dry = mutate.sw_dry_run_feature_add(pid)
        report["dry_run"] = dry
        if not dry.get("ok"):
            report["overall"] = "FAIL-DRYRUN"
            return _emit(report, 1)

        commit = mutate.sw_commit_feature_add(pid)
        report["commit"] = commit
        if not commit.get("ok"):
            report["overall"] = "FAIL-COMMIT"
            return _emit(report, 1)

        report["verify"] = _reopen_and_inspect(sw, path)
        ok = bool(report["verify"].get("has_base_flange")) and bool(
            commit.get("doc_saved")
        )
        report["overall"] = "PASS" if ok else "PARTIAL"
        return _emit(report, 0 if ok else 2)
    finally:
        pythoncom.CoUninitialize()


def _emit(report: dict[str, Any], code: int) -> int:
    out = _TMP / "baseflange_pae.json"
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    print(f"\nwrote {out}", file=sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
