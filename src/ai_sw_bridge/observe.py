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
    SW_DOC_PART,
    get_active_doc,
    get_sw_app,
    resolve,
)
from .observe_bbox import sw_get_bbox_from_doc
from .observe_clearance import sw_get_clearance
from .observe_draft import sw_get_draft_analysis
from .observe_inertia import sw_get_inertia
from .observe_interference import sw_get_interference
from .observe_measure import sw_get_measure_from_doc
from .observe_selection import sw_get_selection


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


def collect_feature_health(doc: Any) -> dict[str, Any]:
    """Walk *doc*'s feature tree and report every feature whose state is
    non-OK (legacy ``GetErrorCode`` != 0).

    Pure doc-walker: takes the document directly, with no app / active-doc
    acquisition, so two callers can share it (X2, FR-X-02):
      - ``sw_get_feature_errors`` (below) on the active doc;
      - ``spec.builder.build`` on ``ctx.doc`` right after its final rebuild,
        to gate ``BuildResult.ok`` on post-rebuild health.

    Fail-soft: a FeatureManager / FirstFeature failure is reported via the
    ``error`` key rather than raised, and each per-feature read is wrapped, so
    a hostile tree degrades to an empty issue list instead of crashing the
    caller's build.

    Returns ``{"total_features": int, "issues": list[dict], "error": str|None}``
    where each issue is ``{name, type_name, depth, state_code, state,
    description, suppressed}`` and only non-OK features are listed.
    """
    out: dict[str, Any] = {"total_features": 0, "issues": [], "error": None}

    try:
        feat_mgr = resolve(doc, "FeatureManager")
    except Exception as exc:
        out["error"] = f"FeatureManager failed: {exc!r}"
        return out

    if feat_mgr is None:
        out["error"] = "FeatureManager returned None"
        return out

    try:
        first = resolve(feat_mgr, "FirstFeature")
    except Exception as exc:
        try:
            first = resolve(doc, "FirstFeature")
        except Exception:
            out["error"] = (
                f"FirstFeature failed on FeatureManager and doc: {exc!r}"
            )
            return out

    if first is None:
        return out  # empty tree: no issues, no error

    features = _walk_feature_tree(first)
    out["total_features"] = len(features)

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

        out["issues"].append(
            {
                "name": name,
                "type_name": type_name,
                "depth": depth,
                "state_code": state_code,
                "state": FEATURE_STATE_NAMES.get(
                    state_code, f"unknown({state_code})"
                ),
                "description": description,
                "suppressed": suppressed,
            }
        )

    return out


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

        health = collect_feature_health(doc)
        result["total_features"] = health["total_features"]
        result["issues"] = health["issues"]
        if health["error"] is not None:
            result["error"] = health["error"]
            return result

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
            result["manager_status"] = EQ_STATUS_NAMES.get(
                mgr_status, f"unknown({mgr_status})"
            )
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


def sw_get_bbox() -> dict[str, Any]:
    """Return the active part's axis-aligned bounding box in part coords.

    Uses ``IPartDoc.GetPartBox(bUseDefaultMode=True)`` which returns a
    6-tuple [Xmin, Ymin, Zmin, Xmax, Ymax, Zmax] in METERS in the part's
    coordinate system. Values are reported in BOTH meters (the SW-native
    unit) and millimetres (the spec-layer unit) so tools downstream don't
    have to guess; spans are pre-computed.

    Parts only. Assemblies/drawings get a typed error result -- assembly
    bbox would need a different call (and a different normalization
    decision, since per-component bboxes are useful in different ways).

    The reported bbox includes every solid body in the part. For single-
    body bboxes use ``IBody2.GetBodyBox``; not exposed here yet because
    no caller has asked for it.
    """
    result: dict[str, Any] = {
        "ok": False,
        "doc_path": None,
        "x_min_mm": None,
        "x_max_mm": None,
        "x_span_mm": None,
        "y_min_mm": None,
        "y_max_mm": None,
        "y_span_mm": None,
        "z_min_mm": None,
        "z_max_mm": None,
        "z_span_mm": None,
        "x_min_m": None,
        "x_max_m": None,
        "y_min_m": None,
        "y_max_m": None,
        "z_min_m": None,
        "z_max_m": None,
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
        if doc_type != SW_DOC_PART:
            result["error"] = (
                f"sw_get_bbox requires a part (swDocPART={SW_DOC_PART}); active "
                f"doc is type {doc_type} ({DOC_TYPE_NAMES.get(doc_type)})"
            )
            return result
        try:
            box = doc.GetPartBox(True)
        except Exception as exc:
            result["error"] = f"GetPartBox failed: {exc!r}"
            return result
        # An empty part (no bodies) returns a degenerate 6-tuple of zeros
        # rather than None on SW 2024 SP1; surface that as ok=True with
        # all spans = 0 so callers can distinguish "no geometry" from
        # "API failure" via the error field.
        if box is None or len(box) < 6:
            result["error"] = f"GetPartBox returned unexpected shape: {box!r}"
            return result
        x_min, y_min, z_min = float(box[0]), float(box[1]), float(box[2])
        x_max, y_max, z_max = float(box[3]), float(box[4]), float(box[5])
        result.update(
            x_min_m=x_min,
            x_max_m=x_max,
            y_min_m=y_min,
            y_max_m=y_max,
            z_min_m=z_min,
            z_max_m=z_max,
            x_min_mm=x_min * 1000.0,
            x_max_mm=x_max * 1000.0,
            y_min_mm=y_min * 1000.0,
            y_max_mm=y_max * 1000.0,
            z_min_mm=z_min * 1000.0,
            z_max_mm=z_max * 1000.0,
            x_span_mm=(x_max - x_min) * 1000.0,
            y_span_mm=(y_max - y_min) * 1000.0,
            z_span_mm=(z_max - z_min) * 1000.0,
        )
        result["ok"] = True
        return result
    except Exception as exc:
        result["error"] = f"dispatch failed: {exc!r}"
        return result


def sw_get_volume() -> dict[str, Any]:
    """Return volume + surface area + mass of the active part.

    Uses ``IModelDocExtension.CreateMassProperty`` (returns an
    IMassProperty2), then reads ``Volume`` (m^3), ``SurfaceArea`` (m^2),
    ``Mass`` (kg), ``Density`` (kg/m^3), and ``CenterOfMass`` (3-tuple, m).

    Volume + surface area are converted to mm^3 / mm^2 for the spec
    layer; raw SI values are also reported so callers don't have to
    re-derive. Mass is honest about the source: if no material is
    assigned to the part, SW falls back to the default density
    (~1000 kg/m^3) and `mass_kg` is meaningless on its own -- combine
    with `density_kg_m3` to know whether to trust it.

    Parts only. Returns a typed error result for assemblies/drawings.

    Volume oracle hook (see P0.5 in the enhancement plan): the
    `volume_mm3` field here is the single source of truth that the
    upcoming `_expect` checker compares spec-declared volumes against.
    Do not change its units, name, or sign without updating the checker.
    """
    result: dict[str, Any] = {
        "ok": False,
        "doc_path": None,
        "volume_mm3": None,
        "volume_m3": None,
        "surface_area_mm2": None,
        "surface_area_m2": None,
        "mass_kg": None,
        "density_kg_m3": None,
        "center_of_mass_mm": None,
        "body_count": None,
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
        if doc_type != SW_DOC_PART:
            result["error"] = (
                f"sw_get_volume requires a part (swDocPART={SW_DOC_PART}); "
                f"active doc is type {doc_type} ({DOC_TYPE_NAMES.get(doc_type)})"
            )
            return result

        # Body count is purely diagnostic -- a zero-body part with
        # volume == 0 is the "silent-no-op" signature we want callers to
        # be able to detect at a glance.
        try:
            bodies = doc.GetBodies2(0, True)  # swBodyType_e.swSolidBody=0
            result["body_count"] = len(bodies) if bodies is not None else 0
        except Exception:
            pass

        try:
            ext = resolve(doc, "Extension")
        except Exception as exc:
            result["error"] = f"Extension unavailable: {exc!r}"
            return result
        try:
            mp = resolve(ext, "CreateMassProperty")
        except Exception as exc:
            result["error"] = f"CreateMassProperty failed: {exc!r}"
            return result
        if mp is None:
            result["error"] = "CreateMassProperty returned None"
            return result

        try:
            vol_m3 = float(resolve(mp, "Volume"))
        except Exception as exc:
            result["error"] = f"MassProperty.Volume failed: {exc!r}"
            return result

        # The remaining fields are best-effort -- volume is the load-bearing
        # one for the silent-no-op check, so any of these missing should
        # not fail the call.
        area_m2 = None
        try:
            area_m2 = float(resolve(mp, "SurfaceArea"))
        except Exception:
            pass
        mass_kg = None
        try:
            mass_kg = float(resolve(mp, "Mass"))
        except Exception:
            pass
        density = None
        try:
            density = float(resolve(mp, "Density"))
        except Exception:
            pass
        com_mm: list[float] | None = None
        try:
            com = resolve(mp, "CenterOfMass")
            if com is not None and len(com) >= 3:
                com_mm = [float(com[i]) * 1000.0 for i in range(3)]
        except Exception:
            pass

        result.update(
            volume_m3=vol_m3,
            volume_mm3=vol_m3 * 1e9,
            surface_area_m2=area_m2,
            surface_area_mm2=area_m2 * 1e6 if area_m2 is not None else None,
            mass_kg=mass_kg,
            density_kg_m3=density,
            center_of_mass_mm=com_mm,
        )
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
        "PLANE",
        "FACE",
        "EDGE",
        "VERTEX",
        "AXIS",
        "SKETCH",
        "BODYFEATURE",
        "REFERENCEFEATURE",
        "",
    ]
    for type_str in type_attempts:
        try:
            ok = bool(doc.SelectByID(entity, type_str, 0.0, 0.0, 0.0))
            if ok:
                return True
        except Exception:
            continue
    return False


def sw_get_custom_props() -> dict[str, Any]:
    """Read every custom property from the active document.

    Uses ``IModelDoc2.GetCustomInfoNames3`` to enumerate field names, then
    ``IModelDoc2.GetCustomInfoValue2`` per field. The active configuration
    name is read from ``IGetActiveConfiguration`` when reachable.

    Parts, assemblies, and drawings all support custom properties. An empty
    document (no custom props set) returns ``{"ok": True, "properties": {}}``
    rather than an error.
    """
    result: dict[str, Any] = {
        "ok": False,
        "properties": {},
        "active_configuration": None,
        "count": 0,
        "error": None,
    }

    try:
        sw = get_sw_app()
        doc = get_active_doc(sw)
        if doc is None:
            result["error"] = "no_active_doc"
            return result

        try:
            cfg = resolve(doc, "IGetActiveConfiguration")
            if cfg is not None:
                name = resolve(cfg, "Name")
                if callable(name):
                    name = name()
                if name:
                    result["active_configuration"] = str(name)
        except Exception:
            pass

        names: tuple[str, ...] | list[str] | None = None
        try:
            names = doc.GetCustomInfoNames3
            if callable(names):
                names = names()
        except Exception as exc:
            result["error"] = f"GetCustomInfoNames3 failed: {exc!r}"
            return result

        if names is None:
            result["ok"] = True
            return result

        if isinstance(names, (tuple, list)):
            field_names = [str(n) for n in names if n]
        else:
            field_names = []

        props: dict[str, str] = {}
        for field in field_names:
            try:
                val = doc.GetCustomInfoValue2("", field)
                if val is not None:
                    props[field] = str(val)
            except Exception:
                pass

        result["properties"] = props
        result["count"] = len(props)
        result["ok"] = True
        return result

    except Exception as exc:
        result["error"] = f"dispatch failed: {exc!r}"
        return result


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
            result["error"] = (
                "no_selection - select entities in SW first, or pass entity_a/entity_b"
            )
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


# ---------------------------------------------------------------------------
# W45 — DFM perception probes: min-wall-thickness + undercut detection
#
# Both are READ-ONLY (the observe/perception axis). They extend the W37
# draft-analysis idiom (IBody2.GetFaces -> IFace2.Normal/GetArea) so an LLM
# can self-correct generated geometry against molding/casting/printing rules.
#
# The geometry/classification logic is split into PURE shape-functions
# (``_min_wall_from_samples`` / ``_classify_undercut_faces``) that take plain
# Python numbers and are fully unit-testable WITHOUT a SOLIDWORKS seat. The
# COM-acquisition wrappers (``sw_min_wall_thickness`` / ``sw_undercut_faces``)
# do only the marshaling and delegate every decision to the shape-functions.
#
# Status: SEAT-CONFIRMED 2026-06-09 (W45 PAE on SW 2024). Both probes
# discriminate on the live seat:
#   * undercut — clean fixture flagged 1 (the bottom seat face vs a +Y pull),
#     dirty fixture flagged 2; dirty > clean, every flagged face dot_pull <= 0.
#     Stands on the proven W37 GetBodies2/GetFaces/IFace2.Normal primitives.
#   * min-wall — thin fixture = 2.0 mm (the shell wall), thick = 40.0 mm;
#     discriminates cleanly. CAVEAT (downstream agents READ THIS): the value is
#     a closest-point-projection estimate via IFace2.GetClosestPointOn — it is
#     EXACT only for planar parallel opposite faces and is an UPPER BOUND on the
#     true normal-ray wall for non-planar geometry. Native Thickness Analysis is
#     add-in-gated and unreachable out-of-process. Use as a thin-region screen,
#     not a certified minimum.
# Both stay on the CLI `experimental` tier (read-only; new this wave).
# ---------------------------------------------------------------------------


def _vec_dot(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    """Dot product of two 3-vectors."""
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _vec_norm(a: tuple[float, float, float]) -> float:
    """Euclidean length of a 3-vector."""
    return (a[0] * a[0] + a[1] * a[1] + a[2] * a[2]) ** 0.5


def _vec_unit(
    a: tuple[float, float, float],
) -> tuple[float, float, float] | None:
    """Return *a* normalized to unit length, or None for a degenerate vector."""
    n = _vec_norm(a)
    if n < 1e-12:
        return None
    return (a[0] / n, a[1] / n, a[2] / n)


def _min_wall_from_samples(
    sample_distances_m: list[float],
    *,
    floor_m: float = 1e-6,
) -> dict[str, Any]:
    """Pure: reduce per-sample opposite-wall distances to a min-wall metric.

    Each entry of ``sample_distances_m`` is the through-material distance
    (in meters) from one sampled surface point, cast inward along the face
    normal, to the first opposite face it hits -- i.e. a local wall
    thickness probe. The COM wrapper produces these by sampling faces and
    casting; this function owns the *reduction* so the discrimination logic
    is unit-testable without a seat.

    Returns a dict with:
      min_wall_m / min_wall_mm  -- the smallest valid sample (the risk metric)
      sample_count              -- how many samples were fed in
      valid_sample_count        -- samples above ``floor_m`` (degenerate/
                                   self-hit samples below the floor are dropped
                                   so a coincident ray-origin can't report a
                                   bogus ~0 wall)
      mean_wall_mm              -- diagnostic average of valid samples

    Empty / all-degenerate input yields min_wall_* = None with a populated
    note rather than raising, so the wrapper can surface "no measurable wall"
    distinctly from a COM failure.
    """
    valid = [d for d in sample_distances_m if d is not None and d > floor_m]
    out: dict[str, Any] = {
        "min_wall_m": None,
        "min_wall_mm": None,
        "mean_wall_mm": None,
        "sample_count": len(sample_distances_m),
        "valid_sample_count": len(valid),
        "note": None,
    }
    if not valid:
        out["note"] = "no_valid_samples"
        return out
    mn = min(valid)
    out["min_wall_m"] = mn
    out["min_wall_mm"] = mn * 1000.0
    out["mean_wall_mm"] = (sum(valid) / len(valid)) * 1000.0
    return out


def _classify_undercut_faces(
    faces: list[dict[str, Any]],
    pull_dir: tuple[float, float, float],
    *,
    side_tol_deg: float = 0.5,
) -> dict[str, Any]:
    """Pure: classify faces as undercut / releasable along a pull direction.

    ``faces`` is a list of ``{"index", "normal", "area_m2"}`` dicts where
    ``normal`` is the face's OUTWARD unit normal in part coords. ``pull_dir``
    is the mold/tool withdrawal direction (need not be unit; normalized
    here).

    Withdrawal model (the cousin of draft analysis): a face is releasable
    along +pull if its outward normal has a NON-NEGATIVE component along the
    pull direction (it faces the way the tool leaves, or is a side wall
    exactly parallel). A face whose outward normal points OPPOSITE the pull
    (negative dot) is on the back side of the part relative to this half of
    the mold and would be released by the OTHER half -- it is only an
    undercut for *this* pull if it can't be reached from either side. To
    keep the metric honest and tool-agnostic we report, per pull axis:

      undercut   : dot(normal, pull) < -sin(side_tol)   (normal points back
                   into the tool along this pull; a true trap for a
                   single-direction pull such as a 3D-print/Z-pull or a
                   one-sided core)
      releasable : dot(normal, pull) >  +sin(side_tol)
      side_wall  : |dot| <= sin(side_tol)               (parallel to pull;
                   draft ~ 0, neither blocks nor releases)

    The ``draft_deg`` per face is ``90 - acos(dot)`` clamped, matching the
    W37 convention so callers can reuse one mental model. Faces with a
    degenerate (zero) normal are skipped and counted in ``skipped``.

    Returns a dict with the per-face classification, the undercut subset
    (the actionable output an LLM self-corrects against), and counts. The
    GREEN discrimination criterion: a part with a back-facing undercut face
    yields ``undercut_count >= 1`` and lists that face; a draft-clean part
    (every face releasable or a side wall) yields ``undercut_count == 0``.
    """
    import math

    pull_u = _vec_unit(pull_dir)
    out: dict[str, Any] = {
        "pull_dir": list(pull_dir),
        "face_count": len(faces),
        "undercut_count": 0,
        "releasable_count": 0,
        "side_wall_count": 0,
        "skipped": 0,
        "undercut_faces": [],
        "faces": [],
        "note": None,
    }
    if pull_u is None:
        out["note"] = "degenerate_pull_dir"
        return out

    side_threshold = math.sin(math.radians(side_tol_deg))

    for f in faces:
        nrm_raw = f.get("normal")
        if nrm_raw is None or len(nrm_raw) < 3:
            out["skipped"] += 1
            continue
        nrm = _vec_unit((float(nrm_raw[0]), float(nrm_raw[1]), float(nrm_raw[2])))
        if nrm is None:
            out["skipped"] += 1
            continue
        dot = _vec_dot(nrm, pull_u)
        # Clamp for acos numerical safety.
        dot_clamped = max(-1.0, min(1.0, dot))
        draft_deg = 90.0 - math.degrees(math.acos(dot_clamped))

        if dot < -side_threshold:
            kind = "undercut"
            out["undercut_count"] += 1
        elif dot > side_threshold:
            kind = "releasable"
            out["releasable_count"] += 1
        else:
            kind = "side_wall"
            out["side_wall_count"] += 1

        entry = {
            "index": f.get("index"),
            "normal": [nrm[0], nrm[1], nrm[2]],
            "area_m2": f.get("area_m2"),
            "area_mm2": (
                float(f["area_m2"]) * 1e6 if f.get("area_m2") is not None else None
            ),
            "dot_pull": dot,
            "draft_deg": draft_deg,
            "classification": kind,
        }
        out["faces"].append(entry)
        if kind == "undercut":
            out["undercut_faces"].append(entry)

    return out


def _enum_solid_faces(doc: Any) -> tuple[list[Any], str | None]:
    """Acquire every solid-body face of a part via late-bound COM.

    Mirrors the proven W37 / ``_face_geometry`` idiom:
        IModelDoc2 (part) -> GetBodies2(0, True) [swSolidBody=0]
                          -> IBody2.GetFaces()
    GetBodies2 is reachable on the late-bound part dispatch (proven at
    ``spec/_face_geometry.py``: ``ctx.doc.GetBodies2(0, True)``); no early-bind
    QI is needed on this build. Returns (faces, error). On any COM failure
    returns ([], "<reason>").
    """
    try:
        bodies = doc.GetBodies2(0, True)  # swBodyType_e.swSolidBody = 0
    except Exception as exc:
        return [], f"GetBodies2 failed: {exc!r}"
    if bodies is None:
        return [], "GetBodies2 returned None (no solid bodies)"
    faces: list[Any] = []
    for body in bodies:
        try:
            body_faces = body.GetFaces()
        except Exception:
            continue
        if body_faces is None:
            continue
        for fobj in body_faces:
            faces.append(fobj)
    return faces, None


def sw_undercut_faces(
    pull_x: float = 0.0,
    pull_y: float = 1.0,
    pull_z: float = 0.0,
) -> dict[str, Any]:
    """Report faces that block tool/mold withdrawal along a pull direction.

    READ-ONLY DFM probe. Cousin of draft analysis: enumerates every solid
    face of the active PART, reads its outward ``IFace2.Normal``, and
    classifies each as undercut / releasable / side-wall vs the pull
    direction (default +Y, the SW Top-plane up axis). See
    ``_classify_undercut_faces`` for the withdrawal model.

    COM call sequence (all PROVEN-reachable by analogy to W37 /
    ``_face_geometry``):
        GetType -> require swDocPART
        GetBodies2(0, True) -> [IBody2]      (proven late-bound)
        IBody2.GetFaces() -> [IFace2]        (proven late-bound)
        IFace2.Normal -> (nx, ny, nz)        (proven late-bound)
        IFace2.GetArea -> float (m^2)        (best-effort; diagnostic only)

    Parts only -- assemblies/drawings get a typed error result. The
    classification is delegated wholesale to the pure shape-function so the
    discrimination logic is seat-independent and unit-tested.
    """
    result: dict[str, Any] = {
        "ok": False,
        "doc_path": None,
        "pull_dir": [pull_x, pull_y, pull_z],
        "face_count": 0,
        "undercut_count": 0,
        "releasable_count": 0,
        "side_wall_count": 0,
        "skipped": 0,
        "undercut_faces": [],
        "faces": [],
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
        if doc_type != SW_DOC_PART:
            result["error"] = (
                f"sw_undercut_faces requires a part (swDocPART={SW_DOC_PART}); "
                f"active doc is type {doc_type} ({DOC_TYPE_NAMES.get(doc_type)})"
            )
            return result

        faces, enum_err = _enum_solid_faces(doc)
        if enum_err is not None:
            result["error"] = enum_err
            return result

        face_records: list[dict[str, Any]] = []
        for i, fobj in enumerate(faces):
            try:
                nrm = fobj.Normal
            except Exception:
                continue
            if nrm is None or len(nrm) < 3:
                continue
            area = None
            try:
                area = float(fobj.GetArea)
            except Exception:
                try:
                    area = float(fobj.GetArea())
                except Exception:
                    area = None
            face_records.append(
                {
                    "index": i,
                    "normal": (float(nrm[0]), float(nrm[1]), float(nrm[2])),
                    "area_m2": area,
                }
            )

        classified = _classify_undercut_faces(
            face_records, (pull_x, pull_y, pull_z)
        )
        result.update(
            face_count=classified["face_count"],
            undercut_count=classified["undercut_count"],
            releasable_count=classified["releasable_count"],
            side_wall_count=classified["side_wall_count"],
            skipped=classified["skipped"],
            undercut_faces=classified["undercut_faces"],
            faces=classified["faces"],
        )
        if classified.get("note"):
            result["error"] = classified["note"]
            return result
        result["ok"] = True
        return result
    except Exception as exc:
        result["error"] = f"dispatch failed: {exc!r}"
        return result


def sw_min_wall_thickness(samples_per_face: int = 4) -> dict[str, Any]:
    """Report the minimum wall thickness of the active solid PART.

    READ-ONLY DFM probe -- the thin-region risk metric for molding /
    casting / printing. Geometric derivation (no native add-in): for each
    solid face, sample interior surface points and cast the INWARD normal
    ray through the body to the first opposite face; the smallest such
    through-material distance is the min wall.

    COM call sequence:
        GetType -> require swDocPART                       (proven)
        GetBodies2(0, True) -> [IBody2]                    (proven late-bound)
        IBody2.GetFaces() -> [IFace2]                      (proven late-bound)
        IFace2.Normal -> outward unit normal               (proven late-bound)
        IFace2.GetClosestPointOn(x,y,z) -> point on face   (PROVEN: used in
            spec/_face_geometry.py:_select_extrude_face)    -- gives a sample
            point that is guaranteed ON the face.
        --- the ray/distance primitive (SEAT-UNKNOWN, see risks) ---
        IBody2.GetFirstFace / ray-cast: this wrapper attempts
            ``IBody2.RayIntersections`` style distance via
            ``IFace2.GetClosestPointOn`` on EVERY OTHER face from the sample
            point along -normal, taking the min positive projection. This
            uses only the PROVEN GetClosestPointOn primitive (no
            RayIntersections), trading exactness for reachability.

    The reduction (min over valid samples, degenerate-sample floor) is the
    pure ``_min_wall_from_samples`` shape-function -- unit-tested without a
    seat. Honest caveat: the closest-point-projection wall estimate is an
    UPPER bound on the true normal-ray wall for non-planar opposite faces;
    flagged in risks. Parts only.
    """
    result: dict[str, Any] = {
        "ok": False,
        "doc_path": None,
        "min_wall_mm": None,
        "min_wall_m": None,
        "mean_wall_mm": None,
        "sample_count": 0,
        "valid_sample_count": 0,
        "samples_per_face": samples_per_face,
        "method": "closest_point_projection",
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
        if doc_type != SW_DOC_PART:
            result["error"] = (
                f"sw_min_wall_thickness requires a part (swDocPART={SW_DOC_PART}); "
                f"active doc is type {doc_type} ({DOC_TYPE_NAMES.get(doc_type)})"
            )
            return result

        faces, enum_err = _enum_solid_faces(doc)
        if enum_err is not None:
            result["error"] = enum_err
            return result
        if not faces:
            result["error"] = "no_solid_faces"
            return result

        # Build (sample_point, inward_normal) probes from each face's
        # GetClosestPointOn (a point guaranteed on the face), then measure
        # the through-material distance to the nearest OTHER face along the
        # inward normal via _measure_opposite_distance.
        sample_distances: list[float] = []
        for fobj in faces:
            try:
                nrm = fobj.Normal
            except Exception:
                continue
            if nrm is None or len(nrm) < 3:
                continue
            inward = _vec_unit((-float(nrm[0]), -float(nrm[1]), -float(nrm[2])))
            if inward is None:
                continue
            for sp in _face_sample_points(fobj, samples_per_face):
                dist = _measure_opposite_distance(faces, fobj, sp, inward)
                if dist is not None:
                    sample_distances.append(dist)

        reduced = _min_wall_from_samples(sample_distances)
        result.update(
            min_wall_mm=reduced["min_wall_mm"],
            min_wall_m=reduced["min_wall_m"],
            mean_wall_mm=reduced["mean_wall_mm"],
            sample_count=reduced["sample_count"],
            valid_sample_count=reduced["valid_sample_count"],
        )
        if reduced.get("note") == "no_valid_samples":
            result["error"] = "no_measurable_wall (no valid opposite-face samples)"
            return result
        result["ok"] = True
        return result
    except Exception as exc:
        result["error"] = f"dispatch failed: {exc!r}"
        return result


def _face_sample_points(fobj: Any, n: int) -> list[tuple[float, float, float]]:
    """Yield up to *n* points guaranteed to lie ON face *fobj*.

    Strategy: probe the face's parametric box centre and a few offsets via
    ``IFace2.GetClosestPointOn`` (PROVEN reachable). GetClosestPointOn(x,y,z)
    returns the nearest point ON the face to an arbitrary 3D probe; feeding
    it the face's own UV-box corners/centre (from ``IFace2.GetUVBounds`` /
    ``GetBox`` when available) yields well-distributed on-face samples. We
    fail soft: any probe that errors is skipped.
    """
    pts: list[tuple[float, float, float]] = []
    # Prefer the face's 3D box centre + box corners as probe seeds.
    seeds: list[tuple[float, float, float]] = []
    try:
        box = fobj.GetBox  # 6-tuple [xmin,ymin,zmin,xmax,ymax,zmax]
        if callable(box):
            box = box()
        if box is not None and len(box) >= 6:
            xmin, ymin, zmin, xmax, ymax, zmax = (float(box[i]) for i in range(6))
            cx, cy, cz = (
                (xmin + xmax) / 2,
                (ymin + ymax) / 2,
                (zmin + zmax) / 2,
            )
            seeds.append((cx, cy, cz))
            # A few box-corner-ward probes for spatial spread.
            seeds.append((xmin, ymin, zmin))
            seeds.append((xmax, ymax, zmax))
            seeds.append((xmin, ymax, zmin))
    except Exception:
        pass
    if not seeds:
        seeds = [(0.0, 0.0, 0.0)]
    for seed in seeds[: max(1, n)]:
        try:
            cp = fobj.GetClosestPointOn(seed[0], seed[1], seed[2])
        except Exception:
            continue
        if cp is None or len(cp) < 3:
            continue
        pts.append((float(cp[0]), float(cp[1]), float(cp[2])))
    return pts


def _measure_opposite_distance(
    all_faces: list[Any],
    origin_face: Any,
    point: tuple[float, float, float],
    inward: tuple[float, float, float],
    *,
    min_wall_floor_m: float = 1e-5,
) -> float | None:
    """Through-material distance from *point* along *inward* to the nearest
    opposite face.

    For every face other than *origin_face*, take its closest point to
    *point* (``GetClosestPointOn``, PROVEN), project the (closest - point)
    vector onto *inward*, and keep the smallest STRICTLY-POSITIVE projection
    above ``min_wall_floor_m`` (so adjacent faces sharing an edge with
    ~0 distance don't masquerade as a thin wall). Returns the distance in
    meters, or None when no opposite face lies inward of the point.

    This is the closest-point-projection wall estimate (see
    sw_min_wall_thickness docstring): it needs only GetClosestPointOn, the
    proven primitive, rather than a body-ray intersection.
    """
    best: float | None = None
    px, py, pz = point
    ix, iy, iz = inward
    for fobj in all_faces:
        if fobj is origin_face:
            continue
        try:
            cp = fobj.GetClosestPointOn(px, py, pz)
        except Exception:
            continue
        if cp is None or len(cp) < 3:
            continue
        dx, dy, dz = float(cp[0]) - px, float(cp[1]) - py, float(cp[2]) - pz
        proj = dx * ix + dy * iy + dz * iz
        if proj <= min_wall_floor_m:
            continue
        # Reject points that are far off the inward ray (the closest point
        # is on a side wall, not the opposite wall): require the lateral
        # offset to be small relative to the projection.
        perp_x = dx - proj * ix
        perp_y = dy - proj * iy
        perp_z = dz - proj * iz
        perp = (perp_x * perp_x + perp_y * perp_y + perp_z * perp_z) ** 0.5
        if perp > proj:  # more than 45deg off-axis -> not the opposite wall
            continue
        if best is None or proj < best:
            best = proj
    return best


# ---------------------------------------------------------------------------
# W7.1 — Add-in enumeration (docs/addins_research.md §5, §7)
# ---------------------------------------------------------------------------

KNOWN_PROBLEMATIC_ADDINS: frozenset[str] = frozenset(
    {
        "SOLIDWORKS Toolbox",
        "SOLIDWORKS Routing",
        "SOLIDWORKS Electrical",
        "SOLIDWORKS Simulation",
        "SOLIDWORKS Inspection",
        "SOLIDWORKS Composer",
        "SOLIDWORKS PDM Standard",
        "SOLIDWORKS PDM Professional",
        "3DEXPERIENCE PLM Connector",
        # Names match what GetEnabledAddIns returns; VERIFY by running
        # spikes/v0_13/spike_addin_enumeration.py with each enabled.
    }
)

# Lowercase lookup set for case-insensitive matching (§9 open question).
_KNOWN_LOWER: frozenset[str] = frozenset(n.lower() for n in KNOWN_PROBLEMATIC_ADDINS)


def sw_get_enabled_addins() -> dict[str, Any]:
    """Enumerate currently-loaded SOLIDWORKS add-ins (W7.1).

    Returns a dict with keys:
        ok               -- bool; True when the query ran without COM error.
        addins           -- list[str]; every name reported by
                            ISldWorks::GetEnabledAddIns.
        known_problematic -- list[str]; the subset of *addins* that
                            intersects KNOWN_PROBLEMATIC_ADDINS
                            (case-insensitive).
        error            -- str | None; populated on COM failure.

    Fail-soft: if GetEnabledAddIns is absent on this SW build, returns
    ok=True with addins=[] and a note in *error*.  The build does not
    fail on the absence of the API -- many SW builds may expose the
    API only when at least one add-in is enabled.
    """
    result: dict[str, Any] = {
        "ok": False,
        "addins": [],
        "known_problematic": [],
        "error": None,
    }

    try:
        sw = get_sw_app()
    except Exception as exc:
        result["error"] = f"dispatch failed: {exc!r}"
        return result

    # GetEnabledAddIns may be absent on some SW builds; treat as
    # non-fatal (§7 fail-soft contract).
    getter = getattr(sw, "GetEnabledAddIns", None)
    if getter is None:
        result["ok"] = True
        result["error"] = "api_not_present"
        return result

    try:
        raw = getter()
    except Exception as exc:
        result["error"] = f"GetEnabledAddIns failed: {exc!r}"
        return result

    # GetEnabledAddIns returns a Variant that pywin32 surfaces as a
    # tuple, list, or None (when zero add-ins are loaded).
    if raw is None:
        addins: list[str] = []
    elif isinstance(raw, (tuple, list)):
        addins = [str(name) for name in raw if name]
    else:
        # Unexpected shape -- surface as a warning, not a hard error.
        addins = []
        result["error"] = f"unexpected_return_type: {type(raw).__name__}"

    # Case-insensitive intersection with the curated list (§9).
    known_problematic = [name for name in addins if name.lower() in _KNOWN_LOWER]

    result["addins"] = addins
    result["known_problematic"] = known_problematic
    result["ok"] = True
    return result


# ---------------------------------------------------------------------------
# v0.14 — class-based facade over the legacy ``sw_get_*`` free functions.
#
# The free functions above are the canonical implementations and remain
# the documented backward-compatible API. The class is the recommended
# entry point for new code and for tests that want a single instance to
# group calls. A deeper migration (move logic into methods, extract a
# template method to remove the get_sw_app/get_active_doc ceremony) is
# logged as ``D-v0.14-06`` in ``docs/DEFERRED.md`` and targets v0.15.
# ---------------------------------------------------------------------------


class SolidWorksObserver:
    """Class-based observation API. New in v0.14.

    Methods return the same JSON-shaped dicts as the legacy
    ``sw_get_*`` free functions in this module — the class is a thin
    facade so callers can prefer instance-method syntax. Instances are
    stateless; nothing is cached between calls.
    """

    def active_doc(self) -> dict[str, Any]:
        """Return metadata about the currently active SOLIDWORKS document."""
        return sw_get_active_doc()

    def feature_errors(self) -> dict[str, Any]:
        """Walk the active document's feature tree and report non-OK features."""
        return sw_get_feature_errors()

    def equations(self) -> dict[str, Any]:
        """Dump every equation in the active document with value + status."""
        return sw_get_equations()

    def bbox(self) -> dict[str, Any]:
        """Return the active part's axis-aligned bounding box (parts only).

        Legacy method — returns both m and mm values plus spans.
        For W30-style report (only mm values with dx_mm/dy_mm/dz_mm),
        use ``bounding_box()`` instead.
        """
        return sw_get_bbox()

    def bounding_box(self) -> dict[str, Any]:
        """Return the active part's bounding box (W30 perception axis).

        Uses ``IPartDoc.GetPartBox(True)`` to get axis-aligned bounding box
        in the part's coordinate system. Returns mm values only:
        ``{"ok": bool, "bounding_box": {x_min_mm..z_max_mm, dx_mm,dy_mm,dz_mm}}``.

        Parts only — assemblies/drawings get a typed error result.
        """
        doc = get_active_doc(get_sw_app())
        if doc is None:
            return {"ok": False, "error": "no_active_doc"}
        return sw_get_bbox_from_doc(doc)

    def volume(self) -> dict[str, Any]:
        """Return volume, surface area, mass, and CoM of the active part."""
        return sw_get_volume()

    def inertia(self) -> dict[str, Any]:
        """Return inertia properties of the active part (Wave-5 E1).

        Reads the centre of mass and the full 3x3 inertia tensor (about
        the centre of mass, SI kg*m^2) from IMassProperty2 via
        ``GetMomentOfInertia(0)``; principal moments and axes are derived
        from the tensor by eigendecomposition (``PrincipalAxesOfInertia``
        is unreachable out-of-process). Keys: ``center_of_mass_mm``,
        ``inertia_tensor_kg_m2``, ``principal_moments_kg_m2``,
        ``principal_axes``.
        """
        doc = get_active_doc(get_sw_app())
        if doc is None:
            return {"ok": False, "error": "no_active_doc"}
        return sw_get_inertia(doc)

    def screenshot(
        self,
        width: int = 640,
        height: int = 360,
        fit_view: bool = False,
        filename: str | None = None,
    ) -> dict[str, Any]:
        """Capture the active SW viewport to a PNG on disk."""
        return sw_screenshot(
            width=width,
            height=height,
            fit_view=fit_view,
            filename=filename,
        )

    def mate_errors(self) -> dict[str, Any]:
        """Walk an assembly's mate set and report status per mate."""
        return sw_get_mate_errors()

    def custom_props(self) -> dict[str, Any]:
        """Read every custom property from the active document."""
        return sw_get_custom_props()

    def measure(
        self,
        entity_a: str | None = None,
        entity_b: str | None = None,
    ) -> dict[str, Any]:
        """Measure entities in the active document.

        Legacy method — supports named entity selection via entity_a/entity_b args.
        For W30-style measurement of pre-selected entities, use
        ``measure_selection()`` instead (reads Distance, DeltaX/Y/Z only).
        """
        return sw_measure(entity_a=entity_a, entity_b=entity_b)

    def measure_selection(self) -> dict[str, Any]:
        """Measure currently selected entities (W30 perception axis).

        Uses ``IModelDocExtension.CreateMeasure`` → ``IMeasure.Calculate(None)``
        to measure whatever is currently selected in SW. Returns:
        ``{"ok": bool, "measure": {distance_mm, delta_x_mm, delta_y_mm, delta_z_mm}}``.

        Caller must pre-select entities via ``select_entity`` or SW UI.
        Returns error if no entities are selected.
        """
        doc = get_active_doc(get_sw_app())
        if doc is None:
            return {"ok": False, "error": "no_active_doc"}
        return sw_get_measure_from_doc(doc)

    def enabled_addins(self) -> dict[str, Any]:
        """Enumerate currently-loaded SOLIDWORKS add-ins (W7.1)."""
        return sw_get_enabled_addins()

    def interference(self) -> dict[str, Any]:
        """Detect physical interferences in the active assembly (Wave-27 E4).

        Uses ``IAssemblyDoc.InterferenceDetectionManager`` (dispid 126) to
        detect component clashes. Returns ``interference_count`` and a list
        of interferences with component names and volumes (mm³).

        Assembly documents only. Parts/drawings get a typed error result.
        """
        doc = get_active_doc(get_sw_app())
        if doc is None:
            return {"ok": False, "error": "no_active_doc"}
        return sw_get_interference(doc)

    def clearance(self, comp_a: str, comp_b: str) -> dict[str, Any]:
        """Measure minimum distance between two assembly components (Wave-35).

        Uses ``IModelDocExtension.CreateMeasure`` → ``IMeasure.Distance``
        after selecting both components via ``IComponent2.Select2``. The
        ``Distance`` value is proven to be the minimum gap (not
        center-to-center or corner-to-corner distance).

        Returns ``{min_distance_mm, components: [a, b], touching: bool}``.
        ``touching=True`` when components are flush (0mm) or overlapping.

        Assembly documents only. Parts/drawings get a typed error result.
        """
        doc = get_active_doc(get_sw_app())
        if doc is None:
            return {"ok": False, "error": "no_active_doc"}
        return sw_get_clearance(doc, comp_a, comp_b)

    def draft_analysis(
        self,
        pull_direction: str,
        min_angle_deg: float = 1.0,
    ) -> dict[str, Any]:
        """DFM draft analysis of the active part (Wave-37).

        Classifies every face as positive/negative/vertical draft relative
        to *pull_direction*.  Reports minimum draft angle and faces below
        *min_angle_deg*.  Uses first-principles face-normal sweep
        (``GetBodies2`` → ``GetFaces`` → ``IFace2.Normal`` vs pull vector).

        Part documents only. Assemblies/drawings get a typed error result.
        """
        doc = get_active_doc(get_sw_app())
        if doc is None:
            return {"ok": False, "error": "no_active_doc"}
        return sw_get_draft_analysis(doc, pull_direction, min_angle_deg)

    def selection(self) -> dict[str, Any]:
        """Read the active document's current selection (Wave-43).

        Reports what the engineer has clicked: count, per-entity type
        (``swSelectType_e``), and a durable persist-reference token
        (``GetPersistReference3``, base64url-encoded) when obtainable.

        Works on any document type (part, assembly, drawing).
        Empty selection is valid: ``{count: 0, selections: []}``.
        """
        doc = get_active_doc(get_sw_app())
        if doc is None:
            return {"ok": False, "error": "no_active_doc"}
        return sw_get_selection(doc)

    def undercut_faces(
        self,
        pull_x: float = 0.0,
        pull_y: float = 1.0,
        pull_z: float = 0.0,
    ) -> dict[str, Any]:
        """Report faces that block tool/mold withdrawal along a pull direction."""
        return sw_undercut_faces(pull_x=pull_x, pull_y=pull_y, pull_z=pull_z)

    def min_wall_thickness(self, samples_per_face: int = 4) -> dict[str, Any]:
        """Report the minimum wall thickness of the active solid part (DFM)."""
        return sw_min_wall_thickness(samples_per_face=samples_per_face)
