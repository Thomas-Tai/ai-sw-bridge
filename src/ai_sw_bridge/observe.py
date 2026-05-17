"""
Read-only observation tools. Run freely without approval.

Each function returns a plain dict suitable for json.dumps. The CLI driver
(ai_sw_bridge.cli.observe) serializes one function call per invocation.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from PIL import Image

from .sw_com import (
    DOC_TYPE_NAMES,
    get_active_doc,
    get_sw_app,
    resolve,
)


def _captures_dir() -> Path:
    """Where screenshots get written.

    Order of precedence:
      1. AI_SW_BRIDGE_CAPTURES env var (explicit override)
      2. <tempdir>/ai-sw-bridge/captures (user-local, always writable)

    The historical default of ./captures (cwd-relative) was changed because
    cwd is frequently a cloud-synced folder (OneDrive, Dropbox) which can
    deny SW's SaveBMP write with PermissionError(13).
    """
    import tempfile

    override = os.environ.get("AI_SW_BRIDGE_CAPTURES")
    if override:
        return Path(override).resolve()
    return (Path(tempfile.gettempdir()) / "ai-sw-bridge" / "captures").resolve()


# IEquationMgr.Status return values per SW API
EQ_STATUS_NAMES = {
    0: "ok",
    1: "syntax_error",
    2: "circular_dependency",
    3: "evaluation_error",
    4: "unknown",
    5: "dimension_not_found",
}


# SW feature error/warning state codes per ISldWorks::IFeature::GetErrorCode2
# 0 = no error, 1 = warning, 2 = error. Exact meanings vary by feature type;
# we surface the raw code plus any text description SW exposes.
FEATURE_STATE_NAMES = {0: "ok", 1: "warning", 2: "error"}


def sw_get_active_doc() -> dict[str, Any]:
    """Return metadata about whatever document is currently active in SW."""
    result: dict[str, Any] = {
        "ok": False,
        "path": None,
        "type": None,
        "type_id": None,
        "title": None,
        "is_dirty": None,
        "error": None,
    }

    try:
        sw = get_sw_app()
        doc = get_active_doc(sw)
        if doc is None:
            result["ok"] = True
            result["error"] = "no_active_doc"
            return result

        try:
            result["path"] = str(resolve(doc, "GetPathName"))
        except Exception as exc:
            result["error"] = f"GetPathName failed: {exc!r}"

        try:
            type_id = int(resolve(doc, "GetType"))
            result["type_id"] = type_id
            result["type"] = DOC_TYPE_NAMES.get(type_id, f"Unknown({type_id})")
        except Exception as exc:
            result["error"] = (result["error"] or "") + f" | GetType failed: {exc!r}"

        try:
            result["title"] = str(resolve(doc, "GetTitle"))
        except Exception:
            pass

        try:
            result["is_dirty"] = bool(resolve(doc, "GetSaveFlag"))
        except Exception:
            pass

        result["ok"] = True
        return result

    except Exception as exc:
        result["error"] = f"dispatch failed: {exc!r}"
        return result


def _walk_feature_tree(first_feature: Any, max_depth: int = 8) -> list[Any]:
    """
    Walk the feature tree from the first feature, collecting every feature
    and sub-feature. SW exposes (zero-arg, late-bound as properties):
      feat.GetNextFeature  -> sibling at same level
      feat.GetFirstSubFeature -> child
      subfeat.GetNextSubFeature -> sibling at child level
    """
    collected: list[Any] = []

    def is_dispatch_null(obj: Any) -> bool:
        return obj is None

    current = first_feature
    while not is_dispatch_null(current):
        collected.append((0, current))
        try:
            sub = resolve(current, "GetFirstSubFeature")
        except Exception:
            sub = None
        if not is_dispatch_null(sub) and max_depth > 0:
            sub_current = sub
            while not is_dispatch_null(sub_current):
                collected.append((1, sub_current))
                try:
                    sub_current = resolve(sub_current, "GetNextSubFeature")
                except Exception:
                    break
        try:
            current = resolve(current, "GetNextFeature")
        except Exception:
            break

    return collected


def sw_get_feature_errors() -> dict[str, Any]:
    """Walk the active document's feature tree and report any feature whose
    state is non-OK. Also returns the total feature count for sanity."""
    result: dict[str, Any] = {
        "ok": False,
        "doc_path": None,
        "total_features": 0,
        "issues": [],
        "error": None,
    }

    try:
        sw = get_sw_app()
        doc = get_active_doc(sw)
        if doc is None:
            result["error"] = "no_active_doc"
            return result

        try:
            result["doc_path"] = str(resolve(doc, "GetPathName"))
        except Exception:
            pass

        try:
            feat_mgr = resolve(doc, "FeatureManager")
        except Exception as exc:
            result["error"] = f"FeatureManager failed: {exc!r}"
            return result

        if feat_mgr is None:
            result["error"] = "FeatureManager returned None"
            return result

        try:
            first = resolve(feat_mgr, "FirstFeature")
        except Exception as exc:
            try:
                first = resolve(doc, "FirstFeature")
            except Exception:
                result["error"] = f"FirstFeature failed on FeatureManager and doc: {exc!r}"
                return result

        if first is None:
            result["ok"] = True
            return result

        features = _walk_feature_tree(first)
        result["total_features"] = len(features)

        for depth, feat in features:
            try:
                name = str(resolve(feat, "Name"))
            except Exception:
                name = "<unnamed>"

            try:
                type_name = str(resolve(feat, "GetTypeName2"))
            except Exception:
                try:
                    type_name = str(resolve(feat, "GetTypeName"))
                except Exception:
                    type_name = None

            # GetErrorCode2 takes args pywin32 can't marshal; use legacy
            # GetErrorCode which late-binds as auto-invoked property.
            state_code = None
            try:
                state_code = int(resolve(feat, "GetErrorCode"))
            except Exception:
                state_code = None

            if state_code is None or state_code == 0:
                continue

            description = None
            try:
                description = str(resolve(feat, "ErrorMessage"))
            except Exception:
                description = None

            suppressed = None
            try:
                suppressed = bool(resolve(feat, "IsSuppressed"))
            except Exception:
                pass

            result["issues"].append(
                {
                    "name": name,
                    "type_name": type_name,
                    "depth": depth,
                    "state_code": state_code,
                    "state": FEATURE_STATE_NAMES.get(state_code, f"unknown({state_code})"),
                    "description": description,
                    "suppressed": suppressed,
                }
            )

        result["ok"] = True
        return result

    except Exception as exc:
        result["error"] = f"dispatch failed: {exc!r}"
        return result


def sw_get_equations() -> dict[str, Any]:
    """Dump every equation in the active document with its current value,
    solve status, and the linked external locals file if any."""
    result: dict[str, Any] = {
        "ok": False,
        "doc_path": None,
        "linked_file": None,
        "link_active": None,
        "auto_solve_order": None,
        "auto_rebuild": None,
        "manager_status_code": None,
        "manager_status": None,
        "equation_count": 0,
        "equations": [],
        "error": None,
    }

    try:
        sw = get_sw_app()
        doc = get_active_doc(sw)
        if doc is None:
            result["error"] = "no_active_doc"
            return result

        try:
            result["doc_path"] = str(resolve(doc, "GetPathName"))
        except Exception:
            pass

        eq_mgr = None
        for path in ("GetEquationMgr",):
            try:
                eq_mgr = resolve(doc, path)
                if eq_mgr is not None:
                    break
            except Exception:
                continue
        if eq_mgr is None:
            try:
                ext = resolve(doc, "Extension")
                eq_mgr = resolve(ext, "GetEquationMgr")
            except Exception as exc:
                result["error"] = f"GetEquationMgr unavailable: {exc!r}"
                return result

        if eq_mgr is None:
            result["error"] = "equation manager is None"
            return result

        try:
            result["linked_file"] = str(resolve(eq_mgr, "FilePath")) or None
        except Exception:
            pass
        try:
            result["link_active"] = bool(resolve(eq_mgr, "LinkToFile"))
        except Exception:
            pass
        try:
            result["auto_solve_order"] = bool(resolve(eq_mgr, "AutomaticSolveOrder"))
        except Exception:
            pass
        try:
            result["auto_rebuild"] = bool(resolve(eq_mgr, "AutomaticRebuild"))
        except Exception:
            pass

        try:
            mgr_status = int(resolve(eq_mgr, "Status"))
            result["manager_status_code"] = mgr_status
            result["manager_status"] = EQ_STATUS_NAMES.get(mgr_status, f"unknown({mgr_status})")
        except Exception:
            pass

        try:
            count = int(resolve(eq_mgr, "GetCount"))
        except Exception:
            try:
                count = int(resolve(eq_mgr, "Count"))
            except Exception as exc:
                result["error"] = f"Count unavailable: {exc!r}"
                return result

        result["equation_count"] = count

        for i in range(count):
            entry: dict[str, Any] = {
                "index": i,
                "expression": None,
                "value": None,
                "is_global_var": None,
                "is_suppressed": None,
            }
            try:
                entry["expression"] = str(eq_mgr.Equation(i))
            except Exception as exc:
                entry["expression"] = f"<error: {exc!r}>"

            try:
                v = eq_mgr.Value(i)
                entry["value"] = float(v) if isinstance(v, (int, float)) else str(v)
            except Exception:
                pass

            try:
                entry["is_global_var"] = bool(eq_mgr.GlobalVariable(i))
            except Exception:
                pass

            try:
                entry["is_suppressed"] = bool(eq_mgr.Suppression(i))
            except Exception:
                pass

            result["equations"].append(entry)

        result["ok"] = True
        return result

    except Exception as exc:
        result["error"] = f"dispatch failed: {exc!r}"
        return result


def sw_screenshot(
    width: int = 640,
    height: int = 360,
    fit_view: bool = False,
    filename: str | None = None,
) -> dict[str, Any]:
    """
    Capture the active SW viewport to a PNG on disk.

    Default resolution is 640x360 - good for sanity checks. Pass
    width=1280, height=720 for detail work (fillets, cross-references).

    Output goes to AI_SW_BRIDGE_CAPTURES env var if set, else ./captures
    relative to the current working directory.
    """
    captures_dir = _captures_dir()
    result: dict[str, Any] = {
        "ok": False,
        "path": None,
        "doc_path": None,
        "width": width,
        "height": height,
        "fit_view_applied": False,
        "error": None,
    }

    try:
        sw = get_sw_app()
        doc = get_active_doc(sw)
        if doc is None:
            result["error"] = "no_active_doc"
            return result

        try:
            result["doc_path"] = str(resolve(doc, "GetPathName"))
        except Exception:
            pass

        if fit_view:
            try:
                _ = resolve(doc, "ViewZoomtofit2")
                result["fit_view_applied"] = True
            except Exception as exc:
                result["error"] = f"ViewZoomtofit2 failed (non-fatal): {exc!r}"

        captures_dir.mkdir(parents=True, exist_ok=True)
        if filename is None:
            try:
                title = str(resolve(doc, "GetTitle"))
            except Exception:
                title = "capture"
            stem = "".join(
                c if c.isalnum() or c in "._-" else "_"
                for c in os.path.splitext(title)[0]
            )
            filename = f"{stem}_{int(time.time())}.png"

        out_path = (captures_dir / filename).resolve()
        if out_path.suffix.lower() != ".png":
            out_path = out_path.with_suffix(".png")
        bmp_path = out_path.with_suffix(".bmp")

        try:
            ok = bool(doc.SaveBMP(str(bmp_path), int(width), int(height)))
        except Exception as exc:
            result["error"] = f"SaveBMP raised: {exc!r}"
            return result

        if not ok or not bmp_path.exists():
            result["error"] = f"SaveBMP returned False or file missing: {bmp_path}"
            return result

        try:
            with Image.open(bmp_path) as im:
                im.save(out_path, format="PNG", optimize=True)
            bmp_path.unlink(missing_ok=True)
        except Exception as exc:
            result["error"] = f"PNG conversion failed: {exc!r}"
            result["path"] = str(bmp_path)
            return result

        result["path"] = str(out_path)
        result["ok"] = True
        return result

    except Exception as exc:
        result["error"] = f"dispatch failed: {exc!r}"
        return result


# IMate2.Status values per SW API
MATE_STATUS_NAMES = {
    0: "ok",
    1: "warning",
    2: "error",
    3: "suppressed",
    4: "deactivated",
    5: "over_defined",
    6: "under_defined",
    7: "not_solved",
}

# IMate2.Type -> human readable (subset; SW has ~30 mate types)
MATE_TYPE_NAMES = {
    0: "coincident",
    1: "concentric",
    2: "perpendicular",
    3: "parallel",
    4: "tangent",
    5: "distance",
    6: "angle",
    7: "lock",
    8: "symmetric",
    9: "cam_follower",
    10: "universal_joint",
    11: "gear",
    12: "hinge",
    13: "rack_pinion",
    14: "slot",
    15: "width",
    16: "screw",
}


def sw_get_mate_errors() -> dict[str, Any]:
    """Walk an assembly's mate set and report status per mate.

    Active document MUST be an assembly. Returns an error for parts/drawings.
    """
    result: dict[str, Any] = {
        "ok": False,
        "doc_path": None,
        "mate_count": 0,
        "mates": [],
        "summary": {"by_status": {}, "broken_count": 0},
        "error": None,
    }

    try:
        sw = get_sw_app()
        doc = get_active_doc(sw)
        if doc is None:
            result["error"] = "no_active_doc"
            return result

        try:
            result["doc_path"] = str(resolve(doc, "GetPathName"))
        except Exception:
            pass

        try:
            doc_type = int(resolve(doc, "GetType"))
        except Exception as exc:
            result["error"] = f"GetType failed: {exc!r}"
            return result

        if doc_type != 2:
            result["error"] = (
                f"active doc is type {doc_type} ({DOC_TYPE_NAMES.get(doc_type)}); "
                "sw_get_mate_errors requires an assembly"
            )
            return result

        try:
            first = resolve(doc, "FirstFeature")
        except Exception as exc:
            result["error"] = f"FirstFeature failed: {exc!r}"
            return result

        mategroup = None
        f = first
        depth_cap = 200
        while f is not None and depth_cap > 0:
            try:
                tn = resolve(f, "GetTypeName2")
            except Exception:
                tn = None
            if tn == "MateGroup":
                mategroup = f
                break
            try:
                f = resolve(f, "GetNextFeature")
            except Exception:
                break
            depth_cap -= 1

        if mategroup is None:
            result["ok"] = True  # assembly with zero mates is valid
            return result

        try:
            sub = resolve(mategroup, "GetFirstSubFeature")
        except Exception as exc:
            result["error"] = f"MateGroup.GetFirstSubFeature failed: {exc!r}"
            return result

        status_counter: dict[str, int] = {}
        mate_count = 0

        while sub is not None:
            mate_count += 1
            entry: dict[str, Any] = {
                "name": None,
                "feature_type": None,
                "type_code": None,
                "type": None,
                "status_code": None,
                "status": None,
                "is_suppressed": None,
                "components": [],
            }

            try:
                entry["name"] = str(resolve(sub, "Name"))
            except Exception:
                entry["name"] = "<unnamed>"

            try:
                entry["feature_type"] = str(resolve(sub, "GetTypeName2"))
            except Exception:
                pass

            try:
                mate = resolve(sub, "GetSpecificFeature2")
            except Exception:
                mate = None

            if mate is not None:
                try:
                    tc = int(resolve(mate, "Type"))
                    entry["type_code"] = tc
                    entry["type"] = MATE_TYPE_NAMES.get(tc, f"unknown({tc})")
                except Exception:
                    pass

            try:
                sc = int(resolve(sub, "GetErrorCode"))
                entry["status_code"] = sc
                entry["status"] = MATE_STATUS_NAMES.get(sc, f"unknown({sc})")
            except Exception:
                pass

            try:
                entry["is_suppressed"] = bool(resolve(sub, "IsSuppressed"))
            except Exception:
                pass

            result["mates"].append(entry)

            status_name = entry["status"] or "unknown"
            status_counter[status_name] = status_counter.get(status_name, 0) + 1

            try:
                sub = resolve(sub, "GetNextSubFeature")
            except Exception:
                break

        result["mate_count"] = mate_count
        result["summary"]["by_status"] = status_counter
        result["summary"]["broken_count"] = sum(
            c for s, c in status_counter.items() if s not in ("ok", "suppressed")
        )

        result["ok"] = True
        return result

    except Exception as exc:
        result["error"] = f"dispatch failed: {exc!r}"
        return result


def _select_by_id(doc: Any, entity: str, append: bool = False) -> bool:
    """Drive SW selection via IModelDoc2.SelectByID (legacy 5-arg form)."""
    type_attempts = [
        "PLANE", "FACE", "EDGE", "VERTEX", "AXIS",
        "SKETCH", "BODYFEATURE", "REFERENCEFEATURE", "",
    ]
    for type_str in type_attempts:
        try:
            ok = bool(doc.SelectByID(entity, type_str, 0.0, 0.0, 0.0))
            if ok:
                return True
        except Exception:
            continue
    return False


def sw_measure(
    entity_a: str | None = None,
    entity_b: str | None = None,
) -> dict[str, Any]:
    """
    Measure entities in the active document.

    Two modes:
      - No args: measure whatever is currently selected in SW UI.
        Ctrl-click both entities in SW, then call sw_measure().
      - With entity_a: programmatically select that one entity by name
        and return its area/perimeter/etc.

    Two-entity named selection is NOT supported on most SW builds via
    late-binding (Callout arg in SelectByID2 cannot be marshaled).
    """
    result: dict[str, Any] = {
        "ok": False,
        "mode": "selection" if entity_a is None else "named",
        "selected_count": 0,
        "distance": None,
        "deltax": None,
        "deltay": None,
        "deltaz": None,
        "angle_rad": None,
        "arc_length": None,
        "area": None,
        "perimeter": None,
        "selection_summary": [],
        "error": None,
    }

    try:
        sw = get_sw_app()
        doc = get_active_doc(sw)
        if doc is None:
            result["error"] = "no_active_doc"
            return result

        try:
            ext = resolve(doc, "Extension")
        except Exception as exc:
            result["error"] = f"Extension unavailable: {exc!r}"
            return result

        if entity_a is not None:
            try:
                _ = doc.ClearSelection2(True)
            except Exception:
                pass

            ok_a = _select_by_id(doc, entity_a, append=False)
            if not ok_a:
                result["error"] = f"could not select entity_a: {entity_a!r}"
                return result

            if entity_b is not None:
                result["error"] = (
                    "entity_b ignored: two-entity named selection unsupported. "
                    "Select both entities in SW UI and call sw_measure() with no args."
                )

        try:
            sel_mgr = resolve(doc, "SelectionManager")
        except Exception as exc:
            result["error"] = f"SelectionManager unavailable: {exc!r}"
            return result

        try:
            count = int(resolve(sel_mgr, "GetSelectedObjectCount2"))
        except Exception:
            try:
                count = int(resolve(sel_mgr, "GetSelectedObjectCount"))
            except Exception as exc:
                result["error"] = f"selection count unavailable: {exc!r}"
                return result

        result["selected_count"] = count
        if count == 0:
            result["error"] = "no_selection - select entities in SW first, or pass entity_a/entity_b"
            return result

        for i in range(1, count + 1):
            try:
                obj_name = str(sel_mgr.GetSelectedObjectsComponent4(i, -1))
            except Exception:
                obj_name = ""
            try:
                type_id = int(sel_mgr.GetSelectedObjectType3(i, -1))
            except Exception:
                type_id = -1
            result["selection_summary"].append(f"#{i} type={type_id} {obj_name}")

        try:
            measure = resolve(ext, "CreateMeasure")
        except Exception as exc:
            result["error"] = f"CreateMeasure failed: {exc!r}"
            return result

        try:
            _ = resolve(measure, "Calculate")
        except Exception as exc:
            result["error"] = f"Calculate failed: {exc!r}"
            return result

        def safe_float(attr_name: str) -> float | None:
            try:
                v = resolve(measure, attr_name)
                if v is None:
                    return None
                fv = float(v)
                if fv == -1.0:
                    return None
                return fv
            except Exception:
                return None

        result["distance"] = safe_float("Distance")
        result["deltax"] = safe_float("DeltaX")
        result["deltay"] = safe_float("DeltaY")
        result["deltaz"] = safe_float("DeltaZ")
        result["angle_rad"] = safe_float("Angle")
        result["arc_length"] = safe_float("ArcLength")
        result["area"] = safe_float("Area")
        result["perimeter"] = safe_float("Perimeter")

        result["ok"] = True
        return result

    except Exception as exc:
        result["error"] = f"dispatch failed: {exc!r}"
        return result
