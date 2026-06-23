"""Recipe-C cut #3 — ref-geometry family.

ref_plane (incl. normal-to-edge) / ref_axis / coordinate_system / ref_point
relocated from mutate.py into the HANDLER_REGISTRY seam.

All seat-proven (W3/W5/W6/W64); the W64 ref_axis VARIANT-null SelectByID2
OOP fix is carried byte-identically.  The ``_SW_REFPLANE_*`` constants are
DUPLICATED here (also used by the edge_flange island left in mutate).

``SPIKE_STATUS = "GREEN"``
"""

from __future__ import annotations

import base64
from typing import Any

import pythoncom
import win32com.client.dynamic as _w32dyn
from win32com.client import VARIANT

from ..com.earlybind import typed
from ..com.sw_type_info import wrapper_module
from ..selection import (
    DurableEdgeRef,
    resolve_edge_ref,
    resolve_manifest_face,
    resolve_persist_id,
    select_entity,
)
from .verify import materialized as _materialized

SPIKE_STATUS = "GREEN"


def _latebound(com_obj: Any) -> Any:
    """Re-wrap a COM proxy as LATE-BOUND (``win32com.client.dynamic.Dispatch``).

    A ``VARIANT(VT_DISPATCH, None)`` ICallout argument marshals on a late-bound
    proxy but NOT on a makepy-typed one (raises ``TypeError('The Python
    instance can not be converted to a COM object')``). The disk-transaction
    path opens docs TYPED (``mutate._open_doc_typed``), so any Extension callout
    must be late-bound first. Isolated as a seam so offline tests can
    monkeypatch it to identity and still spy the underlying COM call.
    """
    return _w32dyn.Dispatch(com_obj)


# swRefPlaneReferenceConstraint_e (duplicated — also used by the edge_flange
# island that stays in mutate.py).
_SW_REFPLANE_OFFSET = 8         # _Distance (bit-flag)
_SW_REFPLANE_PERPENDICULAR = 2  # _Perpendicular
_SW_REFPLANE_COINCIDENT = 4     # _Coincident


def _create_ref_plane(
    doc: Any, feature: dict, target: dict
) -> tuple[bool, str | None]:
    """Create a reference plane — offset-from-plane OR normal-to-edge.

    Two seat-proven variants, dispatched by ``target`` shape:

    * **Offset** — ``{"plane": <name>}`` + ``feature.distance_mm`` (spike_refgeom,
      W3 PASS): ``doc.SelectByID(plane,"PLANE",...)`` →
      ``fm.InsertRefPlane(8, dist_m, 0,0,0,0)`` where 8 =
      swRefPlaneReferenceConstraint_Distance.
    * **Normal-to-edge** — ``{"edge_ref": <DurableEdgeRef dict>}`` (T6 v2 spike
      ``13b35e3`` = GREEN, SW 2024 SP1): a plane perpendicular to a durable edge,
      anchored at the edge's start vertex. See
      :func:`_create_ref_plane_normal_to_edge`.
    """
    if not isinstance(target, dict):
        return False, "target must be a dict with 'plane' or 'edge_ref'"

    if target.get("edge_ref") is not None:
        return _create_ref_plane_normal_to_edge(doc, target["edge_ref"])

    plane_name = target.get("plane")
    if not plane_name:
        return False, "target.plane must be a non-empty plane name"
    distance_mm = feature.get("distance_mm") if isinstance(feature, dict) else None
    if not isinstance(distance_mm, (int, float)) or distance_mm <= 0:
        return False, "distance_mm must be a positive number"
    distance_m = float(distance_mm) / 1000.0
    try:
        doc.ClearSelection2(True)
        doc.SelectByID(plane_name, "PLANE", 0, 0, 0)
        fm = doc.FeatureManager
        feat = fm.InsertRefPlane(
            _SW_REFPLANE_OFFSET, distance_m, 0, 0, 0, 0
        )
        if _materialized(feat):
            return True, None
        return False, "InsertRefPlane did not materialize"
    except Exception as exc:
        return False, f"ref-plane pipeline failed: {exc!r}"


def _create_ref_plane_normal_to_edge(
    doc: Any, edge_ref: Any
) -> tuple[bool, str | None]:
    """Create a reference plane perpendicular to a durable edge.

    Seat-validated recipe (T6 v2 spike ``13b35e3`` = GREEN, SW 2024 SP1). A
    normal-to-edge plane is a **two-reference** construction: it needs the edge
    (Perpendicular) *and* an anchor point (Coincident) — without the anchor the
    plane is geometrically under-defined and ``InsertRefPlane`` no-ops. We use
    the edge's own start vertex as the anchor.

    Recipe (each step seat-proven):

    1. Resolve the durable edge (:func:`resolve_edge_ref`); derive its start
       vertex via the typed ``IEdge.GetStartVertex()`` — a live entity in this
       same doc session, directly selectable (no second persist round-trip).
    2. Select **vertex first** (``mark=0`` → Coincident slot), then **edge**
       (``append``, ``mark=1`` → Perpendicular slot). The marks matter: the v2
       seat sweep showed edge ``mark=0`` no-ops, ``mark=1`` materializes (same
       per-feature mark sensitivity as the dome).
    3. ``fm.InsertRefPlane(4, 0, 2, 0, 0, 0)`` — Coincident=4, Perpendicular=2;
       the flag order matches the selection order. The enum is typelib-verified
       (Distance=8 anchors the block).
    4. ``InsertRefPlane`` returns ``None`` (mark=0) or a bare COMObject (mark=1)
       — never trust the return value; verify via a feature-count delta using
       ``len(FeatureManager.GetFeatures(True))`` (dome lesson).
    """
    mod = wrapper_module()
    try:
        ref = DurableEdgeRef.from_dict(edge_ref)
    except Exception as exc:  # noqa: BLE001
        return False, f"invalid edge_ref: {exc!r}"
    # Rebuild BEFORE resolving — ForceRebuild3 invalidates any entity proxy
    # resolved beforehand (stale COM disconnect). The v2 spike had no rebuild
    # between resolve and GetStartVertex; this production handler does, so the
    # order must match the dome handler: rebuild, then resolve a fresh entity.
    doc.ForceRebuild3(False)
    res = resolve_edge_ref(doc, ref)
    if res.entity is None:
        return False, f"edge unresolved (method={res.method})"
    try:
        try:
            vertex = typed(res.entity, "IEdge", module=mod).GetStartVertex()
        except Exception as exc:  # noqa: BLE001
            return False, f"could not derive edge start vertex: {exc!r}"
        if vertex is None:
            return False, "edge has no start vertex to anchor the plane"

        _feats = doc.FeatureManager.GetFeatures(True)
        before = len(_feats) if _feats else 0

        doc.ClearSelection2(True)
        # vertex = Coincident anchor (mark=0); edge = Perpendicular (mark=1).
        if not select_entity(vertex, mark=0):
            return False, "could not select edge start vertex (Coincident anchor)"
        if not select_entity(res.entity, append=True, mark=1):
            return False, "could not select edge (Perpendicular reference)"

        fm = doc.FeatureManager
        fm.InsertRefPlane(
            _SW_REFPLANE_COINCIDENT, 0, _SW_REFPLANE_PERPENDICULAR, 0, 0, 0
        )
        doc.ForceRebuild3(False)
        _feats = doc.FeatureManager.GetFeatures(True)
        after = len(_feats) if _feats else 0
        if after > before:
            return True, None
        return False, (
            f"normal-to-edge plane did not materialize (count {before} -> {after})"
        )
    except Exception as exc:  # noqa: BLE001
        return False, f"normal-to-edge ref-plane pipeline failed: {exc!r}"


def _create_ref_axis(
    doc: Any, feature: dict, target: dict
) -> tuple[bool, str | None]:
    """Create a reference axis from two-plane intersection.

    Seat-proven recipe (spike_refgeom, W3):
      Select plane1, append-select plane2, then doc.InsertAxis2(True).
      InsertAxis2 is on IModelDoc2, NOT IFeatureManager.
    """
    planes = target.get("planes") if isinstance(target, dict) else None
    if not isinstance(planes, list) or len(planes) != 2:
        return False, "target.planes must be a 2-element list of plane names"
    try:
        doc.ClearSelection2(True)
        # Append-select the 2nd plane via IModelDocExtension.SelectByID2 — the
        # 5-arg IModelDoc2.SelectByID has no Append and does NOT accumulate
        # (seat-proven: a 2nd SelectByID leaves sel_count==1). Its 8th arg
        # (ICallout) needs VARIANT(VT_DISPATCH, None) — but that VARIANT only
        # marshals on a LATE-BOUND Extension. The disk-transaction path
        # (dry_run/commit) opens the doc via _open_doc_typed → a TYPED
        # IModelDocExtension, on which the VARIANT callout raises
        # TypeError('The Python instance can not be converted to a COM object').
        # The W64 fix (VARIANT vs bare-None) was characterized on a late-bound
        # OOP probe, NOT the typed transaction path it actually runs in — so it
        # fixed the wrong binding and the full lifecycle was never seat-proven
        # until cut #3's gate. _latebound() re-wraps the Extension late-bound so
        # the callout marshals regardless of how the doc was opened (typed
        # transaction docs AND late-bound direct calls); InsertAxis2 still runs
        # on the original doc — both proxies share the one live selection set.
        # Seat-proven 2026-06-23 (probe_ref_axis_typed_select2 candidate D).
        doc.SelectByID(planes[0], "PLANE", 0, 0, 0)
        ext = _latebound(doc.Extension)
        ext.SelectByID2(
            planes[1], "PLANE", 0, 0, 0, True, 0,
            VARIANT(pythoncom.VT_DISPATCH, None), 0,
        )
        # InsertAxis2 on IModelDoc2 returns a VARIANT_BOOL (True = success)
        # in late-bound COM, not a Feature dispatch. Treat True as materialized;
        # False / None / int as failure.
        feat = doc.InsertAxis2(True)
        if feat is True:
            return True, None
        if feat is not None and not isinstance(feat, (int, bool)):
            return True, None
        return False, f"InsertAxis2 did not materialize (returned {feat!r})"
    except Exception as exc:
        return False, f"ref-axis pipeline failed: {exc!r}"


# Coordinate-system PropertyManager selection-mark routing (seat-confirmed
# W64 2026-06-17, mark-grid probe won on the first distinct-mark permutation):
# Origin / X-axis / Y-axis boxes consume the marked pre-selection set.
_CSYS_ROLE_MARKS: tuple[tuple[str, int], ...] = (
    ("origin_ref", 1),
    ("x_axis_ref", 2),
    ("y_axis_ref", 4),
)


def _persist_id_from_ref(ref: Any) -> bytes | None:
    """Extract raw persist-token bytes from a durable role-ref dict.

    Accepts ``{"persist_id": <base64url, no padding>}`` (the uniform durable
    shape ``capture_persist_id`` + base64url produces for ANY entity —
    vertex / edge / face). Returns ``None`` if absent or malformed.
    """
    if not isinstance(ref, dict):
        return None
    b64 = ref.get("persist_id")
    if not isinstance(b64, str) or not b64:
        return None
    try:
        pad = "=" * (-len(b64) % 4)
        return base64.urlsafe_b64decode(b64 + pad)
    except Exception:  # noqa: BLE001
        return None


def _create_coordinate_system(
    doc: Any, feature: dict, target: dict
) -> tuple[bool, str | None]:
    """Create a coordinate system — default-origin OR durable origin/axis placement.

    Two ``target`` shapes:

    * **Default origin (Wave-5, spike_refgeom W3):** no role refs —
      ``fm.InsertCoordinateSystem(flip_x, flip_y, flip_z)`` places a CS at the
      model origin with the requested axis flips. Backward-compatible default.
    * **Durable origin/axis (W64 upgrade, seat-proven 2026-06-18):** optional
      ``target.origin_ref`` / ``x_axis_ref`` / ``y_axis_ref``, each a durable
      ``{"persist_id": <base64url>}`` for a vertex (origin) or edge/face (axis).
      The refs are resolved (tier-1 persist) and pre-selected with the
      PropertyManager role marks origin=1 / X=2 / Y=4 (``_CSYS_ROLE_MARKS``),
      so ``InsertCoordinateSystem`` anchors the CS to real geometry rather than
      the model origin. Absent refs fall through to the default-origin path —
      so a caller that supplies none gets the exact legacy behavior.

    The flip toggles still come from ``feature`` (``flip_x/y/z``); the 3 args to
    InsertCoordinateSystem are flip toggles ONLY (DLL reflection 32.1.0.123) —
    the origin/axes are entirely selection-driven.
    """
    flip_x = bool(feature.get("flip_x", False)) if isinstance(feature, dict) else False
    flip_y = bool(feature.get("flip_y", False)) if isinstance(feature, dict) else False
    flip_z = bool(feature.get("flip_z", False)) if isinstance(feature, dict) else False

    # Collect optional durable role refs in (origin, X, Y) order.
    role_refs: list[tuple[str, bytes, int]] = []
    if isinstance(target, dict):
        for key, mark in _CSYS_ROLE_MARKS:
            ref = target.get(key)
            if ref is None:
                continue
            pid = _persist_id_from_ref(ref)
            if pid is None:
                return False, (
                    f"coordinate_system: {key} must carry a 'persist_id' "
                    f"(base64url durable token)"
                )
            role_refs.append((key, pid, mark))

    try:
        doc.ClearSelection2(True)
        # Durable origin/axis pre-selection (W64). Rebuild first so the persist
        # tokens resolve against the current B-rep (the fillet/dome pattern),
        # then select each with its role mark — origin (mark 1) un-appended,
        # the axes appended.
        if role_refs:
            doc.ForceRebuild3(False)
            for i, (key, pid, mark) in enumerate(role_refs):
                pr = resolve_persist_id(doc, pid)
                if pr.entity is None:
                    return False, (
                        f"coordinate_system: {key} unresolved "
                        f"(status={pr.status_name})"
                    )
                if not select_entity(pr.entity, append=(i > 0), mark=mark):
                    return False, f"coordinate_system: could not select {key}"

        fm = doc.FeatureManager
        feat = fm.InsertCoordinateSystem(flip_x, flip_y, flip_z)
        if _materialized(feat):
            return True, None
        return False, "InsertCoordinateSystem did not materialize"
    except Exception as exc:
        return False, f"coordinate-system pipeline failed: {exc!r}"


def _create_ref_point(
    doc: Any, feature: dict, target: dict
) -> tuple[bool, str | None]:
    """Create a reference point — durable face-centroid or legacy vertex coord.

    Two ``target`` shapes:

    * **Durable face-centroid (W5.3 Epic B, seat-GREEN spike ``880486a``):**
      ``{"face_ref": <manifest-face dict>}`` — the face is resolved through the
      persist→fingerprint hierarchy (:func:`resolve_manifest_face`) and selected
      as a live entity (:func:`select_entity`, the same durable round-trip
      ``wizard_hole``/``draft`` use), then
      ``fm.InsertReferencePoint(4, 0, 0.0, 1)`` (type 4 =
      ``swRefPointTypeInCentreOfFace``) materialises a point at the face
      centroid. Proven out-of-process: entity-select cracked via typed
      ``IEntity.Select2`` over the persist round-trip.
    * **Legacy vertex coordinate (spike_refgeom, W3):**
      ``{"point": [x,y,z]}`` — ``SelectByID("","VERTEX",x,y,z)`` then
      ``InsertReferencePoint(5, 0, 0.0, 1)``. This path **walls** out-of-process
      (SelectByID(VERTEX) returns False) and is retained only as a fallback; it
      is *not* the advertised path. See docs/DEFERRED.md.
    """
    if not isinstance(target, dict):
        return False, "target must be a dict with 'face_ref' or 'point'"

    fm = doc.FeatureManager

    # Durable face-centroid path (type 4). Preferred + seat-proven.
    face_ref = target.get("face_ref")
    if face_ref is not None:
        try:
            try:
                doc.ClearSelection2(True)
            except Exception:  # noqa: BLE001
                pass
            res = resolve_manifest_face(doc, face_ref)
            if res.entity is None:
                return False, f"ref-point face unresolved (method={res.method})"
            if not select_entity(res.entity):
                return False, "could not select resolved face for ref-point"
            # type 4 = swRefPointTypeInCentreOfFace (centroid of selected face).
            feat = fm.InsertReferencePoint(4, 0, 0.0, 1)
            if isinstance(feat, tuple):
                feat = feat[0] if len(feat) == 1 else None
            if feat is None or isinstance(feat, (int, bool)):
                return False, (
                    f"InsertReferencePoint(centroid) did not materialize "
                    f"(returned {feat!r})"
                )
            return True, None
        except Exception as exc:
            return False, f"ref-point (face-centroid) pipeline failed: {exc!r}"

    # Legacy vertex-coordinate path (type 5). Walls out-of-process.
    point = target.get("point")
    if not isinstance(point, (list, tuple)) or len(point) != 3:
        return False, "target must contain a 'face_ref' or a 3-element 'point' [x,y,z]"
    try:
        doc.ClearSelection2(True)
        sel_ok = doc.SelectByID(
            "", "VERTEX", float(point[0]), float(point[1]), float(point[2])
        )
        if not sel_ok:
            return False, (
                f"SelectByID(VERTEX at {list(point)}) failed -- "
                "no selectable vertex at those coordinates"
            )
        # InsertReferencePoint returns a Feature on success, but late-bound
        # COM may wrap it as a 1-tuple (None,) on failure. Reject None, False,
        # int, and any tuple whose only element is None.
        feat = fm.InsertReferencePoint(5, 0, 0.0, 1)
        if isinstance(feat, tuple):
            feat = feat[0] if len(feat) == 1 else None
        if feat is None or isinstance(feat, (int, bool)):
            return False, f"InsertReferencePoint did not materialize (returned {feat!r})"
        return True, None
    except Exception as exc:
        return False, f"ref-point pipeline failed: {exc!r}"
