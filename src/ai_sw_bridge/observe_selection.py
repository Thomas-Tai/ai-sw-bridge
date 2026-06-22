"""Selection observation helper — W43 (perception axis).

Read-only report of the running SOLIDWORKS session's **current selection**
— what the engineer has clicked in the open document — as structured,
durable references the agent can act on.

COM route (de-risked by W31v2):
  - ``doc.SelectionManager`` (CDispatch, memid 65537, PROPGET) — proven.
    The ``ISelectionManager`` QI (memid 65711) FAILS "Unable to read
    write-only property" — never use it.
  - ``GetSelectedObjectCount2(-1)`` → count (-1 = all marks).
  - Per index ``i`` (1-based):
    - ``GetSelectedObjectType3(i, -1)`` → ``swSelectType_e`` int.
    - ``GetSelectedObject6(i, -1)`` → the entity dispatch.
  - Per entity: attempt ``GetPersistReference3`` via typed extension
    (fail-soft — ``durable_ref: null`` on any failure).

Seat-validated on SW 2024 SP1 (rev 32.1.0):
  - Programmatic ``SelectByID2`` a known face → read-back count==1,
    type==face, persist-ref round-trips.
  - Clear selection → count==0.
  - Two entities → count==2 with correct types.
  - No active doc → typed error (fail-closed).

v1 scope: read current selection from a single active document.
DEFER: selection-by-ray/screen-point, selection change events/callbacks
(unreachable out-of-process), sketch-entity sub-selection,
component-in-assembly context, mate/feature selection semantics,
multi-doc selection.
"""

from __future__ import annotations

import base64
import logging
from typing import Any

from .com.earlybind import read_persist_reference, typed
from .com.sw_type_info import wrapper_module
from .sw_com import resolve

logger = logging.getLogger(__name__)

# swSelectType_e — authoritative SOLIDWORKS values. The original W43 map was
# GUESSED and wrong from index 1 up (it labelled edge=1 as "everything",
# vertex=3 as "edge", etc.). Seat-verified on SW 2024 SP1 via SelectByID2
# read-back: EDGE→1, FACE→2, VERTEX→3, PLANE→4, BODYFEATURE→22, SOLIDBODY→76.
SELECT_TYPE_NAMES: dict[int, str] = {
    0: "nothing",
    1: "edge",            # swSelEDGES (seat-verified: EDGE select → 1)
    2: "face",            # swSelFACES (seat-verified: FACE select → 2)
    3: "vertex",          # swSelVERTICES (seat-verified)
    4: "datum_plane",     # swSelDATUMPLANES (seat-verified: PLANE select → 4)
    5: "datum_axis",      # swSelDATUMAXES
    6: "datum_point",     # swSelDATUMPOINTS
    7: "ole_item",        # swSelOLEITEMS
    8: "attribute",       # swSelATTRIBUTES
    9: "sketch",          # swSelSKETCHES
    10: "sketch_segment",  # swSelSKETCHSEGS
    11: "sketch_point",   # swSelSKETCHPOINTS
    12: "component",      # swSelCOMPONENTS
    13: "sheet",          # swSelSHEETS
    14: "block_inst",     # swSelBLOCKINST
    20: "bodies",         # swSelBODIES (generic)
    22: "body_feature",   # swSelBODYFEATURES (seat-verified: BODYFEATURE → 22)
    29: "dimensions",     # swSelDIMENSIONS
    31: "notes",          # swSelNOTES
    76: "solid_body",     # swSelSOLIDBODIES (seat-verified: SOLIDBODY → 76)
    98: "everything",     # swSelEVERYTHING
}


def _entity_info(entity: Any, type_id: int) -> dict[str, Any]:
    """Extract best-effort info dict for a selected entity."""
    info: dict[str, Any] = {}
    if entity is None:
        return info

    if type_id in (2, 3, 4):
        try:
            name = entity.Name
            if callable(name):
                name = name()
            if name:
                info["name"] = str(name)
        except Exception:
            pass

    if type_id == 11:
        try:
            fname = entity.Name
            if callable(fname):
                fname = fname()
            if fname:
                info["feature_name"] = str(fname)
        except Exception:
            pass

    if type_id == 12:
        try:
            cname = entity.Name2
            if callable(cname):
                cname = cname()
            if cname:
                info["component_name"] = str(cname)
        except Exception:
            pass

    return info


def read_selection(doc: Any, mod: Any = None) -> dict[str, Any]:
    """Read the current selection from the active document.

    Pipeline:
      1. Acquire ``SelectionManager`` via ``doc.SelectionManager`` (PROPGET).
      2. ``GetSelectedObjectCount2(-1)`` → total count.
      3. For each index ``i`` (1-based):
         - ``GetSelectedObjectType3(i, -1)`` → ``swSelectType_e``.
         - ``GetSelectedObject6(i, -1)`` → entity dispatch (fail-soft).
         - ``read_persist_reference(doc, entity)`` → durable token (fail-soft).
      4. Return structured report.

    Returns dict with:
      - count (int)
      - selections (list[dict]) — per-entity: {index, type, type_name,
        durable_ref, entity_info}
      - errors (list[str])
    """
    result: dict[str, Any] = {
        "count": 0,
        "selections": [],
        "errors": [],
    }

    if mod is None:
        mod = wrapper_module()

    try:
        doc_typed = typed(doc, "IModelDoc2", module=mod)
    except Exception as exc:
        result["errors"].append(f"typed(IModelDoc2): {exc!r}")
        return result

    try:
        sel_mgr = doc_typed.SelectionManager
    except Exception as exc:
        result["errors"].append(f"SelectionManager: {exc!r}")
        return result

    try:
        count = int(sel_mgr.GetSelectedObjectCount2(-1))
    except Exception as exc:
        result["errors"].append(f"GetSelectedObjectCount2: {exc!r}")
        return result

    result["count"] = count

    for i in range(1, count + 1):
        entry: dict[str, Any] = {
            "index": i,
            "type": None,
            "type_name": None,
            "durable_ref": None,
            "entity_info": {},
        }

        try:
            type_id = int(sel_mgr.GetSelectedObjectType3(i, -1))
            entry["type"] = type_id
            entry["type_name"] = SELECT_TYPE_NAMES.get(type_id, f"unknown({type_id})")
        except Exception:
            entry["type"] = -1
            entry["type_name"] = "error"

        entity = None
        try:
            entity = sel_mgr.GetSelectedObject6(i, -1)
        except Exception:
            pass

        if entity is not None:
            entry["entity_info"] = _entity_info(entity, entry["type"] or 0)

            pid_bytes = read_persist_reference(doc, entity)
            if pid_bytes is not None:
                entry["durable_ref"] = (
                    base64.urlsafe_b64encode(pid_bytes).decode("ascii").rstrip("=")
                )

        result["selections"].append(entry)

    return result


def _sw_get_selection_impl(doc: Any) -> dict[str, Any]:
    """Core: read the current selection from *doc* (v0.18 implementation).

    Returns structured report:
    ``{"ok": bool, "selection": {count, selections}, "error": str|None}``.
    Internal callers (the ``SolidWorksClient.observe`` facade) call this
    directly so they bypass the deprecation shim; the public
    :func:`sw_get_selection` free function routes here behind a
    ``PendingDeprecationWarning``.

    Fail-closed:
      - SelectionManager failure → ``ok=False``, typed error.
      - Empty selection → ``ok=True``, ``{count:0, selections:[]}``.
      - Per-entity persist-ref failure → ``durable_ref:null`` (not an error).
    """
    result: dict[str, Any] = {
        "ok": False,
        "error": None,
        "selection": None,
    }

    mod = wrapper_module()
    selection = read_selection(doc, mod)

    if selection["errors"]:
        result["error"] = "; ".join(selection["errors"])
        result["selection"] = {
            "count": selection["count"],
            "selections": selection["selections"],
        }
    else:
        result["selection"] = {
            "count": selection["count"],
            "selections": selection["selections"],
        }
        result["ok"] = True

    return result


def sw_get_selection(doc: Any) -> dict[str, Any]:
    """Deprecated free-function shim — use ``SolidWorksClient().observe.selection()``.

    Preserved for backward compatibility (v0.18 grace line). Emits a
    ``PendingDeprecationWarning`` and routes to :func:`_sw_get_selection_impl`,
    returning identical data. The class-based API is the stable contract.
    """
    import warnings

    warnings.warn(
        "sw_get_selection() is deprecated; use SolidWorksClient().observe.selection(). "
        "It will be removed in a future release.",
        PendingDeprecationWarning,
        stacklevel=2,
    )
    return _sw_get_selection_impl(doc)
