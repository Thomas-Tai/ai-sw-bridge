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
from pathlib import Path
from typing import Any

from .locals_io import (
    ExclusiveLock,
    atomic_write,
    find_entry,
    parse,
    replace_rhs,
)
from .sw_com import get_active_doc, get_sw_app, resolve


# Proposal store: one JSON file per proposal. Override via env var,
# else defaults to ./proposals relative to the current working directory.
def _proposals_dir() -> Path:
    override = os.environ.get("AI_SW_BRIDGE_PROPOSALS")
    if override:
        return Path(override).resolve()
    return (Path.cwd() / "proposals").resolve()


ST_PROPOSED = "proposed"
ST_DRY_RUN_OK = "dry_run_ok"
ST_DRY_RUN_BROKE = "dry_run_broke"
ST_COMMITTED = "committed"
ST_UNDONE = "undone"


def _proposal_path(proposal_id: str) -> Path:
    return _proposals_dir() / f"{proposal_id}.json"


def _load_proposal(proposal_id: str) -> dict[str, Any] | None:
    p = _proposal_path(proposal_id)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def _save_proposal(proposal_id: str, data: dict[str, Any]) -> None:
    _proposals_dir().mkdir(parents=True, exist_ok=True)
    _proposal_path(proposal_id).write_text(
        json.dumps(data, indent=2), encoding="utf-8"
    )


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


def sw_propose_local_change(var: str, new_value: str) -> dict[str, Any]:
    """Stage a change to a single variable in the linked *_locals.txt file.

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


def sw_dry_run(proposal_id: str) -> dict[str, Any]:
    """Apply a proposed change, force-rebuild, capture state, roll back."""
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


def sw_commit(proposal_id: str) -> dict[str, Any]:
    """Re-apply a proposal that passed dry-run, save the SW document,
    and mark the proposal as committed."""
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
        new_text = replace_rhs(
            current_text, rec["line_index"], rec["new_expression"]
        )
        atomic_write(locals_path, new_text)

        rebuild_ok, rebuild_err = _force_rebuild(doc)
        if not rebuild_ok:
            result["error"] = f"rebuild failed after commit-apply: {rebuild_err}"
            return result

        try:
            saved = bool(doc.Save())
            result["doc_saved"] = saved
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


def sw_run_macro(macro_path: str, module: str = "Module1", sub: str = "main") -> dict[str, Any]:
    """Execute a SW VBA macro via RunMacro / RunMacro2.

    NOTE: as of 0.1.0 this only works for BINARY .swp files produced by
    SW's own VBA editor. Plain-text .swp/.bas files generated externally
    are silently rejected (RunMacro returns False). The recommended Path C
    workflow is to paste the generated .bas into VBE manually and press F5.
    This tool is kept for future use if/when we figure out binary .swp
    write-back.
    """
    result: dict[str, Any] = {
        "ok": False,
        "macro_path": macro_path,
        "ran": False,
        "error_code": None,
        "error": None,
    }

    p = Path(macro_path)
    if not p.exists():
        result["error"] = f"macro file does not exist: {macro_path}"
        return result

    try:
        sw = get_sw_app()
        attempts = [
            ("RunMacro", (str(p), module, sub)),
            ("RunMacro2", (str(p), module, sub, 1)),
            ("RunMacro2", (str(p), module, sub, 0)),
        ]
        last_err = None
        for method, args in attempts:
            try:
                fn = getattr(sw, method)
                ran = bool(fn(*args))
                result["ran"] = ran
                result["ok"] = ran
                result["error"] = None if ran else f"{method} returned False"
                result["method_used"] = f"{method}{args}"
                return result
            except Exception as exc:
                last_err = f"{method}{args} raised: {exc!r}"
                continue
        result["error"] = last_err or "all macro-run attempts failed"
        return result
    except Exception as exc:
        result["error"] = f"dispatch failed: {exc!r}"
        return result


def sw_undo_last_commit() -> dict[str, Any]:
    """Revert the most recently committed proposal by restoring its
    snapshot, force-rebuilding, and saving."""
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
        if rec.get("state") == ST_COMMITTED and rec.get("committed_at"):
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
            result["doc_saved"] = bool(doc.Save())
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
