"""Spike W20 / LOFT — materialization probe (production-mirror bind).

Tests the EXACT production sequence from _create_loft (mutate.py:874)
to determine GO/NO-GO for advertising ``feature_add: loft``.

The v0_16 spike (spike_loft.py) called CreateDefinition(9) BEFORE
selecting profiles → CreateDefinition returned None.  The production
handler selects FIRST, then calls CreateDefinition.  This spike
mirrors the production order to determine whether the loft was
misdiagnosed in Wave-5.

Records:
  * feature count before/after (liveness gate)
  * CreateFeature return-value analysis (success-signal contract)
  * CreateDefinition(9) behavior with pre-selected profiles
  * confirmed selection mark
  * feature type name (GetTypeName2)

Verdicts:
  GO    — count +1, Loft/Blend-typed, non-degenerate.
  NO-GO — CreateDefinition(9) None, or CreateFeature no-ops.

Usage:
    .venv-py310/Scripts/python.exe spikes/v0_2x/spike_loft.py
"""

from __future__ import annotations

import json
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
RESULTS_PATH = WORKTREE / "spikes" / "v0_2x" / "_results" / "loft.json"

import pythoncom  # noqa: E402

from ai_sw_bridge.com.earlybind import typed, typed_qi  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402

from spike_earlybind_persist import connect_running_sw, ensure_sw_module  # noqa: E402

SW_DEFAULT_TEMPLATE_PART = 8
SWCONST_TLB = Path(r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\swconst.tlb")


def _type_name(feat: Any) -> str | None:
    for attr in ("GetTypeName2", "GetTypeName"):
        try:
            m = getattr(feat, attr)
            return str(m() if callable(m) else m)
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


def _materialized(feat: Any) -> bool:
    return feat is not None and not isinstance(feat, int)


def _feat_count(fm: Any) -> int:
    _feats = fm.GetFeatures(True)
    return len(_feats) if _feats else 0


def _walk_swconst() -> dict[str, Any]:
    report: dict[str, Any] = {"path": str(SWCONST_TLB), "loadable": False}
    if not SWCONST_TLB.exists():
        report["error"] = f"not found at {SWCONST_TLB}"
        return report
    try:
        tlb = pythoncom.LoadTypeLib(str(SWCONST_TLB))
    except Exception as e:
        report["error"] = f"{type(e).__name__}: {e}"
        return report
    report["loadable"] = True
    for i in range(tlb.GetTypeInfoCount()):
        name = tlb.GetDocumentation(i)[0]
        if name == "swFeatureNameID_e":
            info = tlb.GetTypeInfo(i)
            ta = info.GetTypeAttr()
            for v in range(ta.cVars):
                vd = info.GetVarDesc(v)
                mname = info.GetNames(vd.memid)[0]
                if "Blend" in mname or "Loft" in mname:
                    report[f"swconst.{mname}"] = vd.value
    return report


def _build_geometry(doc: Any, mod: Any) -> dict[str, Any]:
    """Two offset ref planes with profile sketches (nozzle-adapter setup).

    Plane A = Front Plane  → circle sketch (Sketch1)
    Plane B = Plane1       → rectangle sketch (Sketch2)
              (50 mm offset from Front Plane)
    """
    out: dict[str, Any] = {}
    fm = doc.FeatureManager

    # Profile 1: circle on Front Plane
    try:
        doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
        doc.SketchManager.InsertSketch(True)
        doc.SketchManager.CreateCircleByRadius(0.0, 0.0, 0.0, 0.01)
        doc.SketchManager.InsertSketch(True)
        out["profile1"] = "Sketch1"
        out["profile1_plane"] = "Front Plane"
    except Exception as e:
        out["profile1_error"] = f"{type(e).__name__}: {e}"
        return out

    # Ref plane offset 50 mm from Front Plane
    try:
        doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
        fm.InsertRefPlane(8, 0.05, 0, 0, 0, 0)
        out["ref_plane"] = "Plane1"
    except Exception as e:
        out["ref_plane_error"] = f"{type(e).__name__}: {e}"
        return out

    # Profile 2: center-rectangle on Plane1
    try:
        doc.SelectByID("Plane1", "PLANE", 0, 0, 0)
        doc.SketchManager.InsertSketch(True)
        doc.SketchManager.CreateCenterRectangle(0, 0, 0, 0.008, 0.008, 0)
        doc.SketchManager.InsertSketch(True)
        out["profile2"] = "Sketch2"
        out["profile2_plane"] = "Plane1"
    except Exception as e:
        out["profile2_error"] = f"{type(e).__name__}: {e}"

    try:
        doc.EditRebuild3()
    except Exception:
        pass
    return out


def _probe_loft(
    doc: Any, fm: Any, mod: Any, profiles: list[str]
) -> dict[str, Any]:
    """Production-mirror probe: exact _create_loft sequence with telemetry."""
    result: dict[str, Any] = {}
    ext = typed(doc.Extension, "IModelDocExtension", module=mod)

    count_before = _feat_count(fm)
    result["feature_count_before"] = count_before

    # Step 1: ClearSelection2 (production handler does this)
    doc.ClearSelection2(True)

    # Step 2: Select profiles — all with mark=1 (production handler convention)
    sel_results: list[dict[str, Any]] = []
    for i, p in enumerate(profiles):
        append = i > 0
        try:
            ok = ext.SelectByID2(p, "SKETCH", 0, 0, 0, append, 1, None, 0)
            sel_results.append({
                "profile": p, "append": append, "mark": 1, "result": ok,
            })
        except Exception as e:
            sel_results.append({
                "profile": p, "append": append, "mark": 1,
                "exception": f"{type(e).__name__}: {e}",
            })
    result["selections"] = sel_results
    result["confirmed_mark"] = 1

    # Step 2b: Verify selection set is live (diagnostic)
    try:
        sel_mgr = typed(doc.SelectionManager, "ISelectionMgr", module=mod)
        sel_count = sel_mgr.GetSelectedObjectCount2(-1)
        result["selection_count"] = sel_count
        sel_details = []
        for idx in range(1, (sel_count or 0) + 1):
            try:
                obj = sel_mgr.GetSelectedObject6(idx, -1)
                obj_type = type(obj).__name__ if obj else "None"
                sel_details.append({"index": idx, "type": obj_type})
            except Exception as e:
                sel_details.append({"index": idx, "error": str(e)[:100]})
        result["selected_objects"] = sel_details
    except Exception as e:
        result["selection_verify"] = {"error": f"{type(e).__name__}: {e}"}

    # Step 3: CreateDefinition(9) — swFmBlend
    try:
        data = fm.CreateDefinition(9)
        result["create_definition"] = {
            "returned_none": data is None,
            "type": "NoneType" if data is None else type(data).__name__,
        }
    except Exception as e:
        result["create_definition"] = {
            "exception": f"{type(e).__name__}: {e}",
            "returned_none": True,
        }
        data = None

    # Step 3b: Cross-check — CreateDefinition(9) WITHOUT any pre-selection
    try:
        doc.ClearSelection2(True)
        data_bare = fm.CreateDefinition(9)
        result["create_definition_no_selection"] = {
            "returned_none": data_bare is None,
            "type": "NoneType" if data_bare is None else type(data_bare).__name__,
        }
    except Exception as e:
        result["create_definition_no_selection"] = {
            "exception": f"{type(e).__name__}: {e}",
        }

    if data is None:
        # Step 3c: Legacy path cross-check — InsertProtrusionBlend arity probe
        legacy_results = []
        # Probe: does InsertProtrusionBlend exist? What arity?
        for method_name in ("InsertProtrusionBlend", "InsertProtrusionBlend2"):
            try:
                method = getattr(fm, method_name, None)
                if method is None:
                    legacy_results.append({
                        "method": method_name, "exists": False,
                    })
                    continue
                legacy_results.append({
                    "method": method_name, "exists": True,
                    "callable": callable(method),
                    "type": type(method).__name__,
                })
            except Exception as e:
                legacy_results.append({
                    "method": method_name,
                    "error": f"{type(e).__name__}: {e}",
                })
        result["legacy_probe"] = legacy_results

        # Step 3d: Legacy call attempts — re-select and try InsertProtrusionBlend
        # with the simplest reasonable arg tuple (all defaults).
        legacy_call_results = []
        try:
            doc.ClearSelection2(True)
            for i, p in enumerate(profiles):
                ext.SelectByID2(p, "SKETCH", 0, 0, 0, i > 0, 1, None, 0)
        except Exception:
            pass
        # InsertProtrusionBlend: 17 args (v0_16 found). Try the simplest combo.
        # (direction_fwd, options, tangency_start, tangency_end,
        #  draft_angle_start, draft_angle_end, start_draft_dist,
        #  end_draft_dist, merge_result, feature_scope, thin_feature,
        #  auto_select, t1, t2, t3, t4, t5)
        simple_args = [True, 0, 0, 0, 0.0, 0.0, 0.0, 0.0,
                       True, True, False, True, 0, 0, 0, 0, 0]
        try:
            ret = fm.InsertProtrusionBlend(*simple_args)
            legacy_call_results.append({
                "method": "InsertProtrusionBlend",
                "args_count": len(simple_args),
                "returned_none": ret is None,
                "return_type": type(ret).__name__,
            })
        except Exception as e:
            legacy_call_results.append({
                "method": "InsertProtrusionBlend",
                "exception": f"{type(e).__name__}: {e}"[:200],
            })
        # InsertProtrusionBlend2: 18 args (v0_16 found)
        simple_args2 = [True, 0, 0, 0, 0.0, 0.0, 0.0, 0.0,
                        True, True, False, True, 0, 0, 0, 0, 0, 0]
        try:
            ret2 = fm.InsertProtrusionBlend2(*simple_args2)
            legacy_call_results.append({
                "method": "InsertProtrusionBlend2",
                "args_count": len(simple_args2),
                "returned_none": ret2 is None,
                "return_type": type(ret2).__name__,
            })
        except Exception as e:
            legacy_call_results.append({
                "method": "InsertProtrusionBlend2",
                "exception": f"{type(e).__name__}: {e}"[:200],
            })
        count_after_legacy = _feat_count(fm)
        result["legacy_call_results"] = legacy_call_results
        result["feature_count_after_legacy"] = count_after_legacy
        result["count_delta_legacy"] = count_after_legacy - count_before

        result["verdict"] = "NO-GO"
        result["failure_point"] = "CreateDefinition(9) returned None"
        count_after = _feat_count(fm)
        result["feature_count_after"] = count_after
        result["count_delta"] = count_after - count_before
        return result

    # Step 4: typed_qi(ILoftFeatureData)
    try:
        fd = typed_qi(data, "ILoftFeatureData", module=mod)
        result["typed_qi"] = {
            "ok": True,
            "type": type(fd).__name__,
        }
    except Exception as e:
        result["typed_qi"] = {
            "ok": False,
            "exception": f"{type(e).__name__}: {e}",
        }
        result["verdict"] = "NO-GO"
        result["failure_point"] = "typed_qi(ILoftFeatureData) failed"
        count_after = _feat_count(fm)
        result["feature_count_after"] = count_after
        result["count_delta"] = count_after - count_before
        return result

    # Step 5: CreateFeature(fd)
    try:
        feat = fm.CreateFeature(fd)
    except Exception as e:
        result["create_feature"] = {
            "exception": f"{type(e).__name__}: {e}",
        }
        result["verdict"] = "NO-GO"
        result["failure_point"] = "CreateFeature raised"
        count_after = _feat_count(fm)
        result["feature_count_after"] = count_after
        result["count_delta"] = count_after - count_before
        return result

    # Step 6: LIVENESS GATE — feature count + type analysis
    count_after = _feat_count(fm)
    delta = count_after - count_before
    result["feature_count_after"] = count_after
    result["count_delta"] = delta

    result["create_feature_return"] = {
        "is_none": feat is None,
        "is_int": isinstance(feat, int),
        "type": type(feat).__name__,
        "materialized_check": _materialized(feat),
    }
    if _materialized(feat):
        result["create_feature_return"]["type_name"] = _type_name(feat)

    # Scan for the new feature by type name (Blend/Loft)
    new_feat_type: str | None = None
    try:
        feats = fm.GetFeatures(True)
        if feats:
            for f in feats:
                tn = _type_name(f)
                if tn and ("Blend" in tn or "Loft" in tn):
                    new_feat_type = tn
                    break
    except Exception:
        pass
    result["new_feature_type_name"] = new_feat_type

    # ForceRebuild3 + recount (sweep_cut pattern)
    try:
        doc.ForceRebuild3(False)
    except Exception:
        pass
    count_after_rebuild = _feat_count(fm)
    result["feature_count_after_rebuild"] = count_after_rebuild
    result["count_delta_after_rebuild"] = count_after_rebuild - count_before

    # Determine success-signal contract
    if delta == 1 and new_feat_type:
        if feat is None or isinstance(feat, int):
            result["success_signal_contract"] = "COUNT_DELTA"
            result["handler_needs_fix"] = True
            result["handler_fix_detail"] = (
                "CreateFeature returns None/int on success — handler must use "
                "GetFeatures(True) count-delta (mirror dome/shell/sweep_cut)"
            )
        else:
            result["success_signal_contract"] = "RETURN_VALUE"
            result["handler_needs_fix"] = False
            result["handler_fix_detail"] = (
                "CreateFeature returns the feature — _materialized() check is correct"
            )
        result["verdict"] = "GO"
    elif count_after_rebuild - count_before == 1 and new_feat_type:
        if feat is None or isinstance(feat, int):
            result["success_signal_contract"] = "COUNT_DELTA_AFTER_REBUILD"
            result["handler_needs_fix"] = True
            result["handler_fix_detail"] = (
                "Loft materializes after ForceRebuild3 only — handler must use "
                "count-delta + ForceRebuild3 (mirror sweep_cut)"
            )
        else:
            result["success_signal_contract"] = "RETURN_VALUE"
            result["handler_needs_fix"] = False
        result["verdict"] = "GO"
    else:
        result["success_signal_contract"] = "NONE"
        result["handler_needs_fix"] = None
        result["verdict"] = "NO-GO"
        result["failure_point"] = (
            f"Loft did not materialize (delta={delta}, "
            f"delta_after_rebuild={count_after_rebuild - count_before}, "
            f"new_type={new_feat_type})"
        )

    return result


def run() -> dict[str, Any]:
    result: dict[str, Any] = {
        "spike": "w20_loft_materialization",
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

    typelib = _walk_swconst()
    result["typelib"] = typelib

    sw = connect_running_sw()
    try:
        result["sw_revision"] = str(sw.RevisionNumber)
    except Exception:
        result["sw_revision"] = "<unreadable>"

    tmp_dir = Path(tempfile.gettempdir()) / "ai-sw-bridge"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        result["verdict"] = "NO-GO"
        result["failure_point"] = "NewDocument returned None"
        return result

    fm = doc.FeatureManager

    # Build geometry
    geom = _build_geometry(doc, mod)
    result["geometry"] = geom

    if "profile1_error" in geom or "profile2_error" in geom:
        result["verdict"] = "NO-GO"
        result["failure_point"] = "geometry build failed"
        _try_close(sw, doc)
        return result

    profiles = [geom["profile1"], geom["profile2"]]

    # Run the production-mirror probe
    probe = _probe_loft(doc, fm, mod, profiles)
    result["probe"] = probe
    result["verdict"] = probe["verdict"]

    if probe["verdict"] == "GO":
        result["interpretation"] = (
            f"Loft materialized (count +{probe['count_delta']}, "
            f"type={probe['new_feature_type_name']}, "
            f"contract={probe['success_signal_contract']}). "
            f"Handler fix needed: {probe.get('handler_needs_fix')}"
        )
    else:
        result["interpretation"] = (
            f"Loft did NOT materialize. "
            f"Failure point: {probe.get('failure_point', 'unknown')}"
        )

    _try_close(sw, doc)
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
    return 0 if result.get("verdict") == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())
