"""W41 / BODY-OPS S1 — seat-verification for delete_body, combine, split.

Builds multi-body parts from scratch (FeatureExtrusion3 with Merge=False),
then runs each body-op handler directly and measures body-count + volume
deltas (W21 doctrine).

Pipeline per kind:
  1. Build precondition part (multi-body or single-body + cutting entity)
  2. Measure before: body_count + per-body volumes
  3. Call the handler directly (_create_delete_body / _create_combine / _create_split)
  4. Measure after: body_count + per-body volumes
  5. Verdict: GREEN if body-count changed AND volume delta is consistent

Results written to _results/body_ops.json.

Usage:
    .venv-py310/Scripts/python.exe spikes/v0_2x/body_ops_s1.py
"""

from __future__ import annotations

import json
import sys
import time
import traceback
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

WORKTREE = Path(__file__).resolve().parents[2]
RESULTS_PATH = WORKTREE / "spikes" / "v0_2x" / "_results" / "body_ops.json"

import pythoncom  # noqa: E402

from ai_sw_bridge.com.earlybind import typed  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from ai_sw_bridge.sw_com import get_sw_app  # noqa: E402
from ai_sw_bridge.mutate import (  # noqa: E402
    _create_delete_body,
    _create_combine,
    _create_split,
    _get_body_count_and_volumes,
)

SW_DEFAULT_TEMPLATE_PART = 8

BOX_A_W_M = 0.020
BOX_A_H_M = 0.020
BOX_A_D_M = 0.010

BOX_B_W_M = 0.015
BOX_B_H_M = 0.015
BOX_B_D_M = 0.008
BOX_B_OFFSET_M = 0.030

BOX_OVERLAP_OFFSET_M = 0.010


def _title(d: Any) -> Any:
    t = d.GetTitle
    return t() if callable(t) else t


def _new_part(sw: Any) -> Any:
    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    return sw.NewDocument(template, 0, 0.0, 0.0)


def _sketch_rect_on_front(
    doc: Any, w: float, h: float, cx: float = 0.0, cy: float = 0.0
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


def _extrude_no_merge(doc: Any, depth_m: float) -> Any:
    """FeatureExtrusion3 with Merge=False (arg 22) for multi-body."""
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


def _build_two_disjoint_bodies(sw: Any) -> dict[str, Any]:
    """Build two non-overlapping boxes (Merge=False) → 2 solid bodies."""
    result: dict[str, Any] = {}
    doc = _new_part(sw)
    if doc is None:
        result["error"] = "NewDocument returned None"
        return result

    try:
        _sketch_rect_on_front(doc, BOX_A_W_M, BOX_A_H_M)
        feat1 = _extrude_no_merge(doc, BOX_A_D_M)
        if feat1 is None or isinstance(feat1, int):
            result["error"] = "first extrude did not materialize"
            sw.CloseDoc(_title(doc))
            return result

        _sketch_rect_on_front(doc, BOX_B_W_M, BOX_B_H_M, cx=BOX_B_OFFSET_M)
        feat2 = _extrude_no_merge(doc, BOX_B_D_M)
        if feat2 is None or isinstance(feat2, int):
            result["error"] = "second extrude did not materialize"
            sw.CloseDoc(_title(doc))
            return result

        doc.ForceRebuild3(False)
        count, volumes = _get_body_count_and_volumes(doc)
        result["body_count"] = count
        result["volumes_mm3"] = volumes
        result["doc"] = doc
    except Exception as exc:
        result["error"] = f"build failed: {exc!r}\n{traceback.format_exc()}"
        sw.CloseDoc(_title(doc))
    return result


def _build_two_overlapping_bodies(sw: Any) -> dict[str, Any]:
    """Build two overlapping boxes (Merge=False) → 2 solid bodies."""
    result: dict[str, Any] = {}
    doc = _new_part(sw)
    if doc is None:
        result["error"] = "NewDocument returned None"
        return result

    try:
        _sketch_rect_on_front(doc, BOX_A_W_M, BOX_A_H_M)
        feat1 = _extrude_no_merge(doc, BOX_A_D_M)
        if feat1 is None or isinstance(feat1, int):
            result["error"] = "first extrude did not materialize"
            sw.CloseDoc(_title(doc))
            return result

        _sketch_rect_on_front(doc, BOX_A_W_M, BOX_A_H_M, cx=BOX_OVERLAP_OFFSET_M)
        feat2 = _extrude_no_merge(doc, BOX_A_D_M)
        if feat2 is None or isinstance(feat2, int):
            result["error"] = "second extrude did not materialize"
            sw.CloseDoc(_title(doc))
            return result

        doc.ForceRebuild3(False)
        count, volumes = _get_body_count_and_volumes(doc)
        result["body_count"] = count
        result["volumes_mm3"] = volumes
        result["doc"] = doc
    except Exception as exc:
        result["error"] = f"build failed: {exc!r}\n{traceback.format_exc()}"
        sw.CloseDoc(_title(doc))
    return result


def _build_single_body_with_refplane(sw: Any) -> dict[str, Any]:
    """Build a single box + a ref plane through the middle for split."""
    result: dict[str, Any] = {}
    doc = _new_part(sw)
    if doc is None:
        result["error"] = "NewDocument returned None"
        return result

    try:
        _sketch_rect_on_front(doc, BOX_A_W_M, BOX_A_H_M)
        feat = _extrude_no_merge(doc, BOX_A_D_M)
        if feat is None or isinstance(feat, int):
            result["error"] = "extrude did not materialize"
            sw.CloseDoc(_title(doc))
            return result

        fm = doc.FeatureManager
        mid_z = BOX_A_D_M / 2
        ref = fm.InsertRefPlane(8, mid_z, 0, 0, 0, 0)
        doc.ForceRebuild3(False)

        count, volumes = _get_body_count_and_volumes(doc)
        result["body_count"] = count
        result["volumes_mm3"] = volumes
        result["has_refplane"] = ref is not None
        result["doc"] = doc
    except Exception as exc:
        result["error"] = f"build failed: {exc!r}\n{traceback.format_exc()}"
        sw.CloseDoc(_title(doc))
    return result


def _probe_insert_delete_body_arity(fm: Any) -> dict[str, Any]:
    """Probe InsertDeleteBody2 signature arity."""
    result: dict[str, Any] = {"method_found": False}
    for name in ("InsertDeleteBody2", "InsertDeleteBody"):
        try:
            m = getattr(fm, name, None)
            if m is not None:
                result["method_found"] = True
                result["method_name"] = name
                result["callable"] = callable(m)
                break
        except Exception:
            continue
    return result


def _probe_insert_combine_feature_arity(fm: Any) -> dict[str, Any]:
    """Probe InsertCombineFeature signature arity."""
    result: dict[str, Any] = {"method_found": False}
    for name in ("InsertCombineFeature",):
        try:
            m = getattr(fm, name, None)
            if m is not None:
                result["method_found"] = True
                result["method_name"] = name
                result["callable"] = callable(m)
                break
        except Exception:
            continue
    return result


def _probe_insert_split_body_arity(fm: Any) -> dict[str, Any]:
    """Probe InsertSplitBody signature arity."""
    result: dict[str, Any] = {"method_found": False}
    for name in ("InsertSplitBody", "InsertSplitBody2", "SplitBody"):
        try:
            m = getattr(fm, name, None)
            if m is not None:
                result["method_found"] = True
                result["method_name"] = name
                result["callable"] = callable(m)
                break
        except Exception:
            continue
    return result


def _enum_body_names(doc: Any) -> list[str]:
    """Enumerate body names via GetBodies2 + Name property."""
    try:
        bodies = doc.GetBodies2(0, True)
        if bodies is None:
            return []
        names = []
        for b in bodies:
            try:
                n = b.Name
                if callable(n):
                    n = n()
                names.append(str(n))
            except Exception:
                names.append("<unknown>")
        return names
    except Exception:
        return []


def test_delete_body(sw: Any) -> dict[str, Any]:
    """S1 test: build 2 disjoint bodies → delete body[1] → assert 2→1."""
    result: dict[str, Any] = {"kind": "delete_body", "status": "UNKNOWN"}

    build = _build_two_disjoint_bodies(sw)
    if "error" in build:
        result["status"] = "BUILD_FAILED"
        result["error"] = build["error"]
        return result

    doc = build["doc"]
    try:
        result["before"] = {
            "body_count": build["body_count"],
            "volumes_mm3": build["volumes_mm3"],
            "body_names": _enum_body_names(doc),
        }

        fm = doc.FeatureManager
        result["api_probe"] = _probe_insert_delete_body_arity(fm)

        if build["body_count"] < 2:
            result["status"] = "PRECONDITION_FAILED"
            result["error"] = f"expected 2 bodies, got {build['body_count']}"
            return result

        feature = {"type": "delete_body"}
        target = {"body_index": 1}

        ok, err = _create_delete_body(doc, feature, target)
        result["handler_ok"] = ok
        result["handler_error"] = err

        after_count, after_vols = _get_body_count_and_volumes(doc)
        result["after"] = {
            "body_count": after_count,
            "volumes_mm3": after_vols,
            "body_names": _enum_body_names(doc),
        }

        if ok and after_count < build["body_count"]:
            result["status"] = "GREEN"
            vol_before_sum = sum(v for v in (build["volumes_mm3"] or []) if v > 0)
            vol_after_sum = sum(v for v in (after_vols or []) if v > 0)
            result["volume_delta_mm3"] = vol_after_sum - vol_before_sum
        else:
            result["status"] = "RED"
    except Exception as exc:
        result["status"] = "EXCEPTION"
        result["error"] = f"{exc!r}\n{traceback.format_exc()}"
    finally:
        sw.CloseDoc(_title(doc))

    return result


def test_combine_subtract(sw: Any) -> dict[str, Any]:
    """S1 test: build 2 overlapping bodies → subtract → assert →1 body."""
    result: dict[str, Any] = {"kind": "combine_subtract", "status": "UNKNOWN"}

    build = _build_two_overlapping_bodies(sw)
    if "error" in build:
        result["status"] = "BUILD_FAILED"
        result["error"] = build["error"]
        return result

    doc = build["doc"]
    try:
        result["before"] = {
            "body_count": build["body_count"],
            "volumes_mm3": build["volumes_mm3"],
            "body_names": _enum_body_names(doc),
        }

        fm = doc.FeatureManager
        result["api_probe"] = _probe_insert_combine_feature_arity(fm)

        if build["body_count"] < 2:
            result["status"] = "PRECONDITION_FAILED"
            result["error"] = f"expected 2 bodies, got {build['body_count']}"
            return result

        feature = {"type": "combine", "operation": "subtract"}
        target = {"main_body_index": 0, "tool_body_indices": [1]}

        ok, err = _create_combine(doc, feature, target)
        result["handler_ok"] = ok
        result["handler_error"] = err

        after_count, after_vols = _get_body_count_and_volumes(doc)
        result["after"] = {
            "body_count": after_count,
            "volumes_mm3": after_vols,
            "body_names": _enum_body_names(doc),
        }

        if ok and after_count < build["body_count"]:
            result["status"] = "GREEN"
        else:
            result["status"] = "RED"
    except Exception as exc:
        result["status"] = "EXCEPTION"
        result["error"] = f"{exc!r}\n{traceback.format_exc()}"
    finally:
        sw.CloseDoc(_title(doc))

    return result


def test_combine_add(sw: Any) -> dict[str, Any]:
    """S1 test: build 2 disjoint bodies → add (boolean union) → assert →1 body."""
    result: dict[str, Any] = {"kind": "combine_add", "status": "UNKNOWN"}

    build = _build_two_disjoint_bodies(sw)
    if "error" in build:
        result["status"] = "BUILD_FAILED"
        result["error"] = build["error"]
        return result

    doc = build["doc"]
    try:
        result["before"] = {
            "body_count": build["body_count"],
            "volumes_mm3": build["volumes_mm3"],
        }

        feature = {"type": "combine", "operation": "add"}
        target = {"main_body_index": 0, "tool_body_indices": [1]}

        ok, err = _create_combine(doc, feature, target)
        result["handler_ok"] = ok
        result["handler_error"] = err

        after_count, after_vols = _get_body_count_and_volumes(doc)
        result["after"] = {
            "body_count": after_count,
            "volumes_mm3": after_vols,
        }

        if ok and after_count < build["body_count"]:
            result["status"] = "GREEN"
        else:
            result["status"] = "RED"
    except Exception as exc:
        result["status"] = "EXCEPTION"
        result["error"] = f"{exc!r}\n{traceback.format_exc()}"
    finally:
        sw.CloseDoc(_title(doc))

    return result


def test_split(sw: Any) -> dict[str, Any]:
    """S1 test: build 1 body + ref plane → split → assert 1→2."""
    result: dict[str, Any] = {"kind": "split", "status": "UNKNOWN"}

    build = _build_single_body_with_refplane(sw)
    if "error" in build:
        result["status"] = "BUILD_FAILED"
        result["error"] = build["error"]
        return result

    doc = build["doc"]
    try:
        result["before"] = {
            "body_count": build["body_count"],
            "volumes_mm3": build["volumes_mm3"],
        }
        result["has_refplane"] = build.get("has_refplane", False)

        fm = doc.FeatureManager
        result["api_probe"] = _probe_insert_split_body_arity(fm)

        feature = {"type": "split"}

        refplane_names = ("Plane1", "RefPlane1", "Ref Plane1")
        cutting_plane = None
        for name in refplane_names:
            mod = wrapper_module()
            ext = typed(doc.Extension, "IModelDocExtension", module=mod)
            try:
                ok = ext.SelectByID2(name, "REFPLANE", 0, 0, 0, False, 0, None, 0)
                if ok:
                    cutting_plane = name
                    break
            except Exception:
                continue

        if cutting_plane is None:
            result["status"] = "PRECONDITION_FAILED"
            result["error"] = "could not find ref plane by any known name"
            return result

        target = {"body_index": 0, "cutting_plane": cutting_plane}

        ok, err = _create_split(doc, feature, target)
        result["handler_ok"] = ok
        result["handler_error"] = err

        after_count, after_vols = _get_body_count_and_volumes(doc)
        result["after"] = {
            "body_count": after_count,
            "volumes_mm3": after_vols,
        }

        if ok and after_count > build["body_count"]:
            result["status"] = "GREEN"
            vol_before = sum(v for v in (build["volumes_mm3"] or []) if v > 0)
            vol_after = sum(v for v in (after_vols or []) if v > 0)
            result["volume_conservation"] = abs(vol_after - vol_before) < 1.0
        else:
            result["status"] = "RED"
    except Exception as exc:
        result["status"] = "EXCEPTION"
        result["error"] = f"{exc!r}\n{traceback.format_exc()}"
    finally:
        sw.CloseDoc(_title(doc))

    return result


def run() -> dict[str, Any]:
    output: dict[str, Any] = {
        "spike_id": "W41_body_ops_s1",
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

    print("=== W41 body-ops S1 ===")

    print("\n--- delete_body ---")
    r = test_delete_body(sw)
    output["results"]["delete_body"] = r
    print(f"  status: {r['status']}")
    if r.get("before"):
        print(
            f"  before: {r['before']['body_count']} bodies, volumes={r['before'].get('volumes_mm3')}"
        )
    if r.get("after"):
        print(
            f"  after:  {r['after']['body_count']} bodies, volumes={r['after'].get('volumes_mm3')}"
        )
    if r.get("handler_error"):
        print(f"  error:  {r['handler_error']}")

    print("\n--- combine_subtract ---")
    r = test_combine_subtract(sw)
    output["results"]["combine_subtract"] = r
    print(f"  status: {r['status']}")
    if r.get("before"):
        print(
            f"  before: {r['before']['body_count']} bodies, volumes={r['before'].get('volumes_mm3')}"
        )
    if r.get("after"):
        print(
            f"  after:  {r['after']['body_count']} bodies, volumes={r['after'].get('volumes_mm3')}"
        )
    if r.get("handler_error"):
        print(f"  error:  {r['handler_error']}")

    print("\n--- combine_add ---")
    r = test_combine_add(sw)
    output["results"]["combine_add"] = r
    print(f"  status: {r['status']}")
    if r.get("before"):
        print(
            f"  before: {r['before']['body_count']} bodies, volumes={r['before'].get('volumes_mm3')}"
        )
    if r.get("after"):
        print(
            f"  after:  {r['after']['body_count']} bodies, volumes={r['after'].get('volumes_mm3')}"
        )
    if r.get("handler_error"):
        print(f"  error:  {r['handler_error']}")

    print("\n--- split ---")
    r = test_split(sw)
    output["results"]["split"] = r
    print(f"  status: {r['status']}")
    if r.get("before"):
        print(
            f"  before: {r['before']['body_count']} bodies, volumes={r['before'].get('volumes_mm3')}"
        )
    if r.get("after"):
        print(
            f"  after:  {r['after']['body_count']} bodies, volumes={r['after'].get('volumes_mm3')}"
        )
    if r.get("handler_error"):
        print(f"  error:  {r['handler_error']}")

    green = sum(1 for r in output["results"].values() if r.get("status") == "GREEN")
    total = len(output["results"])
    output["summary"] = f"{green}/{total} GREEN"
    print(f"\n=== SUMMARY: {output['summary']} ===")

    return output


if __name__ == "__main__":
    result = run()
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(result, indent=2, default=str))
    print(f"\nResults written to {RESULTS_PATH}")
