"""Spike W22 / ASM_PATTERNS — assembly component-pattern materialization probe.

Tests three routes for replicating a placed seed COMPONENT in an assembly:
  LINEAR:   select seed component + direction edge → IFeatureManager.FeatureLinearPattern5
  CIRCULAR: select seed component + axis → IFeatureManager.FeatureCircularPattern5
  MIRROR:   mirror plane + seed component → IAssemblyDoc.MirrorComponents (v1, 9 args)

FINDINGS (SW 2024 SP1, seat-proven 2026-06-06):
  LINEAR:   NO-GO — FeatureLinearPattern5 returns None on assembly FeatureManager.
            Also tested: FeatureLinearPattern4, FeatureLinearPattern3,
            FeatureDimensionPattern — all None. No API path for assembly linear
            component patterns found on IFeatureManager or IAssemblyDoc.
  CIRCULAR: NO-GO — same wall. FeatureCircularPattern5 returns None in assembly context.
  MIRROR:   GO — MirrorComponents v1 (9 args) creates a mirrored component copy.
            CRITICAL: must use raw PyIDispatch (_oleobj_) not gen_py wrappers.
            MirrorComponents2/3 return None; IMirrorComponents raises TypeError.
            Recipe: MirrorComponents(rawPlane, VARIANT(VT_ARRAY|VT_DISPATCH, (rawComp,)),
            same_array, None, False, 0, "", dir_path, False).

Typelib dump (gen_py, SW 2024 SP1):
  - IFeatureManager.FeatureLinearPattern5: 22 args, returns IFeature — PART ONLY
  - IFeatureManager.FeatureCircularPattern5: 14 args, returns IFeature — PART ONLY
  - IAssemblyDoc.MirrorComponents: 9 args, returns IFeature — ASSEMBLY PROVEN
    Plane(IDISPATCH*) ComponentsToInstance(VT_ARRAY|VT_DISPATCH)
    ComponentsToMirror(VT_ARRAY|VT_DISPATCH) MirroredComponentFilenames(VARIANT)
    RecreateMates(BOOL) ComponentModifier(I4) ComponentNameModifier(BSTR)
    MirroredFileLocation(BSTR) CopyCustomProperties(BOOL)
  - IAssemblyDoc.MirrorComponents2: 13 args — WALLS (returns None)
  - IAssemblyDoc.MirrorComponents3: 14 args — WALLS (returns None)

Component selection: SelectByID2 "COMPONENT" returns False for assembly components.
IFeature.Select2(append, mark) on the feature-tree entry is the proven path.

Liveness gate (W21 lesson): GetComponentCount must grow by +1 for mirror.
Type name alone is NOT proof (W21 circular angle bug).

Usage:
    .venv-py310/Scripts/python.exe spikes/v0_2x/spike_asm_patterns.py
"""

from __future__ import annotations

import glob
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

WORKTREE = Path(__file__).resolve().parents[2]
RESULTS_PATH = WORKTREE / "spikes" / "v0_2x" / "_results" / "asm_patterns.json"

import pythoncom  # noqa: E402
import win32com.client as w32  # noqa: E402

from ai_sw_bridge.com.earlybind import typed, typed_qi  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402


_WORKTREE = Path(__file__).resolve().parents[2]
_V15 = Path(__file__).resolve().parents[1] / "v0_15"
sys.path.insert(0, str(_V15))

from spike_earlybind_persist import connect_running_sw  # noqa: E402


def _title(d: Any) -> Any:
    t = d.GetTitle
    if isinstance(t, tuple):
        t = t[0]
    return t() if callable(t) else t


def _try_close(sw: Any, doc: Any) -> None:
    try:
        sw.CloseDoc(_title(doc))
    except Exception:
        pass


def _comp_count(typed_asm: Any, top_only: bool = True) -> int:
    try:
        return int(typed_asm.GetComponentCount(top_only))
    except Exception:
        return -1


def _feat_name(feat: Any) -> str | None:
    for attr in ("Name",):
        try:
            v = getattr(feat, attr)
            return str(v() if callable(v) else v)
        except Exception:
            continue
    return None


def _type_name(feat: Any) -> str | None:
    for attr in ("GetTypeName2", "GetTypeName"):
        try:
            m = getattr(feat, attr)
            return str(m() if callable(m) else m)
        except Exception:
            continue
    return None


def _find_feat_by_name(fm: Any, name: str) -> Any:
    feats = fm.GetFeatures(True)
    if not feats:
        return None
    for f in feats:
        if _feat_name(f) == name:
            return f
    return None


def _build_box_part(save_path: str, mod: Any) -> bool:
    """Build a 20x20x10mm box part using the production builder."""
    from ai_sw_bridge.spec.builder import build as part_build

    spec = {
        "schema_version": 1,
        "name": "AsmPatternBox",
        "features": [
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK",
                "plane": "Front",
                "width": 20.0,
                "height": 10.0,
            },
            {
                "type": "boss_extrude_blind",
                "name": "EX",
                "sketch": "SK",
                "depth": 10.0,
            },
        ],
    }
    r = part_build(spec, save_as=save_path, save_format="current", no_dim=True)
    return r.ok and Path(save_path).is_file()


def _create_assembly(sw: Any, mod: Any) -> Any:
    """Create a new assembly document from the default template."""
    templates = glob.glob(
        r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\*.ASMDOT"
    )
    if not templates:
        return None
    return sw.NewDocument(templates[0], 0, 0.1, 0.1)


def _place_seed(sw: Any, asm_doc: Any, part_path: str, mod: Any) -> dict[str, Any]:
    """Place one component via AddComponent4 (pre-opened)."""
    typed_sw = typed(sw, "ISldWorks", module=mod)
    typed_asm = typed(asm_doc, "IAssemblyDoc", module=mod)

    # Pre-open (mandatory)
    open_ret = typed_sw.OpenDoc6(part_path, 1, 1, "", 0, 0)
    if isinstance(open_ret, tuple):
        part_doc = open_ret[0]
    else:
        part_doc = open_ret
    if part_doc is None:
        return {"error": "OpenDoc6 returned None"}

    # Place at origin
    comp = typed_asm.AddComponent4(part_path, "", 0.0, 0.0, 0.0)
    if comp is None or isinstance(comp, int):
        return {"error": "AddComponent4 returned None"}

    # Get component name in tree
    try:
        comp_name = comp.Name
        if callable(comp_name):
            comp_name = comp_name()
    except Exception:
        comp_name = None

    return {"comp": comp, "name": comp_name, "type": type(comp).__name__}


def _create_ref_axis(asm_doc: Any, mod: Any) -> dict[str, Any]:
    """Create a reference axis from Front Plane ∩ Right Plane intersection."""
    try:
        asm_doc.ClearSelection2(True)
        ok1 = asm_doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
        ext = typed(asm_doc.Extension, "IModelDocExtension", module=mod)
        ok2 = ext.SelectByID2("Right Plane", "PLANE", 0, 0, 0, True, 0, None, 0)
        if ok1 and ok2:
            asm_doc.InsertAxis2(True)
            return {"ok": True, "method": "Front∩Right"}
        return {"ok": False, "select_ok1": ok1, "select_ok2": ok2}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"[:200]}


def _select_component(doc: Any, mod: Any, comp_name: str, mark: int, append: bool) -> dict[str, Any]:
    """Select a component in the assembly by tree-name via IFeature.Select2.

    Seat-proven W22 diag: SelectByID2 "COMPONENT" returns False for assembly
    components. IComponent2.Select4 raises TypeError (gen_py wrapper can't
    convert). The working path is IFeature.Select2 on the feature-tree entry
    (same as W21 part-level patterns).
    """
    result: dict[str, Any] = {}
    fm = doc.FeatureManager

    if not append:
        doc.ClearSelection2(True)

    # Find the component's feature-tree entry by name
    feat_obj = _find_feat_by_name(fm, comp_name)
    if feat_obj is None:
        result["selected"] = False
        result["error"] = f"component '{comp_name}' not found in feature tree"
        return result

    try:
        ok = feat_obj.Select2(append, mark)
        result["method"] = "IFeature.Select2"
        result["ok"] = ok
        result["selected"] = ok
    except Exception as e:
        result["selected"] = False
        result["exception"] = f"{type(e).__name__}: {e}"[:200]

    return result


def _select_entity(doc: Any, mod: Any, name: str, entity_type: str, mark: int, append: bool) -> dict[str, Any]:
    """Select a non-component entity (edge, axis, plane) with a mark."""
    result: dict[str, Any] = {}
    ext = typed(doc.Extension, "IModelDocExtension", module=mod)

    if not append:
        doc.ClearSelection2(True)

    # Try SelectByID2 first
    try:
        ok = ext.SelectByID2(name, entity_type, 0, 0, 0, append, mark, None, 0)
        result["select_by_id2"] = {"ok": ok}
        if ok:
            result["selected"] = True
            return result
    except Exception as e:
        result["select_by_id2"] = {"exception": f"{type(e).__name__}: {e}"[:200]}

    # Fallback: SelectByID (5-arg) + SetSelectedObjectMark
    try:
        ok = doc.SelectByID(name, entity_type, 0, 0, 0)
        result["select_by_id_5arg"] = {"ok": ok}
        if ok:
            sel_mgr = doc.SelectionManager
            sel_mgr.SetSelectedObjectMark(1, mark, 0)
            result["selected"] = True
            return result
    except Exception as e:
        result["select_by_id_5arg"] = {"exception": f"{type(e).__name__}: {e}"[:200]}

    result["selected"] = False
    return result


def _probe_linear(
    asm_doc: Any, typed_asm: Any, fm: Any, mod: Any, comp_name: str
) -> dict[str, Any]:
    """Linear component pattern: seed component + direction edge → FeatureLinearPattern5."""
    result: dict[str, Any] = {}
    ext = typed(asm_doc.Extension, "IModelDocExtension", module=mod)

    count_before = _comp_count(typed_asm)
    result["component_count_before"] = count_before

    # Step 1: Select direction — an edge on the component
    # Try an edge at (10mm, 0, 10mm) = (0.01, 0, 0.01) m
    doc = asm_doc
    doc.ClearSelection2(True)
    edge_selected = False

    # Try several edge probe points on the 20x10x10 box at origin
    edge_points = [
        (0.01, 0.0, 0.01),
        (0.01, 0.005, 0.01),
        (0.0, 0.005, 0.01),
        (0.01, 0.0, 0.0),
        (0.0, 0.0, 0.01),
        (0.01, 0.005, 0.0),
    ]
    for i, (x, y, z) in enumerate(edge_points):
        try:
            ok = doc.SelectByID("", "EDGE", x, y, z)
            if ok:
                sel_mgr = doc.SelectionManager
                sel_mgr.SetSelectedObjectMark(1, 1, 0)  # mark=1 for direction
                edge_selected = True
                result["direction_select"] = {
                    "method": "SelectByID EDGE",
                    "point": [x, y, z],
                    "ok": True,
                    "mark": 1,
                }
                break
        except Exception as e:
            continue

    if not edge_selected:
        # Try assembly default axis (Axis1) if we created one
        try:
            ok = doc.SelectByID("Axis1", "AXIS", 0, 0, 0)
            if ok:
                sel_mgr = doc.SelectionManager
                sel_mgr.SetSelectedObjectMark(1, 1, 0)
                edge_selected = True
                result["direction_select"] = {
                    "method": "SelectByID AXIS Axis1",
                    "ok": True,
                    "mark": 1,
                }
        except Exception:
            pass

    if not edge_selected:
        result["verdict"] = "NO-GO"
        result["failure_point"] = "could not select direction entity"
        result["component_count_after"] = _comp_count(typed_asm)
        return result

    # Step 2: Select seed component (mark=4)
    sel_result = _select_component(doc, mod, comp_name, mark=4, append=True)
    result["seed_select"] = sel_result
    if not sel_result.get("selected"):
        result["verdict"] = "NO-GO"
        result["failure_point"] = f"could not select seed component '{comp_name}'"
        result["component_count_after"] = _comp_count(typed_asm)
        return result

    # Verify selection set
    try:
        sel_mgr = doc.SelectionManager
        sel_count = sel_mgr.GetSelectedObjectCount2(-1)
        result["selection_count"] = sel_count
    except Exception:
        pass

    # Step 3: FeatureLinearPattern5 (22 args) — same as part-level proven recipe
    spacing_m = 0.015  # 15mm
    pattern_count = 3
    try:
        feat = fm.FeatureLinearPattern5(
            pattern_count, spacing_m, 1, 0.0,  # Num1, Spacing1, Num2, Spacing2
            False, False,  # FlipDir1, FlipDir2
            "", "",  # DName1, DName2
            False, False,  # GeometryPattern, VaryInstance
            False, False,  # HasOffset1, HasOffset2
            False, False,  # CtrlByNum1, CtrlByNum2
            False, False,  # FromCentroid1, FromCentroid2
            False, False,  # RevOffset1, RevOffset2
            0.0, 0.0,  # Offset1, Offset2
            False, False,  # D2PatternSeedOnly, SyncSubAssemblies
        )
        result["create_feature"] = {
            "is_none": feat is None,
            "type": type(feat).__name__ if feat else "NoneType",
        }
        if feat and not isinstance(feat, int):
            result["create_feature"]["type_name"] = _type_name(feat)
            result["create_feature"]["name"] = _feat_name(feat)
    except Exception as e:
        result["create_feature"] = {"exception": f"{type(e).__name__}: {e}"[:300]}
        feat = None

    # Liveness gate — component count delta
    count_after = _comp_count(typed_asm)
    delta = count_after - count_before
    result["component_count_after"] = count_after
    result["count_delta"] = delta

    # Find pattern feature in tree
    pattern_type = None
    pattern_name = None
    try:
        feats = fm.GetFeatures(True)
        if feats:
            for f in feats:
                tn = _type_name(f)
                if tn and ("LPattern" in tn or "LocalLPattern" in tn or "LinearPattern" in tn):
                    pattern_type = tn
                    pattern_name = _feat_name(f)
                    break
    except Exception:
        pass
    result["pattern_feature"] = {"type": pattern_type, "name": pattern_name}

    # Feature tree dump for diagnostics
    try:
        feats = fm.GetFeatures(True)
        tree = []
        if feats:
            for f in feats:
                tree.append({"name": _feat_name(f), "type": _type_name(f)})
        result["feature_tree"] = tree
    except Exception:
        pass

    # Verdict
    if delta >= 1 and pattern_type:
        expected_delta = pattern_count - 1  # 2 additional instances
        if delta >= expected_delta:
            result["verdict"] = "GO"
            result["instance_verified"] = True
        else:
            result["verdict"] = "PARTIAL"
            result["note"] = f"pattern created but delta={delta} (expected {expected_delta})"
        if feat is None or isinstance(feat, int):
            result["success_signal_contract"] = "COUNT_DELTA"
        else:
            result["success_signal_contract"] = "RETURN_VALUE"
    elif pattern_type and delta == 0:
        result["verdict"] = "NO-GO"
        result["failure_point"] = "pattern feature created but 0 component instances added (hollow)"
    else:
        result["verdict"] = "NO-GO"
        result["failure_point"] = (
            f"pattern did not materialize (delta={delta}, type={pattern_type})"
        )

    return result


def _probe_circular(
    asm_doc: Any, typed_asm: Any, fm: Any, mod: Any, comp_name: str
) -> dict[str, Any]:
    """Circular component pattern: seed component + axis → FeatureCircularPattern5."""
    result: dict[str, Any] = {}
    doc = asm_doc

    count_before = _comp_count(typed_asm)
    result["component_count_before"] = count_before

    # Step 1: Select axis (mark=1)
    doc.ClearSelection2(True)
    axis_selected = False

    # Try Axis1
    try:
        ok = doc.SelectByID("Axis1", "AXIS", 0, 0, 0)
        if ok:
            sel_mgr = doc.SelectionManager
            sel_mgr.SetSelectedObjectMark(1, 1, 0)
            axis_selected = True
            result["axis_select"] = {"method": "SelectByID AXIS", "ok": True}
    except Exception as e:
        result["axis_select"] = {"exception": f"{type(e).__name__}: {e}"[:200]}

    if not axis_selected:
        # Try "Axis 1" (with space)
        try:
            ok = doc.SelectByID("Axis 1", "AXIS", 0, 0, 0)
            if ok:
                sel_mgr = doc.SelectionManager
                sel_mgr.SetSelectedObjectMark(1, 1, 0)
                axis_selected = True
                result["axis_select_alt"] = {"method": "SelectByID 'Axis 1'", "ok": True}
        except Exception:
            pass

    if not axis_selected:
        result["verdict"] = "NO-GO"
        result["failure_point"] = "could not select axis"
        result["component_count_after"] = _comp_count(typed_asm)
        return result

    # Step 2: Select seed component (mark=4)
    sel_result = _select_component(doc, mod, comp_name, mark=4, append=True)
    result["seed_select"] = sel_result
    if not sel_result.get("selected"):
        result["verdict"] = "NO-GO"
        result["failure_point"] = f"could not select seed component '{comp_name}'"
        result["component_count_after"] = _comp_count(typed_asm)
        return result

    # Step 3: FeatureCircularPattern5 (14 args)
    pattern_count = 4
    # W21 lesson: Spacing is in DEGREES, not radians
    angle_deg = 360.0
    try:
        feat = fm.FeatureCircularPattern5(
            pattern_count,  # Number
            angle_deg,  # Spacing (DEGREES — W21 seat-proven)
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
        result["create_feature"] = {
            "is_none": feat is None,
            "type": type(feat).__name__ if feat else "NoneType",
        }
        if feat and not isinstance(feat, int):
            result["create_feature"]["type_name"] = _type_name(feat)
            result["create_feature"]["name"] = _feat_name(feat)
    except Exception as e:
        result["create_feature"] = {"exception": f"{type(e).__name__}: {e}"[:300]}
        feat = None

    # Liveness gate
    count_after = _comp_count(typed_asm)
    delta = count_after - count_before
    result["component_count_after"] = count_after
    result["count_delta"] = delta

    # Find pattern feature
    pattern_type = None
    pattern_name = None
    try:
        feats = fm.GetFeatures(True)
        if feats:
            for f in feats:
                tn = _type_name(f)
                if tn and ("CirPattern" in tn or "LocalCirPattern" in tn or "CircularPattern" in tn):
                    pattern_type = tn
                    pattern_name = _feat_name(f)
                    break
    except Exception:
        pass
    result["pattern_feature"] = {"type": pattern_type, "name": pattern_name}

    # Feature tree
    try:
        feats = fm.GetFeatures(True)
        tree = []
        if feats:
            for f in feats:
                tree.append({"name": _feat_name(f), "type": _type_name(f)})
        result["feature_tree"] = tree
    except Exception:
        pass

    # Verdict
    if delta >= 1 and pattern_type:
        expected_delta = pattern_count - 1
        if delta >= expected_delta:
            result["verdict"] = "GO"
            result["instance_verified"] = True
        else:
            result["verdict"] = "PARTIAL"
            result["note"] = f"pattern created but delta={delta} (expected {expected_delta})"
        if feat is None or isinstance(feat, int):
            result["success_signal_contract"] = "COUNT_DELTA"
        else:
            result["success_signal_contract"] = "RETURN_VALUE"
    elif pattern_type and delta == 0:
        result["verdict"] = "NO-GO"
        result["failure_point"] = "pattern feature created but 0 component instances added (hollow)"
    else:
        result["verdict"] = "NO-GO"
        result["failure_point"] = (
            f"pattern did not materialize (delta={delta}, type={pattern_type})"
        )

    return result


def _probe_mirror(
    asm_doc: Any, typed_asm: Any, fm: Any, mod: Any, comp_name: str,
    asm_path: str,
) -> dict[str, Any]:
    """Mirror components: mirror plane + seed component → MirrorComponents2."""
    result: dict[str, Any] = {}
    doc = asm_doc

    count_before = _comp_count(typed_asm)
    result["component_count_before"] = count_before

    # Save the assembly first (MirrorComponents2 creates new files)
    try:
        save_ret = doc.SaveAs3(asm_path, 0, 2)
        result["save_before_mirror"] = {"return": str(save_ret)[:100]}
    except Exception as e:
        result["save_before_mirror"] = {"exception": f"{type(e).__name__}: {e}"[:200]}

    # Get the mirror plane entity
    # Select "Right Plane" as the mirror plane
    doc.ClearSelection2(True)
    plane_entity = None
    try:
        ok = doc.SelectByID("Right Plane", "PLANE", 0, 0, 0)
        if ok:
            sel_mgr = doc.SelectionManager
            plane_entity = sel_mgr.GetSelectedObject6(1, -1)
            result["plane_select"] = {"ok": True, "entity_type": type(plane_entity).__name__ if plane_entity else "None"}
        else:
            result["plane_select"] = {"ok": False}
    except Exception as e:
        result["plane_select"] = {"exception": f"{type(e).__name__}: {e}"[:200]}

    if plane_entity is None:
        result["verdict"] = "NO-GO"
        result["failure_point"] = "could not select mirror plane"
        result["component_count_after"] = _comp_count(typed_asm)
        return result

    # Get the seed component dispatch
    # We need the IComponent2 object for the ComponentsToMirror array
    seed_comp = None
    try:
        comps = typed_asm.GetComponents(True)
        if comps:
            for c in comps:
                try:
                    n = c.Name
                    if callable(n):
                        n = n()
                    if n == comp_name:
                        seed_comp = c
                        break
                except Exception:
                    continue
    except Exception as e:
        result["get_components"] = {"exception": f"{type(e).__name__}: {e}"[:200]}

    if seed_comp is None:
        result["verdict"] = "NO-GO"
        result["failure_point"] = f"could not find seed component '{comp_name}'"
        result["component_count_after"] = _comp_count(typed_asm)
        return result

    result["seed_component"] = {"name": comp_name, "type": type(seed_comp).__name__}

    # MirrorComponents v1 (9 args) — seat-proven W22 recipe.
    # CRITICAL: must use raw PyIDispatch pointers (_oleobj_) not gen_py wrappers.
    # MirrorComponents2/MirrorComponents3 both wall (None).
    # IMirrorComponents walls (TypeError: can't convert gen_py wrapper).
    asm_dir = str(Path(asm_path).parent)

    # Raw dispatch pointers
    raw_plane = plane_entity._oleobj_
    raw_comp = seed_comp._oleobj_

    # VARIANT(VT_ARRAY|VT_DISPATCH) with raw PyIDispatch
    comp_array = w32.VARIANT(
        pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, (raw_comp,)
    )

    try:
        ret = typed_asm.MirrorComponents(
            raw_plane,  # Plane (PyIDispatch)
            comp_array,  # ComponentsToInstance (VT_ARRAY|VT_DISPATCH)
            comp_array,  # ComponentsToMirror (VT_ARRAY|VT_DISPATCH)
            None,  # MirroredComponentFilenames (auto-generate)
            False,  # RecreateMates
            0,  # ComponentModifier (I4, NOT BSTR — 0 = none)
            "",  # ComponentNameModifier (BSTR)
            asm_dir,  # MirroredFileLocation (BSTR)
            False,  # CopyCustomProperties (BOOL)
        )
        result["mirror_call"] = {
            "method": "MirrorComponents (v1, 9 args)",
            "return_type": type(ret).__name__,
            "return_value": str(ret)[:200] if ret is not None else "None",
        }
    except Exception as e:
        result["mirror_call"] = {"exception": f"{type(e).__name__}: {e}"[:400]}
        ret = None

    # Force rebuild
    try:
        doc.ForceRebuild3(False)
    except Exception:
        pass

    # Liveness gate
    count_after = _comp_count(typed_asm)
    delta = count_after - count_before
    result["component_count_after"] = count_after
    result["count_delta"] = delta

    # Feature tree
    try:
        feats = fm.GetFeatures(True)
        tree = []
        if feats:
            for f in feats:
                tree.append({"name": _feat_name(f), "type": _type_name(f)})
        result["feature_tree"] = tree
    except Exception:
        pass

    # Find mirror-related feature
    mirror_type = None
    try:
        feats = fm.GetFeatures(True)
        if feats:
            for f in feats:
                tn = _type_name(f)
                if tn and ("Mirror" in tn or "MirrorComponent" in tn):
                    mirror_type = tn
                    break
    except Exception:
        pass
    result["mirror_feature"] = {"type": mirror_type}

    # Verdict
    if delta >= 1:
        result["verdict"] = "GO"
        result["instance_verified"] = True
        result["success_signal_contract"] = "COUNT_DELTA"
    elif mirror_type:
        result["verdict"] = "PARTIAL"
        result["failure_point"] = f"mirror feature created ({mirror_type}) but delta=0"
    else:
        result["verdict"] = "NO-GO"
        result["failure_point"] = (
            f"mirror did not materialize (delta={delta}, mirror_type={mirror_type})"
        )

    return result


def run() -> dict[str, Any]:
    result: dict[str, Any] = {
        "spike": "w22_asm_component_patterns",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "binding": "hybrid early (com.earlybind pattern)",
    }

    mod = wrapper_module()
    if mod is None:
        result["overall"] = "NO-GO"
        result["failure_point"] = "wrapper_module() returned None"
        return result

    import win32com.client as w32_compat

    try:
        sw_app = connect_running_sw()
    except Exception as e:
        result["overall"] = "NO-GO"
        result["failure_point"] = f"could not connect to SW: {e}"
        return result

    try:
        result["sw_revision"] = str(sw_app.RevisionNumber)
    except Exception:
        result["sw_revision"] = "<unreadable>"

    # Build a test part
    _tmp = Path(tempfile.gettempdir())
    _ts = int(time.time())
    part_path = str(_tmp / f"w22_pattern_box_{_ts}.SLDPRT")

    print("--- Building test part ---", file=sys.stderr)
    if not _build_box_part(part_path, mod):
        result["overall"] = "NO-GO"
        result["failure_point"] = "part build failed"
        return result
    result["part_path"] = part_path

    # Close all docs for clean slate
    try:
        docs = sw_app.GetDocuments()
        if docs:
            for d in docs:
                try:
                    t = d.GetTitle
                    if isinstance(t, tuple):
                        t = t[0]
                    name = t() if callable(t) else t
                    sw_app.CloseDoc(name)
                except Exception:
                    pass
    except Exception:
        pass

    # ===== LINEAR PATTERN =====
    print("--- LINEAR PATTERN ---", file=sys.stderr)
    asm_doc = _create_assembly(sw_app, mod)
    if asm_doc is None:
        result["overall"] = "NO-GO"
        result["failure_point"] = "assembly creation failed"
        return result

    typed_asm = typed(asm_doc, "IAssemblyDoc", module=mod)
    fm = asm_doc.FeatureManager

    placed = _place_seed(sw_app, asm_doc, part_path, mod)
    result["seed_placement"] = placed
    if "error" in placed:
        result["overall"] = "NO-GO"
        result["failure_point"] = f"seed placement failed: {placed['error']}"
        _try_close(sw_app, asm_doc)
        return result

    comp_name = placed["name"]
    result["seed_component_name"] = comp_name

    # Create a ref axis for circular pattern direction
    axis_result = _create_ref_axis(asm_doc, mod)
    result["ref_axis"] = axis_result

    # Probe linear pattern
    linear = _probe_linear(asm_doc, typed_asm, fm, mod, comp_name)
    result["linear_pattern"] = linear
    print(f"  linear verdict: {linear.get('verdict')}", file=sys.stderr)

    _try_close(sw_app, asm_doc)

    # ===== CIRCULAR PATTERN =====
    print("--- CIRCULAR PATTERN ---", file=sys.stderr)
    # Need fresh assembly (linear pattern changed component state)
    asm_doc2 = _create_assembly(sw_app, mod)
    if asm_doc2 is None:
        result["circular_pattern"] = {"verdict": "NO-GO", "failure_point": "could not create second assembly"}
    else:
        typed_asm2 = typed(asm_doc2, "IAssemblyDoc", module=mod)
        fm2 = asm_doc2.FeatureManager
        placed2 = _place_seed(sw_app, asm_doc2, part_path, mod)
        if "error" in placed2:
            result["circular_pattern"] = {"verdict": "NO-GO", "failure_point": f"seed2 placement: {placed2['error']}"}
        else:
            comp_name2 = placed2["name"]
            axis2 = _create_ref_axis(asm_doc2, mod)
            circular = _probe_circular(asm_doc2, typed_asm2, fm2, mod, comp_name2)
            result["circular_pattern"] = circular
            print(f"  circular verdict: {circular.get('verdict')}", file=sys.stderr)
        _try_close(sw_app, asm_doc2)

    # ===== MIRROR COMPONENTS =====
    print("--- MIRROR COMPONENTS ---", file=sys.stderr)
    asm_doc3 = _create_assembly(sw_app, mod)
    if asm_doc3 is None:
        result["mirror_components"] = {"verdict": "NO-GO", "failure_point": "could not create third assembly"}
    else:
        typed_asm3 = typed(asm_doc3, "IAssemblyDoc", module=mod)
        fm3 = asm_doc3.FeatureManager
        placed3 = _place_seed(sw_app, asm_doc3, part_path, mod)
        if "error" in placed3:
            result["mirror_components"] = {"verdict": "NO-GO", "failure_point": f"seed3 placement: {placed3['error']}"}
        else:
            comp_name3 = placed3["name"]
            asm_path3 = str(_tmp / f"w22_mirror_asm_{_ts}.SLDASM")
            mirror = _probe_mirror(asm_doc3, typed_asm3, fm3, mod, comp_name3, asm_path3)
            result["mirror_components"] = mirror
            print(f"  mirror verdict: {mirror.get('verdict')}", file=sys.stderr)
        _try_close(sw_app, asm_doc3)

    # Overall verdict
    verdicts = []
    for route in ("linear_pattern", "circular_pattern", "mirror_components"):
        v = result.get(route, {}).get("verdict", "NO-GO")
        verdicts.append(v)
    if any(v == "GO" for v in verdicts):
        result["overall"] = "GO"
    else:
        result["overall"] = "NO-GO"

    result["summary"] = {
        "linear": result.get("linear_pattern", {}).get("verdict", "NO-GO"),
        "circular": result.get("circular_pattern", {}).get("verdict", "NO-GO"),
        "mirror": result.get("mirror_components", {}).get("verdict", "NO-GO"),
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
