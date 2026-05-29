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
        """Return the active part's axis-aligned bounding box (parts only)."""
        return sw_get_bbox()

    def volume(self) -> dict[str, Any]:
        """Return volume, surface area, mass, and CoM of the active part."""
        return sw_get_volume()

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
        """Measure entities in the active document."""
        return sw_measure(entity_a=entity_a, entity_b=entity_b)

    def enabled_addins(self) -> dict[str, Any]:
        """Enumerate currently-loaded SOLIDWORKS add-ins (W7.1)."""
        return sw_get_enabled_addins()
