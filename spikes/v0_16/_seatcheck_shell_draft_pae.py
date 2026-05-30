"""Seat-check: drive the shell + draft feature_add handlers through the real
PAE lifecycle (propose -> dry_run -> commit) against mutate.py.

Non-destructive: own boxes in temp .sldprt files; proposals to a temp dir.

Usage:  .venv-py310\Scripts\python spikes\v0_16\_seatcheck_shell_draft_pae.py
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

_TMP = Path(tempfile.mkdtemp(prefix="aiswb_sd_"))
os.environ["AI_SW_BRIDGE_PROPOSALS"] = str(_TMP / "proposals")

from ai_sw_bridge import mutate  # noqa: E402
from spike_earlybind_persist import connect_running_sw  # noqa: E402

W, H, D = 0.040, 0.030, 0.020


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
    base = (True, False, False, 0, 0, D, 0.0, False, False, False, False,
            0.0, 0.0, False, False, False, False, True, True, True, 0, 0.0)
    try:
        feat = fm.FeatureExtrusion2(*base, False)
    except Exception:  # noqa: BLE001
        feat = fm.FeatureExtrusion2(*base)
    return feat is not None


def _make_part(sw: Any, name: str) -> str | None:
    template = sw.GetUserPreferenceStringValue(8)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None or not _build_box(doc):
        return None
    path = str(_TMP / name)
    doc.SaveAs3(path, 0, 0)
    sw.CloseDoc(_title(doc))
    return path


def _pae(path: str, feature: dict, target: dict) -> dict[str, Any]:
    out: dict[str, Any] = {}
    prop = mutate.sw_propose_feature_add(path, feature, target)
    out["propose"] = {"ok": prop.get("ok"), "error": prop.get("error")}
    if not prop.get("ok"):
        out["overall"] = "FAIL-PROPOSE"
        return out
    pid = prop["proposal_id"]
    dry = mutate.sw_dry_run_feature_add(pid)
    out["dry_run"] = {"ok": dry.get("ok"), "state": dry.get("state"),
                      "result": dry.get("dry_run_result"), "error": dry.get("error")}
    if not dry.get("ok"):
        out["overall"] = "FAIL-DRYRUN"
        return out
    commit = mutate.sw_commit_feature_add(pid)
    out["commit"] = {"ok": commit.get("ok"), "doc_saved": commit.get("doc_saved"),
                     "error": commit.get("error")}
    out["overall"] = "PASS" if (commit.get("ok") and commit.get("doc_saved")) else "PARTIAL"
    return out


def main() -> int:
    pythoncom.CoInitialize()
    report: dict[str, Any] = {"tmp": str(_TMP)}
    try:
        sw = connect_running_sw()

        shell_path = _make_part(sw, "shell_test.sldprt")
        if shell_path:
            report["shell"] = _pae(
                shell_path,
                {"type": "shell", "thickness_mm": 2.0, "outward": False},
                {"faces": [[0.0, 0.0, D]]},  # remove the top face
            )
        else:
            report["shell"] = {"overall": "FAIL-BUILD"}

        draft_path = _make_part(sw, "draft_test.sldprt")
        if draft_path:
            report["draft"] = _pae(
                draft_path,
                {"type": "draft", "angle_deg": 5.0, "propagation": "none"},
                {"neutral_face": [0.0, 0.0, 0.0],     # bottom plane
                 "faces": [[W / 2, 0.0, D / 2]]},     # +X side face midpoint
            )
        else:
            report["draft"] = {"overall": "FAIL-BUILD"}

        sv = report["shell"].get("overall")
        dv = report["draft"].get("overall")
        report["overall"] = "PASS" if (sv == "PASS" and dv == "PASS") else f"shell={sv} draft={dv}"
        code = 0 if report["overall"] == "PASS" else 2
        return _emit(report, code)
    finally:
        pythoncom.CoUninitialize()


def _emit(report: dict[str, Any], code: int) -> int:
    out = _TMP / "shell_draft_pae.json"
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    print(f"\nwrote {out}", file=sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
