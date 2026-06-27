"""
Mutation tools (Propose-Approve-Execute, dry-run-then-commit).

Workflow:
    1. sw_propose_local_change(var, new_value)
       -> creates a proposal record on disk, no SW touched yet, returns proposal_id
    2. sw_dry_run(proposal_id)
       -> applies in SW, force-rebuilds, captures errors+manager_status,
          rolls back, returns the delta. Safe to inspect.
    3. sw_commit(proposal_id)
       -> re-applies, leaves the change in place, saves the SW doc.
    4. sw_undo_last_commit()
       -> reverts the most recent committed proposal.

All mutations route through the SW-linked *_locals.txt file so the
single source of truth stays in version control.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from enum import Enum
from pathlib import Path
from typing import Any

from .locals_io import (
    ExclusiveLock,
    atomic_write,
    find_entry,
    parse,
    replace_rhs,
)
from .sw_com import (
    SW_DOC_PART as _SW_DOC_PART,
    SW_OPEN_SILENT as _SW_OPEN_SILENT,
    get_active_doc,
    get_sw_app,
    resolve,
)


from .com.earlybind import typed

# typed_qi is re-exported on this module's surface so the test-suite can patch
# ``mutate.typed_qi``; intentionally imported-but-unused here.
from .com.earlybind import typed_qi  # noqa: F401
from .com.sw_type_info import wrapper_module
from .features import HANDLER_REGISTRY


# Proposal store: one JSON file per proposal. Override via env var,
# else defaults to ./proposals relative to the current working directory.
def _proposals_dir() -> Path:
    override = os.environ.get("AI_SW_BRIDGE_PROPOSALS")
    if override:
        return Path(override).resolve()
    return (Path.cwd() / "proposals").resolve()


class ProposalState(str, Enum):
    """Lifecycle states of a proposal record on disk (v0.14+).

    Subclasses ``str`` so existing on-disk JSON values (plain strings)
    compare equal to enum members.
    """

    PROPOSED = "proposed"
    DRY_RUN_OK = "dry_run_ok"
    DRY_RUN_BROKE = "dry_run_broke"
    COMMITTED = "committed"
    UNDONE = "undone"


# Module-level constants kept for backward compatibility — every state
# string used by callers, fixtures, and the on-disk JSON records.
ST_PROPOSED = ProposalState.PROPOSED.value
ST_DRY_RUN_OK = ProposalState.DRY_RUN_OK.value
ST_DRY_RUN_BROKE = ProposalState.DRY_RUN_BROKE.value
ST_COMMITTED = ProposalState.COMMITTED.value
ST_UNDONE = ProposalState.UNDONE.value


def _proposal_path(proposal_id: str) -> Path:
    return _proposals_dir() / f"{proposal_id}.json"


def _load_proposal(proposal_id: str) -> dict[str, Any] | None:
    p = _proposal_path(proposal_id)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def _save_proposal(proposal_id: str, data: dict[str, Any]) -> None:
    _proposals_dir().mkdir(parents=True, exist_ok=True)
    _proposal_path(proposal_id).write_text(json.dumps(data, indent=2), encoding="utf-8")


# ---- feature_add support ----------------------------------------------------

# _SW_DOC_PART / _SW_OPEN_SILENT are imported from sw_com (the canonical home
# for the OpenDoc6 call shape) under their original private aliases so the
# OpenDoc6 call site below reads unchanged.

# swWzdGeneralHoleTypes_e — used by propose-time validation only; handler
# moved to features/advanced_shapes.py (Recipe-C cut #4).
_WZD_GENERIC_HOLE_TYPES = {
    "counterbore": 0,
    "countersink": 1,
    "hole": 2,
    "tap": 3,
    "pipe_tap": 4,
    "slot": 6,
}
# swEndConditions_e for the hole's end condition.
_WZD_END_CONDITIONS = {
    "blind": 0,
    "through_all": 1,
    "through_next": 2,
    "up_to_vertex": 3,
    "up_to_surface": 4,
    "offset_from_surface": 5,
}

# swDraftFacePropagationType_e — draft face propagation.
_DRAFT_PROPAGATION = {
    "none": 0,
    "tangent": 1,
    "all_loops": 2,
    "inner_loops": 3,
    "outer_loops": 4,
}

# Feature types the feature_add PAE lifecycle knows how to build.
# ---- Recipe-C cut #4: dress-up/advanced-shapes/flanges relocated ----
# fillet_constant_radius, chamfer, variable_radius_fillet, shell, draft,
# loft, rib, dome, wrap, boundary_boss, wizard_hole, base_flange, edge_flange
# are all now in features.HANDLER_REGISTRY (dress_up / advanced_shapes /
# flanges modules).
# ---- W41 body-ops RELOCATED to features/body_ops.py (Recipe-C cut #2) ----
# delete_body is GREEN in features.HANDLER_REGISTRY; combine/split are WALLED
# (registered DORMANT) — all three are no longer in this tuple.
# ---- Recipe-C cut #6: sweep/sweep_cut RELOCATED to features/sweep.py ----
# Every kind now lives in HANDLER_REGISTRY; _apply_feature is a pure registry
# lookup. _SUPPORTED_FEATURE_TYPES is empty — kept defined for back-compat.
_SUPPORTED_FEATURE_TYPES = ()


def _open_doc_typed(doc_path: str) -> Any:
    """Open a SW doc silently via typed OpenDoc6 (byref ints for errors/warnings)."""
    sw = get_sw_app()
    mod = wrapper_module()
    tsw = typed(sw, "ISldWorks", module=mod)
    ret = tsw.OpenDoc6(doc_path, _SW_DOC_PART, _SW_OPEN_SILENT, "", 0, 0)
    return ret[0] if isinstance(ret, tuple) else ret


def _doc_title(doc: Any) -> Any:
    """Get the document title (name) for CloseDoc."""
    return resolve(doc, "GetTitle")


def _save_doc(doc: Any) -> bool:
    """Save *doc* and report whether it succeeded.

    Late-bound pywin32 drops ``IModelDoc2.Save``'s ``VARIANT_BOOL`` S_OK
    return value as ``None`` (the retval is swallowed), so a successful save
    looks falsy and ``bool(doc.Save())`` wrongly reports ``False`` even though
    the file is written. A genuine COM failure raises ``com_error`` (caught by
    the callers), so under late binding the only truthy *failure* signal is an
    explicit ``False``. Treat anything that is not ``False`` as success.
    """
    return doc.Save() is not False


_CHAMFER_TYPES = ("angle_distance", "distance_distance", "vertex")


# _PIERCE_TOKEN / _first_arc_center_coords / _sketch_centroid_coords /
# _sketch_to_model_coords / _apply_auto_pierce / _create_sweep / _create_sweep_cut
# relocated to features/sweep.py (Recipe-C cut #6 — the FINAL extraction).

# _create_loft / _create_rib / _create_dome / _create_wrap / _create_boundary_boss
# relocated to features/advanced_shapes.py (Recipe-C cut #4).


# _get_definition / _create_variable_fillet / _arrays_from_out /
# _hole_table_sizes / _SIZE_ERROR_DISPLAY_LIMIT / _format_size_catalog /
# _resolve_hole_args / _create_wizard_hole / _get_face_entity /
# _create_shell / _create_draft all relocated to
# features/dress_up.py and features/advanced_shapes.py (Recipe-C cut #4).


def _apply_feature(doc: Any, feature: dict, target: dict) -> tuple[bool, str | None]:
    """Dispatch a feature-add proposal to its per-type build pipeline.

    Shared by dry-run and commit so the two paths can never diverge. Returns
    (ok, error); an unknown type returns ``(False, <reason>)`` rather than
    raising (propose-time validation already rejects unsupported types).

    Recipe-C cut #6: sweep/sweep_cut relocated to features/sweep.py; every
    kind now lives in HANDLER_REGISTRY. _apply_feature is a pure registry
    lookup — there are no inline built-in branches left.
    """
    ftype = feature.get("type") if isinstance(feature, dict) else None
    # W56 seam: kinds wired as per-lane modules under features/ dispatch here.
    # Recipe-C cuts #1–#6 relocated all handlers into the registry; this
    # function is now a pure registry dispatch (no inline branches).
    handler = HANDLER_REGISTRY.get(ftype) if isinstance(ftype, str) else None
    if handler is not None:
        return handler(doc, feature, target)
    return False, f"unsupported feature type {ftype!r}"


def _get_linked_locals(doc: Any) -> Path | None:
    """Return the *_locals.txt path the active doc's equation manager is
    tracking, or None if no link is active."""
    try:
        eq_mgr = resolve(doc, "GetEquationMgr")
    except Exception:
        return None
    try:
        if not bool(resolve(eq_mgr, "LinkToFile")):
            return None
    except Exception:
        return None
    try:
        fp = str(resolve(eq_mgr, "FilePath"))
    except Exception:
        return None
    return Path(fp) if fp else None


def _force_rebuild(doc: Any) -> tuple[bool, str | None]:
    """Reload linked locals file, then rebuild the SW doc.

    Two-step process because plain rebuild does NOT re-import linked
    *_locals.txt; the equation manager needs an explicit reload trigger:

    1. EquationMgr.UpdateValuesFromExternalEquationFile - auto-invoked
       as property; returns bool. Re-reads the linked file and applies
       values to the equation manager.
    2. IModelDoc2.EditRebuild3 - auto-invoked property; equivalent to
       Ctrl+B. Rebuilds geometry with the updated equations.

    Returns (ok, error_message).
    """
    try:
        eq_mgr = resolve(doc, "GetEquationMgr")
    except Exception as exc:
        return False, f"GetEquationMgr failed: {exc!r}"

    # Trigger the locals-file reload. SW returns False here when there is
    # nothing to reload (file unchanged since last poll) -- NOT an error.
    # Treat raise as fatal but False as informational; the rebuild that
    # follows is the real success signal.
    reload_warning = None
    try:
        reload_ok = bool(resolve(eq_mgr, "UpdateValuesFromExternalEquationFile"))
        if not reload_ok:
            reload_warning = (
                "UpdateValuesFromExternalEquationFile returned False "
                "(usually means file unchanged since last poll; non-fatal)"
            )
    except Exception as exc:
        return False, f"UpdateValuesFromExternalEquationFile raised: {exc!r}"

    try:
        rebuild_ok = bool(resolve(doc, "EditRebuild3"))
        # Even if the reload returned False, a successful rebuild means
        # the doc is in the desired state. Surface the warning text only
        # when the rebuild ALSO failed -- otherwise it's noise.
        if rebuild_ok:
            return True, None
        return False, reload_warning or "EditRebuild3 returned False"
    except Exception as exc:
        return False, f"EditRebuild3 failed: {exc!r}"


def _read_manager_status(doc: Any) -> int | None:
    try:
        eq_mgr = resolve(doc, "GetEquationMgr")
        return int(resolve(eq_mgr, "Status"))
    except Exception:
        return None


def _read_var_value(doc: Any, var_name: str) -> float | str | None:
    """Read the SW-evaluated value of a global var from the equation manager."""
    try:
        eq_mgr = resolve(doc, "GetEquationMgr")
        count = int(resolve(eq_mgr, "GetCount"))
    except Exception:
        return None
    for i in range(count):
        try:
            expr = str(eq_mgr.Equation(i))
        except Exception:
            continue
        if f'"{var_name}"' in expr.split("=")[0]:
            try:
                v = eq_mgr.Value(i)
                return float(v) if isinstance(v, (int, float)) else str(v)
            except Exception:
                return None
    return None


def _sw_propose_local_change_impl(var: str, new_value: str) -> dict[str, Any]:
    """Core: stage a change to a single variable in the linked *_locals.txt file (v0.18 implementation).

    Internal callers (the ``SolidWorksClient.mutate`` facade) call this
    directly so they bypass the deprecation shim; the public
    :func:`sw_propose_local_change` free function routes here behind a
    ``PendingDeprecationWarning``.

    No SW state is modified. We read the file (under exclusive lock) to
    verify the var exists and to snapshot its current value, so we can
    audit and roll back later.
    """
    result: dict[str, Any] = {
        "ok": False,
        "proposal_id": None,
        "locals_path": None,
        "var": var,
        "old_expression": None,
        "new_expression": new_value,
        "line_index": None,
        "doc_path": None,
        "state": ST_PROPOSED,
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

        locals_path = _get_linked_locals(doc)
        if locals_path is None or not locals_path.exists():
            result["error"] = (
                f"no linked locals file (LinkToFile must be true and file must exist): {locals_path}"
            )
            return result
        result["locals_path"] = str(locals_path)

        try:
            with ExclusiveLock(locals_path) as lock:
                text = lock.read_text()
        except OSError as exc:
            result["error"] = f"could not lock locals file: {exc}"
            return result

        entries = parse(text)
        entry = find_entry(entries, var)
        if entry is None:
            result["error"] = f"variable {var!r} not found in {locals_path.name}"
            return result

        result["old_expression"] = entry.expression
        result["line_index"] = entry.line_index

        proposal_id = uuid.uuid4().hex[:12]
        record = {
            "proposal_id": proposal_id,
            "created_at": time.time(),
            "doc_path": result["doc_path"],
            "locals_path": str(locals_path),
            "var": var,
            "old_expression": entry.expression,
            "new_expression": new_value,
            "line_index": entry.line_index,
            "snapshot_text": text,
            "state": ST_PROPOSED,
            "dry_run_result": None,
            "committed_at": None,
            "undone_at": None,
        }
        _save_proposal(proposal_id, record)
        result["proposal_id"] = proposal_id
        result["ok"] = True
        return result

    except Exception as exc:
        result["error"] = f"unexpected: {exc!r}"
        return result


def _sw_dry_run_impl(proposal_id: str) -> dict[str, Any]:
    """Core: apply a proposed change, force-rebuild, capture state, roll back (v0.18 implementation).

    Internal callers (the ``SolidWorksClient.mutate`` facade) call this
    directly so they bypass the deprecation shim; the public
    :func:`sw_dry_run` free function routes here behind a
    ``PendingDeprecationWarning``.
    """
    result: dict[str, Any] = {
        "ok": False,
        "proposal_id": proposal_id,
        "applied": False,
        "rolled_back": False,
        "before": {"manager_status": None, "var_value": None},
        "after": {"manager_status": None, "var_value": None},
        "rebuild_ok": False,
        "state": ST_PROPOSED,
        "warnings": [],
        "error": None,
    }

    rec = _load_proposal(proposal_id)
    if rec is None:
        result["error"] = f"proposal {proposal_id} not found"
        return result

    if rec["state"] not in (ST_PROPOSED, ST_DRY_RUN_OK, ST_DRY_RUN_BROKE):
        result["error"] = f"proposal is in state {rec['state']!r}, cannot dry-run"
        return result

    locals_path = Path(rec["locals_path"])
    if not locals_path.exists():
        result["error"] = f"locals file vanished: {locals_path}"
        return result

    try:
        sw = get_sw_app()
        doc = get_active_doc(sw)
        if doc is None:
            result["error"] = "no_active_doc"
            return result

        result["before"]["manager_status"] = _read_manager_status(doc)
        result["before"]["var_value"] = _read_var_value(doc, rec["var"])

        try:
            with ExclusiveLock(locals_path) as lock:
                current_text = lock.read_text()
            if current_text != rec["snapshot_text"]:
                result["warnings"].append(
                    "locals file changed since proposal was created; dry-run will use current text as base"
                )
            try:
                new_text = replace_rhs(
                    current_text, rec["line_index"], rec["new_expression"]
                )
            except ValueError as exc:
                result["error"] = f"replace_rhs failed: {exc}"
                return result

            atomic_write(locals_path, new_text)
            result["applied"] = True

            rebuild_ok, rebuild_err = _force_rebuild(doc)
            result["rebuild_ok"] = rebuild_ok
            if rebuild_err:
                result["warnings"].append(rebuild_err)

            result["after"]["manager_status"] = _read_manager_status(doc)
            result["after"]["var_value"] = _read_var_value(doc, rec["var"])

            mgr_after = result["after"]["manager_status"]
            mgr_before = result["before"]["manager_status"]
            broke = (
                mgr_after is not None
                and mgr_before is not None
                and mgr_after != mgr_before
                and mgr_after != 0
            ) or not rebuild_ok
            result["state"] = ST_DRY_RUN_BROKE if broke else ST_DRY_RUN_OK

        finally:
            try:
                atomic_write(locals_path, rec["snapshot_text"])
                _force_rebuild(doc)
                with ExclusiveLock(locals_path) as lock:
                    verify = lock.read_text()
                if verify == rec["snapshot_text"]:
                    result["rolled_back"] = True
                else:
                    result["warnings"].append(
                        "ROLLBACK WROTE OK but on-disk content differs from snapshot"
                    )
            except Exception as exc:
                result["warnings"].append(
                    f"ROLLBACK FAILED - locals file may be stale: {exc!r}"
                )

        rec["state"] = result["state"]
        rec["dry_run_result"] = {
            "ran_at": time.time(),
            "before": result["before"],
            "after": result["after"],
            "rebuild_ok": result["rebuild_ok"],
            "warnings": list(result["warnings"]),
        }
        _save_proposal(proposal_id, rec)

        result["ok"] = result["rolled_back"]
        return result

    except Exception as exc:
        result["error"] = f"unexpected: {exc!r}"
        return result


def _sw_commit_impl(proposal_id: str) -> dict[str, Any]:
    """Core: re-apply a proposal that passed dry-run, save the SW document,
    and mark the proposal as committed (v0.18 implementation).

    Internal callers (the ``SolidWorksClient.mutate`` facade) call this
    directly so they bypass the deprecation shim; the public
    :func:`sw_commit` free function routes here behind a
    ``PendingDeprecationWarning``.
    """
    result: dict[str, Any] = {
        "ok": False,
        "proposal_id": proposal_id,
        "doc_saved": False,
        "state": ST_PROPOSED,
        "error": None,
    }

    rec = _load_proposal(proposal_id)
    if rec is None:
        result["error"] = f"proposal {proposal_id} not found"
        return result

    if rec["state"] != ST_DRY_RUN_OK:
        result["error"] = (
            f"refusing to commit proposal in state {rec['state']!r}; "
            "must be 'dry_run_ok' (run sw_dry_run first)"
        )
        return result

    locals_path = Path(rec["locals_path"])
    try:
        sw = get_sw_app()
        doc = get_active_doc(sw)
        if doc is None:
            result["error"] = "no_active_doc"
            return result

        with ExclusiveLock(locals_path) as lock:
            current_text = lock.read_text()
        new_text = replace_rhs(current_text, rec["line_index"], rec["new_expression"])
        atomic_write(locals_path, new_text)

        rebuild_ok, rebuild_err = _force_rebuild(doc)
        if not rebuild_ok:
            result["error"] = f"rebuild failed after commit-apply: {rebuild_err}"
            return result

        try:
            result["doc_saved"] = _save_doc(doc)
        except Exception as exc:
            result["error"] = f"doc.Save raised: {exc!r}"
            return result

        rec["state"] = ST_COMMITTED
        rec["committed_at"] = time.time()
        _save_proposal(proposal_id, rec)

        result["state"] = ST_COMMITTED
        result["ok"] = True
        return result

    except Exception as exc:
        result["error"] = f"unexpected: {exc!r}"
        return result


def _sw_undo_last_commit_impl() -> dict[str, Any]:
    """Core: revert the most recently committed proposal by restoring its
    snapshot, force-rebuilding, and saving (v0.18 implementation).

    Internal callers (the ``SolidWorksClient.mutate`` facade) call this
    directly so they bypass the deprecation shim; the public
    :func:`sw_undo_last_commit` free function routes here behind a
    ``PendingDeprecationWarning``.
    """
    result: dict[str, Any] = {
        "ok": False,
        "proposal_id": None,
        "var": None,
        "restored_to": None,
        "doc_saved": False,
        "error": None,
    }

    proposals_dir = _proposals_dir()
    proposals_dir.mkdir(parents=True, exist_ok=True)
    candidates: list[tuple[float, str, dict[str, Any]]] = []
    for p in proposals_dir.glob("*.json"):
        try:
            rec = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if rec.get("state") != ST_COMMITTED or not rec.get("committed_at"):
            continue
        # undo_last_commit reverts a LOCAL-change proposal by restoring its
        # locals snapshot. The proposals dir is shared across all families, so
        # it also holds feature/assembly/drawing/properties commits (keyed by
        # `kind`/`spec`, with no `var`). Skip those rather than crashing on
        # their absent local-change keys.
        if "var" not in rec or "proposal_id" not in rec:
            continue
        candidates.append((rec["committed_at"], rec["proposal_id"], rec))

    if not candidates:
        result["error"] = "no committed proposal to undo"
        return result

    candidates.sort(reverse=True)
    _, proposal_id, rec = candidates[0]
    result["proposal_id"] = proposal_id
    result["var"] = rec["var"]
    result["restored_to"] = rec["old_expression"]

    try:
        sw = get_sw_app()
        doc = get_active_doc(sw)
        if doc is None:
            result["error"] = "no_active_doc"
            return result

        locals_path = Path(rec["locals_path"])
        atomic_write(locals_path, rec["snapshot_text"])

        rebuild_ok, rebuild_err = _force_rebuild(doc)
        if not rebuild_ok:
            result["error"] = f"rebuild failed during undo: {rebuild_err}"
            return result

        try:
            result["doc_saved"] = _save_doc(doc)
        except Exception as exc:
            result["error"] = f"doc.Save raised: {exc!r}"
            return result

        rec["state"] = ST_UNDONE
        rec["undone_at"] = time.time()
        _save_proposal(proposal_id, rec)

        result["ok"] = True
        return result

    except Exception as exc:
        result["error"] = f"unexpected: {exc!r}"
        return result


# ---- feature_add PAE functions ---------------------------------------------


def _sw_propose_feature_add_impl(
    doc_path: str, feature: dict, target: dict
) -> dict[str, Any]:
    """Core: stage a feature-add proposal (v0.18 implementation).

    Internal callers (the ``SolidWorksClient.mutate`` facade) call this
    directly so they bypass the deprecation shim; the public
    :func:`sw_propose_feature_add` free function routes here behind a
    ``PendingDeprecationWarning``.

    No SW state is modified.
    """
    result: dict[str, Any] = {
        "ok": False,
        "proposal_id": None,
        "doc_path": doc_path,
        "feature": feature,
        "target": target,
        "state": ST_PROPOSED,
        "error": None,
    }
    try:
        feat_type = feature.get("type") if isinstance(feature, dict) else None
        if (
            feat_type not in _SUPPORTED_FEATURE_TYPES
            and feat_type not in HANDLER_REGISTRY
        ):
            result["error"] = (
                f"unsupported feature type {feat_type!r}; "
                f"supported: {', '.join((*_SUPPORTED_FEATURE_TYPES, *HANDLER_REGISTRY))}"
            )
            return result

        # Per-type parameter validation.
        if feat_type == "fillet_constant_radius":
            radius_mm = feature.get("radius_mm")
            if not isinstance(radius_mm, (int, float)) or radius_mm <= 0:
                result["error"] = (
                    f"radius_mm must be a positive number, got {radius_mm!r}"
                )
                return result
        elif feat_type == "chamfer":
            chamfer_type = feature.get("chamfer_type", "angle_distance")
            if chamfer_type not in _CHAMFER_TYPES:
                result["error"] = (
                    f"chamfer_type must be one of {list(_CHAMFER_TYPES)}, "
                    f"got {chamfer_type!r}"
                )
                return result
            distance_mm = feature.get("distance_mm")
            if not isinstance(distance_mm, (int, float)) or distance_mm <= 0:
                result["error"] = (
                    f"distance_mm must be a positive number, got {distance_mm!r}"
                )
                return result
            if chamfer_type == "angle_distance":
                angle_deg = feature.get("angle_deg", 45.0)
                if not isinstance(angle_deg, (int, float)) or not (0 < angle_deg < 90):
                    result["error"] = f"angle_deg must be in (0, 90), got {angle_deg!r}"
                    return result
            elif chamfer_type == "distance_distance":
                d2 = feature.get("distance2_mm")
                if not isinstance(d2, (int, float)) or d2 <= 0:
                    result["error"] = (
                        f"distance_distance chamfer requires positive distance2_mm, got {d2!r}"
                    )
                    return result
            else:  # vertex
                for pname in ("distance2_mm", "distance3_mm"):
                    pval = feature.get(pname)
                    if not isinstance(pval, (int, float)) or pval <= 0:
                        result["error"] = (
                            f"vertex chamfer requires positive {pname}, got {pval!r}"
                        )
                        return result
                point = target.get("point") if isinstance(target, dict) else None
                if not (isinstance(point, (list, tuple)) and len(point) == 3):
                    result["error"] = (
                        "vertex chamfer requires target.point = [x, y, z] (mm)"
                    )
                    return result
        elif feat_type == "base_flange":
            for pname in ("thickness_mm", "bend_radius_mm"):
                pval = feature.get(pname)
                if not isinstance(pval, (int, float)) or pval <= 0:
                    result["error"] = f"{pname} must be a positive number, got {pval!r}"
                    return result
        elif feat_type == "wizard_hole":
            # Shape-only checks here; the standard/fastener/size are validated
            # against the live DB at dry-run (they need SW).
            ht = feature.get("hole_type")
            if ht not in _WZD_GENERIC_HOLE_TYPES:
                result["error"] = (
                    f"hole_type must be one of {sorted(_WZD_GENERIC_HOLE_TYPES)}, "
                    f"got {ht!r}"
                )
                return result
            ec = feature.get("end_condition", "blind")
            if ec not in _WZD_END_CONDITIONS:
                result["error"] = (
                    f"end_condition must be one of {sorted(_WZD_END_CONDITIONS)}, "
                    f"got {ec!r}"
                )
                return result
            for pname in ("standard", "fastener_type", "size"):
                if not isinstance(feature.get(pname), str) or not feature[pname]:
                    result["error"] = f"{pname} must be a non-empty string"
                    return result
            depth_mm = feature.get("depth_mm")
            if depth_mm is not None and (
                not isinstance(depth_mm, (int, float)) or depth_mm <= 0
            ):
                result["error"] = (
                    f"depth_mm must be a positive number, got {depth_mm!r}"
                )
                return result
        elif feat_type == "shell":
            thickness_mm = feature.get("thickness_mm")
            if not isinstance(thickness_mm, (int, float)) or thickness_mm <= 0:
                result["error"] = (
                    f"thickness_mm must be a positive number, got {thickness_mm!r}"
                )
                return result
        elif feat_type == "draft":
            angle_deg = feature.get("angle_deg")
            if not isinstance(angle_deg, (int, float)) or angle_deg <= 0:
                result["error"] = (
                    f"angle_deg must be a positive number, got {angle_deg!r}"
                )
                return result
            prop = feature.get("propagation", "none")
            if prop not in _DRAFT_PROPAGATION:
                result["error"] = (
                    f"propagation must be one of {sorted(_DRAFT_PROPAGATION)}, got {prop!r}"
                )
                return result

        if not isinstance(target, dict) or not target:
            result["error"] = "target must be a non-empty dict"
            return result

        # A base flange is built on a named profile sketch, not an edge ref.
        if feat_type == "base_flange" and not target.get("sketch"):
            result["error"] = "base_flange target must contain a 'sketch' name"
            return result

        # A variable-radius fillet carries an ordered list of (edge, radius).
        if feat_type == "variable_radius_fillet":
            edge_specs = target.get("edges")
            if not isinstance(edge_specs, list) or not edge_specs:
                result["error"] = (
                    "variable_radius_fillet target must contain a non-empty "
                    "'edges' list"
                )
                return result
            for k, es in enumerate(edge_specs):
                if (
                    not isinstance(es, dict)
                    or not isinstance(es.get("ref"), dict)
                    or not es["ref"]
                ):
                    result["error"] = f"edges[{k}] must contain a non-empty 'ref' dict"
                    return result
                r = es.get("radius_mm")
                if not isinstance(r, (int, float)) or r <= 0:
                    result["error"] = (
                        f"edges[{k}].radius_mm must be a positive number, got {r!r}"
                    )
                    return result

        # A wizard hole is placed at a point on a face. The face is given
        # either durably (``face_ref``: a manifest-face dict, preferred) or by
        # raw model-metre coords (``face``: [x,y,z], v1). ``point`` is the
        # on-face hole location in model metres in both cases.
        if feat_type == "wizard_hole":
            point = target.get("point")
            if not isinstance(point, (list, tuple)) or len(point) != 3:
                result["error"] = "wizard_hole target.point must be a 3-element [x,y,z]"
                return result
            face_ref = target.get("face_ref")
            face = target.get("face")
            if face_ref is not None:
                if not isinstance(face_ref, dict) or not face_ref:
                    result["error"] = (
                        "wizard_hole target.face_ref must be a non-empty "
                        "manifest-face dict"
                    )
                    return result
            elif not (isinstance(face, (list, tuple)) and len(face) == 3):
                result["error"] = (
                    "wizard_hole target needs a 'face_ref' (durable manifest-face "
                    "dict) or a 'face' ([x,y,z] coords)"
                )
                return result

        def _is_coord(v: Any) -> bool:
            return isinstance(v, (list, tuple)) and len(v) == 3

        # A shell removes a non-empty list of faces.
        if feat_type == "shell":
            faces = target.get("faces")
            if (
                not isinstance(faces, list)
                or not faces
                or not all(_is_coord(f) for f in faces)
            ):
                result["error"] = (
                    "shell target.faces must be a non-empty list of [x,y,z] coords"
                )
                return result

        # A draft needs a neutral face + a non-empty list of faces to draft.
        if feat_type == "draft":
            if not _is_coord(target.get("neutral_face")):
                result["error"] = (
                    "draft target.neutral_face must be a 3-element [x,y,z]"
                )
                return result
            faces = target.get("faces")
            if (
                not isinstance(faces, list)
                or not faces
                or not all(_is_coord(f) for f in faces)
            ):
                result["error"] = (
                    "draft target.faces must be a non-empty list of [x,y,z] coords"
                )
                return result

        # A sweep is built on two named sketches: a profile and a path.
        if feat_type == "sweep":
            for pname in ("profile", "path"):
                if not isinstance(target.get(pname), str) or not target.get(pname):
                    result["error"] = (
                        f"sweep target.{pname} must be a non-empty sketch name"
                    )
                    return result

        # Wave-5/6: ref_plane is either an offset plane (plane name +
        # distance_mm) or a normal-to-edge plane (durable edge_ref).
        if feat_type == "ref_plane":
            if target.get("edge_ref") is not None:
                if not isinstance(target.get("edge_ref"), dict):
                    result["error"] = (
                        "ref_plane target.edge_ref must be a DurableEdgeRef dict"
                    )
                    return result
            else:
                if not isinstance(target.get("plane"), str) or not target.get("plane"):
                    result["error"] = (
                        "ref_plane target needs an 'edge_ref' (normal-to-edge) "
                        "or a non-empty 'plane' name (offset)"
                    )
                    return result
                dist = feature.get("distance_mm")
                if not isinstance(dist, (int, float)) or dist <= 0:
                    result["error"] = (
                        f"ref_plane distance_mm must be a positive number, got {dist!r}"
                    )
                    return result

        # Wave-5: ref_axis needs two plane names.
        if feat_type == "ref_axis":
            planes = target.get("planes")
            if not isinstance(planes, list) or len(planes) != 2:
                result["error"] = (
                    "ref_axis target.planes must be a 2-element list of plane names"
                )
                return result

        # Wave-5 / W5.3 Epic B: ref_point accepts a durable face-ref
        # (face-centroid, preferred) OR a legacy 3-element vertex coordinate.
        if feat_type == "ref_point":
            face_ref = target.get("face_ref")
            point = target.get("point")
            if face_ref is not None:
                if not isinstance(face_ref, dict) or not face_ref:
                    result["error"] = (
                        "ref_point target.face_ref must be a non-empty manifest-face dict"
                    )
                    return result
            elif not isinstance(point, (list, tuple)) or len(point) != 3:
                result["error"] = (
                    "ref_point target needs a 'face_ref' (durable manifest-face dict) "
                    "or a 3-element 'point' [x,y,z]"
                )
                return result

        # Wave-5: sweep_cut mirrors sweep (profile + path).
        if feat_type == "sweep_cut":
            for pname in ("profile", "path"):
                if not isinstance(target.get(pname), str) or not target.get(pname):
                    result["error"] = (
                        f"sweep_cut target.{pname} must be a non-empty sketch name"
                    )
                    return result

        # Wave-5: loft needs >=2 profile sketch names.
        if feat_type == "loft":
            profiles = target.get("profiles")
            if not isinstance(profiles, list) or len(profiles) < 2:
                result["error"] = (
                    "loft target.profiles must be a list of >=2 sketch names"
                )
                return result

        # Wave-5: rib needs a sketch name.
        if feat_type == "rib":
            if not isinstance(target.get("sketch"), str) or not target.get("sketch"):
                result["error"] = "rib target.sketch must be a non-empty sketch name"
                return result

        # Wave-6 T2: dome takes a durable face_ref (preferred) or legacy coord.
        if feat_type == "dome":
            face_ref = target.get("face_ref")
            face = target.get("face")
            if face_ref is not None:
                if not isinstance(face_ref, dict) or not face_ref:
                    result["error"] = (
                        "dome target.face_ref must be a non-empty manifest-face dict"
                    )
                    return result
            elif not isinstance(face, (list, tuple)) or len(face) != 3:
                result["error"] = (
                    "dome target needs a 'face_ref' (durable manifest-face dict) "
                    "or a 3-element 'face' [x,y,z]"
                )
                return result

        # Wave-7: edge_flange takes a durable edge_ref + positive height_mm;
        # angle_deg (0,180) and radius_mm default if absent.
        if feat_type == "edge_flange":
            if not isinstance(target.get("edge_ref"), dict) or not target.get(
                "edge_ref"
            ):
                result["error"] = (
                    "edge_flange target.edge_ref must be a DurableEdgeRef dict"
                )
                return result
            h = feature.get("height_mm")
            if not isinstance(h, (int, float)) or h <= 0:
                result["error"] = (
                    f"edge_flange height_mm must be a positive number, got {h!r}"
                )
                return result
            ang = feature.get("angle_deg", 90.0)
            if not isinstance(ang, (int, float)) or not (0 < ang < 180):
                result["error"] = (
                    f"edge_flange angle_deg must be in (0, 180), got {ang!r}"
                )
                return result
            rad = feature.get("radius_mm", 2.0)
            if not isinstance(rad, (int, float)) or rad <= 0:
                result["error"] = (
                    f"edge_flange radius_mm must be a positive number, got {rad!r}"
                )
                return result

        # Wave-5: wrap needs sketch + face.
        if feat_type == "wrap":
            if not isinstance(target.get("sketch"), str) or not target.get("sketch"):
                result["error"] = "wrap target.sketch must be a non-empty sketch name"
                return result
            face = target.get("face")
            if not isinstance(face, (list, tuple)) or len(face) != 3:
                result["error"] = "wrap target.face must be a 3-element [x,y,z]"
                return result

        # Wave-5: boundary_boss needs dir1 + dir2 profile lists.
        if feat_type == "boundary_boss":
            for key in ("dir1_profiles", "dir2_profiles"):
                val = target.get(key)
                if not isinstance(val, list) or not val:
                    result["error"] = (
                        f"boundary_boss target.{key} must be a non-empty list"
                    )
                    return result

        # W21: linear_pattern — seed + direction + spacing_mm + count.
        if feat_type == "linear_pattern":
            if not isinstance(target.get("seed"), str) or not target.get("seed"):
                result["error"] = (
                    "linear_pattern target.seed must be a non-empty feature name"
                )
                return result
            direction = target.get("direction")
            if not isinstance(direction, dict):
                result["error"] = (
                    "linear_pattern target.direction must be a dict with x, y, z"
                )
                return result
            for axis in ("x", "y", "z"):
                v = direction.get(axis)
                if not isinstance(v, (int, float)):
                    result["error"] = (
                        f"linear_pattern target.direction.{axis} must be a number"
                    )
                    return result
            spacing = feature.get("spacing_mm")
            if not isinstance(spacing, (int, float)) or spacing <= 0:
                result["error"] = (
                    f"linear_pattern spacing_mm must be a positive number, got {spacing!r}"
                )
                return result
            cnt = feature.get("count")
            if not isinstance(cnt, int) or cnt < 2:
                result["error"] = (
                    f"linear_pattern count must be an integer >= 2, got {cnt!r}"
                )
                return result

        # W21: circular_pattern — seed + axis + count + angle/equal_spacing.
        if feat_type == "circular_pattern":
            if not isinstance(target.get("seed"), str) or not target.get("seed"):
                result["error"] = (
                    "circular_pattern target.seed must be a non-empty feature name"
                )
                return result
            if not isinstance(target.get("axis"), str) or not target.get("axis"):
                result["error"] = (
                    "circular_pattern target.axis must be a non-empty axis name"
                )
                return result
            cnt = feature.get("count")
            if not isinstance(cnt, int) or cnt < 2:
                result["error"] = (
                    f"circular_pattern count must be an integer >= 2, got {cnt!r}"
                )
                return result
            angle = feature.get("angle_deg", 360.0)
            if not isinstance(angle, (int, float)) or angle <= 0:
                result["error"] = (
                    f"circular_pattern angle_deg must be a positive number, got {angle!r}"
                )
                return result

        # W21: mirror_feature — seed + plane.
        if feat_type == "mirror_feature":
            if not isinstance(target.get("seed"), str) or not target.get("seed"):
                result["error"] = (
                    "mirror_feature target.seed must be a non-empty feature name"
                )
                return result
            if not isinstance(target.get("plane"), str) or not target.get("plane"):
                result["error"] = (
                    "mirror_feature target.plane must be a non-empty plane name"
                )
                return result

        # W41: delete_body — body_index or body_name.
        if feat_type == "delete_body":
            body_index = target.get("body_index")
            body_name = target.get("body_name")
            if body_name is not None:
                if not isinstance(body_name, str) or not body_name:
                    result["error"] = (
                        "delete_body target.body_name must be a non-empty string"
                    )
                    return result
            elif body_index is not None:
                if not isinstance(body_index, int) or body_index < 0:
                    result["error"] = (
                        f"delete_body target.body_index must be a non-negative int, "
                        f"got {body_index!r}"
                    )
                    return result
            else:
                result["error"] = (
                    "delete_body target must contain 'body_index' or 'body_name'"
                )
                return result

        # W41: combine — operation + main + tool bodies.
        if feat_type == "combine":
            operation = feature.get("operation", "subtract")
            if operation not in ("add", "subtract", "common"):
                result["error"] = (
                    f"combine operation must be one of ['add', 'subtract', 'common'], "
                    f"got {operation!r}"
                )
                return result
            has_main = (
                target.get("main_body_index") is not None
                or target.get("main_body_name") is not None
            )
            has_tool = (
                target.get("tool_body_indices") is not None
                or target.get("tool_body_names") is not None
            )
            if not has_main:
                result["error"] = (
                    "combine target must contain 'main_body_index' or 'main_body_name'"
                )
                return result
            if not has_tool:
                result["error"] = (
                    "combine target must contain 'tool_body_indices' or 'tool_body_names'"
                )
                return result

        # W41: split — body + cutting entity.
        if feat_type == "split":
            if (
                target.get("cutting_plane") is None
                and target.get("cutting_surface") is None
            ):
                result["error"] = (
                    "split target must contain 'cutting_plane' or 'cutting_surface'"
                )
                return result

        if not doc_path or not Path(doc_path).exists():
            result["error"] = f"doc_path does not exist: {doc_path}"
            return result

        proposal_id = uuid.uuid4().hex[:12]
        record = {
            "kind": "feature_add",
            "proposal_id": proposal_id,
            "created_at": time.time(),
            "doc_path": doc_path,
            "feature": feature,
            "target": target,
            "state": ST_PROPOSED,
            "dry_run_result": None,
            "committed_at": None,
        }
        _save_proposal(proposal_id, record)
        result["proposal_id"] = proposal_id
        result["ok"] = True
        return result

    except Exception as exc:
        result["error"] = f"unexpected: {exc!r}"
        return result


def _sw_propose_assembly_impl(spec: dict[str, Any]) -> dict[str, Any]:
    """Core: stage an assembly proposal (v0.18 implementation).

    Internal callers (the ``SolidWorksClient.mutate`` facade) call this
    directly so they bypass the deprecation shim; the public
    :func:`sw_propose_assembly` free function routes here behind a
    ``PendingDeprecationWarning``.

    Validates offline; no SW state touched. The assembly kind is
    **de-advertised** — this function is the only entry point and is not
    reachable through ``sw_propose_feature_add``. It validates the spec
    structurally (jsonschema against ``ASSEMBLY_SCHEMA``) and semantically
    (``validate_assembly``) before writing a proposal record with
    ``kind: "assembly"``.
    """
    import jsonschema

    from .assembly.schema import ASSEMBLY_SCHEMA
    from .assembly.validator import AssemblyValidationError, validate_assembly

    result: dict[str, Any] = {
        "ok": False,
        "proposal_id": None,
        "kind": "assembly",
        "spec": spec,
        "state": ST_PROPOSED,
        "error": None,
    }
    try:
        if not isinstance(spec, dict):
            result["error"] = "spec must be a dict"
            return result

        try:
            jsonschema.validate(spec, ASSEMBLY_SCHEMA)
        except jsonschema.ValidationError as exc:
            result["error"] = f"schema: {exc.message}"
            return result

        try:
            validate_assembly(spec)
        except AssemblyValidationError as exc:
            result["error"] = str(exc)
            return result

        proposal_id = uuid.uuid4().hex[:12]
        record = {
            "kind": "assembly",
            "proposal_id": proposal_id,
            "created_at": time.time(),
            "spec": spec,
            "state": ST_PROPOSED,
            "dry_run_result": None,
            "committed_at": None,
        }
        _save_proposal(proposal_id, record)
        result["proposal_id"] = proposal_id
        result["ok"] = True
        return result

    except Exception as exc:
        result["error"] = f"unexpected: {exc!r}"
        return result


def _sw_dry_run_assembly_impl(proposal_id: str) -> dict[str, Any]:
    """Core: dry-run an assembly proposal (v0.18 implementation).

    Internal callers (the ``SolidWorksClient.mutate`` facade) call this
    directly so they bypass the deprecation shim; the public
    :func:`sw_dry_run_assembly` free function routes here behind a
    ``PendingDeprecationWarning``.

    Validates bindings without mutating SW. Resolves part file paths,
    confirms files exist, and validates mate face_refs are well-formed.
    Does not open any SW documents.
    """
    from .assembly.lifecycle import dry_run_assembly

    result: dict[str, Any] = {
        "ok": False,
        "proposal_id": proposal_id,
        "state": ST_PROPOSED,
        "error": None,
    }

    rec = _load_proposal(proposal_id)
    if rec is None:
        result["error"] = f"proposal {proposal_id} not found"
        return result
    if rec.get("kind") != "assembly":
        result["error"] = f"proposal {proposal_id} is not an assembly proposal"
        return result

    spec = rec["spec"]
    dry = dry_run_assembly(spec)
    result.update(dry)

    if dry.get("ok"):
        rec["state"] = ST_DRY_RUN_OK
        rec["dry_run_result"] = dry
        _save_proposal(proposal_id, rec)
        result["state"] = ST_DRY_RUN_OK

    return result


def _sw_commit_assembly_impl(
    proposal_id: str,
    output_path: str,
    *,
    part_paths: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Core: build the assembly (v0.18 implementation).

    Internal callers (the ``SolidWorksClient.mutate`` facade) call this
    directly so they bypass the deprecation shim; the public
    :func:`sw_commit_assembly` free function routes here behind a
    ``PendingDeprecationWarning``.

    Requires the proposal to be in ``dry_run_ok`` state. Opens an assembly
    document, places all components, creates all mates, saves the ``.sldasm``,
    and writes the assembly manifest alongside it.
    """
    from .assembly.lifecycle import commit_assembly

    result: dict[str, Any] = {
        "ok": False,
        "proposal_id": proposal_id,
        "state": ST_PROPOSED,
        "error": None,
    }

    rec = _load_proposal(proposal_id)
    if rec is None:
        result["error"] = f"proposal {proposal_id} not found"
        return result
    if rec.get("kind") != "assembly":
        result["error"] = f"proposal {proposal_id} is not an assembly proposal"
        return result
    if rec["state"] != ST_DRY_RUN_OK:
        result["error"] = (
            f"refusing to commit proposal in state {rec['state']!r}; "
            "must be 'dry_run_ok' (run sw_dry_run_assembly first)"
        )
        return result

    spec = rec["spec"]

    try:
        sw = get_sw_app()
    except Exception as exc:
        result["error"] = f"could not connect to SW: {exc!r}"
        return result

    commit = commit_assembly(sw, spec, output_path, part_paths=part_paths)
    result.update(commit)

    if commit.get("ok"):
        rec["state"] = ST_COMMITTED
        rec["committed_at"] = time.time()
        rec["manifest"] = commit.get("manifest")
        _save_proposal(proposal_id, rec)
        result["state"] = ST_COMMITTED

    return result


def _sw_edit_assembly_impl(manifest_path: str, op: dict[str, Any]) -> dict[str, Any]:
    """Core: edit an assembly via its manifest sidecar (v0.18 implementation).

    Internal callers (the ``SolidWorksClient.mutate`` facade) call this
    directly so they bypass the deprecation shim; the public
    :func:`sw_edit_assembly` free function routes here behind a
    ``PendingDeprecationWarning``.

    Loads the manifest, extracts the verbatim spec via ``to_spec()``,
    applies the declarative edit op, re-validates, and proposes the
    edited spec. Returns a ``proposal_id`` that feeds the existing
    ``dry_run_assembly`` → ``commit_assembly`` pipeline.

    Args:
        manifest_path: path to the ``.manifest.json`` sidecar.
        op: a declarative edit op dict (see ``assembly.edit``).

    Returns:
        A result dict with ``ok``, ``proposal_id``, ``edit_applied``,
        and ``error``.
    """
    from pathlib import Path as _Path

    from .assembly.edit import AssemblyEditError, apply_edit_op
    from .assembly.storage import AssemblyManifest
    from .assembly.validator import AssemblyValidationError, validate_assembly

    result: dict[str, Any] = {
        "ok": False,
        "proposal_id": None,
        "edit_applied": False,
        "error": None,
    }

    try:
        manifest = AssemblyManifest.load(_Path(manifest_path))
        old_spec = manifest.to_spec()
    except (FileNotFoundError, ValueError) as exc:
        result["error"] = f"manifest load failed: {exc}"
        return result

    try:
        new_spec = apply_edit_op(old_spec, op)
    except AssemblyEditError as exc:
        result["error"] = f"edit op rejected: {exc.message}"
        return result

    result["edit_applied"] = True

    try:
        validate_assembly(new_spec)
    except AssemblyValidationError as exc:
        result["error"] = f"edited spec failed validation: {exc.message}"
        return result

    propose = _sw_propose_assembly_impl(new_spec)
    result.update(propose)
    return result


# ---- Drawing lifecycle (Wave-16) ----


def _sw_propose_drawing_impl(spec: dict[str, Any]) -> dict[str, Any]:
    """Core: propose a drawing spec (v0.18 implementation).

    Internal callers (the ``SolidWorksClient.mutate`` facade) call this
    directly so they bypass the deprecation shim; the public
    :func:`sw_propose_drawing` free function routes here behind a
    ``PendingDeprecationWarning``.

    Validates offline. Returns a result dict with ``ok``, ``proposal_id``,
    and ``error``.
    """
    import jsonschema

    from .drawing.lifecycle import validate_drawing_spec
    from .drawing.spec_schema import DRAWING_SPEC_SCHEMA

    result: dict[str, Any] = {
        "ok": False,
        "proposal_id": None,
        "kind": "drawing",
        "state": ST_PROPOSED,
        "error": None,
    }

    try:
        jsonschema.validate(spec, DRAWING_SPEC_SCHEMA)
    except jsonschema.ValidationError as exc:
        result["error"] = f"schema error: {exc.message}"
        return result

    try:
        validate_drawing_spec(spec)
    except ValueError as exc:
        result["error"] = str(exc)
        return result

    pid = uuid.uuid4().hex[:12]
    rec = {
        "kind": "drawing",
        "state": ST_PROPOSED,
        "spec": spec,
        "proposed_at": time.time(),
    }
    _save_proposal(pid, rec)
    result["ok"] = True
    result["proposal_id"] = pid
    return result


def _sw_dry_run_drawing_impl(proposal_id: str) -> dict[str, Any]:
    """Core: dry-run a drawing proposal (v0.18 implementation).

    Internal callers (the ``SolidWorksClient.mutate`` facade) call this
    directly so they bypass the deprecation shim; the public
    :func:`sw_dry_run_drawing` free function routes here behind a
    ``PendingDeprecationWarning``.

    Confirms the model file exists without mutating SW.
    """
    from .drawing.lifecycle import dry_run_drawing

    result: dict[str, Any] = {
        "ok": False,
        "proposal_id": proposal_id,
        "state": ST_PROPOSED,
        "error": None,
    }

    rec = _load_proposal(proposal_id)
    if rec is None:
        result["error"] = f"proposal {proposal_id} not found"
        return result
    if rec.get("kind") != "drawing":
        result["error"] = f"proposal {proposal_id} is not a drawing proposal"
        return result

    dry = dry_run_drawing(rec["spec"])
    result.update(dry)

    if dry.get("ok"):
        rec["state"] = ST_DRY_RUN_OK
        _save_proposal(proposal_id, rec)
        result["state"] = ST_DRY_RUN_OK

    return result


def _sw_commit_drawing_impl(
    proposal_id: str,
    output_path: str,
) -> dict[str, Any]:
    """Core: commit a drawing proposal (v0.18 implementation).

    Internal callers (the ``SolidWorksClient.mutate`` facade) call this
    directly so they bypass the deprecation shim; the public
    :func:`sw_commit_drawing` free function routes here behind a
    ``PendingDeprecationWarning``.

    Creates views from the model and saves the ``.SLDDRW`` to
    ``output_path``. Only allowed after the proposal is in ``dry_run_ok``
    state.
    """
    from .drawing.lifecycle import commit_drawing

    result: dict[str, Any] = {
        "ok": False,
        "proposal_id": proposal_id,
        "state": ST_PROPOSED,
        "error": None,
    }

    rec = _load_proposal(proposal_id)
    if rec is None:
        result["error"] = f"proposal {proposal_id} not found"
        return result
    if rec.get("kind") != "drawing":
        result["error"] = f"proposal {proposal_id} is not a drawing proposal"
        return result
    if rec["state"] != ST_DRY_RUN_OK:
        result["error"] = (
            f"refusing to commit proposal in state {rec['state']!r}; "
            "must be 'dry_run_ok'"
        )
        return result

    try:
        sw = get_sw_app()
    except Exception as exc:
        result["error"] = f"could not connect to SW: {exc!r}"
        return result

    commit = commit_drawing(sw, rec["spec"], output_path)
    result.update(commit)

    if commit.get("ok"):
        rec["state"] = ST_COMMITTED
        rec["committed_at"] = time.time()
        _save_proposal(proposal_id, rec)
        result["state"] = ST_COMMITTED

    return result


# ---- properties support (W29) ------------------------------------------------


def _sw_propose_properties_impl(spec: dict[str, Any]) -> dict[str, Any]:
    """Core: propose a properties spec (v0.18 implementation).

    Internal callers (the ``SolidWorksClient.mutate`` facade) call this
    directly so they bypass the deprecation shim; the public
    :func:`sw_propose_properties` free function routes here behind a
    ``PendingDeprecationWarning``.

    Validates offline. Returns a result dict with ``ok``, ``proposal_id``,
    and ``error``.
    """
    import jsonschema

    from .metadata.lifecycle import propose_properties
    from .metadata.spec_schema import PROPERTIES_SPEC_SCHEMA

    result: dict[str, Any] = {
        "ok": False,
        "proposal_id": None,
        "kind": "properties",
        "state": ST_PROPOSED,
        "error": None,
    }

    try:
        jsonschema.validate(spec, PROPERTIES_SPEC_SCHEMA)
    except jsonschema.ValidationError as exc:
        result["error"] = f"schema validation failed: {exc.message}"
        return result

    propose_result = propose_properties(spec)
    if not propose_result.get("ok"):
        result["error"] = propose_result.get("error")
        return result

    pid = uuid.uuid4().hex[:12]
    rec = {
        "kind": "properties",
        "state": ST_PROPOSED,
        "spec": spec,
        "proposed_at": time.time(),
    }
    _save_proposal(pid, rec)

    result["ok"] = True
    result["proposal_id"] = pid
    return result


def _sw_dry_run_properties_impl(proposal_id: str) -> dict[str, Any]:
    """Core: dry-run a properties proposal (v0.18 implementation).

    Internal callers (the ``SolidWorksClient.mutate`` facade) call this
    directly so they bypass the deprecation shim; the public
    :func:`sw_dry_run_properties` free function routes here behind a
    ``PendingDeprecationWarning``.

    Confirms the model file exists without mutating SW.
    """
    from .metadata.lifecycle import dry_run_properties

    result: dict[str, Any] = {
        "ok": False,
        "proposal_id": proposal_id,
        "state": ST_PROPOSED,
        "error": None,
    }

    rec = _load_proposal(proposal_id)
    if rec is None:
        result["error"] = f"proposal {proposal_id} not found"
        return result
    if rec.get("kind") != "properties":
        result["error"] = f"proposal {proposal_id} is not a properties proposal"
        return result

    dry = dry_run_properties(rec["spec"])
    result.update(dry)

    if dry.get("ok"):
        rec["state"] = ST_DRY_RUN_OK
        rec["dry_run_at"] = time.time()
        _save_proposal(proposal_id, rec)
        result["state"] = ST_DRY_RUN_OK

    return result


def _sw_commit_properties_impl(proposal_id: str) -> dict[str, Any]:
    """Core: commit a properties proposal (v0.18 implementation).

    Internal callers (the ``SolidWorksClient.mutate`` facade) call this
    directly so they bypass the deprecation shim; the public
    :func:`sw_commit_properties` free function routes here behind a
    ``PendingDeprecationWarning``.

    Sets the custom properties on the model, saves, and verifies
    read-back. Only allowed after the proposal is in ``dry_run_ok`` state.
    """
    from .metadata.lifecycle import commit_properties

    result: dict[str, Any] = {
        "ok": False,
        "proposal_id": proposal_id,
        "state": ST_PROPOSED,
        "error": None,
    }

    rec = _load_proposal(proposal_id)
    if rec is None:
        result["error"] = f"proposal {proposal_id} not found"
        return result
    if rec.get("kind") != "properties":
        result["error"] = f"proposal {proposal_id} is not a properties proposal"
        return result
    if rec["state"] != ST_DRY_RUN_OK:
        result["error"] = (
            f"refusing to commit proposal in state {rec['state']!r}; "
            "must be 'dry_run_ok'"
        )
        return result

    try:
        sw = get_sw_app()
    except Exception as exc:
        result["error"] = f"could not connect to SW: {exc!r}"
        return result

    commit_result = commit_properties(sw, rec["spec"])
    result.update(commit_result)

    if commit_result.get("ok"):
        rec["state"] = ST_COMMITTED
        rec["committed_at"] = time.time()
        _save_proposal(proposal_id, rec)
        result["state"] = ST_COMMITTED

    return result


def _sw_dry_run_feature_add_impl(proposal_id: str) -> dict[str, Any]:
    """Core: open the doc, resolve the edge, add the fillet, rebuild, close without saving (v0.18 implementation).

    Internal callers (the ``SolidWorksClient.mutate`` facade) call this
    directly so they bypass the deprecation shim; the public
    :func:`sw_dry_run_feature_add` free function routes here behind a
    ``PendingDeprecationWarning``.
    """
    result: dict[str, Any] = {
        "ok": False,
        "proposal_id": proposal_id,
        "state": ST_PROPOSED,
        "dry_run_result": None,
        "error": None,
    }

    rec = _load_proposal(proposal_id)
    if rec is None:
        result["error"] = f"proposal {proposal_id} not found"
        return result

    if rec.get("kind", "local_change") != "feature_add":
        result["error"] = f"proposal {proposal_id} is not a feature_add proposal"
        return result

    if rec["state"] not in (ST_PROPOSED, ST_DRY_RUN_OK, ST_DRY_RUN_BROKE):
        result["error"] = f"proposal is in state {rec['state']!r}, cannot dry-run"
        return result

    doc_path = rec["doc_path"]
    doc = None
    sw = None

    try:
        sw = get_sw_app()
        active = get_active_doc(sw)
        if active is not None:
            try:
                active_path = str(resolve(active, "GetPathName"))
                if (
                    active_path
                    and Path(active_path).resolve() == Path(doc_path).resolve()
                ):
                    result["error"] = (
                        f"target doc is the active document ({doc_path}); "
                        "close it before dry-run"
                    )
                    return result
            except Exception:
                pass

        doc = _open_doc_typed(doc_path)
        if doc is None:
            result["error"] = f"failed to open doc: {doc_path}"
            return result

        feat_ok, feat_err = _apply_feature(doc, rec["feature"], rec["target"])

        try:
            rebuild_ok = bool(doc.ForceRebuild3(False))
        except Exception:
            rebuild_ok = False

        dry_run_result = {
            "ran_at": time.time(),
            "feature_ok": feat_ok,
            "rebuild_ok": rebuild_ok,
            "error": feat_err,
        }

        if feat_ok:
            state = ST_DRY_RUN_OK
        else:
            state = ST_DRY_RUN_BROKE
            result["error"] = feat_err

        result["state"] = state
        result["dry_run_result"] = dry_run_result

    finally:
        if doc is not None and sw is not None:
            try:
                sw.CloseDoc(_doc_title(doc))
            except Exception:
                pass

    rec["state"] = state
    rec["dry_run_result"] = dry_run_result
    _save_proposal(proposal_id, rec)

    result["ok"] = state == ST_DRY_RUN_OK
    result["state"] = state
    return result


def _sw_commit_feature_add_impl(proposal_id: str) -> dict[str, Any]:
    """Core: re-run the feature-add pipeline and save the document (v0.18 implementation).

    Internal callers (the ``SolidWorksClient.mutate`` facade) call this
    directly so they bypass the deprecation shim; the public
    :func:`sw_commit_feature_add` free function routes here behind a
    ``PendingDeprecationWarning``.
    """
    result: dict[str, Any] = {
        "ok": False,
        "proposal_id": proposal_id,
        "doc_saved": False,
        "state": ST_PROPOSED,
        "error": None,
    }

    rec = _load_proposal(proposal_id)
    if rec is None:
        result["error"] = f"proposal {proposal_id} not found"
        return result

    if rec.get("kind", "local_change") != "feature_add":
        result["error"] = f"proposal {proposal_id} is not a feature_add proposal"
        return result

    if rec["state"] != ST_DRY_RUN_OK:
        result["error"] = (
            f"refusing to commit proposal in state {rec['state']!r}; "
            "must be 'dry_run_ok' (run sw_dry_run_feature_add first)"
        )
        return result

    doc_path = rec["doc_path"]
    doc = None
    sw = None

    try:
        sw = get_sw_app()
        active = get_active_doc(sw)
        if active is not None:
            try:
                active_path = str(resolve(active, "GetPathName"))
                if (
                    active_path
                    and Path(active_path).resolve() == Path(doc_path).resolve()
                ):
                    result["error"] = (
                        f"target doc is the active document ({doc_path}); "
                        "close it before commit"
                    )
                    return result
            except Exception:
                pass

        doc = _open_doc_typed(doc_path)
        if doc is None:
            result["error"] = f"failed to open doc: {doc_path}"
            return result

        feat_ok, feat_err = _apply_feature(doc, rec["feature"], rec["target"])
        if not feat_ok:
            result["error"] = f"feature creation failed during commit: {feat_err}"
            return result

        try:
            result["doc_saved"] = _save_doc(doc)
        except Exception as exc:
            result["error"] = f"doc.Save raised: {exc!r}"
            return result

        rec["state"] = ST_COMMITTED
        rec["committed_at"] = time.time()
        _save_proposal(proposal_id, rec)

        result["state"] = ST_COMMITTED
        result["ok"] = True
        return result

    except Exception as exc:
        result["error"] = f"unexpected: {exc!r}"
        return result

    finally:
        if doc is not None and sw is not None:
            try:
                sw.CloseDoc(_doc_title(doc))
            except Exception:
                pass


def _sw_batch_feature_add_impl(
    doc_path: str,
    proposals: "list[dict]",
    strict: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Apply a SEQUENCE of feature-add proposals in ONE open-doc transaction.

    ``dry_run=True`` is the PLAN-ONLY mode (the MCP ``sw_batch_plan`` surface):
    every proposal's handler still runs — so each B-rep is genuinely validated
    on the live kernel (the handler's verify-the-effect gate fires) — but
    ``_save_doc`` is NEVER called, and the ``finally`` ``CloseDoc`` discards all
    in-memory changes. The document on disk is guaranteed untouched. The manifest
    is identical in shape (``committed`` = what WOULD commit, ``fault``/``skipped``
    as usual), with ``doc_saved`` always False and ``dry_run=True``. This is the
    autonomous-safe half of the §6.5 boundary: an agent may PLAN over MCP; the
    irreversible commit stays a human-gated CLI action.

    The throughput primitive for agent-generated multi-feature edits: instead
    of N propose→dry-run→commit round-trips (each opening + closing the doc),
    ``batch`` opens *doc_path* ONCE via :func:`_open_doc_typed`, runs each
    proposal's handler in order through :func:`_apply_feature`, saves the green
    features, and closes.

    **Fail-fast best-effort (default, ``strict=False``):** execute proposals in
    order; on the FIRST handler ``False`` return or raised exception, HALT
    immediately (subsequent features almost always depend on the topological
    success of prior ones — continuing would cascade meaningless faults). The
    green features that already materialized ARE saved. Returns the recovery
    manifest. ``strict=True`` is all-or-nothing: on any fault the doc is closed
    WITHOUT saving (SW has no native transaction rollback, so unsaved ==
    discarded) — clean atomicity at the cost of throwing away the greens.

    Each proposal is ``{"feature": dict, "target": dict}`` — the same shapes
    :func:`_apply_feature` consumes (``feature["type"]`` keys ``HANDLER_REGISTRY``).

    Manifest (ratified schema — designed for agent recovery)::

        ok               bool   — True iff EVERY proposal committed
        doc_path         str
        total            int    — proposals submitted
        attempted        int    — how many actually ran (fail-fast: halted_at+1)
        committed_count  int
        doc_saved        bool   — were the green features written to disk
        halted_at        int|None — 0-based index of the terminal fault
        strict           bool   — the semantic in force
        committed        [{index, kind, note}]      — the SUCCESS TRAIL (ordered)
        fault            {index, kind, stage, error, feature, target} | None
                                 — the SINGULAR terminal fault (fail-fast ⇒ ≤1);
                                   stage ∈ {"open_doc","apply","save"}; feature/
                                   target echoed VERBATIM for re-edit
        skipped          [{index, kind}]            — the RESUME QUEUE (unattempted)
        error            str|None — top-level human summary

    Fail-soft: never raises; every failure mode lands in the manifest.
    """
    manifest: dict[str, Any] = {
        "ok": False,
        "doc_path": doc_path,
        "total": len(proposals) if isinstance(proposals, (list, tuple)) else 0,
        "attempted": 0,
        "committed_count": 0,
        "doc_saved": False,
        "halted_at": None,
        "strict": bool(strict),
        "dry_run": bool(dry_run),
        "committed": [],
        "fault": None,
        "skipped": [],
        "error": None,
    }

    # --- validation (fail closed BEFORE any COM is touched) ---
    if not isinstance(doc_path, str) or not doc_path:
        manifest["error"] = "doc_path must be a non-empty string"
        return manifest
    if not isinstance(proposals, (list, tuple)):
        manifest["error"] = "proposals must be a list of {'feature','target'} dicts"
        return manifest
    if not proposals:
        manifest["error"] = "proposals list is empty"
        return manifest
    proposals = list(proposals)
    for i, p in enumerate(proposals):
        if (
            not isinstance(p, dict)
            or not isinstance(p.get("feature"), dict)
            or not isinstance(p.get("target"), dict)
        ):
            manifest["error"] = (
                f"proposal[{i}] must be {{'feature': dict, 'target': dict}}"
            )
            return manifest

    total = len(proposals)

    def _kind(p: dict) -> Any:
        feat = p.get("feature")
        return feat.get("type") if isinstance(feat, dict) else None

    def _skipped_from(start: int) -> "list[dict]":
        return [{"index": j, "kind": _kind(proposals[j])} for j in range(start, total)]

    doc = None
    sw = None
    try:
        sw = get_sw_app()
        # Active-doc guard (mirror the single-commit contract): refuse if the
        # target is the active document — an open doc can't be re-opened typed.
        active = get_active_doc(sw)
        if active is not None:
            try:
                active_path = str(resolve(active, "GetPathName"))
                if (
                    active_path
                    and Path(active_path).resolve() == Path(doc_path).resolve()
                ):
                    manifest["error"] = (
                        f"target doc is the active document ({doc_path}); "
                        "close it before batch"
                    )
                    return manifest
            except Exception:
                pass

        doc = _open_doc_typed(doc_path)
        if doc is None:
            # open_doc-stage fault: nothing attempted, everything skipped.
            manifest["halted_at"] = 0
            manifest["fault"] = {
                "index": 0,
                "kind": _kind(proposals[0]),
                "stage": "open_doc",
                "error": f"failed to open doc: {doc_path}",
                "feature": proposals[0].get("feature"),
                "target": proposals[0].get("target"),
            }
            manifest["skipped"] = _skipped_from(1)
            manifest["error"] = (
                f"batch halted at 0/{total} (open_doc): failed to open {doc_path}"
            )
            return manifest

        # --- the sequential, fail-fast execution loop ---
        for i, p in enumerate(proposals):
            feature, target, kind = p["feature"], p["target"], _kind(p)
            manifest["attempted"] = i + 1
            try:
                ok, note = _apply_feature(doc, feature, target)
            except Exception as exc:  # noqa: BLE001 — a handler raised; treat as fault
                ok, note = False, f"handler raised: {exc!r}"
            if not ok:
                manifest["halted_at"] = i
                manifest["fault"] = {
                    "index": i,
                    "kind": kind,
                    "stage": "apply",
                    "error": note,
                    "feature": feature,
                    "target": target,
                }
                manifest["skipped"] = _skipped_from(i + 1)
                manifest["error"] = f"batch halted at {i}/{total} ({kind}): {note}"
                break
            manifest["committed"].append({"index": i, "kind": kind, "note": note})
            manifest["committed_count"] += 1

        green = manifest["committed_count"]
        faulted = manifest["fault"] is not None

        # --- PLAN-ONLY (dry_run): never persist; finally CloseDoc discards. ---
        if dry_run:
            if not faulted:
                manifest["ok"] = True  # every feature validated / WOULD commit
            return manifest

        # --- save policy ---
        if faulted and strict:
            # all-or-nothing: the greens are discarded (finally closes w/o save).
            manifest["error"] = (
                f"{manifest['error']} [strict — {green} green feature(s) "
                "discarded, doc NOT saved]"
            )
            return manifest

        if green > 0:
            try:
                manifest["doc_saved"] = _save_doc(doc)
            except Exception as exc:  # noqa: BLE001
                manifest["doc_saved"] = False
                save_err = f"doc.Save raised: {exc!r}"
                if not faulted:
                    # all-green but the SAVE is the terminal fault.
                    manifest["fault"] = {
                        "index": None,
                        "kind": None,
                        "stage": "save",
                        "error": save_err,
                        "feature": None,
                        "target": None,
                    }
                    manifest["error"] = save_err
                else:
                    manifest["error"] = f"{manifest['error']} ; ALSO {save_err}"
                return manifest

        if not faulted:
            manifest["ok"] = True
        return manifest

    except Exception as exc:  # noqa: BLE001 — never raise out of the batch engine
        manifest["error"] = f"unexpected: {exc!r}"
        return manifest

    finally:
        if doc is not None and sw is not None:
            try:
                sw.CloseDoc(_doc_title(doc))
            except Exception:
                pass


# ---------------------------------------------------------------------------
# v0.14 — class-based facade over the legacy ``sw_*`` free functions.
#
# The free functions above are the canonical implementations and remain
# the documented backward-compatible API. ``ProposalStore`` is the
# recommended entry point for new code. A deeper migration (move
# logic into methods, extract the file-locking + state-transition
# ceremony into one place) is logged as ``D-v0.14-06`` in
# ``docs/DEFERRED.md`` and targets v0.15.
# ---------------------------------------------------------------------------


class ProposalStore:
    """File-backed proposal lifecycle store. New in v0.14.

    Methods return the same JSON-shaped dicts as the legacy
    ``sw_*`` free functions in this module — the class is a thin
    facade so callers can prefer instance-method syntax and so a
    future refactor can swap the on-disk format without touching
    call sites. Instances are stateless; nothing is cached between
    calls.

    Proposals persist under :func:`_proposals_dir` (``./proposals``
    by default; override with ``AI_SW_BRIDGE_PROPOSALS``).
    """

    def propose(self, var: str, new_value: str) -> dict[str, Any]:
        """Stage a change to *var* — no SW state is modified yet."""
        return _sw_propose_local_change_impl(var=var, new_value=new_value)

    def dry_run(self, proposal_id: str) -> dict[str, Any]:
        """Apply a proposal, force-rebuild, capture state, roll back."""
        return _sw_dry_run_impl(proposal_id=proposal_id)

    def commit(self, proposal_id: str) -> dict[str, Any]:
        """Re-apply a dry-run-ok proposal and save the SW document."""
        return _sw_commit_impl(proposal_id=proposal_id)

    def undo_last(self) -> dict[str, Any]:
        """Revert the most recently committed proposal."""
        return _sw_undo_last_commit_impl()

    def propose_feature_add(
        self, doc_path: str, feature: dict, target: dict
    ) -> dict[str, Any]:
        """Stage a feature-add proposal — no SW state is modified yet."""
        return _sw_propose_feature_add_impl(
            doc_path=doc_path, feature=feature, target=target
        )

    def dry_run_feature_add(self, proposal_id: str) -> dict[str, Any]:
        """Apply a feature-add proposal, rebuild, close without saving."""
        return _sw_dry_run_feature_add_impl(proposal_id=proposal_id)

    def commit_feature_add(self, proposal_id: str) -> dict[str, Any]:
        """Re-run a dry-run-ok feature-add and save the SW document."""
        return _sw_commit_feature_add_impl(proposal_id=proposal_id)
