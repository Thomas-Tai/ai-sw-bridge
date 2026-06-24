"""Spike W21 / PATTERNS — materialization probe for linear + circular + mirror.

Tests feature_add pattern creation via the proven build-spec COM recipes
(FeatureLinearPattern5 / FeatureCircularPattern5 / InsertMirrorFeature2)
adapted for the mutate path (select seed BY NAME via SelectByID2 or
IFeature.Select2, instead of by direct IFeature reference).

CRUX: can a feature be selected by tree-name out-of-process for pattern
creation? The build-spec builder has IFeature references from build
order; feature_add only has string names.

Probes per route:
  LINEAR:   seed (BODYFEATURE) + direction edge → FeatureLinearPattern5 (22 args)
  CIRCULAR: seed (BODYFEATURE) + ref axis → FeatureCircularPattern5 (14 args)
  MIRROR:   seed (BODYFEATURE) + named plane → InsertMirrorFeature2 (5 args)

For each: selection mark, success-signal contract, feature count delta,
pattern type name, instance count.

Usage:
    .venv-py310/Scripts/python.exe spikes/v0_2x/spike_patterns.py
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
_V15 = Path(__file__).resolve().parents[1] / "v0_15"
sys.path.insert(0, str(_PKG_ROOT))
sys.path.insert(0, str(_V15))

WORKTREE = Path(__file__).resolve().parents[2]
RESULTS_PATH = WORKTREE / "spikes" / "v0_2x" / "_results" / "patterns.json"

import pythoncom  # noqa: E402

from ai_sw_bridge.com.earlybind import typed, typed_qi  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402

from spike_earlybind_persist import connect_running_sw, ensure_sw_module  # noqa: E402

SW_DEFAULT_TEMPLATE_PART = 8


def _type_name(feat: Any) -> str | None:
    for attr in ("GetTypeName2", "GetTypeName"):
        try:
            m = getattr(feat, attr)
            return str(m() if callable(m) else m)
        except Exception:
            continue
    return None


def _feat_name(feat: Any) -> str | None:
    for attr in ("Name",):
        try:
            v = getattr(feat, attr)
            return str(v() if callable(v) else v)
        except Exception:
            continue
    return None


def _title(d: Any) -> Any:
    t = d.GetTitle
    return t() if callable(t) else t


def _try_close(sw: Any, doc: Any) -> None:
    try:
        sw.CloseDoc(_title(doc))
    except Exception:
        pass


def _feat_count(fm: Any) -> int:
    _feats = fm.GetFeatures(True)
    return len(_feats) if _feats else 0


def _find_feature_by_name(fm: Any, name: str) -> Any:
    feats = fm.GetFeatures(True)
    if not feats:
        return None
    for f in feats:
        n = _feat_name(f)
        if n == name:
            return f
    return None


def _count_pattern_instances(fm: Any, pattern_name: str) -> int | None:
    """Count instances in a pattern feature by examining sub-features or body delta."""
    feat = _find_feature_by_name(fm, pattern_name)
    if feat is None:
        return None
    # Method 1: GetSubFeatures (pattern sub-features = instances)
    try:
        sub_feats = feat.GetSubFeatures()
        if sub_feats and len(sub_feats) > 0:
            return len(sub_feats)
    except Exception:
        pass
    # Method 2: try GetPatternFeatureCount or similar
    for method_name in (
        "GetPatternFeatureCount",
        "GetInstanceCount",
        "GetFeatureCount",
    ):
        try:
            method = getattr(feat, method_name, None)
            if method is not None:
                val = method() if callable(method) else method
                if isinstance(val, int) and val > 0:
                    return val
        except Exception:
            continue
    return None


def _build_geometry(doc: Any, mod: Any) -> dict[str, Any]:
    """Build: 20x20x10mm box + 5mm boss at (5,5) + ref_axis."""
    out: dict[str, Any] = {}
    fm = doc.FeatureManager

    # Box: sketch 20x20 rectangle on Front Plane, extrude 10mm
    try:
        doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
        doc.SketchManager.InsertSketch(True)
        doc.SketchManager.CreateCornerRectangle(-0.01, -0.01, 0, 0.01, 0.01, 0)
        doc.SketchManager.InsertSketch(True)
        f = fm.FeatureExtrusion3(
            True,
            False,
            False,
            0,
            0,
            0.01,
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
            0.0,
            0.0,
            False,
        )
        if f:
            f.Name = "Boss_Box"
            out["box"] = "Boss_Box"
        else:
            out["box_error"] = "FeatureExtrusion3 returned None"
            return out
    except Exception as e:
        out["box_error"] = f"{type(e).__name__}: {e}"
        return out

    # Boss: sketch 5mm circle at (5mm, 5mm) on top face, extrude 3mm
    try:
        doc.SelectByID("Boss_Box", "BODYFEATURE", 0, 0, 0)
        # Select top face by coordinate (0, 0, 10mm)
        ext = typed(doc.Extension, "IModelDocExtension", module=mod)
        if not ext.SelectByID2("", "FACE", 0.0, 0.0, 0.01, False, 0, None, 0):
            out["boss_error"] = "could not select top face"
            return out
        doc.SketchManager.InsertSketch(True)
        doc.SketchManager.CreateCircleByRadius(0.005, 0.005, 0, 0.0025)
        doc.SketchManager.InsertSketch(True)
        f = fm.FeatureExtrusion3(
            True,
            False,
            False,
            0,
            0,
            0.003,
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
            0.0,
            0.0,
            False,
        )
        if f:
            f.Name = "Boss_Seed"
            out["seed"] = "Boss_Seed"
        else:
            out["boss_error"] = "boss extrusion returned None"
    except Exception as e:
        out["boss_error"] = f"{type(e).__name__}: {e}"

    # Ref axis: intersection of Front Plane and Right Plane (the Y axis)
    try:
        doc.ClearSelection2(True)
        doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
        ext.SelectByID2("Right Plane", "PLANE", 0, 0, 0, True, 0, None, 0)
        doc.InsertAxis2(True)
        out["ref_axis"] = True
    except Exception as e:
        out["ref_axis_error"] = f"{type(e).__name__}: {e}"

    try:
        doc.ForceRebuild3(False)
    except Exception:
        pass

    return out


def _test_seed_selection(doc: Any, mod: Any, seed_name: str) -> dict[str, Any]:
    """Test selecting a feature by name — BODYFEATURE vs IFeature.Select2."""
    result: dict[str, Any] = {}
    ext = typed(doc.Extension, "IModelDocExtension", module=mod)

    # Method A: SelectByID2 with "BODYFEATURE"
    doc.ClearSelection2(True)
    try:
        ok = ext.SelectByID2(seed_name, "BODYFEATURE", 0, 0, 0, False, 4, None, 0)
        result["select_by_id2"] = {"result": ok}
    except Exception as e:
        result["select_by_id2"] = {"exception": f"{type(e).__name__}: {e}"[:200]}

    # Verify selection
    try:
        sel_mgr = doc.SelectionManager
        count = sel_mgr.GetSelectedObjectCount2(-1)
        result["select_by_id2"]["sel_count"] = count
        if count and count > 0:
            obj = sel_mgr.GetSelectedObject6(1, -1)
            result["select_by_id2"]["obj_type"] = type(obj).__name__ if obj else "None"
    except Exception as e:
        result["select_by_id2"]["verify_error"] = str(e)[:100]

    # Method B: GetFeatureByName + IFeature.Select2
    doc.ClearSelection2(True)
    try:
        fm = doc.FeatureManager
        feat = _find_feature_by_name(fm, seed_name)
        if feat is None:
            result["ifeature_select2"] = {"error": "feature not found by name"}
        else:
            ok = feat.Select2(False, 4)
            result["ifeature_select2"] = {"result": ok}
            sel_mgr = doc.SelectionManager
            count = sel_mgr.GetSelectedObjectCount2(-1)
            result["ifeature_select2"]["sel_count"] = count
    except Exception as e:
        result["ifeature_select2"] = {"exception": f"{type(e).__name__}: {e}"[:200]}

    doc.ClearSelection2(True)
    return result


def _probe_linear(doc: Any, fm: Any, mod: Any, seed_name: str) -> dict[str, Any]:
    """Linear pattern: seed + direction edge → FeatureLinearPattern5."""
    result: dict[str, Any] = {}
    ext = typed(doc.Extension, "IModelDocExtension", module=mod)

    count_before = _feat_count(fm)
    result["feature_count_before"] = count_before

    # Step 1: Select direction edge (mark=1)
    # Use SelectByID (5-arg, no Callout) + SetSelectedObjectMark
    # Edge on box top: point at (0, 10mm, 10mm) = (0, 0.01, 0.01) m
    doc.ClearSelection2(True)
    try:
        ok = doc.SelectByID("", "EDGE", 0.0, 0.01, 0.01)
        result["direction_select"] = {"method": "SelectByID+SetMark", "result": ok}
        if ok:
            sel_mgr = doc.SelectionManager
            sel_mgr.SetSelectedObjectMark(1, 1, 0)  # mark=1 for direction
            result["direction_select"]["mark_set"] = True
    except Exception as e:
        result["direction_select"] = {"exception": f"{type(e).__name__}: {e}"[:200]}
        result["verdict"] = "NO-GO"
        result["failure_point"] = "direction edge selection failed"
        return result

    if not result["direction_select"].get("result"):
        # Try alternate point
        try:
            ok2 = doc.SelectByID("", "EDGE", 0.01, 0.0, 0.01)
            result["direction_select_alt"] = {"result": ok2}
            if ok2:
                sel_mgr = doc.SelectionManager
                sel_mgr.SetSelectedObjectMark(1, 1, 0)
        except Exception:
            pass
        if not ok2:
            result["verdict"] = "NO-GO"
            result["failure_point"] = "direction edge not found at probe points"
            result["feature_count_after"] = _feat_count(fm)
            return result

    # Step 2: Select seed feature (mark=4)
    try:
        feat_obj = _find_feature_by_name(fm, seed_name)
        if feat_obj is None:
            result["seed_select"] = {"error": "feature not found"}
            result["verdict"] = "NO-GO"
            result["failure_point"] = f"seed feature '{seed_name}' not found"
            return result
        ok = feat_obj.Select2(True, 4)  # append=True, mark=4
        result["seed_select"] = {"method": "IFeature.Select2", "result": ok}
    except Exception as e:
        result["seed_select"] = {"exception": f"{type(e).__name__}: {e}"[:200]}
        result["verdict"] = "NO-GO"
        result["failure_point"] = "seed selection failed"
        return result

    # Verify selection set + marks
    try:
        sel_mgr = doc.SelectionManager
        sel_count = sel_mgr.GetSelectedObjectCount2(-1)
        result["selection_count"] = sel_count
        sel_details = []
        for idx in range(1, (sel_count or 0) + 1):
            try:
                obj = sel_mgr.GetSelectedObject6(idx, -1)
                obj_type = type(obj).__name__ if obj else "None"
                sel_details.append({"index": idx, "type": obj_type})
            except Exception:
                sel_details.append({"index": idx, "error": True})
        result["selected_objects"] = sel_details
    except Exception:
        pass

    # Step 3: FeatureLinearPattern5 (22 args) — proven builder recipe
    spacing_m = 0.005  # 5mm
    pattern_count = 3
    try:
        args = (
            pattern_count,
            spacing_m,
            1,
            0.0,  # Num1, Spacing1, Num2, Spacing2
            False,
            False,  # FlipDir1, FlipDir2
            "",
            "",  # DName1, DName2
            False,
            False,  # GeometryPattern, VaryInstance
            False,
            False,  # HasOffset1, HasOffset2
            False,
            False,  # CtrlByNum1, CtrlByNum2
            False,
            False,  # FromCentroid1, FromCentroid2
            False,
            False,  # RevOffset1, RevOffset2
            0.0,
            0.0,  # Offset1, Offset2
            False,
            False,  # D2PatternSeedOnly, SyncSubAssemblies
        )
        feat = fm.FeatureLinearPattern5(*args)
        result["create_feature"] = {
            "is_none": feat is None,
            "type": type(feat).__name__ if feat else "NoneType",
        }
        if feat:
            result["create_feature"]["type_name"] = _type_name(feat)
            result["create_feature"]["name"] = _feat_name(feat)
    except Exception as e:
        result["create_feature"] = {"exception": f"{type(e).__name__}: {e}"[:200]}
        feat = None

    # Liveness gate
    count_after = _feat_count(fm)
    delta = count_after - count_before
    result["feature_count_after"] = count_after
    result["count_delta"] = delta

    # Dump feature tree for diagnostics
    try:
        feats = fm.GetFeatures(True)
        tree = []
        if feats:
            for f in feats:
                tree.append(
                    {
                        "name": _feat_name(f),
                        "type": _type_name(f),
                    }
                )
        result["feature_tree"] = tree
    except Exception:
        pass

    # Find the new pattern feature
    new_feat_type = None
    new_feat_name = None
    try:
        feats = fm.GetFeatures(True)
        if feats:
            for f in feats:
                tn = _type_name(f)
                if tn and ("LPattern" in tn or "LinearPattern" in tn):
                    new_feat_type = tn
                    new_feat_name = _feat_name(f)
                    break
    except Exception:
        pass
    result["new_feature_type_name"] = new_feat_type
    result["new_feature_name"] = new_feat_name

    # Instance count
    if new_feat_name:
        instances = _count_pattern_instances(fm, new_feat_name)
        result["instance_count"] = instances

    # Success-signal contract
    if delta >= 1 and new_feat_type:
        instances = result.get("instance_count")
        if instances is not None and instances >= 2:
            result["verdict"] = "GO"
            result["instance_verified"] = True
        elif instances is None:
            result["verdict"] = "GO"
            result["instance_verified"] = False
            result["instance_note"] = (
                "GetSubFeatures returned None; pattern type name confirms creation "
                "but exact instance count unverified out-of-process"
            )
        else:
            result["verdict"] = "NO-GO"
            result["failure_point"] = (
                f"pattern created but instances={instances} (need >=2)"
            )
        if feat is None or isinstance(feat, int):
            result["success_signal_contract"] = "COUNT_DELTA"
        else:
            result["success_signal_contract"] = "RETURN_VALUE"
    else:
        result["verdict"] = "NO-GO"
        result["failure_point"] = (
            f"pattern did not materialize (delta={delta}, type={new_feat_type})"
        )

    # Alternate approach: use ref_axis as direction (like circular uses axis)
    if result["verdict"] == "NO-GO" and delta == 0:
        doc.ClearSelection2(True)
        alt_result: dict[str, Any] = {}
        try:
            ok = ext.SelectByID2("Axis1", "AXIS", 0, 0, 0, False, 1, None, 0)
            alt_result["axis_direction_select"] = {"result": ok}
        except Exception as e:
            alt_result["axis_direction_select"] = {"exception": str(e)[:100]}
            ok = False

        if ok:
            try:
                feat_obj2 = _find_feature_by_name(fm, seed_name)
                if feat_obj2:
                    ok2 = feat_obj2.Select2(True, 4)
                    alt_result["seed_select_alt"] = {"result": ok2}
            except Exception:
                ok2 = False

            if ok2:
                count_before_alt = _feat_count(fm)
                try:
                    feat_alt = fm.FeatureLinearPattern5(
                        pattern_count,
                        spacing_m,
                        1,
                        0.0,
                        False,
                        False,
                        "",
                        "",
                        False,
                        False,
                        False,
                        False,
                        False,
                        False,
                        False,
                        False,
                        False,
                        False,
                        0.0,
                        0.0,
                        False,
                        False,
                    )
                    alt_result["create_feature_alt"] = {
                        "is_none": feat_alt is None,
                        "type": type(feat_alt).__name__ if feat_alt else "NoneType",
                    }
                    if feat_alt:
                        alt_result["create_feature_alt"]["type_name"] = _type_name(
                            feat_alt
                        )
                except Exception as e:
                    alt_result["create_feature_alt"] = {"exception": str(e)[:100]}
                    feat_alt = None

                count_after_alt = _feat_count(fm)
                alt_result["count_delta_alt"] = count_after_alt - count_before_alt

                # Check for pattern
                try:
                    feats = fm.GetFeatures(True)
                    if feats:
                        for f in feats:
                            tn = _type_name(f)
                            if tn and ("LPattern" in tn or "LinearPattern" in tn):
                                alt_result["alt_pattern_found"] = tn
                                break
                except Exception:
                    pass

        result["alternate_axis_approach"] = alt_result

    return result


def _probe_circular(doc: Any, fm: Any, mod: Any, seed_name: str) -> dict[str, Any]:
    """Circular pattern: seed + axis → FeatureCircularPattern5."""
    result: dict[str, Any] = {}
    ext = typed(doc.Extension, "IModelDocExtension", module=mod)

    count_before = _feat_count(fm)
    result["feature_count_before"] = count_before

    # Step 1: Select axis reference (mark=1)
    # Try: select "Axis1" (the ref axis we created) via SelectByID2
    doc.ClearSelection2(True)
    axis_selected = False
    # Method A: SelectByID2 with "AXIS"
    try:
        ok = ext.SelectByID2("Axis1", "AXIS", 0, 0, 0, False, 1, None, 0)
        result["axis_select"] = {"method": "SelectByID2 AXIS", "result": ok}
        if ok:
            axis_selected = True
    except Exception as e:
        result["axis_select"] = {"exception": f"{type(e).__name__}: {e}"[:200]}

    # Method B: try "DATUMAXIS" type
    if not axis_selected:
        try:
            ok = ext.SelectByID2("Axis1", "DATUMAXIS", 0, 0, 0, False, 1, None, 0)
            result["axis_select_datum"] = {"result": ok}
            if ok:
                axis_selected = True
        except Exception:
            pass

    # Method C: SelectByID (5-arg) + SetSelectedObjectMark
    if not axis_selected:
        try:
            ok = doc.SelectByID("Axis1", "AXIS", 0, 0, 0)
            if ok:
                sel_mgr = doc.SelectionManager
                sel_mgr.SetSelectedObjectMark(1, 1, 0)
                axis_selected = True
            result["axis_select_5arg"] = {"result": ok}
        except Exception:
            pass

    if not axis_selected:
        result["verdict"] = "NO-GO"
        result["failure_point"] = "could not select axis reference"
        result["feature_count_after"] = _feat_count(fm)
        result["count_delta"] = 0
        return result

    # Step 2: Select seed feature (mark=4)
    try:
        feat_obj = _find_feature_by_name(fm, seed_name)
        if feat_obj is None:
            result["seed_select"] = {"error": "feature not found"}
            result["verdict"] = "NO-GO"
            result["failure_point"] = f"seed '{seed_name}' not found"
            return result
        ok = feat_obj.Select2(True, 4)
        result["seed_select"] = {"method": "IFeature.Select2", "result": ok}
    except Exception as e:
        result["seed_select"] = {"exception": f"{type(e).__name__}: {e}"[:200]}
        result["verdict"] = "NO-GO"
        result["failure_point"] = "seed selection failed"
        return result

    # Step 3: FeatureCircularPattern5 (14 args)
    pattern_count = 4
    total_angle_rad = 2 * math.pi  # 360 degrees
    try:
        args = (
            pattern_count,  # Number
            total_angle_rad,  # Spacing (total angle when EqualSpacing=True)
            False,  # FlipDirection
            "",  # DName
            False,  # GeometryPattern
            True,  # EqualSpacing
            False,  # VaryInstance
            False,  # SyncSubAssemblies
            False,  # BDir2
            False,  # BSymmetric
            1,  # Number2
            0.0,  # Spacing2
            "",  # DName2
            False,  # EqualSpacing2
        )
        feat = fm.FeatureCircularPattern5(*args)
        result["create_feature"] = {
            "is_none": feat is None,
            "type": type(feat).__name__ if feat else "NoneType",
        }
        if feat:
            result["create_feature"]["type_name"] = _type_name(feat)
            result["create_feature"]["name"] = _feat_name(feat)
    except Exception as e:
        result["create_feature"] = {"exception": f"{type(e).__name__}: {e}"[:200]}
        feat = None

    # Liveness gate
    count_after = _feat_count(fm)
    delta = count_after - count_before
    result["feature_count_after"] = count_after
    result["count_delta"] = delta

    new_feat_type = None
    new_feat_name = None
    try:
        feats = fm.GetFeatures(True)
        if feats:
            for f in feats:
                tn = _type_name(f)
                if tn and (
                    "CirPattern" in tn or "CircularPattern" in tn or "LPattern" in tn
                ):
                    new_feat_type = tn
                    new_feat_name = _feat_name(f)
                    break
    except Exception:
        pass
    result["new_feature_type_name"] = new_feat_type
    result["new_feature_name"] = new_feat_name

    if new_feat_name:
        instances = _count_pattern_instances(fm, new_feat_name)
        result["instance_count"] = instances

    if delta >= 1 and new_feat_type:
        instances = result.get("instance_count")
        if instances is not None and instances >= 2:
            result["verdict"] = "GO"
            result["instance_verified"] = True
        elif instances is None:
            result["verdict"] = "GO"
            result["instance_verified"] = False
            result["instance_note"] = (
                "GetSubFeatures returned None; pattern type name confirms creation "
                "but exact instance count unverified out-of-process"
            )
        else:
            result["verdict"] = "NO-GO"
            result["failure_point"] = (
                f"pattern created but instances={instances} (need >=2)"
            )
        if feat is None or isinstance(feat, int):
            result["success_signal_contract"] = "COUNT_DELTA"
        else:
            result["success_signal_contract"] = "RETURN_VALUE"
    else:
        result["verdict"] = "NO-GO"
        result["failure_point"] = (
            f"pattern did not materialize (delta={delta}, type={new_feat_type})"
        )

    return result


def _probe_mirror(doc: Any, fm: Any, mod: Any, seed_name: str) -> dict[str, Any]:
    """Mirror feature: seed + plane → InsertMirrorFeature2."""
    result: dict[str, Any] = {}
    ext = typed(doc.Extension, "IModelDocExtension", module=mod)

    count_before = _feat_count(fm)
    result["feature_count_before"] = count_before

    # Step 1: Select mirror plane (mark=2)
    doc.ClearSelection2(True)
    try:
        ok = doc.SelectByID("Right Plane", "PLANE", 0, 0, 0)
        result["plane_select"] = {"method": "SelectByID+SetMark", "result": ok}
        if ok:
            sel_mgr = doc.SelectionManager
            sel_mgr.SetSelectedObjectMark(1, 2, 0)  # mark=2 for mirror plane
    except Exception as e:
        result["plane_select"] = {"exception": f"{type(e).__name__}: {e}"[:200]}
        result["verdict"] = "NO-GO"
        result["failure_point"] = "plane selection failed"
        return result

    # Step 2: Select seed (mark=1)
    try:
        feat_obj = _find_feature_by_name(fm, seed_name)
        if feat_obj is None:
            result["verdict"] = "NO-GO"
            result["failure_point"] = f"seed '{seed_name}' not found"
            return result
        ok = feat_obj.Select2(True, 1)  # append=True, mark=1
        result["seed_select"] = {"method": "IFeature.Select2", "result": ok}
    except Exception as e:
        result["seed_select"] = {"exception": f"{type(e).__name__}: {e}"[:200]}
        result["verdict"] = "NO-GO"
        result["failure_point"] = "seed selection failed"
        return result

    # Step 3: InsertMirrorFeature2 (5 args)
    try:
        feat = fm.InsertMirrorFeature2(False, False, False, False, 0)
        result["create_feature"] = {
            "is_none": feat is None,
            "type": type(feat).__name__ if feat else "NoneType",
        }
        if feat:
            result["create_feature"]["type_name"] = _type_name(feat)
            result["create_feature"]["name"] = _feat_name(feat)
    except Exception as e:
        result["create_feature"] = {"exception": f"{type(e).__name__}: {e}"[:200]}
        feat = None

    # Liveness gate
    count_after = _feat_count(fm)
    delta = count_after - count_before
    result["feature_count_after"] = count_after
    result["count_delta"] = delta

    new_feat_type = None
    new_feat_name = None
    try:
        feats = fm.GetFeatures(True)
        if feats:
            for f in feats:
                tn = _type_name(f)
                if tn and ("Mirror" in tn or "MirrorPattern" in tn):
                    new_feat_type = tn
                    new_feat_name = _feat_name(f)
                    break
    except Exception:
        pass
    result["new_feature_type_name"] = new_feat_type

    if delta >= 1 and new_feat_type:
        result["verdict"] = "GO"
        if feat is None or isinstance(feat, int):
            result["success_signal_contract"] = "COUNT_DELTA"
        else:
            result["success_signal_contract"] = "RETURN_VALUE"
    else:
        result["verdict"] = "NO-GO"
        result["failure_point"] = (
            f"mirror did not materialize (delta={delta}, type={new_feat_type})"
        )

    return result


def run() -> dict[str, Any]:
    result: dict[str, Any] = {
        "spike": "w21_patterns_materialization",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "binding": "hybrid early (com.earlybind pattern)",
    }

    mod = wrapper_module()
    mod_source = "com.sw_type_info.wrapper_module"
    if mod is None:
        mod, info = ensure_sw_module()
        mod_source = "spike_earlybind_persist.ensure_sw_module (fallback)"
        result["module_fallback_info"] = info
    result["module_source"] = mod_source

    sw = connect_running_sw()
    try:
        result["sw_revision"] = str(sw.RevisionNumber)
    except Exception:
        result["sw_revision"] = "<unreadable>"

    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        result["overall"] = "NO-GO"
        result["failure_point"] = "NewDocument returned None"
        return result

    fm = doc.FeatureManager

    # Build geometry
    geom = _build_geometry(doc, mod)
    result["geometry"] = geom

    seed_name = geom.get("seed")
    if not seed_name:
        result["overall"] = "NO-GO"
        result["failure_point"] = f"geometry build failed: {geom}"
        _try_close(sw, doc)
        return result

    # Test seed selection methods
    sel_test = _test_seed_selection(doc, mod, seed_name)
    result["seed_selection_probe"] = sel_test

    # Probe linear pattern
    print("--- LINEAR PATTERN ---", file=sys.stderr)
    linear = _probe_linear(doc, fm, mod, seed_name)
    result["linear_pattern"] = linear
    print(f"  verdict: {linear.get('verdict')}", file=sys.stderr)

    # If linear failed, try standalone cylinder (avoids ICE seed type)
    if linear.get("verdict") == "NO-GO":
        print("--- LINEAR ALT: standalone cylinder ---", file=sys.stderr)
        _try_close(sw, doc)
        doc = sw.NewDocument(template, 0, 0.0, 0.0)
        if doc:
            fm = doc.FeatureManager
            ext_alt = typed(doc.Extension, "IModelDocExtension", module=mod)
            try:
                # Build box only (Extrusion type, no boss)
                doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
                doc.SketchManager.InsertSketch(True)
                doc.SketchManager.CreateCornerRectangle(-0.01, -0.01, 0, 0.01, 0.01, 0)
                doc.SketchManager.InsertSketch(True)
                f = fm.FeatureExtrusion3(
                    True,
                    False,
                    False,
                    0,
                    0,
                    0.01,
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
                    0.0,
                    0.0,
                    False,
                )
                if f:
                    f.Name = "Box"
                doc.ForceRebuild3(False)
                feat_obj = _find_feature_by_name(fm, "Box")
                result["linear_alt_seed_type"] = (
                    _type_name(feat_obj) if feat_obj else "?"
                )

                # Select direction: box edge at (0, 10mm, 10mm)
                doc.ClearSelection2(True)
                ok = doc.SelectByID("", "EDGE", 0.0, 0.01, 0.01)
                if ok:
                    sel_mgr = doc.SelectionManager
                    sel_mgr.SetSelectedObjectMark(1, 1, 0)
                    # Select seed
                    if feat_obj:
                        ok2 = feat_obj.Select2(True, 4)
                        if ok2:
                            count_b = _feat_count(fm)
                            feat_result = fm.FeatureLinearPattern5(
                                3,
                                0.005,
                                1,
                                0.0,
                                False,
                                False,
                                "",
                                "",
                                False,
                                False,
                                False,
                                False,
                                False,
                                False,
                                False,
                                False,
                                False,
                                False,
                                0.0,
                                0.0,
                                False,
                                False,
                            )
                            count_a = _feat_count(fm)
                            result["linear_alt_box"] = {
                                "create_result": (
                                    type(feat_result).__name__
                                    if feat_result
                                    else "None"
                                ),
                                "count_delta": count_a - count_b,
                            }
                            if feat_result:
                                result["linear_alt_box"]["type_name"] = _type_name(
                                    feat_result
                                )
                else:
                    result["linear_alt_box"] = {"direction_select": False}
            except Exception as e:
                result["linear_alt_box_error"] = str(e)[:200]

    # If still failing, try the box approach from first doc with Extrusion seed
    if (
        linear.get("verdict") == "NO-GO"
        and result.get("linear_alt_box", {}).get("count_delta", 0) == 0
    ):
        print("--- LINEAR ALT2: box seed (Extrusion type) ---", file=sys.stderr)
        # Use first doc's box as seed instead of Boss_Seed
        _try_close(sw, doc)
        doc = sw.NewDocument(template, 0, 0.0, 0.0)
        if doc:
            fm = doc.FeatureManager
            try:
                doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
                doc.SketchManager.InsertSketch(True)
                doc.SketchManager.CreateCornerRectangle(-0.01, -0.01, 0, 0.01, 0.01, 0)
                doc.SketchManager.InsertSketch(True)
                f = fm.FeatureExtrusion3(
                    True,
                    False,
                    False,
                    0,
                    0,
                    0.01,
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
                    0.0,
                    0.0,
                    False,
                )
                if f:
                    f.Name = "Box"
                doc.ForceRebuild3(False)
                box_feat = _find_feature_by_name(fm, "Box")
                ext2 = typed(doc.Extension, "IModelDocExtension", module=mod)

                doc.ClearSelection2(True)
                ok = doc.SelectByID("", "EDGE", 0.0, 0.01, 0.01)
                if ok:
                    sel_mgr = doc.SelectionManager
                    sel_mgr.SetSelectedObjectMark(1, 1, 0)
                    if box_feat:
                        ok2 = box_feat.Select2(True, 4)
                        if ok2:
                            count_b2 = _feat_count(fm)
                            feat_r2 = fm.FeatureLinearPattern5(
                                3,
                                0.005,
                                1,
                                0.0,
                                False,
                                False,
                                "",
                                "",
                                False,
                                False,
                                False,
                                False,
                                False,
                                False,
                                False,
                                False,
                                False,
                                False,
                                0.0,
                                0.0,
                                False,
                                False,
                            )
                            count_a2 = _feat_count(fm)
                            result["linear_alt2_box_extrusion"] = {
                                "seed_type": "Extrusion",
                                "create_result": (
                                    type(feat_r2).__name__ if feat_r2 else "None"
                                ),
                                "count_delta": count_a2 - count_b2,
                            }
                            if feat_r2:
                                result["linear_alt2_box_extrusion"]["type_name"] = (
                                    _type_name(feat_r2)
                                )
                else:
                    result["linear_alt2_box_extrusion"] = {"direction_select": False}
            except Exception as e:
                result["linear_alt2_error"] = str(e)[:200]

    # Probe circular pattern (needs new doc — linear pattern changed geometry)
    _try_close(sw, doc)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        result["overall"] = "PARTIAL"
        result["failure_point"] = "could not create second doc for circular"
        return result
    fm = doc.FeatureManager
    geom2 = _build_geometry(doc, mod)
    seed_name2 = geom2.get("seed")
    if not seed_name2:
        result["circular_pattern"] = {
            "verdict": "NO-GO",
            "failure_point": "geometry rebuild failed",
        }
    else:
        print("--- CIRCULAR PATTERN ---", file=sys.stderr)
        circular = _probe_circular(doc, fm, mod, seed_name2)
        result["circular_pattern"] = circular
        print(f"  verdict: {circular.get('verdict')}", file=sys.stderr)

    # Probe mirror (third doc)
    _try_close(sw, doc)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        result["mirror_feature"] = {
            "verdict": "NO-GO",
            "failure_point": "could not create third doc",
        }
    else:
        fm = doc.FeatureManager
        geom3 = _build_geometry(doc, mod)
        seed_name3 = geom3.get("seed")
        if not seed_name3:
            result["mirror_feature"] = {
                "verdict": "NO-GO",
                "failure_point": "geometry rebuild failed",
            }
        else:
            print("--- MIRROR FEATURE ---", file=sys.stderr)
            mirror = _probe_mirror(doc, fm, mod, seed_name3)
            result["mirror_feature"] = mirror
            print(f"  verdict: {mirror.get('verdict')}", file=sys.stderr)
        _try_close(sw, doc)

    # Overall verdict — check alt linear too
    verdicts = []
    linear_verdict = result.get("linear_pattern", {}).get("verdict", "NO-GO")
    alt_linear = result.get("linear_pattern_alt_cylinder", {})
    if alt_linear.get("verdict") == "GO":
        linear_verdict = "GO"
        result["linear_pattern"]["verdict"] = "GO"
        result["linear_pattern"]["alt_cylinder_go"] = True
    for route_verdict in [
        linear_verdict,
        result.get("circular_pattern", {}).get("verdict", "NO-GO"),
        result.get("mirror_feature", {}).get("verdict", "NO-GO"),
    ]:
        verdicts.append(route_verdict)
    if any(v == "GO" for v in verdicts):
        result["overall"] = "GO"
    else:
        result["overall"] = "NO-GO"

    result["summary"] = {
        "linear": result.get("linear_pattern", {}).get("verdict", "NO-GO"),
        "circular": result.get("circular_pattern", {}).get("verdict", "NO-GO"),
        "mirror": result.get("mirror_feature", {}).get("verdict", "NO-GO"),
    }

    return result


def _scrub(o: Any) -> Any:
    if isinstance(o, dict):
        return {k: _scrub(v) for k, v in o.items() if not k.startswith("_")}
    if isinstance(o, list):
        return [_scrub(v) for v in o]
    return o


def main() -> int:
    pythoncom.CoInitialize()
    try:
        result = run()
    finally:
        pythoncom.CoUninitialize()
    payload = json.dumps(
        _scrub(result), indent=2, default=lambda o: f"<{type(o).__name__}>"
    )
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(payload, encoding="utf-8")
    print(f"wrote {RESULTS_PATH}", file=sys.stderr)
    print(payload)
    return 0 if result.get("overall") == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())
