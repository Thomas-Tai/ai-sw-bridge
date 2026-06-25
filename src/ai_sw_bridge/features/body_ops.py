"""Recipe-C cut #2 — body-ops family relocated from mutate.py.

delete_body = W41 SHIPPED (GREEN, ΔVol/count gate).
combine/split = characterized OOP walls (W53: combine needs fragile OOP
IBody2-array marshaling; split's fixtures only built 1 body) — registered
DORMANT (WALLED) so propose keeps fail-closing; kept for provenance.
Bodies byte-identical to the mutate originals.
"""

from __future__ import annotations

import pythoncom
from typing import Any
from win32com.client import VARIANT

from ..com.earlybind import typed
from ..com.sw_type_info import wrapper_module

# delete_body: W41 SHIPPED, seat-proven GREEN. combine/split: characterized OOP
# walls (W53) — registered DORMANT (WALLED sentinel, mirroring move_copy_body) so
# they are never advertised and propose fail-closes; retained for provenance.
DELETE_BODY_STATUS = "GREEN"
COMBINE_STATUS = "WALLED"
SPLIT_STATUS = "WALLED"

_SW_SOLID_BODY = 0  # swBodyType_e.swSolidBody


def _get_body_count_and_volumes(
    doc: Any,
) -> tuple[int, list[float]] | tuple[int, None]:
    """Return (count, [volume_mm3_per_body]) for all solid bodies in *doc*.

    Uses ``IPartDoc.GetBodies2(0, True)`` (swSolidBody) then per-body
    ``CreateMassProperty`` for volume in m³ → mm³ (×1e9).  Returns
    ``(0, None)`` when the doc has no solid bodies.
    """
    # GetBodies2 is an IPartDoc member; the caller may hand a typed
    # IModelDoc2 (which lacks it). QI to IPartDoc — the W37 lesson.
    try:
        pdoc = (
            doc
            if hasattr(doc, "GetBodies2")
            else typed(doc, "IPartDoc", module=wrapper_module())
        )
        bodies = pdoc.GetBodies2(_SW_SOLID_BODY, True)
    except Exception:
        return 0, None
    if bodies is None:
        return 0, None
    count = len(bodies)
    volumes: list[float] = []
    for body in bodies:
        # Volume is read PER-BODY via IBody2.GetMassProperties(density) — its
        # element [3] is the volume in m³. NOTE: CreateMassProperty is an
        # IModelDocExtension method, NOT an IBody2 method (calling it on a body
        # throws "method not found" → was silently yielding 0.0). Seat-proven:
        # GetMassProperties(1.0)[3] == 8e-6 m³ for a 20³ box.
        try:
            mp = body.GetMassProperties(1.0)
            if callable(mp):
                mp = mp(1.0)
            if mp is not None and len(mp) > 3:
                volumes.append(float(mp[3]) * 1e9)
            else:
                volumes.append(0.0)
        except Exception:
            volumes.append(0.0)
    return count, volumes


def _select_body_by_index(doc: Any, index: int) -> bool:
    """Select the solid body at *index* in ``GetBodies2`` order (0-based).

    Seat-proven (W41): a body cannot be selected via ``IBody2.Select2`` (Member
    not found) nor ``select_entity(body)`` (returns False) nor by selecting its
    faces (``InsertDeleteBody2`` then no-ops). The working route is
    ``Extension.SelectByID2(body.Name, "SOLIDBODY", …)`` — so resolve the body
    at *index* to its ``IBody2.Name`` and select by that.
    """
    # GetBodies2 is IPartDoc-only — QI from a typed IModelDoc2 (W37 lesson).
    try:
        pdoc = (
            doc
            if hasattr(doc, "GetBodies2")
            else typed(doc, "IPartDoc", module=wrapper_module())
        )
        bodies = pdoc.GetBodies2(_SW_SOLID_BODY, True)
    except Exception:
        return False
    if bodies is None or index >= len(bodies):
        return False
    try:
        name = bodies[index].Name
        if callable(name):
            name = name()
    except Exception:
        return False
    return _select_body_by_name(doc, str(name))


def _select_body_by_name(doc: Any, name: str) -> bool:
    """Select a solid body by its tree name via ``SelectByID2(..,"SOLIDBODY",..)``.

    Seat-proven (W41): the selection TYPE is ``SOLIDBODY`` (swSelType 76), NOT
    ``BODYFEATURE`` (which selects the feature, type 22, and leaves
    ``InsertDeleteBody2`` a no-op).
    """
    try:
        mod = wrapper_module()
        ext = typed(doc.Extension, "IModelDocExtension", module=mod)
        return bool(ext.SelectByID2(name, "SOLIDBODY", 0, 0, 0, False, 0, None, 0))
    except Exception:
        return False


# ---------------------------------------------------------------------------
# W41 body-ops handlers — delete_body, combine, split.
# ---------------------------------------------------------------------------

_SW_BODY_OP_ADD = 0  # swBodyOperationType_e.swBodyOperationAdd
_SW_BODY_OP_SUBTRACT = 1  # swBodyOperationType_e.swBodyOperationSubtract
_SW_BODY_OP_COMMON = 2  # swBodyOperationType_e.swBodyOperationCommon

_COMBINE_OP_MAP = {
    "add": _SW_BODY_OP_ADD,
    "subtract": _SW_BODY_OP_SUBTRACT,
    "common": _SW_BODY_OP_COMMON,
}


def _create_delete_body(
    doc: Any, feature: dict, target: dict
) -> tuple[bool, str | None]:
    """Delete a solid body via ``IFeatureManager.InsertDeleteBody2``.

    Seat-validated approach (W41, LOW risk): select the target body via
    ``SelectByID2(name, "SOLIDBODY", …)`` (swSelType 76 — NOT BODYFEATURE),
    then call ``InsertDeleteBody2(False)``.  The signature is ONE arg
    (``keepBodies``); the 2-arg form raises "Invalid number of parameters".
    The return value may be ``None`` even on success — verify via body-count
    delta using ``GetBodies2`` (count must drop).

    ``target`` shape::

        {"body_index": 1}          # 0-based index into GetBodies2
        {"body_name": "Body2"}     # feature-tree name (SelectByID2)
    """
    doc.ForceRebuild3(False)
    before_count, before_vols = _get_body_count_and_volumes(doc)
    if before_count < 2:
        return False, (f"delete_body requires >= 2 bodies, found {before_count}")

    try:
        doc.ClearSelection2(True)
    except Exception:
        pass

    body_index = target.get("body_index")
    body_name = target.get("body_name")

    selected = False
    if body_name is not None:
        selected = _select_body_by_name(doc, str(body_name))
    elif body_index is not None:
        if not isinstance(body_index, int) or body_index < 0:
            return False, f"body_index must be a non-negative int, got {body_index!r}"
        selected = _select_body_by_index(doc, body_index)
    else:
        return False, "target must contain 'body_index' or 'body_name'"

    if not selected:
        return False, "could not select target body"

    try:
        fm = doc.FeatureManager
        # Seat-proven (W41): InsertDeleteBody2 takes ONE arg (keepBodies:bool);
        # the 2-arg form raises "Invalid number of parameters". With the target
        # body selected via SelectByID2 SOLIDBODY, InsertDeleteBody2(False)
        # drops the body (2→1, returns an IFeature).
        fm.InsertDeleteBody2(False)
        doc.ForceRebuild3(False)

        after_count, after_vols = _get_body_count_and_volumes(doc)

        if after_count < before_count:
            return True, None
        return False, (
            f"delete_body did not reduce body count "
            f"({before_count} -> {after_count})"
        )
    except Exception as exc:
        return False, f"delete_body pipeline failed: {exc!r}"


def _create_combine(doc: Any, feature: dict, target: dict) -> tuple[bool, str | None]:
    """Boolean combine of solid bodies via ``InsertCombineFeature``.

    Seat-validated approach (W41, MEDIUM risk): select main body + tool
    bodies, then call ``InsertCombineFeature(mainBody, operationType,
    toolBodies)`` where ``operationType`` is from
    ``swBodyOperationType_e`` (ADD=0/SUBTRACT=1/COMMON=2).

    The return value may be ``None`` even on success — verify via body-count
    delta (combine should reduce to 1 body for subtract/common, or merge
    bodies for add).

    ``feature`` shape::

        {"type": "combine", "operation": "subtract"}  # add|subtract|common

    ``target`` shape::

        {"main_body_index": 0, "tool_body_indices": [1]}
        # OR
        {"main_body_name": "Body1", "tool_body_names": ["Body2"]}
    """
    operation = feature.get("operation", "subtract")
    if operation not in _COMBINE_OP_MAP:
        return False, (
            f"operation must be one of {sorted(_COMBINE_OP_MAP)}, " f"got {operation!r}"
        )
    op_type = _COMBINE_OP_MAP[operation]

    doc.ForceRebuild3(False)
    before_count, before_vols = _get_body_count_and_volumes(doc)
    if before_count < 2:
        return False, f"combine requires >= 2 bodies, found {before_count}"

    try:
        doc.ClearSelection2(True)
    except Exception:
        pass

    try:
        bodies = doc.GetBodies2(_SW_SOLID_BODY, True)
    except Exception:
        return False, "GetBodies2 failed"
    if bodies is None:
        return False, "no solid bodies found"

    main_body = None
    tool_bodies: list = []

    main_name = target.get("main_body_name")
    main_idx = target.get("main_body_index")
    tool_names = target.get("tool_body_names")
    tool_idxs = target.get("tool_body_indices")

    if main_name is not None:
        for b in bodies:
            try:
                bname = b.Name
                if callable(bname):
                    bname = bname()
                if str(bname) == str(main_name):
                    main_body = b
                    break
            except Exception:
                continue
        if main_body is None:
            return False, f"main body {main_name!r} not found"
    elif main_idx is not None:
        if not isinstance(main_idx, int) or main_idx < 0 or main_idx >= len(bodies):
            return False, f"main_body_index out of range: {main_idx!r}"
        main_body = bodies[main_idx]
    else:
        return False, "target must contain 'main_body_index' or 'main_body_name'"

    if tool_names is not None:
        for tn in tool_names:
            found = False
            for b in bodies:
                try:
                    bname = b.Name
                    if callable(bname):
                        bname = bname()
                    if str(bname) == str(tn):
                        tool_bodies.append(b)
                        found = True
                        break
                except Exception:
                    continue
            if not found:
                return False, f"tool body {tn!r} not found"
    elif tool_idxs is not None:
        if not isinstance(tool_idxs, list) or not tool_idxs:
            return False, "tool_body_indices must be a non-empty list"
        for idx in tool_idxs:
            if not isinstance(idx, int) or idx < 0 or idx >= len(bodies):
                return False, f"tool_body_index out of range: {idx!r}"
            tool_bodies.append(bodies[idx])
    else:
        return False, "target must contain 'tool_body_indices' or 'tool_body_names'"

    if not tool_bodies:
        return False, "no tool bodies resolved"

    try:
        from ..selection import select_entity as _sel

        if not _sel(main_body):
            return False, "could not select main body"

        tool_array = VARIANT(
            pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, tuple(tool_bodies)
        )

        fm = doc.FeatureManager
        fm.InsertCombineFeature(main_body, op_type, tool_array)
        doc.ForceRebuild3(False)

        after_count, after_vols = _get_body_count_and_volumes(doc)

        if after_count < before_count:
            return True, None
        return False, (
            f"combine did not reduce body count " f"({before_count} -> {after_count})"
        )
    except Exception as exc:
        return False, f"combine pipeline failed: {exc!r}"


def _create_split(doc: Any, feature: dict, target: dict) -> tuple[bool, str | None]:
    """Split a solid body by a cutting entity.

    W41 HIGH risk — may hit the solver-deep COM wall. Fail-closed if the
    API returns None or produces no body-count change.

    ``feature`` shape::

        {"type": "split"}

    ``target`` shape::

        {"body_index": 0, "cutting_plane": "RefPlane1"}
        # OR
        {"body_index": 0, "cutting_surface": "Sketch1"}
    """
    doc.ForceRebuild3(False)
    before_count, before_vols = _get_body_count_and_volumes(doc)
    if before_count < 1:
        return False, "split requires >= 1 body"

    try:
        doc.ClearSelection2(True)
    except Exception:
        pass

    body_index = target.get("body_index", 0)
    if not _select_body_by_index(doc, body_index):
        return False, f"could not select body at index {body_index}"

    cutting_plane = target.get("cutting_plane")
    cutting_surface = target.get("cutting_surface")

    if cutting_plane is not None:
        try:
            mod = wrapper_module()
            ext = typed(doc.Extension, "IModelDocExtension", module=mod)
            if not ext.SelectByID2(
                cutting_plane, "REFPLANE", 0, 0, 0, True, 0, None, 0
            ):
                return False, f"cutting plane {cutting_plane!r} not found"
        except Exception as exc:
            return False, f"could not select cutting plane: {exc!r}"
    elif cutting_surface is not None:
        try:
            mod = wrapper_module()
            ext = typed(doc.Extension, "IModelDocExtension", module=mod)
            if not ext.SelectByID2(
                cutting_surface, "SKETCH", 0, 0, 0, True, 0, None, 0
            ):
                return False, f"cutting surface {cutting_surface!r} not found"
        except Exception as exc:
            return False, f"could not select cutting surface: {exc!r}"
    else:
        return False, "target must contain 'cutting_plane' or 'cutting_surface'"

    try:
        fm = doc.FeatureManager
        fm.InsertSplitBody(True, False)
        doc.ForceRebuild3(False)

        after_count, after_vols = _get_body_count_and_volumes(doc)

        if after_count > before_count:
            return True, None
        return False, (
            f"split did not increase body count " f"({before_count} -> {after_count})"
        )
    except Exception as exc:
        return False, f"split pipeline failed: {exc!r}"
