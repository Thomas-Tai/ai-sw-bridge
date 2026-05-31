"""Gold-standard PAE seat-validation for the sweep feature_add handler.

Proves the *bridge architecture* (not just the COM recipe) can drive a sweep
end-to-end: builds a part with a circle profile (Sketch1) + a perpendicular line
path (Sketch2) — the geometry spike_sweep_v2 proved materializes — saves+closes
it, then runs the real ``mutate.py`` PAE lifecycle:

    sw_propose_feature_add -> sw_dry_run_feature_add -> sw_commit_feature_add

Usage:
    python spikes/v0_16/spike_sweep_pae.py --out spikes/v0_16/_results/sweep_pae.json
"""

from __future__ import annotations

import argparse
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
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pythoncom  # noqa: E402

from spike_earlybind_persist import connect_running_sw  # noqa: E402

SW_DEFAULT_TEMPLATE_PART = 8


def _title(doc: Any) -> Any:
    t = doc.GetTitle
    return t() if callable(t) else t


def _build_and_save(part_path: Path) -> dict[str, Any]:
    """Build circle-profile + perpendicular-path part, save, close. Returns info."""
    sw = connect_running_sw()
    out: dict[str, Any] = {"sw_revision": str(sw.RevisionNumber)}
    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        return {**out, "built": False, "error": "NewDocument returned None"}

    # Profile: circle on Front Plane.
    doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
    doc.SketchManager.InsertSketch(True)
    doc.SketchManager.CreateCircleByRadius(0.0, 0.0, 0.0, 0.005)
    doc.SketchManager.InsertSketch(True)

    # Path: line on Right Plane along local-X (= global Z, perpendicular to the
    # Front-plane profile) — the geometry that made spike_sweep_v2 materialize.
    doc.SelectByID("Right Plane", "PLANE", 0, 0, 0)
    doc.SketchManager.InsertSketch(True)
    doc.SketchManager.CreateLine(0.0, 0.0, 0.0, 0.05, 0.0, 0.0)
    doc.SketchManager.InsertSketch(True)
    try:
        doc.EditRebuild3()
    except Exception:  # noqa: BLE001
        pass

    if part_path.exists():
        try:
            part_path.unlink()
        except OSError:
            pass
    saved = doc.SaveAs(str(part_path))
    out["saveas_return"] = repr(saved)
    out["built"] = part_path.exists()
    out["part_path"] = str(part_path)
    try:
        sw.CloseDoc(_title(doc))
    except Exception:  # noqa: BLE001
        pass
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    pythoncom.CoInitialize()
    result: dict[str, Any] = {}
    try:
        tmp = Path(tempfile.gettempdir()) / "ai-sw-bridge"
        tmp.mkdir(parents=True, exist_ok=True)
        part_path = tmp / "sweep_pae_part.sldprt"

        # Isolate the proposal store so we don't pollute ./proposals.
        os.environ["AI_SW_BRIDGE_PROPOSALS"] = str(tmp / "proposals_sweep_pae")

        result["build"] = _build_and_save(part_path)
        if not result["build"].get("built"):
            result["overall"] = "FAIL"
            result["reason"] = "could not build/save the test part"
            return _emit(result, args.out)

        # Drive the REAL bridge PAE lifecycle.
        from ai_sw_bridge.mutate import (
            sw_commit_feature_add,
            sw_dry_run_feature_add,
            sw_propose_feature_add,
        )

        feature = {"type": "sweep"}
        target = {"profile": "Sketch1", "path": "Sketch2"}

        prop = sw_propose_feature_add(str(part_path), feature, target)
        result["propose"] = prop
        pid = prop.get("proposal_id")
        if not prop.get("ok") or not pid:
            result["overall"] = "FAIL"
            result["reason"] = f"propose failed: {prop.get('error')}"
            return _emit(result, args.out)

        dry = sw_dry_run_feature_add(pid)
        result["dry_run"] = dry
        if not dry.get("ok"):
            result["overall"] = "FAIL"
            result["reason"] = f"dry_run failed: {dry.get('error')}"
            return _emit(result, args.out)

        commit = sw_commit_feature_add(pid)
        result["commit"] = commit

        ok = bool(commit.get("ok"))
        result["overall"] = "PASS" if ok else "FAIL"
        if not ok:
            result["reason"] = f"commit failed: {commit.get('error')}"
        else:
            result["interpretation"] = (
                "Bridge PAE drove a sweep end-to-end: propose -> dry_run -> commit "
                "materialized + saved a Sweep in the live kernel. W2 closed."
            )
        return _emit(result, args.out)
    finally:
        pythoncom.CoUninitialize()


def _emit(result: dict[str, Any], out: Path | None) -> int:
    payload = json.dumps(result, indent=2, default=lambda o: f"<{type(o).__name__}>")
    if out is not None:
        out.write_text(payload, encoding="utf-8")
        print(f"wrote {out}", file=sys.stderr)
    else:
        print(payload)
    return {"PASS": 0, "FAIL": 1}.get(result.get("overall"), 1)


if __name__ == "__main__":
    raise SystemExit(main())
