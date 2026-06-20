"""W67 P5 Track-1 CAPSTONE — end-to-end live build of the PRODUCTION handler.

Builds examples/up_to_surface_boss/spec.json through the real build() pipeline
(same entry ai-sw-build uses) and proves the boss_extrude_up_to_surface handler
materialises geometry that terminates on the durable target_ref surface.

Discriminating witness (the example's overall bbox is a USELESS witness because
EX_Wall is itself 60mm tall): the max Z-extent of any face in the y<0
half-space — the cylinder side, AWAY from the wall (wall lives at y in [30,50]).
  * PostBoss reached the +z=60 target surface -> max zmax(y<0) ~= 60mm. PASS.
  * PostBoss ghosted (selection choreography dropped) -> the only geometry at
    y<0 is the EX_Base plate top at z=10mm -> max zmax(y<0) ~= 10mm. FAIL.

Ephemeral (underscore prefix -> not a committed spike). Non-destructive:
CloseAllDocuments(True) in finally; never saves.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pythoncom

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT / "src"))

from ai_sw_bridge.spec import validate  # noqa: E402
from ai_sw_bridge.spec.builder import build  # noqa: E402
from ai_sw_bridge.sw_com import get_sw_app  # noqa: E402

TARGET_MM = 60.0
TOL_MM = 0.5
Y_NEG_CUT = -0.005  # faces whose y-centre is below this are "cylinder side"


def _box(face: Any) -> list[float] | None:
    try:
        b = face.GetBox
        b = b() if callable(b) else b
        return [float(x) for x in b] if b else None
    except Exception:
        return None


def run() -> dict[str, Any]:
    spec_path = _REPO_ROOT / "examples" / "up_to_surface_boss" / "spec.json"
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    validate(spec)

    out: dict[str, Any] = {"capstone": "up_to_surface_boss"}
    # no_dim=True: resolve the (all-literal) dims upfront and build at target
    # sizes with NO AddDimension2 calls -> zero Modify-Dimension popups, the
    # correct headless mode (inline-parametric blocks on the dialog toll).
    result = build(spec, no_dim=True)
    out["build_ok"] = bool(result.ok)
    out["features_built"] = list(result.features_built or [])
    if not result.ok:
        out["build_error"] = result.error
        out["verdict"] = "BUILD_FAILED"
        return out

    sw = get_sw_app()
    doc = sw.ActiveDoc
    if doc is None:
        out["verdict"] = "NO_ACTIVE_DOC"
        return out
    try:
        doc.ForceRebuild3(False)
    except Exception:
        pass

    out["post_boss_present"] = doc.FeatureByName("PostBoss") is not None

    # Overall solid bbox (sanity; expected 60 from the wall regardless).
    try:
        bodies = doc.GetBodies2(0, False)
        blist = list(bodies) if isinstance(bodies, (list, tuple)) else ([bodies] if bodies else [])
    except Exception:
        blist = []
    out["body_count"] = len(blist)

    # The discriminating witness: scan every face, isolate the y<0 half-space,
    # take the max zmax there.
    max_z_yneg_mm = None
    overall_zmax_mm = None
    for body in blist:
        try:
            faces = body.GetFaces()
        except Exception:
            continue
        flist = list(faces) if isinstance(faces, (list, tuple)) else ([faces] if faces else [])
        for face in flist:
            bx = _box(face)
            if bx is None or len(bx) < 6:
                continue
            zmax = bx[5]
            overall_zmax_mm = zmax * 1000.0 if overall_zmax_mm is None else max(overall_zmax_mm, zmax * 1000.0)
            y_center = (bx[1] + bx[4]) / 2.0
            if y_center < Y_NEG_CUT:
                z = zmax * 1000.0
                max_z_yneg_mm = z if max_z_yneg_mm is None else max(max_z_yneg_mm, z)

    out["overall_bbox_zmax_mm"] = overall_zmax_mm
    out["max_face_zmax_y_neg_mm"] = max_z_yneg_mm
    out["target_mm"] = TARGET_MM

    reached = max_z_yneg_mm is not None and abs(max_z_yneg_mm - TARGET_MM) < TOL_MM
    out["verdict"] = "PASS" if (out["post_boss_present"] and reached) else "GHOST"
    return out


def main() -> int:
    pythoncom.CoInitialize()
    sw = None
    try:
        out = run()
    finally:
        try:
            sw = get_sw_app()
            if sw is not None:
                sw.CloseAllDocuments(True)
        except Exception:
            pass
        pythoncom.CoUninitialize()
    print(json.dumps(out, indent=2, default=str))
    sys.stderr.write(f"\n[capstone] VERDICT: {out.get('verdict')}\n")
    return 0 if out.get("verdict") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
