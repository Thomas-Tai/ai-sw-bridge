"""W44 — B-rep-effect verification-gap audit for AT-RISK feature_add kinds.

Measures ΔVolume (mm³) and ΔFaces for each at-risk material kind that was
shipped with NODE/COUNT-PRESENCE-ONLY verification (the ghost class).

Pattern: build a canonical fixture → measure B-rep before → call the
handler → measure B-rep after → assert GREEN (ΔVol ≠ 0 AND ΔFaces ≠ 0)
or GHOST (handler ok=True but ΔVol = 0 AND ΔFaces = 0).

NOT RUN (no seat) — authored for W0 to drive on the live SOLIDWORKS seat.

Kinds tested:
  1. base_flange  (CreateDefinition(34) → CreateFeature)
  2. shell        (InsertFeatureShell, void return)
  3. draft        (InsertMultiFaceDraft)
  4. sweep        (CreateDefinition(17) → CreateFeature)
  5. sweep_cut    (CreateDefinition(18) → CreateFeature)
  6. dome         (InsertDome, None return)

Results written to _results/brep_verify_w44.json.

Usage (on live seat):
    .venv-py310/Scripts/python.exe spikes/v0_2x/brep_verify_w44.py
"""

from __future__ import annotations

import json
import math
import sys
import time
import traceback
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

WORKTREE = Path(__file__).resolve().parents[2]
RESULTS_PATH = WORKTREE / "spikes" / "v0_2x" / "_results" / "brep_verify_w44.json"

import pythoncom  # noqa: E402

from ai_sw_bridge.com.earlybind import typed  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from ai_sw_bridge.sw_com import get_sw_app  # noqa: E402
from ai_sw_bridge.mutate import (  # noqa: E402
    _create_base_flange,
    _create_dome,
    _create_draft,
    _create_shell,
    _create_sweep,
    _create_sweep_cut,
    _get_body_count_and_volumes,
)

SW_DEFAULT_TEMPLATE_PART = 8

BOX_W_M = 0.040
BOX_H_M = 0.040
BOX_D_M = 0.020


def _title(d: Any) -> Any:
    t = d.GetTitle
    return t() if callable(t) else t


def _new_part(sw: Any) -> Any:
    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    return sw.NewDocument(template, 0, 0.0, 0.0)


def _get_total_face_count(doc: Any) -> int:
    """Sum face count across all solid bodies via IBody2.GetFaces()."""
    try:
        pdoc = (
            doc
            if hasattr(doc, "GetBodies2")
            else typed(doc, "IPartDoc", module=wrapper_module())
        )
        bodies = pdoc.GetBodies2(0, True)
    except Exception:
        return 0
    if bodies is None:
        return 0
    total = 0
    for body in bodies:
        try:
            faces = body.GetFaces()
            if faces is not None:
                total += len(faces)
        except Exception:
            pass
    return total


def _measure_brep(doc: Any) -> dict[str, Any]:
    """Snapshot: body_count, total_volume_mm3, total_face_count."""
    count, volumes = _get_body_count_and_volumes(doc)
    vol_sum = sum(volumes) if volumes else 0.0
    return {
        "body_count": count,
        "volume_mm3": round(vol_sum, 4),
        "face_count": _get_total_face_count(doc),
    }


def _sketch_rect_on_front(
    doc: Any, name: str, w: float, h: float, cx: float = 0.0, cy: float = 0.0
) -> None:
    doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
    sk = doc.SketchManager
    sk.InsertSketch(True)
    sk.CreateCornerRectangle(
        cx - w / 2,
        cy - h / 2,
        0.0,
        cx + w / 2,
        cy + h / 2,
        0.0,
    )
    sk.InsertSketch(True)
    if name:
        feats = doc.FeatureManager.GetFeatures(True)
        if feats:
            last = feats[-1]
            try:
                last.Name = name
            except Exception:
                pass


def _sketch_circle_on_plane(
    doc: Any,
    plane_name: str,
    sketch_name: str,
    cx: float,
    cy: float,
    radius_m: float,
) -> None:
    doc.SelectByID(plane_name, "PLANE", 0, 0, 0)
    sk = doc.SketchManager
    sk.InsertSketch(True)
    sk.CreateCircle(cx, cy, 0.0, cx + radius_m, cy, 0.0)
    sk.InsertSketch(True)
    if sketch_name:
        feats = doc.FeatureManager.GetFeatures(True)
        if feats:
            last = feats[-1]
            try:
                last.Name = sketch_name
            except Exception:
                pass


def _sketch_line_on_plane(
    doc: Any,
    plane_name: str,
    sketch_name: str,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
) -> None:
    doc.SelectByID(plane_name, "PLANE", 0, 0, 0)
    sk = doc.SketchManager
    sk.InsertSketch(True)
    sk.CreateLine(x1, y1, 0.0, x2, y2, 0.0)
    sk.InsertSketch(True)
    if sketch_name:
        feats = doc.FeatureManager.GetFeatures(True)
        if feats:
            last = feats[-1]
            try:
                last.Name = sketch_name
            except Exception:
                pass


def _extrude_blind(doc: Any, depth_m: float) -> Any:
    fm = doc.FeatureManager
    return fm.FeatureExtrusion3(
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


def _build_box(sw: Any) -> dict[str, Any]:
    """Build a 40×40×20 mm box. Returns {doc, before_brep}."""
    result: dict[str, Any] = {}
    doc = _new_part(sw)
    if doc is None:
        result["error"] = "NewDocument returned None"
        return result
    try:
        _sketch_rect_on_front(doc, "SK_Box", BOX_W_M, BOX_H_M)
        feat = _extrude_blind(doc, BOX_D_M)
        if feat is None or isinstance(feat, int):
            result["error"] = "extrude did not materialize"
            sw.CloseDoc(_title(doc))
            return result
        doc.ForceRebuild3(False)
        result["doc"] = doc
        result["before_brep"] = _measure_brep(doc)
    except Exception as exc:
        result["error"] = f"build failed: {exc!r}\n{traceback.format_exc()}"
        sw.CloseDoc(_title(doc))
    return result


def _verdict(
    handler_ok: bool,
    before: dict[str, Any],
    after: dict[str, Any],
    kind: str,
) -> str:
    """GREEN if B-rep changed in the expected direction; GHOST if ok but no change."""
    dvol = after["volume_mm3"] - before["volume_mm3"]
    dfaces = after["face_count"] - before["face_count"]

    if kind in ("shell", "sweep_cut"):
        expected_vol = dvol < 0
    elif kind == "draft":
        expected_vol = abs(dvol) > 0.01
    else:
        expected_vol = dvol > 0

    if kind in ("dome", "draft"):
        if handler_ok and expected_vol:
            return "GREEN"
        if handler_ok and dvol == 0:
            return "GHOST_FEATURE_SHIPPED_NOOP"
        if handler_ok:
            return f"AMBIGUOUS_dvol={dvol:.4f}_dfaces={dfaces}"
        return f"HANDLER_FAILED_handler_ok={handler_ok}"

    if handler_ok and expected_vol and dfaces != 0:
        return "GREEN"
    if handler_ok and dvol == 0 and dfaces == 0:
        return "GHOST_FEATURE_SHIPPED_NOOP"
    if handler_ok:
        return f"AMBIGUOUS_dvol={dvol:.4f}_dfaces={dfaces}"
    return f"HANDLER_FAILED_handler_ok={handler_ok}"


def test_base_flange(sw: Any) -> dict[str, Any]:
    """base_flange: sketch rect on Front → _create_base_flange → ΔVol > 0."""
    result: dict[str, Any] = {"kind": "base_flange", "status": "UNKNOWN"}
    doc = _new_part(sw)
    if doc is None:
        result["status"] = "BUILD_FAILED"
        result["error"] = "NewDocument returned None"
        return result
    try:
        _sketch_rect_on_front(doc, "SK_Flange", BOX_W_M, BOX_H_M)
        doc.ForceRebuild3(False)

        before = _measure_brep(doc)
        result["before"] = before

        ok, err = _create_base_flange(
            doc, {"sketch": "SK_Flange"}, thickness_mm=2.0, bend_radius_mm=2.0
        )
        result["handler_ok"] = ok
        result["handler_error"] = err

        doc.ForceRebuild3(False)
        after = _measure_brep(doc)
        result["after"] = after
        result["delta"] = {
            "vol": round(after["volume_mm3"] - before["volume_mm3"], 4),
            "faces": after["face_count"] - before["face_count"],
        }
        result["status"] = _verdict(ok, before, after, "base_flange")
    except Exception as exc:
        result["status"] = "EXCEPTION"
        result["error"] = f"{exc!r}\n{traceback.format_exc()}"
    finally:
        sw.CloseDoc(_title(doc))
    return result


def test_shell(sw: Any) -> dict[str, Any]:
    """shell: build box → _create_shell(top face) → ΔVol < 0, ΔFaces > 0."""
    result: dict[str, Any] = {"kind": "shell", "status": "UNKNOWN"}

    build = _build_box(sw)
    if "error" in build:
        result["status"] = "BUILD_FAILED"
        result["error"] = build["error"]
        return result

    doc = build["doc"]
    try:
        before = build["before_brep"]
        result["before"] = before

        back_z = BOX_D_M
        ok, err = _create_shell(
            doc,
            {"thickness_mm": 1.0, "outward": False},
            {"faces": [[0.0, 0.0, back_z]]},
        )
        result["handler_ok"] = ok
        result["handler_error"] = err

        doc.ForceRebuild3(False)
        after = _measure_brep(doc)
        result["after"] = after
        result["delta"] = {
            "vol": round(after["volume_mm3"] - before["volume_mm3"], 4),
            "faces": after["face_count"] - before["face_count"],
        }
        result["status"] = _verdict(ok, before, after, "shell")
    except Exception as exc:
        result["status"] = "EXCEPTION"
        result["error"] = f"{exc!r}\n{traceback.format_exc()}"
    finally:
        sw.CloseDoc(_title(doc))
    return result


def _pick_face_by_normal(
    doc: Any, want: tuple[float, float, float], tol: float = 0.3
) -> Any:
    """Find a face entity whose outward normal matches *want*."""
    try:
        pdoc = (
            doc
            if hasattr(doc, "GetBodies2")
            else typed(doc, "IPartDoc", module=wrapper_module())
        )
        bodies = pdoc.GetBodies2(0, True)
    except Exception:
        return None
    if bodies is None:
        return None
    for body in bodies:
        try:
            faces = body.GetFaces()
        except Exception:
            continue
        if faces is None:
            continue
        for face in faces:
            try:
                n = face.Normal
                if callable(n):
                    n = n()
                n = list(n) if not isinstance(n, (list, tuple)) else n
                if len(n) >= 3 and all(abs(n[i] - want[i]) < tol for i in range(3)):
                    return face
            except Exception:
                continue
    return None


def test_draft(sw: Any) -> dict[str, Any]:
    """draft: build box → InsertMultiFaceDraft via entity-based face pick → ΔVol ≠ 0.

    Bypasses _create_draft's coordinate-based _get_face_entity and instead
    picks faces by normal direction (matching the proven spike_shell_draft_v2
    approach). Neutral = bottom face (normal 0,0,-1), draft = side face.
    """
    result: dict[str, Any] = {"kind": "draft", "status": "UNKNOWN"}

    build = _build_box(sw)
    if "error" in build:
        result["status"] = "BUILD_FAILED"
        result["error"] = build["error"]
        return result

    doc = build["doc"]
    try:
        before = build["before_brep"]
        result["before"] = before

        from ai_sw_bridge.selection import select_entity as _sel_ent

        neutral = _pick_face_by_normal(doc, (0.0, 0.0, -1.0))
        side = _pick_face_by_normal(doc, (1.0, 0.0, 0.0))
        result["neutral_found"] = neutral is not None
        result["side_found"] = side is not None

        if neutral is None or side is None:
            result["handler_ok"] = False
            result["handler_error"] = "could not pick faces by normal"
        else:
            try:
                doc.ClearSelection2(True)
            except Exception:
                pass
            sn = _sel_ent(neutral, append=False, mark=1)
            sf = _sel_ent(side, append=True, mark=2)
            result["sel_neutral"] = sn
            result["sel_face"] = sf

            fm = doc.FeatureManager
            angle_rad = math.radians(3.0)
            _feats_before = fm.GetFeatures(True)
            feat_count_before = len(_feats_before) if _feats_before else 0
            feat = fm.InsertMultiFaceDraft(angle_rad, False, False, 0, False, False)
            ok = feat is not None and not isinstance(feat, int)
            if not ok:
                doc.ForceRebuild3(False)
                _feats_after = fm.GetFeatures(True)
                feat_count_after = len(_feats_after) if _feats_after else 0
                if feat_count_after > feat_count_before:
                    ok = True
            result["handler_ok"] = ok
            result["handler_error"] = (
                None if ok else "InsertMultiFaceDraft did not materialize"
            )

        doc.ForceRebuild3(False)
        after = _measure_brep(doc)
        result["after"] = after
        result["delta"] = {
            "vol": round(after["volume_mm3"] - before["volume_mm3"], 4),
            "faces": after["face_count"] - before["face_count"],
        }
        result["status"] = _verdict(
            result.get("handler_ok", False), before, after, "draft"
        )
    except Exception as exc:
        result["status"] = "EXCEPTION"
        result["error"] = f"{exc!r}\n{traceback.format_exc()}"
    finally:
        sw.CloseDoc(_title(doc))
    return result


def test_sweep(sw: Any) -> dict[str, Any]:
    """sweep: circle on Front (profile) + line on Right (path) → ΔVol > 0."""
    result: dict[str, Any] = {"kind": "sweep", "status": "UNKNOWN"}
    doc = _new_part(sw)
    if doc is None:
        result["status"] = "BUILD_FAILED"
        result["error"] = "NewDocument returned None"
        return result
    try:
        _sketch_circle_on_plane(doc, "Front Plane", "SK_Profile", 0.0, 0.0, 0.005)
        _sketch_line_on_plane(doc, "Right Plane", "SK_Path", -0.030, 0.0, 0.030, 0.0)
        doc.ForceRebuild3(False)

        before = _measure_brep(doc)
        result["before"] = before

        ok, err = _create_sweep(doc, {}, {"profile": "SK_Profile", "path": "SK_Path"})
        result["handler_ok"] = ok
        result["handler_error"] = err

        doc.ForceRebuild3(False)
        after = _measure_brep(doc)
        result["after"] = after
        result["delta"] = {
            "vol": round(after["volume_mm3"] - before["volume_mm3"], 4),
            "faces": after["face_count"] - before["face_count"],
        }
        result["status"] = _verdict(ok, before, after, "sweep")
    except Exception as exc:
        result["status"] = "EXCEPTION"
        result["error"] = f"{exc!r}\n{traceback.format_exc()}"
    finally:
        sw.CloseDoc(_title(doc))
    return result


def test_sweep_cut(sw: Any) -> dict[str, Any]:
    """sweep_cut: box + circle profile + path piercing the box → ΔVol < 0."""
    result: dict[str, Any] = {"kind": "sweep_cut", "status": "UNKNOWN"}

    build = _build_box(sw)
    if "error" in build:
        result["status"] = "BUILD_FAILED"
        result["error"] = build["error"]
        return result

    doc = build["doc"]
    try:
        before = build["before_brep"]
        result["before"] = before

        _sketch_circle_on_plane(doc, "Right Plane", "SK_CutProfile", 0.0, 0.0, 0.003)
        _sketch_line_on_plane(
            doc,
            "Front Plane",
            "SK_CutPath",
            -0.030,
            0.0,
            0.030,
            0.0,
        )
        doc.ForceRebuild3(False)

        ok, err = _create_sweep_cut(
            doc, {}, {"profile": "SK_CutProfile", "path": "SK_CutPath"}
        )
        result["handler_ok"] = ok
        result["handler_error"] = err

        doc.ForceRebuild3(False)
        after = _measure_brep(doc)
        result["after"] = after
        result["delta"] = {
            "vol": round(after["volume_mm3"] - before["volume_mm3"], 4),
            "faces": after["face_count"] - before["face_count"],
        }
        result["status"] = _verdict(ok, before, after, "sweep_cut")
    except Exception as exc:
        result["status"] = "EXCEPTION"
        result["error"] = f"{exc!r}\n{traceback.format_exc()}"
    finally:
        sw.CloseDoc(_title(doc))
    return result


def test_dome(sw: Any) -> dict[str, Any]:
    """dome: build box → _create_dome(top face) → ΔVol > 0."""
    result: dict[str, Any] = {"kind": "dome", "status": "UNKNOWN"}

    build = _build_box(sw)
    if "error" in build:
        result["status"] = "BUILD_FAILED"
        result["error"] = build["error"]
        return result

    doc = build["doc"]
    try:
        before = build["before_brep"]
        result["before"] = before

        back_z = BOX_D_M
        ok, err = _create_dome(
            doc,
            {"distance_mm": 5.0, "reverse": False, "elliptical": False},
            {"face": [0.0, 0.0, back_z]},
        )
        result["handler_ok"] = ok
        result["handler_error"] = err

        doc.ForceRebuild3(False)
        after = _measure_brep(doc)
        result["after"] = after
        result["delta"] = {
            "vol": round(after["volume_mm3"] - before["volume_mm3"], 4),
            "faces": after["face_count"] - before["face_count"],
        }
        result["status"] = _verdict(ok, before, after, "dome")
    except Exception as exc:
        result["status"] = "EXCEPTION"
        result["error"] = f"{exc!r}\n{traceback.format_exc()}"
    finally:
        sw.CloseDoc(_title(doc))
    return result


def run() -> dict[str, Any]:
    output: dict[str, Any] = {
        "spike_id": "W44_brep_verify",
        "timestamp": time.time(),
        "results": {},
    }

    try:
        sw = get_sw_app()
    except Exception as exc:
        output["error"] = f"could not connect to SW: {exc!r}"
        return output

    try:
        sw.CloseAllDocuments(0)
    except Exception:
        pass

    tests = [
        ("base_flange", test_base_flange),
        ("shell", test_shell),
        ("draft", test_draft),
        ("sweep", test_sweep),
        ("sweep_cut", test_sweep_cut),
        ("dome", test_dome),
    ]

    print("=== W44 B-rep verification-gap audit ===")
    for name, fn in tests:
        print(f"\n--- {name} ---")
        r = fn(sw)
        output["results"][name] = r
        status = r.get("status", "?")
        d = r.get("delta", {})
        print(f"  status: {status}")
        if d:
            print(f"  delta:  vol={d.get('vol')}, faces={d.get('faces')}")
        if r.get("handler_error"):
            print(f"  error:  {r['handler_error']}")

    green = sum(1 for r in output["results"].values() if r.get("status") == "GREEN")
    ghost = sum(
        1 for r in output["results"].values() if "GHOST" in str(r.get("status", ""))
    )
    total = len(output["results"])
    output["summary"] = f"{green}/{total} GREEN, {ghost} GHOST"
    print(f"\n=== SUMMARY: {output['summary']} ===")

    return output


if __name__ == "__main__":
    result = run()
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(result, indent=2, default=str))
    print(f"\nResults written to {RESULTS_PATH}")
